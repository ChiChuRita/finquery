"""Importing a file the user dropped into the chat, as one call the `import_file` tool makes.

Same pipeline as the Import page, same functions: sniff the CSV, take the preset or ask the
mapping sub-agent, commit the rows, categorize them. The two differences are where the file
comes from (a stored attachment instead of a multipart upload) and how the user confirms a
mapping nobody has a preset for: the Import page shows a preview, a chat shows a Question card,
so this returns the card and is called a second time with `confirmed=True`.

Every figure in what it returns is counted here, so the assistant can only quote numbers the
import really produced. Progress is reported through `report` as it goes; see
`finquery.progress`.

PDF and image attachments are stored and recognized, but reading them is ticket 11: this
answers with a clear sentence rather than an error, so the assistant can say what it can and
cannot do.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session

from finquery import attachments
from finquery.ask_user import MAPPING_CONFIRMATION, AskApply, AskOption, AskUser
from finquery.categorize import QUESTIONS_PER_CARD, categorize_import, pending_questions
from finquery.db import Attachment, Import
from finquery.ingest.commit import commit_rows, import_summary
from finquery.ingest.csv_reader import (
    CsvUnreadable,
    Mapping,
    Sniffed,
    detect_preset,
    mapping_for,
    parse,
    sniff,
)
from finquery.ingest.mapping_agent import MappingUnusable, propose
from finquery.providers import ModelResolver, ProviderNotAvailable

CARD_SAMPLE_ROWS = 3
"""Bookings shown on the mapping card: enough to see that the columns landed right."""

CONFIRM = "confirm"
REJECT = "reject"

NOT_READY = (
    "I stored `{name}`, but I cannot read a {kind} yet: pulling bookings out of a statement PDF "
    "or a photo is the next piece of work (ticket 11). A CSV export of the same account imports "
    "right away, and the Import page takes one too."
)


class Reporter(Protocol):
    """How this module streams progress: one line, plus counts, as it happens."""

    def __call__(self, stage: str, message: str, **counts: int) -> Awaitable[None]: ...


async def _silent(stage: str, message: str, **counts: int) -> None:
    return None


def mapping_card(file_name: str, proposal: Mapping, note: str, samples: list[str]) -> AskUser:
    """The card that asks whether a proposed column mapping is right.

    No rows, two buttons: the card is one decision, not a list of them. What the mapping says
    and the first bookings it produced are in the note, which is what makes the decision
    answerable at a glance.
    """
    lines = [note.strip(), "", "How I read the columns:"]
    lines += [f"  {label}: {value}" for label, value in _mapping_lines(proposal)]
    lines += ["", f"The first {len(samples)} bookings that come out of it:"]
    lines += [f"  {sample}" for sample in samples]
    return AskUser(
        title=f"Import {file_name} with this mapping?",
        note="\n".join(lines),
        options=[
            AskOption(label="Yes, import it", value=CONFIRM),
            AskOption(label="No, the mapping is wrong", value=REJECT),
        ],
        allow_free_text=False,
        # Nothing for the server to apply: the confirmation is acted on by calling `import_file`
        # again. The kind is here so the answers are not mistaken for a categorization card.
        apply=AskApply(kind=MAPPING_CONFIRMATION),
    )


def _mapping_lines(mapping: Mapping) -> list[tuple[str, str]]:
    pairs = [
        ("date", mapping.date_column),
        ("amount", mapping.amount_column),
        ("money out", mapping.debit_column),
        ("money in", mapping.credit_column),
        ("description", mapping.description_column),
        ("counterparty", mapping.counterparty_column),
    ]
    lines = [(label, value) for label, value in pairs if value]
    lines.append(("date format", mapping.date_format))
    lines.append(("decimal separator", "1.234,56" if mapping.decimal_separator == "comma" else "1,234.56"))
    return lines


def _samples(sniffed: Sniffed, mapping: Mapping) -> list[str]:
    parsed = parse(sniffed, mapping, limit=CARD_SAMPLE_ROWS)
    return [
        f"{row.booked_on.isoformat()}  {row.amount_cents / 100:>10.2f} EUR  {row.description[:48]}"
        for row in parsed.rows
    ]


def _import_payload(record: Import, account_name: str, summary: str) -> dict[str, Any]:
    return {
        "file": record.file_name,
        "account": account_name,
        "rows_read": record.row_count,
        "imported": record.imported_count,
        "duplicates": record.duplicate_count,
        "unreadable_rows": record.skipped_count,
        "summary": summary,
    }


async def import_attachment(
    session: Session,
    profile_id: str,
    conversation_id: str,
    *,
    file_name: str,
    account_name: str | None = None,
    confirmed: bool = False,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    report: Reporter | Callable[..., Awaitable[None]] = _silent,
) -> dict[str, Any]:
    """Turn one stored attachment into transactions, or say why it cannot be done yet."""
    record = attachments.find(session, conversation_id, file_name)
    if record is None:
        known = [item.file_name for item in attachments.of_conversation(session, conversation_id)]
        return {
            "status": "no_such_file",
            "error": f"No file called {file_name!r} is attached to this conversation.",
            "attached_files": known,
        }
    if record.import_id is not None:
        return {
            "status": "already_imported",
            "message": f"`{record.file_name}` was already imported. Nothing was imported twice.",
            "file": record.file_name,
        }
    if record.kind != "csv":
        return {
            "status": "extraction_not_ready",
            "message": NOT_READY.format(name=record.file_name, kind="PDF" if record.kind == "pdf" else "photo"),
            "file": record.file_name,
        }
    return await _import_csv(
        session,
        profile_id,
        record,
        account_name=account_name,
        confirmed=confirmed,
        resolve_model=resolve_model,
        model_settings=model_settings,
        report=report,
    )


async def _mapping_for_file(
    session: Session,
    record: Attachment,
    sniffed: Sniffed,
    *,
    confirmed: bool,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None,
    report: Reporter | Callable[..., Awaitable[None]],
) -> tuple[Mapping | None, str, str, dict[str, Any] | None]:
    """The mapping to commit with, or a payload asking the user to confirm the proposal.

    A recognized bank never reaches the model. An unknown layout is proposed once, stored on the
    attachment and returned as a card; the confirmed second call reads the stored proposal back,
    so what gets committed is the mapping the user saw and not one the model wrote again.
    """
    preset = detect_preset(sniffed.header)
    if preset is not None:
        await report("mapping", f"Recognized as a {preset.label} export", columns=len(sniffed.header))
        return (
            mapping_for(preset, sniffed.header),
            preset.account_name,
            preset.name,
            None,
        )

    stored = Mapping.model_validate_json(record.mapping_json) if record.mapping_json else None
    if confirmed and stored is not None:
        await report("mapping", "Using the mapping you confirmed", columns=len(sniffed.header))
        return stored, record.account_name or "", "", None

    await report("mapping", "No preset knows this header, asking the model for a mapping")
    try:
        model = resolve_model("fast")
        proposal = await propose(sniffed, record.file_name, model=model, model_settings=model_settings)
    except (ProviderNotAvailable, MappingUnusable) as exc:
        return None, "", "", {"status": "mapping_failed", "file": record.file_name, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - any model or transport failure is one message here
        return (
            None,
            "",
            "",
            {
                "status": "mapping_failed",
                "file": record.file_name,
                "error": f"The model could not propose a mapping: {exc}",
            },
        )

    record.mapping_json = proposal.mapping.model_dump_json()
    record.account_name = proposal.account_name
    session.commit()
    card = mapping_card(record.file_name, proposal.mapping, proposal.note, _samples(sniffed, proposal.mapping))
    return (
        proposal.mapping,
        proposal.account_name,
        "",
        {
            "status": "confirm_mapping",
            "file": record.file_name,
            "note": proposal.note,
            "mapping": proposal.mapping.model_dump(),
            "card": card.model_dump(mode="json"),
            "instruction": (
                "Show this `card` with `ask_user`, unchanged. If the user answers "
                f"{CONFIRM!r}, call `import_file` again for this file with confirmed=true. "
                "If they answer anything else, import nothing and say the mapping can be "
                "corrected on the Import page."
            ),
        },
    )


async def _import_csv(
    session: Session,
    profile_id: str,
    record: Attachment,
    *,
    account_name: str | None,
    confirmed: bool,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None,
    report: Reporter | Callable[..., Awaitable[None]],
) -> dict[str, Any]:
    try:
        sniffed = sniff(record.data)
    except CsvUnreadable as exc:
        return {"status": "unreadable", "file": record.file_name, "error": str(exc)}
    await report("read", f"Read {len(sniffed.rows)} rows from {record.file_name}", rows_read=len(sniffed.rows))

    mapping, suggested_account, preset, pending = await _mapping_for_file(
        session,
        record,
        sniffed,
        confirmed=confirmed,
        resolve_model=resolve_model,
        model_settings=model_settings,
        report=report,
    )
    if pending is not None or mapping is None:
        return pending or {"status": "mapping_failed", "file": record.file_name, "error": "No mapping to import with."}

    try:
        parsed = parse(sniffed, mapping)
    except CsvUnreadable as exc:
        return {"status": "unreadable", "file": record.file_name, "error": str(exc)}
    if not parsed.rows:
        return {
            "status": "unreadable",
            "file": record.file_name,
            "error": "No row of the file could be read with this mapping.",
        }

    account = (account_name or "").strip() or suggested_account or "Imported account"
    committed = commit_rows(
        session,
        profile_id,
        rows=parsed.rows,
        mapping=mapping,
        account_name=account,
        file_name=record.file_name,
        preset=preset or None,
        skipped_count=len(parsed.issues),
    )
    record.import_id = committed.id
    record.mapping_json = mapping.model_dump_json()
    record.account_name = account
    session.commit()
    await report(
        "imported",
        f"Imported {committed.imported_count} bookings into {account}",
        imported=committed.imported_count,
        duplicates=committed.duplicate_count,
    )

    await report("categorizing", f"Categorizing {committed.imported_count} bookings")
    categorized = await categorize_import(
        session, profile_id, committed.id, resolve_model=resolve_model, model_settings=model_settings
    )
    await report(
        "categorized",
        f"{categorized.rows - categorized.needs_review} of {categorized.rows} categorized",
        by_rule=categorized.by_rule,
        by_dictionary=categorized.by_dictionary,
        by_model=categorized.by_model,
        needs_review=categorized.needs_review,
    )

    questions, merchants_pending = await pending_questions(
        session,
        profile_id,
        resolve_model=resolve_model,
        model_settings=model_settings,
        limit=QUESTIONS_PER_CARD,
    )
    payload = _import_payload(committed, account, import_summary(session, committed, account))
    payload.update(
        {
            "status": "imported",
            "categorized": {
                "by_rule": categorized.by_rule,
                "by_dictionary": categorized.by_dictionary,
                "by_model": categorized.by_model,
                "needs_review": categorized.needs_review,
                "error": categorized.error,
            },
            # The same shape `review_batch` returns, so the assistant asks about them the way it
            # asks in a review conversation.
            "pending_merchants": merchants_pending,
            "questions": [question.payload() for question in questions],
        }
    )
    return payload
