"""Import endpoints: read a CSV, extract a PDF or a photo, commit, categorize, and list what
an import came to.

Importing is a chat job (`import_file` and the Question cards it leads to); the Import page is
an overview of what those runs produced, with a delete per import and a way back into the
conversation that is still asking about one. `preview` and `create` stay because they are the
same pipeline behind an HTTP door, which is what the tests and `scripts/` drive.

The preview holds no server-side state. The caller keeps the file and posts it again with the
mapping it wants, so editing the mapping is just another preview call and a commit never
depends on an earlier upload still being around.

A PDF or a photo is read in two calls instead of one, because reading it costs a model call per
page and must not happen twice: `POST /imports/extract` returns the rows with the verdict of
both guards on each of them, and `POST /imports/extracted` commits the rows it is sent back.
That second endpoint recomputes the reconciliation itself over exactly those rows, so the line
on the Import record is always what the server worked out and never what a client claimed.

`review-conversation` seeds a conversation whose first turn summarizes the import and asks the
first Question card: the bookings it held aside as possible duplicates, or, when there are
none, the merchants categorization was unsure about. Every figure in that seeded turn is
counted here in code, never written by a model.

A commit inserts nothing it may already have: those rows are held aside as duplicate candidates
(see `finquery.ingest.duplicates`), and the two `duplicates` endpoints list them and apply Keep
both or Remove. The chat asks the same question on a Question card and applies it through the
same function.
"""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finquery.api.chat import persist_turn
from finquery.api.profiles import get_profile_or_404
from finquery.ask_user import ASK_USER, AskUser
from finquery.attachments import kind_of
from finquery.categorize import categorize_import, pending_questions, review_card
from finquery.db import Account, Attachment, Conversation, DuplicateCandidate, Import, Transaction
from finquery.extract.guards import ExtractedRow, Reconciliation, reconcile
from finquery.extract.pdf import PdfUnreadable
from finquery.extract.statement import Extraction, commit_extraction, extract_statement
from finquery.ingest import duplicates
from finquery.ingest.commit import commit_rows, import_summary
from finquery.ingest.csv_reader import (
    CsvUnreadable,
    Mapping,
    Parsed,
    Sniffed,
    detect_preset,
    mapping_for,
    parse,
    sniff,
)
from finquery.ingest.mapping_agent import MappingUnusable, propose
from finquery.providers import ModelSlot, ProviderNotAvailable
from finquery.weblookup import Lookups, lookups_for

router = APIRouter()

PREVIEW_ROWS = 8
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
DUPLICATE_PAGE = 25
"""Duplicate candidates the page asks about at once. A re-imported statement can hold hundreds,
and the shortcut is there for exactly that; this keeps the list readable."""

MappingSource = Literal["preset", "model", "user"]

REVIEW_PROMPT = "Categorize the import I just did."
DUPLICATE_PROMPT = "Decide the bookings this import held aside as possible duplicates."


class PreviewRow(BaseModel):
    booked_on: date
    amount_cents: int
    description: str
    counterparty: str | None


class PreviewOut(BaseModel):
    file_name: str
    encoding: str
    delimiter: str
    header: list[str]
    row_count: int
    preset: str | None
    preset_label: str | None
    mapping: Mapping
    account_name: str
    note: str
    mapping_source: MappingSource
    rows: list[PreviewRow]
    issues: list[str]


class ImportOut(BaseModel):
    """One row of the Import page, which is an overview and nothing else.

    `needs_review` and `conversation_id` are what makes a row actionable: how many of its
    bookings still have no category, and the conversation the file was dropped into, which is
    where anything undecided about it is decided.
    """

    id: str
    file_name: str
    kind: str
    preset: str | None
    account_name: str
    row_count: int
    imported_count: int
    duplicate_count: int
    duplicates_kept: int
    duplicates_removed: int
    skipped_count: int
    reconciliation: str | None
    needs_review: int = 0
    conversation_id: str | None = None
    running: bool = False
    """Whether the chat this file was dropped into is still working on it.

    An import is a chat turn: the rows are committed within seconds and the categorization that
    follows takes minutes, so the counts on this row are still moving. The turn survives a
    closed tab (ticket 33), which is exactly why the page has to say so rather than look
    finished."""
    created_at: datetime


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty, so there is nothing to import.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail="The file is larger than 20 MB. Export a shorter date range and try again."
        )
    return data


