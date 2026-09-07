"""The model catalog over HTTP: what the picker offers, and what is on disk.

`GET /api/models` is the one place the browser learns which models exist, so a selector, a turn
chip or the History can never name a model that is not listed. It answers with every catalog
entry across both providers (`finquery.catalog`), each with its availability and, for a local
one, the download progress the Settings card draws its bars from. The sub-agent fast slot of
each provider comes with it (locally that is the Gemma 4 E4B entry itself), and so does every
sub-agent role with the model its setting resolves to. At most one local entry comes back
`loaded`: the local provider keeps one GGUF in memory (ADR 0013, ticket 68 amendment).

The OpenRouter key is set and cleared here too (`PUT` and `DELETE /api/models/openrouter-key`):
the cloud entry needs one, and a machine whose `.env` has none should not need a restart to get
it. The key is applied in-process and written to the key file for the next start; the browser
only ever gets its last four characters back.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from finquery.catalog import Catalog, Entry
from finquery.settings import Provider, save_openrouter_key

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
    """It is the local model loaded right now, of which there is at most one. Always false for
    a hosted entry, which is not loaded anywhere."""
    swapping: bool = False
    """Memory is being handed to this model: drain the loaded one, unload it, load this one."""
    load_seconds: float | None = None
    n_ctx: int | None = None
    files: list[FileOut] = []


class AdapterOut(BaseModel):
    name: str
    path: str
    present: bool


class RoleOut(BaseModel):
    """One sub-agent role: what it is set to, and what that is right now."""

    role: str
    setting: str
    """`chat`, `fast`, or a catalog key pinning the role to one model."""
    key: str
    label: str
    """The model the role resolves to for a chat on `default_key`. A conversation on another
    entry moves every role set to `chat` or `fast` with it."""


class ModelsOut(BaseModel):
    provider: Provider
    """What `FINQUERY_PROVIDER` says, which decides the default entry and nothing else."""
    default_key: str
    entries: list[EntryOut]
    fast_slots: list[EntryOut]
    """The sub-agent slot of each provider. The local one is the Gemma 4 E4B entry, so its key
    is also in `entries`; the hosted one is never a chat choice."""
    roles: list[RoleOut]
    """Every sub-agent role with its setting, so the models card can say which model does what."""
    adapters: list[AdapterOut]
    downloading: bool
    openrouter_key_hint: str | None = None
    """The last four characters of the key the cloud entry answers with, or None without one.
    Enough to recognise a key, never enough to use it."""


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


def key_hint(key: str | None) -> str | None:
    return f"...{key[-4:]}" if key else None


def _catalog_out(request: Request) -> ModelsOut:
    catalog: Catalog = request.app.state.models
    stack = catalog.local
    return ModelsOut(
        openrouter_key_hint=key_hint(catalog.settings.openrouter_api_key),
        provider=catalog.settings.provider,
        default_key=catalog.default_key,
        entries=[_entry_out(catalog, entry) for entry in catalog.entries],
        fast_slots=[_entry_out(catalog, entry) for entry in catalog.fast_slots.values()],
        roles=[
            RoleOut(
                role=role,
                setting=catalog.settings.subagent_model(role),
                key=entry.key,
                label=entry.label,
            )
            for role, entry in catalog.role_targets(catalog.default_key).items()
        ],
        adapters=[AdapterOut(name=a.name, path=a.path, present=a.present) for a in stack.adapters.states()]
        if stack is not None
        else [],
        downloading=stack.downloads.busy() if stack is not None else False,
    )


@router.get("/models", response_model=ModelsOut)
async def get_models(request: Request) -> ModelsOut:
    return _catalog_out(request)


class KeyIn(BaseModel):
    key: str = Field(min_length=1)


@router.put("/models/openrouter-key", response_model=ModelsOut)
async def put_openrouter_key(request: Request, body: KeyIn) -> ModelsOut:
    """Take an OpenRouter key from Settings: live at once, and in the key file for next time."""
    catalog: Catalog = request.app.state.models
    key = body.key.strip()
    if not key:
        raise HTTPException(status_code=422, detail="The key is empty.")
    save_openrouter_key(catalog.settings.key_file, key)
    catalog.set_openrouter_key(key)
    return _catalog_out(request)


@router.delete("/models/openrouter-key", response_model=ModelsOut)
async def delete_openrouter_key(request: Request) -> ModelsOut:
    """Forget the key: the cloud entry reads as unavailable again, and the file line is emptied."""
    catalog: Catalog = request.app.state.models
    save_openrouter_key(catalog.settings.key_file, None)
    catalog.set_openrouter_key(None)
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
    """Run the sanity check on every local model that is on disk.

    Loads them one at a time, each in place of the last, so this takes a while.
    """
    from finquery.local.check import report_json, run_check

    stack = _require_local(request)
    reports = await run_check(stack)
    return {"reports": report_json(reports), "ok": all(report.ok for report in reports)}
