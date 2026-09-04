"""Duplicate candidates: bookings an ingestion held aside because the profile may have them.

Every path that writes bookings goes through the same two steps. `Matcher` says whether an
incoming booking matches one the profile already has, exactly (same account, date, amount and
normalized description) or nearly (same amount, at most two days apart, a similar description),
and `hold` puts the row into `duplicate_candidate` instead of `transaction`. Nothing is
inserted and nothing is dropped until a human answers, which is the whole point: a repeated
payment is real data and a re-imported statement is not, and only the user knows which.

The question is one card, `ask_user` with `apply.kind = duplicate_decision`, so
`finquery.answers` applies the answers in code before the model runs again: Keep both inserts
the booking from these columns and categorizes it, Remove leaves the data as it was. The same
question is answerable over REST through `/api/imports/{id}/duplicates`, applying through the
same function. A re-import of an identical file would otherwise be hundreds of identical
questions, so a card with more exact candidates than it can hold also offers to remove them all
at once.

Every existing booking is matched at most once, so a genuinely repeated payment (two coffees
of the same amount in the same week) still lands: the second one finds nothing left to match.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from typing import Any

from pydantic_ai.settings import ModelSettings
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finquery.ask_user import DUPLICATE_DECISION, AskAnswer, AskApply, AskOption, AskRow, AskUser
from finquery.categorize import categorize_rows
from finquery.db import (
    Account,
    DuplicateCandidate,
    Import,
    Transaction,
    fingerprint,
    normalize_description,
    utcnow,
)
from finquery.providers import ModelResolver

NEAR_DAYS = 2
"""How far apart two bookings of the same amount may be and still be the same payment."""

SIMILARITY = 0.72
"""How alike two normalized descriptions have to read for a near match. Below it they are two
different payments that happen to cost the same."""

PER_CARD = 5
"""Candidates one card asks about, the cap `ask_user` sets for its rows."""

EXACT = "exact"
NEAR = "near"

KEEP = "keep"
REMOVE = "remove"

ALL_EXACT = "all-exact"
"""The `ref` of the row that stands for every exact candidate at once.

A re-imported statement is hundreds of identical rows, and asking about each one is not a
question, it is a punishment. The card therefore carries one row for the whole group, with
`bookings` saying how many it stands for, the same way a categorization card's row stands for
every booking of a merchant.

