"""The model catalog over HTTP: what the picker offers, and what is on disk.

`GET /api/models` is the one place the browser learns which models exist, so a selector, a turn
chip or the History can never name a model that is not listed. It answers with every catalog
entry across both providers (`finquery.catalog`), each with its availability and, for a local
one, the download progress the Settings card draws its bars from. The sub-agent fast slot of
each provider comes with it, because it is a model the app runs that nobody picks.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from finquery.catalog import Catalog, Entry
from finquery.settings import Provider

router = APIRouter()


class FileOut(BaseModel):
    kind: str
    filename: str
    size: int
    downloaded: int
    state: str
    source: str | None = None
    error: str | None = None


class EntryOut(BaseModel):
    key: str
    label: str
    """What the selector, the turn chips and the History call this model."""
    provider: Provider
    available: bool
    reason: str | None = None
    """Why it cannot answer: no API key, weights missing or still coming down."""
    ready: bool = True
    """Its weights are on disk. Always true for a hosted entry."""
    loaded: bool = False
    """It is the model in its seat right now. Always false for a hosted entry, which has none."""
    swapping: bool = False
    """The local seat is being handed to this model: drain, unload, load."""
    load_seconds: float | None = None
    n_ctx: int | None = None
    files: list[FileOut] = []


class AdapterOut(BaseModel):
    name: str
    path: str
    present: bool


class ModelsOut(BaseModel):
    provider: Provider
    """What `FINQUERY_PROVIDER` says, which decides the default entry and nothing else."""
    default_key: str
    entries: list[EntryOut]
    fast_slots: list[EntryOut]
    """The sub-agent slot of each provider. Never a chat choice, so never in `entries`."""
    adapters: list[AdapterOut]
    downloading: bool


def _entry_out(catalog: Catalog, entry: Entry) -> EntryOut:
    state = catalog.availability(entry)
    out = EntryOut(
        key=entry.key,
        label=entry.label,
        provider=entry.provider,
        available=state.available,
        reason=state.reason,
    )
    if entry.local is None or catalog.local is None:
        return out
    stack = catalog.local
    spec = entry.local
    progress = [row for row in stack.downloads.progress() if row.key == spec.key]
    status = next((s for s in stack.status() if s.key == spec.key), None)
    return out.model_copy(
        update={
            "ready": bool(status and status.ready),
            "loaded": bool(status and status.loaded),
            "swapping": stack.swapping == spec.key,
            "load_seconds": status.load_seconds if status else None,
            "n_ctx": status.n_ctx if status else None,
            "files": [
                FileOut(
                    kind=row.kind,
                    filename=row.filename,
                    size=row.size,
                    downloaded=row.downloaded,
                    state=row.state,
                    source=row.source,
                    error=row.error,
                )
                for row in progress
            ],
        }
    )


def _catalog_out(request: Request) -> ModelsOut:
    catalog: Catalog = request.app.state.models
    stack = catalog.local
    return ModelsOut(
        provider=catalog.settings.provider,
        default_key=catalog.default_key,
        entries=[_entry_out(catalog, entry) for entry in catalog.entries],
        fast_slots=[_entry_out(catalog, entry) for entry in catalog.fast_slots.values()],
        adapters=[AdapterOut(name=a.name, path=a.path, present=a.present) for a in stack.adapters.states()]
        if stack is not None
        else [],
        downloading=stack.downloads.busy() if stack is not None else False,
    )


@router.get("/models", response_model=ModelsOut)
async def get_models(request: Request) -> ModelsOut:
    return _catalog_out(request)


def _require_local(request: Request):  # noqa: ANN201 - the stack type lives in finquery.local
    stack = request.app.state.local
    if stack is None:
        raise HTTPException(status_code=409, detail="This process has no local provider.")
    return stack


@router.post("/models/download", response_model=ModelsOut)
async def download_models(request: Request) -> ModelsOut:
    """Start fetching every missing local file. Returns immediately; poll `GET /api/models`."""
    _require_local(request).downloads.start()
    return _catalog_out(request)


@router.post("/models/check")
async def check_models(request: Request) -> dict[str, object]:
    """Run the sanity check on the fast slot and every local chat model that is on disk.

    Loads them one seat at a time, so this takes a while.
    """
    from finquery.local.check import report_json, run_check

    stack = _require_local(request)
    reports = await run_check(stack)
    return {"reports": report_json(reports), "ok": all(report.ok for report in reports)}
