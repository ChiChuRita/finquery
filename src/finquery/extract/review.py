"""The review step: the flagged rows of an extraction, and what the answers do.

A statement whose guards all passed is imported without asking (`finquery.extract.statement`).
Anything else stops here, because a figure nobody can vouch for must not become a booking
behind the user's back. On the Import page the review is a table with accept, edit and drop per
row; in a chat it is a Question card, and this module is that card plus its applier.

The applier is the point. The answers are acted on in code before the model runs again (ADR
0008): the rows the user accepted, plus every row the guards passed, are committed through
`ingest.commit.commit_rows`, the same commit a CSV import uses, so the duplicate step and the
categorization that follow are the same code for a statement PDF. What it did comes back as
the card's `applied` line, so the model summarizes instead of sequencing.
"""

import logging
from collections.abc import Sequence

from pydantic import ValidationError
from pydantic_ai.settings import ModelSettings
from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.ask_user import EXTRACTION_REVIEW, AskAnswer, AskApply, AskOption, AskRow, AskUser
from finquery.categorize import categorize_import
from finquery.db import Attachment
from finquery.extract.guards import ExtractedRow
from finquery.extract.statement import Extraction, commit_extraction
from finquery.ingest.commit import import_summary
from finquery.providers import ModelResolver

logger = logging.getLogger(__name__)

ACCEPT = "accept"
DROP = "drop"

ROWS_PER_CARD = 4
"""Flagged rows asked about one by one. The rest are one row of their own, because a card of
five is a decision a person can make and a card of forty is not."""

REST = "rest"
"""The ref of the row that stands for every flagged row the card did not list."""

ALL = "all"
"""The ref of the row a card asks with when no single row is flagged but the statement itself
did not reconcile."""


def _row_label(row: ExtractedRow) -> str:
    date = row.booked_on.isoformat() if row.booked_on else "no date"
    return f"{date}  {row.description[:60]}"


def review_card(extraction: Extraction) -> AskUser:
    """The card that asks about what the guards would not pass on their own.

    Every row the guards did pass is imported as soon as one answer arrives, which the note
    says, so the decision on the card is only ever about the rows nobody could verify.
    """
    flagged = [(index, row) for index, row in enumerate(extraction.rows) if row.flagged]
    clean = len(extraction.clean)
    shown = flagged[:ROWS_PER_CARD]
    rows = [
        AskRow(
            ref=f"r{index}",
            label=_row_label(row),
            description=(
                f"{row.reason} Page {row.page}"
                + (f", line {row.line}: {row.source[:90]}" if row.source else "")
            ),
            amount_cents=row.amount_cents,
            date=row.booked_on.isoformat() if row.booked_on else None,
            options=[AskOption(label="Accept as read", value=ACCEPT), AskOption(label="Drop it", value=DROP)],
        )
        for index, row in shown
    ]
    rest = len(flagged) - len(shown)
    if rest > 0:
        rows.append(
            AskRow(
                ref=REST,
                label=f"The other {rest} flagged bookings",
                description="Same decision for all of them at once.",
                bookings=rest,
                options=[
                    AskOption(label=f"Accept all {rest}", value=ACCEPT),
                    AskOption(label=f"Drop all {rest}", value=DROP),
                ],
            )
        )
    if not flagged:
        # Nothing is wrong with a single row, but the arithmetic says a booking is missing.
        rows.append(
            AskRow(
                ref=ALL,
                label=f"All {len(extraction.clean)} bookings that were read",
                description="Import them even though the statement does not add up, or import nothing.",
                bookings=len(extraction.clean),
                options=[
                    AskOption(label="Import them anyway", value=ACCEPT),
                    AskOption(label="Import nothing", value=DROP),
                ],
            )
        )

    note = [extraction.reconciliation.line]
    if flagged:
        note.append(
            f"{clean} of {len(extraction.rows)} bookings passed both guards and are imported as "
            f"soon as you answer. The {len(flagged)} below could not be verified: accept a row to "
            "import it as it was read, drop it to leave it out."
        )
    for error in extraction.errors[:2]:
        note.append(error)
    return AskUser(
        title=(
            f"{len(flagged)} of {len(extraction.rows)} bookings in {extraction.file_name} need your decision"
            if flagged
            else f"{extraction.file_name} does not reconcile. Import it anyway?"
        ),
        note="\n".join(note),
        rows=rows,
        allow_free_text=False,
        apply=AskApply(kind=EXTRACTION_REVIEW),
    )


