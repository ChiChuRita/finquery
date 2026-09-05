"""Importing a file the user dropped into the chat, as one call the `import_file` tool makes.

Same pipeline as the REST commit, same functions: sniff the CSV, take the preset or ask the
mapping sub-agent, commit the rows, categorize them. The two differences are where the file
comes from (a stored attachment instead of a multipart upload) and how the user confirms a
mapping nobody has a preset for: a chat shows a Question card, so this returns the card and is
called a second time with `confirmed=True`.

Every figure in what it returns is counted here, so the assistant can only quote numbers the
import really produced. Progress is reported through `report` as it goes; see
`finquery.progress`.

Three readers, one router. The kind of the attachment decides:

- a **CSV** is read here, as it always was.
- a **PDF** is a bank statement: `finquery.extract.statement` reads its pages and the guards
  check them. A statement that reconciles with nothing flagged is imported straight away, the
  same way a preset CSV is; anything else comes back as a review card first (ADR 0011).
- an **image** is a receipt: `finquery.extract.bill` reads its line items and either proposes a
  split of the booking it matches or previews a new one. A photo dropped into a chat is a till
  receipt, which is what makes this the right guess to make here; a photo of a statement page is
  read as a page only by `POST /api/imports/extract`, which no screen calls.

Whichever reader produced them, the rows are committed by `ingest.commit.commit_rows`, so a
file may hold bookings the profile already has and none of them is inserted or dropped in
silence. They are held aside as duplicate candidates and this returns the first card to ask
about them (`duplicate_card`); the merchants that need a category wait until the candidates are
decided, so the transcript never shows two cards at once. See `finquery.ingest.duplicates`.
"""

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, Protocol

from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session

