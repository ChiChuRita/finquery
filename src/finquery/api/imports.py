"""Import endpoints: preview a CSV upload, commit it, categorize it, hand it to a chat.

The preview holds no server-side state. The browser keeps the dropped file and posts it again
with the mapping it wants, so editing the mapping is just another preview call and a commit
never depends on an earlier upload still being around.

After a commit the page calls `categorize`, and if merchants are left over `review-conversation`,
which seeds a conversation whose first turn summarizes the import and asks the first Question
card. Every figure in that seeded turn is counted here in code, never written by a model.
"""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, UserPromptPart
from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.api.chat import persist_turn
from finquery.api.profiles import get_profile_or_404
from finquery.ask_user import ASK_USER
from finquery.categorize import categorize_import, pending_questions, review_card
from finquery.db import Account, Conversation, Import
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

router = APIRouter()

PREVIEW_ROWS = 8
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

MappingSource = Literal["preset", "model", "user"]

REVIEW_PROMPT = "Categorize the import I just did."


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
    id: str
    file_name: str
    kind: str
    preset: str | None
    account_name: str
    row_count: int
    imported_count: int
    duplicate_count: int
    skipped_count: int
    reconciliation: str | None
    created_at: datetime


async def _read(file: UploadFile) -> bytes:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 20 MB.")
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


def _out(record: Import, account_name: str) -> ImportOut:
    return ImportOut(
        id=record.id,
        file_name=record.file_name,
        kind=record.kind,
        preset=record.preset,
        account_name=account_name,
        row_count=record.row_count,
        imported_count=record.imported_count,
        duplicate_count=record.duplicate_count,
        skipped_count=record.skipped_count,
        reconciliation=record.reconciliation,
        created_at=record.created_at,
    )


@router.get("/imports", response_model=list[ImportOut])
async def list_imports(request: Request, profile_id: str) -> list[ImportOut]:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        rows = session.execute(
            select(Import, Account.name)
            .join(Account, Account.id == Import.account_id)
            .where(Import.profile_id == profile_id)
            .order_by(Import.created_at.desc())
        ).all()
        return [_out(record, account_name) for record, account_name in rows]


# Categorization of an import, and the conversation that asks about what is left.


class ProfileBody(BaseModel):
    """Writes carry the profile in the body; nothing is implicitly profile scoped."""

    profile_id: str


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
    """What the three stages did, and the merchants a human still has to place."""

    import_id: str
    rows: int
    by_rule: int
    by_dictionary: int
    by_model: int
    needs_review: int
    merchants: int
    model_calls: int
    uncertain: list[QuestionOut]
    error: str | None


class ReviewConversationOut(BaseModel):
    conversation_id: str
    title: str
    questions: int
    pending_merchants: int


def _import_or_404(session: Session, profile_id: str, import_id: str) -> Import:
    get_profile_or_404(session, profile_id)
    record = session.get(Import, import_id)
    if record is None or record.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="Import not found")
    return record


@router.post("/imports/{import_id}/categorize", response_model=CategorizeOut)
async def categorize(request: Request, import_id: str, body: ProfileBody) -> CategorizeOut:
    """Run the three stages over what this import brought in.

    Called by the Import page right after a commit. Rules first, then the merchant dictionary,
    then the categorizer sub-agent on the fast slot; rows below the confidence threshold stay
    Needs review and come back here as `uncertain`.
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
        )
    return CategorizeOut(
        import_id=import_id,
        rows=report.rows,
        by_rule=report.by_rule,
        by_dictionary=report.by_dictionary,
        by_model=report.by_model,
        needs_review=report.needs_review,
        merchants=report.merchants,
        model_calls=report.model_calls,
        uncertain=[QuestionOut(**vars(question)) for question in report.questions],
        error=report.error,
    )


@router.post("/imports/{import_id}/review-conversation", response_model=ReviewConversationOut, status_code=201)
async def review_conversation(request: Request, import_id: str, body: ReviewBody) -> ReviewConversationOut:
    """Open the conversation that asks about the rows categorization was unsure about.

    The first turn is seeded, not generated: the user's request, the assistant's summary of the
    import and a pending `ask_user` call holding the first Question card. Answering the card
    resumes that same run, which is what the chat endpoint's deferred-result path is for.
    """
    state = request.app.state
    with state.session_factory() as session:
        record = _import_or_404(session, body.profile_id, import_id)
        account = session.get(Account, record.account_id)
        account_name = account.name if account else "the account"
        questions, pending = await pending_questions(
            session,
            body.profile_id,
            resolve_model=state.resolve_model,
            model_settings=state.subagent_settings,
        )
        if not questions:
            raise HTTPException(status_code=409, detail="Nothing is left to review in this profile.")
        title = f"Review {record.file_name}"[:120]
        conversation = Conversation(profile_id=body.profile_id, model_slot=body.model_slot, title=title)
        session.add(conversation)
        summary = import_summary(session, record, account_name)
        session.commit()
        conversation_id = conversation.id

    card = review_card(questions, pending)
    persist_turn(
        state.session_factory,
        conversation_id,
        [
            ModelRequest(parts=[UserPromptPart(content=REVIEW_PROMPT)]),
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
        questions=len(questions),
        pending_merchants=pending,
    )