def _sniff_or_422(data: bytes) -> Sniffed:
    try:
        return sniff(data)
    except CsvUnreadable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _parse_or_422(sniffed: Sniffed, mapping: Mapping, *, limit: int | None = None) -> Parsed:
    try:
        return parse(sniffed, mapping, limit=limit)
    except CsvUnreadable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _mapping_or_422(raw: str) -> Mapping:
    try:
        return Mapping.model_validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=f"The mapping is not usable: {exc.errors()[0]['msg']}") from exc


async def _propose_mapping(request: Request, sniffed: Sniffed, file_name: str) -> tuple[Mapping, str, str]:
    """Ask the fast slot for a mapping. Only reached when no preset recognizes the header.

    The proposal itself is `mapping_agent.propose`, which the `import_file` chat tool calls too;
    this is only its HTTP shape.
    """
    state = request.app.state
    try:
        model = state.resolve_model("fast")
    except ProviderNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        proposal = await propose(sniffed, file_name, model=model, model_settings=state.subagent_settings)
    except MappingUnusable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - any model or transport failure is one message here
        raise HTTPException(status_code=502, detail=f"The model could not propose a mapping: {exc}") from exc
    return proposal.mapping, proposal.account_name, proposal.note


@router.post("/imports/preview", response_model=PreviewOut)
async def preview_import(
    request: Request,
    file: UploadFile = File(...),
    mapping: str | None = Form(default=None),
    account_name: str | None = Form(default=None),
) -> PreviewOut:
    """Sniff the upload and parse its first rows. Pass `mapping` to preview an edited mapping."""
    data = await _read(file)
    file_name = file.filename or "upload.csv"
    sniffed = _sniff_or_422(data)
    preset = detect_preset(sniffed.header)

    if mapping is not None:
        active = _mapping_or_422(mapping)
        source: MappingSource = "user"
        note = "Mapping edited by you."
        suggested = preset.account_name if preset else "Imported account"
    elif preset is not None:
        active = mapping_for(preset, sniffed.header)
        source = "preset"
        note = f"Recognized as a {preset.label} export from its column headers."
        suggested = preset.account_name
    else:
        active, suggested, note = await _propose_mapping(request, sniffed, file_name)
        source = "model"

    parsed = _parse_or_422(sniffed, active, limit=PREVIEW_ROWS)
    return PreviewOut(
        file_name=file_name,
        encoding=sniffed.encoding,
        delimiter=sniffed.delimiter,
        header=sniffed.header,
        row_count=len(sniffed.rows),
        preset=preset.name if preset else None,
        preset_label=preset.label if preset else None,
        mapping=active,
        account_name=account_name or suggested,
        note=note,
        mapping_source=source,
        rows=[PreviewRow(**vars(row)) for row in parsed.rows],
        issues=parsed.issues,
    )


@router.post("/imports", response_model=ImportOut, status_code=201)
async def create_import(
    request: Request,
    profile_id: str = Form(...),
    file: UploadFile = File(...),
    mapping: str = Form(...),
    account_name: str = Form(...),
) -> ImportOut:
    data = await _read(file)
    sniffed = _sniff_or_422(data)
    active = _mapping_or_422(mapping)
    parsed = _parse_or_422(sniffed, active)
    if not parsed.rows:
        raise HTTPException(status_code=422, detail="No row in the file could be read with this mapping.")

    # The record names a bank only when the committed mapping is still that bank's preset.
    detected = detect_preset(sniffed.header)
    preset = detected if detected and mapping_for(detected, sniffed.header) == active else None
    account = account_name.strip() or "Imported account"
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        record = commit_rows(
            session,
            profile_id,
            rows=parsed.rows,
            mapping=active,
            account_name=account,
            file_name=file.filename or "upload.csv",
            preset=preset.name if preset else None,
            skipped_count=len(parsed.issues),
        )
        return _out(record, account)


