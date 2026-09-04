"""Categorization in stages, in this order: rules, merchant dictionary, web lookup, the model.

    1. The profile's own category rules. Highest priority, no model, and it runs before any
       model call, so a rule the user gave always wins over a guess.
    2. Merchant enrichment: the booking text is stripped to a merchant and looked up in the
       seed dictionary. A hit is a category and an enrichment for free.
    2b. Web lookup, only when the profile switched it on: the merchants the dictionary does not
       know are searched for on the web, and what comes back is a placement with a confidence
       like any other, so the threshold and the Question cards keep working unchanged. A
       merchant it answers does not reach the model. See finquery.weblookup.
    3. The categorizer sub-agent on the fast slot, in batches, one entry per merchant, with a
       confidence. At or above `CONFIDENCE_THRESHOLD` the row is set; below it the row stays
       Needs review and the merchant becomes a Question card entry.

Every row that goes through here gets its enrichment (friendly title, short description)
whatever happens to its category, because the table and the charts read those.

`Unknown` is never written here: it is the category a human picks when nothing fits, and the
absence of a category is Needs review.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING

from pydantic_ai.settings import ModelSettings
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finquery.categorize.merchants import Known, fold, lookup, merchant_of
from finquery.categorize.rules import (
    Placement,
    enrich_row,
    load_categories,
    load_rules,
    matching_rule,
    place_row,
    resolve,
    taxonomy_of,
)
from finquery.categorize.subagent import (
    CONFIDENCE_THRESHOLD,
    MerchantBatchEntry,
    batched,
    categorize_merchants,
)
from finquery.ask_user import AskApply, AskOption, AskRow, AskUser
from finquery.db import Category, Transaction
from finquery.providers import ModelResolver, ProviderNotAvailable

if TYPE_CHECKING:
    # Only a type here: the web lookup imports this package's merchant helpers, so importing it
    # back at runtime would close a circle.
    from finquery.weblookup import Lookups

logger = logging.getLogger(__name__)

QUESTIONS_PER_CARD = 5
"""Merchants a single Question card asks about."""

ALWAYS_ASK = 1.01
"""A threshold no confidence can reach: the pass behind a Question card keeps the model's guess
as the first button instead of applying it."""

MAX_OPTIONS = 5
UNKNOWN = "Unknown"

LOOKUP_BLURB_CHARS = 120
"""How much of a web lookup's summary becomes the row's enrichment."""

LOOKUPS_PER_RUN = 5
"""Merchants one run may look up on the web, busiest first.

A lookup is a handful of model calls and a network round trip each, so an import of an
unfamiliar bank does not turn into minutes of searching. What is left over is asked about in a
Question card, and the next run looks the next few up.
TODO: a fixed cap. Make it a setting if a real import needs more than a card's worth at once."""


@dataclass
class Group:
    """One merchant inside one run of the pipeline, with the rows it stands for."""

    key: str
    title: str
    via: str | None
    rows: list[Transaction] = field(default_factory=list)

    @property
    def sample(self) -> Transaction:
        return self.rows[0]

    @property
    def bookings(self) -> int:
        return len(self.rows)

    @property
    def total_cents(self) -> int:
        return sum(row.amount_cents for row in self.rows)

    @property
    def average_cents(self) -> int:
        return round(self.total_cents / self.bookings)

    @property
    def label(self) -> str:
        return f"{self.title} (via {self.via})" if self.via else self.title

    def entry(self) -> MerchantBatchEntry:
        return MerchantBatchEntry(
            key=self.key,
            sample_description=self.sample.description,
            counterparty=self.sample.counterparty,
            bookings=self.bookings,
            average_cents=self.average_cents,
            incoming=self.total_cents > 0,
            via=self.via,
        )


@dataclass(frozen=True)
class Question:
    """One merchant a human has to place, as a Question card row.

    `pattern` is what an answer becomes a rule for, which is why it is the merchant token and
    not a transaction id: one answer settles every booking of that merchant, now and later.
    """

    pattern: str
    label: str
    description: str
    date: date
    amount_cents: int
    bookings: int
    options: list[str]
    guess: str | None = None
    confidence: float | None = None

    def payload(self) -> dict[str, object]:
        return {
            "pattern": self.pattern,
            "label": self.label,
            "description": self.description,
            "date": self.date.isoformat(),
            "amount_cents": self.amount_cents,
            "bookings": self.bookings,
            "options": self.options,
            "guess": self.guess,
            "confidence": self.confidence,
        }