from finquery import attachments
from finquery.ask_user import MAPPING_CONFIRMATION, AskApply, AskOption, AskUser
from finquery.categorize import QUESTIONS_PER_CARD, categorize_import, pending_questions, review_card
from finquery.db import Attachment, Import
from finquery.extract.bill import bill_outcome, read_bill_image
from finquery.extract.pdf import PdfUnreadable
from finquery.extract.review import review_card as extraction_review_card
from finquery.extract.statement import Extraction, commit_extraction, extract_statement
from finquery.formats import day, eur
from finquery.ingest import duplicates
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
    """The first bookings the mapping produces, written the way the rest of the app writes them.

    The card is where the user decides whether the columns landed right, so a date and an amount
    on it read `01.01.2025` and `-39,90 EUR`, not `2025-01-01  -39.90 EUR` (e2e of 2026-09-05,
    m5). One format, `finquery.formats`.
    """
    parsed = parse(sniffed, mapping, limit=CARD_SAMPLE_ROWS)
    return [
        f"{day(row.booked_on)}  {eur(row.amount_cents):>10} EUR  {row.description[:48]}"
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
    if record.kind == "pdf":
        return await _import_statement(
            session,
            profile_id,
            record,
            account_name=account_name,
            resolve_model=resolve_model,
            model_settings=model_settings,
            report=report,
        )
    if record.kind == "image":
        return await _import_bill(
            session,
            profile_id,
            conversation_id,
            record,
            resolve_model=resolve_model,
            model_settings=model_settings,
            report=report,
        )
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
            "mapping": proposal.mapping.model_dump(),
            # What the sub-agent said about the layout, for the tool step. Named so it cannot be
            # read as a field of the card: it used to be `note`, the card's own field name, and
            # a title and a `note` are exactly what the model built its own button-less card
            # from (e2e of 2026-09-05, B2).
            "mapping_note": proposal.note,
            # The whole question, already written, `options` and all.
            "card": card.model_dump(mode="json"),
            "instruction": (
                "Pass the fields of this `card` to `ask_user` unchanged, including its "
                "`options`: they are the two buttons the user answers with, and a card without "
                "them cannot be answered at all. Then, if the user answers "
                f"{CONFIRM!r}, call `import_file` again for this file with confirmed=true. "
                "If they answer anything else, import nothing and offer to read the file again with "
                "the columns they name."
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
    return await _imported(
        session,
        profile_id,
        committed,
        account,
        resolve_model=resolve_model,
        model_settings=model_settings,
        report=report,
    )


async def _imported(
    session: Session,
    profile_id: str,
    committed: Import,
    account: str,
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None,
    report: Reporter | Callable[..., Awaitable[None]],
) -> dict[str, Any]:
    """Categorize what an import brought in and say what came of it.

    The tail of every import, whatever reader produced the rows: a CSV, a statement PDF the
    guards passed, and the accepted rows of a review card all end here, so the assistant is
    handed the same figures and the same `questions` in every case.
    """
    await report(
        "imported",
        f"Imported {committed.imported_count} bookings into {account}",
        imported=committed.imported_count,
        duplicates=committed.duplicate_count,
    )

    held = duplicates.tally(session, profile_id, import_id=committed.id)
    if held.pending:
        await report(
            "duplicates",
            f"{held.pending} bookings look like ones this profile already has",
            duplicates=held.pending,
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

    # One card at a time, and the duplicates come first: a booking nobody has decided about is
    # not in the data yet, so asking which category it belongs to would be asking too early.
    # The merchants are picked up afterwards with `review_batch`, which costs a model call this
    # would otherwise spend here.
    #
    # The card counts the profile rather than this import, the same as `review_duplicates` and
    # for the same reason: its group row is answered profile-wide, so a number on it that meant
    # something narrower would be a lie.
    review = duplicates.review(session, profile_id) if held.pending else None
    questions, merchants_pending = (
        ([], 0)
        if review
        else await pending_questions(
            session,
            profile_id,
            resolve_model=resolve_model,
            model_settings=model_settings,
            limit=QUESTIONS_PER_CARD,
        )
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
            "exact_duplicates": held.exact,
            "near_duplicates": held.near,
            "duplicate_card": review["card"] if review else None,
            # The same shape `review_batch` returns, so the assistant asks about them the way it
            # asks in a review conversation: one ready card, written here.
            "pending_merchants": merchants_pending,
            "questions": [question.payload() for question in questions],
            "card": review_card(questions, merchants_pending).model_dump(mode="json") if questions else None,
        }
    )
    if committed.reconciliation:
        payload["reconciliation"] = committed.reconciliation
    if review:
        payload["instruction"] = (
            "Say the `summary`, then show `duplicate_card` with `ask_user`, unchanged. The "
            "answers are applied for you; after each one call `review_duplicates` for the next "
            "card until nothing is pending, and only then ask about the merchants with "
            "`review_batch`."
        )
    return payload


async def _import_statement(
    session: Session,
    profile_id: str,
    record: Attachment,
    *,
    account_name: str | None,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None,
    report: Reporter | Callable[..., Awaitable[None]],
) -> dict[str, Any]:
    """A statement PDF: read it, check it, and import it only if nothing needs a decision.

    The extraction is stored on the attachment before anything else happens, exactly as a
    proposed CSV mapping is: the review card is answered in a later request, and what gets
    committed then has to be the rows the user was shown rather than a second, differently
    hallucinated reading of the same file.
    """
    if record.extraction_json:
        extraction = Extraction.model_validate_json(record.extraction_json)
    else:
        try:
            extraction = await extract_statement(
                record.data,
                file_name=record.file_name,
                kind=record.kind,
                resolve_model=resolve_model,
                model_settings=model_settings,
                report=report,
            )
        except PdfUnreadable as exc:
            return {"status": "unreadable", "file": record.file_name, "error": str(exc)}
        except ProviderNotAvailable as exc:
            return {"status": "mapping_failed", "file": record.file_name, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - a failed extraction is a message, not a crash
            return {
                "status": "extraction_failed",
                "file": record.file_name,
                "error": f"The statement could not be read: {exc}",
            }

    if not extraction.rows:
        return {
            "status": "nothing_found",
            "file": record.file_name,
            "error": extraction.note
            or "No booking could be read out of this file. It may not be a bank statement.",
            "problems": extraction.errors,
        }

    extraction.account_name = (account_name or "").strip() or extraction.account_name
    record.extraction_json = extraction.model_dump_json()
    session.commit()
    read = {
        "file": record.file_name,
        "layout": extraction.layout_label,
        "pages": extraction.pages,
        "scanned_pages": len(extraction.scanned_pages),
        "rows_read": len(extraction.rows),
        "flagged": len(extraction.flagged),
        "reconciliation": extraction.reconciliation.line,
        "reconciled": extraction.reconciliation.status,
        "account": extraction.account_name,
    }

    if extraction.needs_review:
        return {
            **read,
            "status": "extraction_review",
            "card": extraction_review_card(extraction).model_dump(mode="json"),
            "instruction": (
                "Nothing has been imported yet. Show this `card` with `ask_user`, unchanged: the "
                "bookings the user accepts on it are imported by the server, together with the "
                "ones both guards already passed, and the card comes back with an `applied` line "
                "saying what happened."
            ),
        }

    committed = commit_extraction(
        session,
        profile_id,
        rows=extraction.clean,
        file_name=extraction.file_name,
        kind=extraction.kind,
        layout=extraction.layout,
        account_name=extraction.account_name,
        reconciliation=extraction.reconciliation,
    )
    record.import_id = committed.id
    record.account_name = extraction.account_name
    session.commit()
    payload = await _imported(
        session,
        profile_id,
        committed,
        extraction.account_name,
        resolve_model=resolve_model,
        model_settings=model_settings,
        report=report,
    )
    return {**read, **payload}


async def _import_bill(
    session: Session,
    profile_id: str,
    conversation_id: str,
    record: Attachment,
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None,
    report: Reporter | Callable[..., Awaitable[None]],
) -> dict[str, Any]:
    """A photo of a receipt: a split of the booking it matches, or a preview of a new one."""
    await report("read", f"Reading {record.file_name} as a receipt")
    try:
        extraction = await read_bill_image(
            record.data,
            today=date.today(),
            resolve_model=resolve_model,
            model_settings=model_settings,
        )
    except PdfUnreadable as exc:
        return {"status": "unreadable", "file": record.file_name, "error": str(exc)}
    except ProviderNotAvailable as exc:
        return {"status": "mapping_failed", "file": record.file_name, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a failed extraction is a message, not a crash
        return {"status": "extraction_failed", "file": record.file_name, "error": f"The photo could not be read: {exc}"}
    if extraction is None:
        return {
            "status": "nothing_found",
            "file": record.file_name,
            "error": (
                "No total and no line item could be read from that photo. Attach a photo of the "
                "receipt itself, or type the booking and I will add it."
            ),
        }
    await report(
        "checking",
        extraction.line,
        items=len(extraction.items),
        total_cents=extraction.total_cents,
    )
    return await bill_outcome(
        session,
        profile_id,
        conversation_id,
        extraction,
        file_name=record.file_name,
        resolve_model=resolve_model,
        model_settings=model_settings,
    )