It is a row rather than a button on the question because a row is what survives the trip
through the model: asked to show a ready-made card, the fast model copies the title, the rows
and the apply hint faithfully and drops the optional `note` and `options` (seen on OpenRouter,
2026-09-04). Only Remove is offered for the group: inserting hundreds of bookings on one click
is not a decision anyone makes deliberately, while keeping one of them is a per-row answer."""


@dataclass(frozen=True)
class Match:
    """The booking an incoming row matched, as it read when the match was made."""

    existing_id: str
    existing_booked_on: date
    existing_description: str
    kind: str


@dataclass(frozen=True)
class _Existing:
    id: str
    booked_on: date
    amount_cents: int
    description: str
    normalized: str


class Matcher:
    """The bookings one account already holds, each available to match one incoming row.

    Loaded once per commit, so a 1500 row import is one query and not fifteen hundred. Split
    children are left out: the booking an import repeats is the parent, never a leg of it.
    """

    def __init__(self, session: Session, profile_id: str, account_id: str) -> None:
        rows = session.execute(
            select(
                Transaction.id,
                Transaction.booked_on,
                Transaction.amount_cents,
                Transaction.description,
            ).where(
                Transaction.profile_id == profile_id,
                Transaction.account_id == account_id,
                Transaction.parent_id.is_(None),
            )
        ).all()
        self._by_amount: dict[int, list[_Existing]] = defaultdict(list)
        for row_id, booked_on, amount_cents, description in rows:
            self._by_amount[amount_cents].append(
                _Existing(row_id, booked_on, amount_cents, description, normalize_description(description))
            )
        self._taken: set[str] = set()

    def take(self, booked_on: date, amount_cents: int, description: str) -> Match | None:
        """The booking this row is a duplicate of, or None. A match is consumed."""
        free = [row for row in self._by_amount.get(amount_cents, ()) if row.id not in self._taken]
        if not free:
            return None
        normalized = normalize_description(description)
        for row in free:
            if row.booked_on == booked_on and row.normalized == normalized:
                return self._matched(row, EXACT)
        near = [
            (abs((row.booked_on - booked_on).days), -_ratio(normalized, row.normalized), row)
            for row in free
            if abs((row.booked_on - booked_on).days) <= NEAR_DAYS and _similar(normalized, row.normalized)
        ]
        if not near:
            return None
        return self._matched(min(near, key=lambda item: item[:2])[2], NEAR)

    def _matched(self, row: _Existing, kind: str) -> Match:
        self._taken.add(row.id)
        return Match(row.id, row.booked_on, row.description, kind)


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


def _similar(left: str, right: str) -> bool:
    """Whether two normalized descriptions read as the same payment.

    Containment counts because a bank shortens its own text between exports ("REWE SAGT DANKE
    1234" and "REWE SAGT DANKE"), and a short string is only compared as a whole so that "PP"
    inside "PPRO" is not a match.
    """
    if left == right:
        return True
    if len(left) >= 4 and len(right) >= 4 and (left in right or right in left):
        return True
    return _ratio(left, right) >= SIMILARITY


def hold(
    session: Session,
    profile_id: str,
    *,
    account_id: str,
    booked_on: date,
    amount_cents: int,
    description: str,
    counterparty: str | None,
    match: Match,
    source: str = "import",
    import_id: str | None = None,
    draft_id: str | None = None,
) -> DuplicateCandidate:
    """Put one booking aside with the booking it matched, and hand back the candidate."""
    candidate = DuplicateCandidate(
        profile_id=profile_id,
        account_id=account_id,
        import_id=import_id,
        draft_id=draft_id,
        ref=next_ref(session, profile_id),
        kind=match.kind,
        booked_on=booked_on,
        amount_cents=amount_cents,
        description=description,
        counterparty=counterparty,
        source=source,
        existing_id=match.existing_id,
        existing_booked_on=match.existing_booked_on,
        existing_description=match.existing_description,
    )
    session.add(candidate)
    session.flush()
    return candidate


def next_ref(session: Session, profile_id: str) -> str:
    """The next handle a card can carry, counted per profile: `d1`, `d2`, ..."""
    taken = session.scalar(
        select(func.count(DuplicateCandidate.id)).where(DuplicateCandidate.profile_id == profile_id)
    )
    return f"d{int(taken or 0) + 1}"


def pending(
    session: Session, profile_id: str, *, import_id: str | None = None, limit: int | None = None
) -> list[DuplicateCandidate]:
    """The candidates nobody has decided yet, oldest first."""
    query = select(DuplicateCandidate).where(
        DuplicateCandidate.profile_id == profile_id, DuplicateCandidate.decision.is_(None)
    )
    if import_id is not None:
        query = query.where(DuplicateCandidate.import_id == import_id)
    query = query.order_by(DuplicateCandidate.created_at, DuplicateCandidate.id)
    if limit is not None:
        query = query.limit(limit)
    return list(session.scalars(query))


def for_draft(session: Session, draft_id: str) -> DuplicateCandidate | None:
    """The candidate a confirmed draft already produced, so it is never asked about twice."""
    return session.scalars(
        select(DuplicateCandidate).where(DuplicateCandidate.draft_id == draft_id)
    ).first()


def by_ref(session: Session, profile_id: str, refs: Sequence[str]) -> dict[str, DuplicateCandidate]:
    """The candidates these refs name, keyed the way an answer spells them.

    A ref travels through a model and a browser, so it is matched without case and without the
    quotes or backticks either of them sometimes adds.
    """
    wanted = {_key(ref) for ref in refs if _key(ref)}
    if not wanted:
        return {}
    rows = session.scalars(
        select(DuplicateCandidate).where(
            DuplicateCandidate.profile_id == profile_id,
            func.lower(DuplicateCandidate.ref).in_(wanted),
        )
    )
    return {row.ref.casefold(): row for row in rows}


def _key(ref: str) -> str:
    return ref.strip().strip("`\"'").casefold()


@dataclass(frozen=True)
class Tally:
    """How many candidates one import (or the whole profile) has, and what became of them."""

    found: int = 0
    pending: int = 0
    exact: int = 0
    near: int = 0
    kept: int = 0
    removed: int = 0

    @property
    def shortcut(self) -> bool:
        """Whether removing every exact candidate at once is worth offering.

        More exact candidates than a card can hold means a re-import of a file the profile
        already has, and asking about 433 identical rows one by one is not a question, it is a
        punishment.
        """
        return self.exact > PER_CARD

    def payload(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "pending": self.pending,
            "exact": self.exact,
            "near": self.near,
            "kept": self.kept,
            "removed": self.removed,
            "shortcut": self.shortcut,
        }


def tally(session: Session, profile_id: str, *, import_id: str | None = None) -> Tally:
    """Count the candidates, pending by kind and decided by decision, in one query."""
    query = select(DuplicateCandidate.kind, DuplicateCandidate.decision, func.count()).where(
        DuplicateCandidate.profile_id == profile_id
    )
    if import_id is not None:
        query = query.where(DuplicateCandidate.import_id == import_id)
    counts = session.execute(query.group_by(DuplicateCandidate.kind, DuplicateCandidate.decision)).all()
    found = sum(count for _, _, count in counts)
    return Tally(
        found=found,
        pending=sum(count for _, decision, count in counts if decision is None),
        exact=sum(count for kind, decision, count in counts if decision is None and kind == EXACT),
        near=sum(count for kind, decision, count in counts if decision is None and kind == NEAR),
        kept=sum(count for _, decision, count in counts if decision == KEEP),
        removed=sum(count for _, decision, count in counts if decision == REMOVE),
    )


def payload(candidate: DuplicateCandidate) -> dict[str, Any]:
    """One candidate as the page and the tool see it."""
    return {
        "ref": candidate.ref,
        "kind": candidate.kind,
        "booked_on": candidate.booked_on.isoformat(),
        "amount_cents": candidate.amount_cents,
        "description": candidate.description,
        "counterparty": candidate.counterparty,
        "existing_id": candidate.existing_id,
        "existing_booked_on": (
            candidate.existing_booked_on.isoformat() if candidate.existing_booked_on else None
        ),
        "existing_description": candidate.existing_description,
    }


def _german(day: date | None) -> str:
    return day.strftime("%d.%m.%Y") if day else "an earlier date"


def _row_note(candidate: DuplicateCandidate) -> str:
    existing = candidate.existing_booked_on
    if candidate.kind == EXACT:
        return f"Already booked on {_german(existing)}, same amount and text"
    days = abs((candidate.booked_on - existing).days) if existing else 0
    when = "the same day" if days == 0 else "1 day apart" if days == 1 else f"{days} days apart"
    return f"Similar booking {when} ({_german(existing)}): {candidate.existing_description}"


def _candidate_row(candidate: DuplicateCandidate) -> AskRow:
    return AskRow(
        ref=candidate.ref,
        label=candidate.description,
        description=_row_note(candidate),
        amount_cents=candidate.amount_cents,
        date=candidate.booked_on.isoformat(),
        options=[AskOption(label="Keep both", value=KEEP), AskOption(label="Remove", value=REMOVE)],
    )


def _group_row(counts: Tally) -> AskRow:
    return AskRow(
        ref=ALL_EXACT,
        label=f"All {counts.exact} exact duplicates",
        description=(
            "Every one of them matches a booking you already have: same account, date, amount "
            "and text. This is what re-importing the same statement looks like."
        ),
        bookings=counts.exact,
        options=[AskOption(label=f"Remove all {counts.exact}", value=REMOVE)],
    )


def card(
    candidates: Sequence[DuplicateCandidate], counts: Tally, *, account_name: str | None = None
) -> AskUser:
    """The card that asks about one batch of candidates, Keep both or Remove on each row.

    With more exact candidates than a card can hold, the first row stands for all of them and
    the rows under it are the ones a human really has to look at (see `ALL_EXACT`).
    """
    rows = [_candidate_row(candidate) for candidate in candidates]
    if counts.shortcut:
        rows = [_group_row(counts), *rows]
    asked = sum(row.bookings or 1 for row in rows)
    more = max(0, counts.pending - asked)
    where = f" in {account_name}" if account_name else ""
    note = (
        f"{asked} of {counts.pending} bookings{where} look like ones you already have"
        + (f", {more} more after these" if more else "")
        + ". Keep both inserts the booking, Remove leaves your data as it is. Nothing was "
        "written yet."
    )
    return AskUser(
        title="Are these bookings you already have?",
        note=note,
        rows=rows,
        allow_free_text=False,
        # The answers are applied here in code: kept rows are inserted and categorized,
        # removed ones never existed. See `finquery.answers`.
        apply=AskApply(kind=DUPLICATE_DECISION),
    )


def one_card(candidate: DuplicateCandidate, *, account_name: str | None = None) -> AskUser:
    """The card for a single held-aside booking, which is what a typed transaction produces."""
    counts = Tally(
        found=1, pending=1, exact=int(candidate.kind == EXACT), near=int(candidate.kind == NEAR)
    )
    return card([candidate], counts, account_name=account_name)


def review(
    session: Session, profile_id: str, *, import_id: str | None = None, limit: int = PER_CARD
) -> dict[str, Any]:
    """The next batch of candidates as a ready card, which is what the chat tool returns.

    When the exact candidates are asked about as one group row, the rows under it are the near
    matches: those are the ones the group does not cover and the ones a human has to weigh.
    """
    counts = tally(session, profile_id, import_id=import_id)
    room = max(1, min(limit, PER_CARD))
    if counts.shortcut:
        batch = [
            candidate
            for candidate in pending(session, profile_id, import_id=import_id)
            if candidate.kind == NEAR
        ][: room - 1]
    else:
        batch = pending(session, profile_id, import_id=import_id, limit=room)
    first = batch[0] if batch else next(iter(pending(session, profile_id, import_id=import_id, limit=1)), None)
    account = session.get(Account, first.account_id) if first else None
    asked = card(batch, counts, account_name=account.name if account else None) if counts.pending else None
    return {
        **counts.payload(),
        "candidates": [payload(candidate) for candidate in batch],
        "card": asked.model_dump(mode="json") if asked else None,
        "apply": AskApply(kind=DUPLICATE_DECISION).model_dump(mode="json"),
        "message": (
            "Every duplicate candidate has been decided."
            if not asked
            else f"{len(asked.rows)} row(s) to ask about, {counts.pending} candidates in total."
        ),
    }


@dataclass
class Decided:
    """What one batch of decisions did."""

    kept: int = 0
    removed: int = 0
    remaining: int = 0
    needs_review: int = 0
    error: str | None = None

    def line(self) -> str:
        """The one line the card and the tool result say about it."""
        said = []
        if self.kept:
            said.append(f"kept {self.kept} booking{'s' if self.kept != 1 else ''}")
        if self.removed:
            said.append(f"removed {self.removed} duplicate{'s' if self.removed != 1 else ''}")
        head = "Applied: " + " and ".join(said) if said else "Nothing was decided"
        tail = (
            f"{self.remaining} candidate{'s' if self.remaining != 1 else ''} still waiting."
            if self.remaining
            else "No duplicate candidate is left."
        )
        return f"{head}. {tail}"


async def apply_decisions(
    session: Session,
    profile_id: str,
    decisions: Mapping[str, str],
    *,
    remove_all_exact: bool = False,
    import_id: str | None = None,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> Decided:
    """Insert what the user kept, discard what they removed, and record both on the import.

    The booking is written from the candidate's own columns, never from anything a model or a
    browser sent back with the answer, so what lands is what the card showed. Keeping is
    followed by categorization of exactly those rows.

    `remove_all_exact` is the group answer: every pending exact candidate, of one import when
    `import_id` names one (a review conversation asks per import) and of the profile otherwise
    (the card's group row counts the profile, which is what `review` shows).
    """
    found = by_ref(session, profile_id, list(decisions))
    chosen: list[tuple[DuplicateCandidate, str]] = []
    for ref, decision in decisions.items():
        candidate = found.get(_key(ref))
        if candidate is None or candidate.decision is not None:
            continue
        if decision in (KEEP, REMOVE):
            chosen.append((candidate, decision))
    if remove_all_exact:
        already = {candidate.id for candidate, _ in chosen}
        chosen += [
            (candidate, REMOVE)
            for candidate in pending(session, profile_id, import_id=import_id)
            if candidate.kind == EXACT and candidate.id not in already
        ]

    inserted: list[Transaction] = []
    touched: set[str] = set()
    for candidate, decision in chosen:
        candidate.decision = decision
        candidate.decided_at = utcnow()
        if candidate.import_id:
            touched.add(candidate.import_id)
        if decision != KEEP:
            continue
        row = Transaction(
            profile_id=profile_id,
            account_id=candidate.account_id,
            booked_on=candidate.booked_on,
            amount_cents=candidate.amount_cents,
            description=candidate.description,
            counterparty=candidate.counterparty,
            source=candidate.source,
            import_id=candidate.import_id,
            fingerprint=fingerprint(
                candidate.account_id, candidate.booked_on, candidate.amount_cents, candidate.description
            ),
        )
        session.add(row)
        session.flush()
        candidate.transaction_id = row.id
        inserted.append(row)
    session.commit()

    for import_id in touched:
        _recount(session, import_id)
    session.commit()

    decided = Decided(
        kept=len(inserted),
        removed=sum(1 for _, decision in chosen if decision == REMOVE),
    )
    if inserted:
        report = await categorize_rows(
            session, profile_id, inserted, resolve_model=resolve_model, model_settings=model_settings
        )
        decided.needs_review = report.needs_review
        decided.error = report.error
    decided.remaining = tally(session, profile_id).pending
    return decided


def _recount(session: Session, import_id: str) -> None:
    """Write the decision counts of one import back onto its record."""
    record = session.get(Import, import_id)
    if record is None:
        return
    counts = tally(session, record.profile_id, import_id=import_id)
    record.duplicate_count = counts.found
    record.duplicates_kept = counts.kept
    record.duplicates_removed = counts.removed
    record.imported_count = session.scalar(
        select(func.count(Transaction.id)).where(Transaction.import_id == import_id)
    ) or 0


def _choice(answer: AskAnswer) -> str:
    return (answer.value or answer.text or "").strip().casefold()


async def apply_answers(
    session: Session,
    profile_id: str,
    rows: Sequence[AskRow],
    answers: Sequence[AskAnswer],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> str | None:
    """The `duplicate_decision` applier: a card's answers, applied before the model continues.

    An answer on the `ALL_EXACT` row decides every exact candidate at once; every other answer
    names one candidate by its own ref. `rows` is not read: what a decision means comes from
    the stored candidate, not from the card the model retyped.
    """
    # A button or the free text field a card may still carry, the same as a categorization
    # card: a typed "keep" or "remove" counts, anything else is no decision at all.
    chosen = {answer.ref: _choice(answer) for answer in answers if answer.ref}
    decisions = {
        ref: choice for ref, choice in chosen.items() if ref != ALL_EXACT and choice in (KEEP, REMOVE)
    }
    # Only Remove is offered for the group, and only Remove is honoured for it: see `ALL_EXACT`.
    group = chosen.get(ALL_EXACT) == REMOVE
    if not decisions and not group:
        return None
    decided = await apply_decisions(
        session,
        profile_id,
        decisions,
        remove_all_exact=group,
        resolve_model=resolve_model,
        model_settings=model_settings,
    )
    if not decided.kept and not decided.removed:
        return None
    return decided.line()