def pending_extraction(session: Session, conversation_id: str) -> Attachment | None:
    """The attachment of this conversation whose extraction is waiting for a decision.

    The newest one, because a card is answered in the turn after it was asked. Two statements
    waiting at once in one conversation would be ambiguous.
    TODO: newest wins. Give the card its own handle if two extractions can ever be open at once.
    """
    return session.scalars(
        select(Attachment)
        .where(
            Attachment.conversation_id == conversation_id,
            Attachment.extraction_json.is_not(None),
            Attachment.import_id.is_(None),
        )
        .order_by(Attachment.created_at.desc())
    ).first()


def _decisions(rows: Sequence[AskRow], answers: Sequence[AskAnswer]) -> dict[str, str]:
    """What was chosen per ref, ignoring anything that is not one of this card's rows."""
    refs = {row.ref for row in rows}
    chosen: dict[str, str] = {}
    for answer in answers:
        value = (answer.value or answer.text or "").strip().casefold()
        if answer.ref in refs and value in {ACCEPT, DROP}:
            chosen[answer.ref] = value
    return chosen


def accepted_rows(extraction: Extraction, rows: Sequence[AskRow], answers: Sequence[AskAnswer]) -> tuple[list[ExtractedRow], int]:
    """The rows to commit, and how many were dropped.

    Every row the guards passed is in, unless the user answered the whole-statement question
    with "import nothing". A flagged row is in only if it was accepted, by itself or through
    the row that stands for the rest.
    """
    chosen = _decisions(rows, answers)
    if chosen.get(ALL) == DROP:
        return [], len(extraction.rows)
    keep = list(extraction.clean)
    dropped = 0
    listed = {row.ref for row in rows}
    for index, row in enumerate(extraction.rows):
        if not row.flagged:
            continue
        ref = f"r{index}"
        decision = chosen.get(ref) if ref in listed else chosen.get(REST)
        if decision == ACCEPT and row.committable:
            keep.append(row)
        else:
            dropped += 1
    # Printed order, so the Import record and the transactions page read like the statement.
    keep.sort(key=lambda row: (row.page, row.line or 0))
    return keep, dropped


async def apply_review(
    session: Session,
    profile_id: str,
    conversation_id: str,
    rows: Sequence[AskRow],
    answers: Sequence[AskAnswer],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> str | None:
    """Commit what the user accepted and categorize it. Returns the card's `applied` line."""
    record = pending_extraction(session, conversation_id)
    if record is None or record.extraction_json is None:
        return None
    try:
        extraction = Extraction.model_validate_json(record.extraction_json)
    except ValidationError:
        logger.warning("a stored extraction could not be read, so nothing was imported")
        return None

    keep, dropped = accepted_rows(extraction, rows, answers)
    if not keep:
        return f"Nothing was imported from {extraction.file_name}: every booking was dropped."

    committed = commit_extraction(
        session,
        profile_id,
        rows=keep,
        file_name=extraction.file_name,
        kind=extraction.kind,
        layout=extraction.layout,
        account_name=extraction.account_name,
        reconciliation=extraction.reconciliation,
        dropped=dropped,
    )
    record.import_id = committed.id
    record.account_name = extraction.account_name
    session.commit()

    report = await categorize_import(
        session,
        profile_id,
        committed.id,
        resolve_model=resolve_model,
        model_settings=model_settings,
    )
    summary = import_summary(session, committed, extraction.account_name)
    accepted = len(keep) - len(extraction.clean)
    said = [f"Applied: {summary}"]
    if accepted:
        said.append(f"{accepted} of them you accepted after the guards flagged them.")
    if dropped:
        said.append(f"{dropped} flagged booking(s) were dropped and not imported.")
    if report.error:
        said.append(report.error)
    return " ".join(said)