@dataclass
class Report:
    """What one run of the pipeline did."""

    rows: int = 0
    by_rule: int = 0
    by_dictionary: int = 0
    by_lookup: int = 0
    by_model: int = 0
    needs_review: int = 0
    merchants: int = 0
    model_calls: int = 0
    lookups: int = 0
    """Merchants the web lookup stage looked up, zero unless the profile switched it on."""
    lookups_refused: int = 0
    """Merchants it refused to look up because nothing was safe to send (a person's name)."""
    questions: list[Question] = field(default_factory=list)
    error: str | None = None

    def payload(self) -> dict[str, object]:
        return {
            "rows": self.rows,
            "by_rule": self.by_rule,
            "by_dictionary": self.by_dictionary,
            "by_lookup": self.by_lookup,
            "by_model": self.by_model,
            "needs_review": self.needs_review,
            "merchants": self.merchants,
            "model_calls": self.model_calls,
            "lookups": self.lookups,
            "lookups_refused": self.lookups_refused,
            "questions": [question.payload() for question in self.questions],
            "error": self.error,
        }


def review_card(questions: list[Question], pending: int) -> AskUser:
    """Turn a batch of questions into the Question card the transcript renders.

    The same shape the assistant produces when it calls `ask_user` itself, so the seeded first
    card of a review conversation and every later one look and behave the same.
    """
    more = pending - len(questions)
    asked = len(questions)
    return AskUser(
        title="Which category do these belong to?",
        note=(
            f"{asked} {'merchant' if asked == 1 else 'merchants'} I am not sure about"
            + (f", {more} more after these" if more > 0 else "")
            + ". One answer becomes a rule for every booking of that merchant."
        ),
        rows=[
            AskRow(
                ref=question.pattern,
                label=question.label,
                description=question.description,
                amount_cents=question.amount_cents,
                date=question.date.isoformat(),
                bookings=question.bookings,
                options=[AskOption(label=option, value=option) for option in question.options],
            )
            for question in questions
        ],
        allow_free_text=True,
        # The answers become category rules in code, before the model is asked to continue.
        apply=AskApply(),
    )


def group_rows(rows: list[Transaction]) -> list[Group]:
    """Bookings by merchant, busiest first: the unit the model and the questions work in."""
    groups: dict[str, Group] = {}
    for row in rows:
        merchant = merchant_of(row.description, row.counterparty)
        key = merchant.key or fold(row.description) or "unnamed"
        group = groups.get(key)
        if group is None:
            group = groups[key] = Group(key=key, title=merchant.title, via=merchant.via)
        group.rows.append(row)
    for group in groups.values():
        group.rows.sort(key=lambda row: row.booked_on, reverse=True)
    return sorted(groups.values(), key=lambda group: (-group.bookings, group.key))


def _known_merchant(group: Group) -> Known | None:
    """The dictionary entry for a merchant, matched on its key and then on its booking text."""
    return lookup(group.key) or lookup(f"{group.key} {fold(group.sample.description)}")


def _in_use(
    session: Session,
    profile_id: str,
    groups: list[Group],
    decided: dict[str, "Decision"],
) -> list[str]:
    """The categories this profile puts to use, busiest first: the fallback buttons of a card.

    Counted over what is already stored plus what this run is about to store, so the very first
    import still offers real categories instead of the whole taxonomy.
    """
    counts: Counter[str] = Counter(
        dict(
            session.execute(
                select(Category.name, func.count(Transaction.id))
                .join(Transaction, Transaction.category_id == Category.id)
                .where(Category.profile_id == profile_id)
                .group_by(Category.id)
            ).all()
        )
    )
    for group in groups:
        placement = decided[group.key].placement
        if placement is not None:
            counts[placement.category.name] += group.bookings
    return [name for name, _ in counts.most_common()]


def _options(guess: Placement | None, common: list[str]) -> list[str]:
    """The buttons on a Question card row: the guess first, then what the profile uses, then Unknown."""
    options = [guess.label] if guess else []
    for name in common:
        if len(options) >= MAX_OPTIONS - 1:
            break
        if name != UNKNOWN and all(not option.startswith(name) for option in options):
            options.append(name)
    options.append(UNKNOWN)
    return options


@dataclass(frozen=True)
class Guess:
    """What the categorizer said about one merchant."""

    placement: Placement | None
    """None when it named a category the profile does not have, or named `Unknown`."""
    confidence: float
    title: str
    blurb: str


@dataclass(frozen=True)
class Decision:
    """What one merchant came to in one run: its enrichment, where it lands, and the guess."""

    title: str
    blurb: str | None
    placement: Placement | None
    guess: Placement | None = None
    confidence: float | None = None