def _out(
    record: Import,
    account_name: str,
    *,
    needs_review: int = 0,
    conversation_id: str | None = None,
    running: bool = False,
) -> ImportOut:
    return ImportOut(
        id=record.id,
        file_name=record.file_name,
        kind=record.kind,
        preset=record.preset,
        account_name=account_name,
        row_count=record.row_count,
        imported_count=record.imported_count,
        duplicate_count=record.duplicate_count,
        duplicates_kept=record.duplicates_kept,
        duplicates_removed=record.duplicates_removed,
        skipped_count=record.skipped_count,
        reconciliation=record.reconciliation,
        needs_review=needs_review,
        conversation_id=conversation_id,
        running=running,
        created_at=record.created_at,
    )


# Statement PDFs and photos. Two calls, because the extraction is the expensive half.


class ProfileBody(BaseModel):
    """Writes carry the profile in the body; nothing is implicitly profile scoped."""

    profile_id: str


class ExtractionOut(BaseModel):
    """What the extraction sub-agent and the guards made of one file. Nothing is written yet."""

    file_name: str
    kind: str
    layout: str
    layout_label: str
    account_name: str
    pages: int
    scanned_pages: list[int]
    rows: list[ExtractedRow]
    reconciliation: Reconciliation
    flagged: int
    note: str | None
    errors: list[str]


class ExtractedRowIn(BaseModel):
    """One row the page sends back to be committed, as it stood after the review."""

    booked_on: date
    amount_cents: int
    description: str
    counterparty: str | None = None
    balance_cents: int | None = None
    page: int = 1
    line: int | None = None


class ExtractedImportIn(ProfileBody):
    file_name: str
    kind: Literal["pdf", "image"]
    layout: str = "unknown"
    account_name: str
    rows: list[ExtractedRowIn]
    dropped: int = 0
    """Rows the user dropped in the review, counted into the record's skipped rows."""


@router.post("/imports/extract", response_model=ExtractionOut)
async def extract_upload(request: Request, file: UploadFile = File(...)) -> ExtractionOut:
    """Read a statement PDF or a photo into rows the page can review. Writes nothing."""
    data = await _read(file)
    file_name = file.filename or "upload.pdf"
    kind = kind_of(file_name, file.content_type or "")
    if kind not in ("pdf", "image"):
        raise HTTPException(status_code=422, detail="This endpoint reads PDFs and images. A CSV goes to /imports/preview.")
    state = request.app.state
    try:
        state.resolve_model("fast")
    except ProviderNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        extraction = await extract_statement(
            data,
            file_name=file_name,
            kind=kind,
            resolve_model=state.resolve_model,
            model_settings=state.subagent_settings,
        )
    except PdfUnreadable as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not extraction.rows:
        # A page that failed says why (a local run out of context, a transport error): that is a
        # different problem from a file that is not a statement, and the user has to be told which.
        raise HTTPException(
            status_code=422,
            detail=extraction.note
            or (extraction.errors[0] if extraction.errors else None)
            or "No booking could be read out of this file. It may not be a bank statement.",
        )
    if _reads_as_a_receipt(extraction):
        raise HTTPException(status_code=422, detail=NOT_A_STATEMENT)
    return _extraction_out(extraction)


NOT_A_STATEMENT = (
    "This looks like a till receipt rather than a page of a bank statement: nothing on it could "
    "be checked against a balance. Drop a receipt into a chat instead, where it is read as a "
    "receipt and becomes a booking or a split."
)


def _reads_as_a_receipt(extraction: Extraction) -> bool:
    """Whether a photo read as a statement page is really a receipt.

    The reader says so itself on most receipts and then there are no rows at all, but twice in
    twenty it wrote the articles out as bookings (`Rucolasauce -0,99`), which this door would
    have handed on as a statement. A page of a statement carries the account's running balance,
    and that is what makes its figures checkable at all (ADR 0011); a photo with no balance
    anywhere, nothing that reconciles and not one row either guard could verify is not one.

    A photo of a statement page that prints no balances is refused by this too. That is the case
    the ADR calls "no proof there is", and the honest answer to it is the sentence above rather
    than a table of figures nothing checked.
    """
    if extraction.kind != "image":
        return False
    if any(row.balance_cents is not None for row in extraction.rows):
        return False
    return extraction.reconciliation.status != "ok" and all(row.flagged for row in extraction.rows)


