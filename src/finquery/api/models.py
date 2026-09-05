"""Model status: what is on disk, how far a download got, and the sanity check.

`GET /api/models` is the progress endpoint the Settings page polls while files are coming down.
It answers on either provider so the page never has to special-case one.
"""


from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from finquery.providers import MODEL_SLOTS, OPENROUTER_LABELS, OPENROUTER_MODELS, ModelSlot

router = APIRouter()


class FileOut(BaseModel):
    kind: str
    filename: str
    size: int
    downloaded: int
    state: str
    source: str | None = None
    error: str | None = None


class SlotOut(BaseModel):
    slot: ModelSlot
    name: str
    label: str
    """The model's display name, which is what the selector and the turn chips show."""
    ready: bool
    loaded: bool
    load_seconds: float | None = None
    n_ctx: int | None = None
    files: list[FileOut] = []


class AdapterOut(BaseModel):
    name: str
    path: str
    present: bool


class ModelsOut(BaseModel):
    provider: str
    models: list[SlotOut]
    adapters: list[AdapterOut]
    downloading: bool


def _local_state(request: Request) -> ModelsOut:
    stack = request.app.state.local
    progress = stack.downloads.progress()
    return ModelsOut(
        provider="local",
        models=[
            SlotOut(
                slot=status.slot,
                name=status.name,
                label=status.label,
                ready=status.ready,
                loaded=status.loaded,
                load_seconds=status.load_seconds,
                n_ctx=status.n_ctx,
                files=[
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
                    if row.slot == status.slot
                ],
            )
            for status in stack.status()
        ],
        adapters=[AdapterOut(name=a.name, path=a.path, present=a.present) for a in stack.adapters.states()],
        downloading=stack.downloads.busy(),
    )


@router.get("/models", response_model=ModelsOut)
async def get_models(request: Request) -> ModelsOut:
    if request.app.state.local is not None:
        return _local_state(request)
    return ModelsOut(
        provider=request.app.state.settings.provider,
        models=[
            SlotOut(slot=slot, name=OPENROUTER_MODELS[slot], label=OPENROUTER_LABELS[slot], ready=True, loaded=True)
            for slot in MODEL_SLOTS
        ],
        adapters=[],
        downloading=False,
    )


def _require_local(request: Request):  # noqa: ANN201 - the stack type lives in finquery.local
    stack = request.app.state.local
    if stack is None:
        raise HTTPException(status_code=409, detail="Set FINQUERY_PROVIDER=local to manage local models.")
    return stack


@router.post("/models/download", response_model=ModelsOut)
async def download_models(request: Request) -> ModelsOut:
    """Start fetching every missing file. Returns immediately; poll `GET /api/models`."""
    _require_local(request).downloads.start()
    return _local_state(request)


@router.post("/models/check")
async def check_models(request: Request) -> dict[str, object]:
    """Run the sanity check on both slots. Loads the models, so this takes a while."""
    from finquery.local.check import report_json, run_check

    stack = _require_local(request)
    reports = await run_check(stack)
    return {"reports": report_json(reports), "ok": all(report.ok for report in reports)}