def _placement_of(categories: list[Category], category: str | None, subcategory: str | None) -> Placement | None:
    """Where automation says a merchant goes, or None when it named nothing this profile has.

    Automation never produces `Unknown`: that is the category a human picks when nothing fits,
    so a row it would land on stays Needs review instead.
    """
    placement = resolve(categories, category or "", subcategory)
    if placement is not None and placement.category.name == UNKNOWN:
        return None
    return placement


async def _look_up(
    groups: list[Group], categories: list[Category], lookups: "Lookups"
) -> tuple[dict[str, Guess], int, int]:
    """Search the web for the merchants the dictionary does not know, busiest first.

    Returns a guess per merchant the lookup placed, how many lookups ran, and how many it
    refused because nothing about the booking was safe to send (a person's name). A merchant it
    could not place is left for the model stage.

    Sequential on purpose: one lookup is its own agent loop and its own network traffic, and
    the point of the cap is that an import stays quick.
    """
    taxonomy = taxonomy_of(categories)
    answers: dict[str, Guess] = {}
    ran = refused = 0
    for group in groups:
        if ran >= LOOKUPS_PER_RUN:
            break
        found = await lookups.merchant(group.sample.description, group.sample.counterparty, taxonomy)
        if not found.token:
            # Nothing was safe to send, so nothing was spent either: it does not use the budget.
            refused += 1
            continue
        ran += 1
        placement = _placement_of(categories, found.category, found.subcategory)
        if placement is None:
            continue
        answers[group.key] = Guess(
            placement=placement,
            confidence=found.confidence,
            title=group.title,
            blurb=found.summary[:LOOKUP_BLURB_CHARS],
        )
    return answers, ran, refused


async def _ask_model(
    groups: list[Group],
    categories: list[Category],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None,
) -> tuple[dict[str, Guess], int, str | None]:
    """Run the categorizer over the groups it is given, batch by batch.

    Returns a `Guess` per merchant key, plus how many model calls it took and what failed.
    """
    if not groups:
        return {}, 0, None
    try:
        model = resolve_model("fast")
    except ProviderNotAvailable as exc:
        return {}, 0, f"The categorizer is unavailable: {exc}"

    taxonomy = taxonomy_of(categories)
    answers: dict[str, Guess] = {}
    calls = 0
    error: str | None = None
    for batch in batched([group.entry() for group in groups]):
        calls += 1
        try:
            batch_answers = await categorize_merchants(model, batch, taxonomy, model_settings=model_settings)
        except Exception as exc:  # noqa: BLE001 - a batch that fails leaves its rows Needs review
            logger.warning("the categorizer failed on a batch of %d merchants", len(batch), exc_info=True)
            error = f"The categorizer failed on one batch: {exc}"
            continue
        for key, answer in batch_answers.items():
            answers[key] = Guess(
                placement=_placement_of(categories, answer.category, answer.subcategory),
                confidence=answer.confidence,
                title=answer.title,
                blurb=answer.description,
            )
    return answers, calls, error