def _extraction_out(extraction: Extraction) -> ExtractionOut:
    return ExtractionOut(
        file_name=extraction.file_name,
        kind=extraction.kind,
        layout=extraction.layout,
        layout_label=extraction.layout_label,
        account_name=extraction.account_name,
        pages=extraction.pages,
        scanned_pages=extraction.scanned_pages,
        rows=extraction.rows,
        reconciliation=extraction.reconciliation,
        flagged=len(extraction.flagged),
        note=extraction.note,
        errors=extraction.errors,
    )


@router.post("/imports/extracted", response_model=ImportOut, status_code=201)
async def create_extracted_import(request: Request, body: ExtractedImportIn) -> ImportOut:
    """Commit the rows the user accepted in the review of an extraction.

    The reconciliation is worked out here, over exactly these rows: a row the user dropped
    leaves a hole in the running balance, and the record says so rather than claiming the
    import added up.
    """
    if not body.rows:
        raise HTTPException(status_code=422, detail="No row was accepted, so there is nothing to import.")
    rows = [ExtractedRow(**row.model_dump()) for row in body.rows]
    # On a copy, so the verdict cannot change an amount the user has already seen and accepted.
    verdict = reconcile([row.model_copy() for row in rows])
    account = body.account_name.strip() or "Imported account"
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, body.profile_id)
        record = commit_extraction(
            session,
            body.profile_id,
            rows=rows,
            file_name=body.file_name,
            kind=body.kind,
            layout=body.layout,
            account_name=account,
            reconciliation=verdict,
            dropped=body.dropped,
        )
        return _out(record, account)


def _import_or_404(session: Session, profile_id: str, import_id: str) -> Import:
    get_profile_or_404(session, profile_id)
    record = session.get(Import, import_id)
    if record is None or record.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Import not found")
    return record


@router.get("/imports", response_model=list[ImportOut])
async def list_imports(request: Request, profile_id: str) -> list[ImportOut]:
    """Every import of the profile, with what is still open about it.

    The conversation is the one the file was dropped into: an attachment is what links a chat
    import to its transcript, so the page can send the user back to the card that is waiting.
    """
    needs_review = (
        select(func.count(Transaction.id))
        .where(Transaction.import_id == Import.id, Transaction.category_id.is_(None))
        .correlate(Import)
        .scalar_subquery()
    )
    came_from = (
        select(Attachment.conversation_id)
        .where(Attachment.import_id == Import.id)
        .correlate(Import)
        .limit(1)
        .scalar_subquery()
    )
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        rows = session.execute(
            select(Import, Account.name, needs_review, came_from)
            .join(Account, Account.id == Import.account_id)
            .where(Import.profile_id == profile_id)
            .order_by(Import.created_at.desc())
        ).all()
        running = request.app.state.running_turns
        return [
            _out(
                record,
                account_name,
                needs_review=review,
                conversation_id=conversation_id,
                running=conversation_id in running,
            )
            for record, account_name, review, conversation_id in rows
        ]


class DeletedOut(BaseModel):
    """What undoing one import took with it."""

    transactions: int
    candidates: int


@router.delete("/imports/{import_id}", response_model=DeletedOut)
async def delete_import(request: Request, import_id: str, profile_id: str) -> DeletedOut:
    """Undo one import: the record, its bookings, and its candidates with the decisions on them.

    There is no other way back from an import into the wrong profile, and a booking whose import
    record is gone is a booking nobody can account for, so the two go together. The bookings of
    other imports stay, including the ones a duplicate candidate of this import matched: those
    were in the profile before it. A booking a Keep both inserted belongs to this import and goes.
    """
    with request.app.state.session_factory() as session:
        record = _import_or_404(session, profile_id, import_id)
        rows = session.scalars(
            select(Transaction).where(
                Transaction.profile_id == profile_id, Transaction.import_id == import_id
            )
        ).all()
        # A split child is imported with its parent, and the foreign key takes it along, so
        # deleting one explicitly would be a second delete of a row that is already gone.
        doomed = {row.id for row in rows}
        for row in rows:
            if row.parent_id not in doomed:
                session.delete(row)
        candidates = session.scalars(
            select(DuplicateCandidate).where(DuplicateCandidate.import_id == import_id)
        ).all()
        for candidate in candidates:
            session.delete(candidate)
        session.delete(record)
        session.commit()
        return DeletedOut(transactions=len(rows), candidates=len(candidates))


