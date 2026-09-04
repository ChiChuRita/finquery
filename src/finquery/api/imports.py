"""Import endpoints: preview a CSV upload, commit it, list past imports.

The preview holds no server-side state. The browser keeps the dropped file and posts it again
with the mapping it wants, so editing the mapping is just another preview call and a commit
never depends on an earlier upload still being around.
"""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import select

from finquery.api.profiles import get_profile_or_404
from finquery.db import Account, Import
from finquery.ingest.commit import commit_rows
from finquery.ingest.csv_reader import (
    CsvUnreadable,
    Mapping,
    Parsed,
    Sniffed,
    detect_preset,
    mapping_for,
    normalize,
    parse,
    sniff,
)
from finquery.ingest.mapping_agent import mapping_agent, mapping_prompt
from finquery.providers import ProviderNotAvailable

router = APIRouter()

PREVIEW_ROWS = 8
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

MappingSource = Literal["preset", "model", "user"]


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
    """Ask the fast slot for a mapping. Only reached when no preset recognizes the header."""
    try:
        model = request.app.state.resolve_model("fast")
    except ProviderNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        result = await mapping_agent.run(mapping_prompt(sniffed, file_name), model=model)
    except Exception as exc:  # noqa: BLE001 - any model or transport failure is one message here
        raise HTTPException(status_code=502, detail=f"The model could not propose a mapping: {exc}") from exc

    proposal = result.output
    known = {normalize(name): name for name in sniffed.header}
    columns = {
        name: value
        for name, value in proposal.mapping.model_dump().items()
        if name.endswith("_column") and value is not None
    }
    unknown = [value for value in columns.values() if normalize(value) not in known]
    if unknown:
        raise HTTPException(
            status_code=502,
            detail=f"The model proposed columns the file does not have: {', '.join(unknown)}.",
        )
    # Accept a mapping that only differs in case or punctuation from the real header.
    mapping = proposal.mapping.model_copy(update={name: known[normalize(value)] for name, value in columns.items()})
    return mapping, proposal.account_name, proposal.note


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