async def categorize_rows(
    session: Session,
    profile_id: str,
    rows: list[Transaction],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    lookups: "Lookups | None" = None,
    question_limit: int = QUESTIONS_PER_CARD,
    threshold: float = CONFIDENCE_THRESHOLD,
) -> Report:
    """The stages over these rows, committing what they place.

    `threshold=ALWAYS_ASK` turns the model pass into a suggestion pass: rules and the
    dictionary still place what they know, and every merchant left becomes a question carrying
    the model's guess as its first button. That is how the review queue is built.

    `lookups` is the web lookup stage, present only for a profile that switched it on
    (`weblookup.lookups_for` returns None otherwise), so "off" needs no branch here.
    """
    report = Report(rows=len(rows))
    if not rows:
        return report

    categories = load_categories(session, profile_id)
    by_id = {category.id: category for category in categories}
    subcategories = {sub.id: sub for category in categories for sub in category.subcategories}

    # Stage 1: the profile's rules, per row, before any model is asked anything.
    rules = load_rules(session, profile_id)
    undecided: list[Transaction] = []
    ruled: dict[str, Placement] = {}
    for row in rows:
        rule = matching_rule(rules, row.description, row.counterparty) if rules else None
        if rule is None:
            undecided.append(row)
            continue
        ruled[row.id] = Placement(
            category=by_id[rule.category_id],
            subcategory=subcategories.get(rule.subcategory_id or ""),
        )
        report.by_rule += 1

    groups = group_rows(rows)
    report.merchants = len(groups)

    # Stage 2: the merchant dictionary, per merchant.
    undecided_ids = {row.id for row in undecided}
    for_model: list[Group] = []
    known: dict[str, Placement] = {}
    for group in groups:
        if not any(row.id in undecided_ids for row in group.rows):
            continue
        entry = _known_merchant(group)
        placement = resolve(categories, entry.category, entry.subcategory) if entry else None
        if placement is None:
            for_model.append(group)
        else:
            known[group.key] = placement

    # Stage 2b: the web, for the merchants the dictionary does not know.
    found: dict[str, Guess] = {}
    if lookups is not None and for_model:
        found, report.lookups, report.lookups_refused = await _look_up(for_model, categories, lookups)
        for_model = [group for group in for_model if group.key not in found]

    # Stage 3: the categorizer sub-agent, for what is left.
    answers, report.model_calls, report.error = await _ask_model(
        for_model, categories, resolve_model=resolve_model, model_settings=model_settings
    )
    guesses = {**found, **answers}

    # What each merchant came to, before anything is written, so the buttons on a Question card
    # can offer the categories this run is putting to use.
    decided: dict[str, Decision] = {}
    for group in groups:
        entry = _known_merchant(group)
        title = group.title
        blurb = entry.blurb if entry is not None else None
        placement = known.get(group.key)
        guessed = guesses.get(group.key)
        if guessed is not None:
            title = guessed.title.strip() or title
            blurb = guessed.blurb.strip() or blurb
            if guessed.confidence >= threshold:
                placement = guessed.placement
        decided[group.key] = Decision(
            title=title,
            blurb=blurb,
            placement=placement,
            guess=guessed.placement if guessed else None,
            confidence=guessed.confidence if guessed else None,
        )

    common = _in_use(session, profile_id, groups, decided)
    for group in groups:
        decision = decided[group.key]
        placed = 0
        for row in group.rows:
            enrich_row(row, decision.title, decision.blurb)
            target = ruled.get(row.id) or decision.placement
            if target is None:
                report.needs_review += 1
                continue
            place_row(row, target)
            if row.id not in ruled:
                placed += 1
        if decision.placement is not None:
            if group.key in known:
                report.by_dictionary += placed
            elif group.key in found:
                report.by_lookup += placed
            else:
                report.by_model += placed
        elif len(report.questions) < question_limit and any(row.id not in ruled for row in group.rows):
            report.questions.append(
                Question(
                    pattern=group.key,
                    label=group.label,
                    description=group.sample.description,
                    date=group.sample.booked_on,
                    amount_cents=group.sample.amount_cents,
                    bookings=group.bookings,
                    options=_options(decision.guess, common),
                    guess=decision.guess.label if decision.guess else None,
                    confidence=decision.confidence,
                )
            )
    session.commit()
    return report


def needs_review_rows(session: Session, profile_id: str, *, import_id: str | None = None) -> list[Transaction]:
    """The profile's uncategorized bookings, optionally only those of one import.

    Split parents are left out: only the children of a split carry a category.
    """
    statement = select(Transaction).where(
        Transaction.profile_id == profile_id,
        Transaction.category_id.is_(None),
        ~Transaction.id.in_(select(Transaction.parent_id).where(Transaction.parent_id.is_not(None))),
    )
    if import_id is not None:
        statement = statement.where(Transaction.import_id == import_id)
    return list(session.scalars(statement.order_by(Transaction.booked_on)).all())


async def categorize_import(
    session: Session,
    profile_id: str,
    import_id: str,
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    lookups: "Lookups | None" = None,
) -> Report:
    """Categorize what one import brought in, which is what a chat import does after its commit."""
    rows = needs_review_rows(session, profile_id, import_id=import_id)
    return await categorize_rows(
        session,
        profile_id,
        rows,
        resolve_model=resolve_model,
        model_settings=model_settings,
        lookups=lookups,
        question_limit=len(rows),
    )


async def pending_questions(
    session: Session,
    profile_id: str,
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    lookups: "Lookups | None" = None,
    limit: int = QUESTIONS_PER_CARD,
) -> tuple[list[Question], int]:
    """The next merchants to ask about, and how many merchants are still waiting in total.

    The rules and dictionary stages run here too, so a merchant a rule created since the
    import already covers is settled instead of asked, and the model's guess rides along as
    the first button of each question.
    """
    rows = needs_review_rows(session, profile_id)
    if not rows:
        return [], 0
    groups = group_rows(rows)
    wanted = {group.key for group in groups[:limit]}
    batch = [row for group in groups if group.key in wanted for row in group.rows]
    report = await categorize_rows(
        session,
        profile_id,
        batch,
        resolve_model=resolve_model,
        model_settings=model_settings,
        lookups=lookups,
        question_limit=limit,
        threshold=ALWAYS_ASK,
    )
    return report.questions, len(groups)