# Categorization of an import, and the conversation that asks about what is left.


class ReviewBody(ProfileBody):
    model_slot: ModelSlot = "fast"


class QuestionOut(BaseModel):
    pattern: str
    label: str
    description: str
    date: date
    amount_cents: int
    bookings: int
    options: list[str]
    guess: str | None
    confidence: float | None


class CategorizeOut(BaseModel):
    """What the stages did, and the merchants a human still has to place."""

    import_id: str
    rows: int
    by_rule: int
    by_dictionary: int
    by_lookup: int
    by_model: int
    needs_review: int
    merchants: int
    model_calls: int
    lookups: int
    lookups_refused: int
    uncertain: list[QuestionOut]
    error: str | None


class ReviewConversationOut(BaseModel):
    conversation_id: str
    title: str
    questions: int
    pending_merchants: int


def _lookups(request: Request, profile_id: str) -> Lookups | None:
    """The web lookup stage for this profile, or None when it has web lookup switched off."""
    state = request.app.state
    return lookups_for(
        state.session_factory,
        profile_id,
        client=state.web_client,
        resolve_model=state.resolve_model,
        model_settings=state.subagent_settings,
    )


# The duplicate candidates one import held aside, and the user's decision about them.


class DuplicateOut(BaseModel):
    """One booking that was not inserted, next to the one it looks like."""

    ref: str
    kind: Literal["exact", "near"]
    booked_on: date
    amount_cents: int
    description: str
    counterparty: str | None
    existing_id: str | None
    existing_booked_on: date | None
    existing_description: str | None


class DuplicatesOut(BaseModel):
    import_id: str
    file_name: str
    account_name: str
    found: int
    pending: int
    exact: int
    near: int
    kept: int
    removed: int
    shortcut: bool
    """Whether removing every exact duplicate at once is worth offering: a re-imported file."""
    candidates: list[DuplicateOut]


class DuplicateDecision(BaseModel):
    ref: str
    decision: Literal["keep", "remove"]


class DecideBody(ProfileBody):
    decisions: list[DuplicateDecision] = []
    remove_all_exact: bool = False
    """The card's shortcut: every exact candidate of this import, removed in one answer."""


class DecidedOut(BaseModel):
    kept: int
    removed: int
    remaining: int
    needs_review: int
    summary: str
    error: str | None


@router.get("/imports/{import_id}/duplicates", response_model=DuplicatesOut)
async def list_duplicates(request: Request, import_id: str, profile_id: str) -> DuplicatesOut:
    """The candidates this import is still waiting on, a page at a time, with the counts."""
    with request.app.state.session_factory() as session:
        record = _import_or_404(session, profile_id, import_id)
        counts = duplicates.tally(session, profile_id, import_id=import_id)
        batch = duplicates.pending(session, profile_id, import_id=import_id, limit=DUPLICATE_PAGE)
        account = session.get(Account, record.account_id)
        return DuplicatesOut(
            import_id=import_id,
            file_name=record.file_name,
            account_name=account.name if account else "the account",
            **counts.payload(),
            candidates=[DuplicateOut(**duplicates.payload(candidate)) for candidate in batch],
        )


@router.post("/imports/{import_id}/duplicates", response_model=DecidedOut)
async def decide_duplicates(request: Request, import_id: str, body: DecideBody) -> DecidedOut:
    """Apply what the user decided: keep both inserts the booking, remove leaves the data alone.

    The same function the chat's Question card answers go through, so a decision means the same
    thing whichever screen it was made on. A kept booking is inserted from the candidate's own
    columns and categorized right away.
    """
    state = request.app.state
    with state.session_factory() as session:
        record = _import_or_404(session, body.profile_id, import_id)
        decided = await duplicates.apply_decisions(
            session,
            body.profile_id,
            {item.ref: item.decision for item in body.decisions},
            remove_all_exact=body.remove_all_exact,
            import_id=import_id,
            resolve_model=state.resolve_model,
            model_settings=state.subagent_settings,
        )
        account = session.get(Account, record.account_id)
        return DecidedOut(
            kept=decided.kept,
            removed=decided.removed,
            remaining=duplicates.tally(session, body.profile_id, import_id=import_id).pending,
            needs_review=decided.needs_review,
            summary=import_summary(session, record, account.name if account else "the account"),
            error=decided.error,
        )


@router.post("/imports/{import_id}/categorize", response_model=CategorizeOut)
async def categorize(request: Request, import_id: str, body: ProfileBody) -> CategorizeOut:
    """Run the stages over what this import brought in.

    Called right after a commit. Rules first, then the merchant dictionary, then the web lookup
    when this profile switched it on, then the categorizer sub-agent on the fast slot; rows below
    the confidence threshold stay Needs review and come back here as `uncertain`.
    """
    state = request.app.state
    with state.session_factory() as session:
        _import_or_404(session, body.profile_id, import_id)
        report = await categorize_import(
            session,
            body.profile_id,
            import_id,
            resolve_model=state.resolve_model,
            model_settings=state.subagent_settings,
            lookups=_lookups(request, body.profile_id),
        )
    return CategorizeOut(
        import_id=import_id,
        rows=report.rows,
        by_rule=report.by_rule,
        by_dictionary=report.by_dictionary,
        by_lookup=report.by_lookup,
        by_model=report.by_model,
        needs_review=report.needs_review,
        merchants=report.merchants,
        model_calls=report.model_calls,
        lookups=report.lookups,
        lookups_refused=report.lookups_refused,
        uncertain=[QuestionOut(**vars(question)) for question in report.questions],
        error=report.error,
    )


@router.post("/imports/{import_id}/review-conversation", response_model=ReviewConversationOut, status_code=201)
async def review_conversation(request: Request, import_id: str, body: ReviewBody) -> ReviewConversationOut:
    """Open the conversation that asks about whatever this import left undecided.

    The first turn is seeded, not generated: the user's request, the assistant's summary of the
    import and a pending `ask_user` call holding the first Question card. Answering the card
    resumes that same run, which is what the chat endpoint's deferred-result path is for.

    Which card it is depends on what is open. Bookings held aside as possible duplicates come
    first, because a booking nobody has decided about is not in the data yet and there is
    nothing to categorize about it; otherwise it is the merchants categorization was unsure
    about. This is how the Import page's "Continue in chat" reaches an import that was committed
    outside a conversation, so nothing an older import left open is stranded.
    """
    state = request.app.state
    with state.session_factory() as session:
        record = _import_or_404(session, body.profile_id, import_id)
        account = session.get(Account, record.account_id)
        account_name = account.name if account else "the account"
        waiting = duplicates.tally(session, body.profile_id, import_id=import_id).pending
        pending = 0
        if waiting:
            batch = duplicates.review(session, body.profile_id, import_id=import_id)
            card = AskUser.model_validate(batch["card"])
            prompt = DUPLICATE_PROMPT
        else:
            questions, pending = await pending_questions(
                session,
                body.profile_id,
                resolve_model=state.resolve_model,
                model_settings=state.subagent_settings,
                lookups=_lookups(request, body.profile_id),
            )
            if not questions:
                raise HTTPException(status_code=409, detail="Nothing is left to review in this profile.")
            card = review_card(questions, pending)
            prompt = REVIEW_PROMPT
        title = f"Review {record.file_name}"[:120]
        conversation = Conversation(profile_id=body.profile_id, model_slot=body.model_slot, title=title)
        session.add(conversation)
        summary = import_summary(session, record, account_name)
        session.commit()
        conversation_id = conversation.id

    persist_turn(
        state.session_factory,
        conversation_id,
        [
            ModelRequest(parts=[UserPromptPart(content=prompt)]),
            ModelResponse(
                parts=[
                    TextPart(content=summary),
                    ToolCallPart(tool_name=ASK_USER, args=card.model_dump(mode="json")),
                ]
            ),
        ],
        slot=body.model_slot,
        metadata={"model_slot": body.model_slot},
    )
    return ReviewConversationOut(
        conversation_id=conversation_id,
        title=title,
        questions=len(card.rows),
        pending_merchants=pending,
    )
