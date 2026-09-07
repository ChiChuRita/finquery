"""The loaded llama.cpp model and everything the local provider owns around it.

One GGUF is loaded at a time, at the configured context. Asking for another model swaps it:
drain the running one, unload it, load the new one, in that order and under one lock. Asking
for the model that is loaded costs nothing, which is the common case, because every sub-agent
role defaults to the chat entry.

A seat is still what a `ModelSpec` carries, and it says which model the `fast` role means and
where the adapters attach; it is not a second place in memory. The model is loaded on its first
use, not at startup, so the app can start (and show download progress) before any weights
exist. See docs/adr/0013-model-catalog-across-providers.md and its ticket 68 amendment.
"""

import asyncio
import contextvars
import ctypes
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic_ai.models import Model

from finquery.local.adapters import AdapterRegistry
from finquery.local.catalog import LOCAL_FAST, LOCAL_MODELS, AdapterName, ModelSpec
from finquery.local.downloads import DownloadManager
from finquery.providers import ModelRole, ProviderNotAvailable
from finquery.settings import Settings

#: True while the current asyncio task holds the model lock, so a sub-agent run nested inside
#: an attached adapter does not deadlock on itself.
_held: contextvars.ContextVar[bool] = contextvars.ContextVar("finquery_holding_model", default=False)

#: Set while a run is falling back to base weights, so the model can attach the note to the
#: response it produces without the sub-agent having to thread it through by hand.
_note: contextvars.ContextVar[str | None] = contextvars.ContextVar("finquery_adapter_note", default=None)

T = TypeVar("T")


def adapter_note() -> str | None:
    """The audit note for the run in progress, if it fell back to the base weights."""
    return _note.get()


@contextmanager
def audited(text: str | None) -> Iterator[None]:
    """Publish one audit note for the length of a run, so the model can put it on its response."""
    token = _note.set(text)
    try:
        yield
    finally:
        _note.reset(token)


class Slot(Protocol):
    """One loaded model. The only thing the Pydantic AI model needs, so a test can fake it."""

    name: str
    load_seconds: float

    def stream(self, **kwargs: Any) -> Iterator[dict[str, Any]]:
        """Run one chat completion, yielding OpenAI-shaped chat completion chunks."""
        ...

    def context_tokens(self) -> int:
        """Tokens in the context after the last completion (prompt plus generated)."""
        ...

    @property
    def model(self) -> Any:
        """The `llama_model *` an adapter is loaded against."""
        ...

    @property
    def ctx(self) -> Any:
        """The `llama_context *` an adapter is attached to."""
        ...

    def reset(self) -> None: ...

    def close(self) -> None:
        """Free the weights. Called when another model takes their place in memory."""
        ...


def _quiet_llama_cpp() -> None:
    """Drop llama.cpp's own logging. `verbose=False` does not reach the multimodal path,
    which otherwise prints every rendered prompt to the server's stderr."""
    import llama_cpp

    global _log_sink
    if _log_sink is None:
        _log_sink = llama_cpp.llama_log_callback(lambda level, text, user_data: None)
        llama_cpp.llama_log_set(_log_sink, ctypes.c_void_p(0))


_log_sink: Any = None


class LlamaSlot:
    """One GGUF loaded through llama-cpp-python with its multimodal projector."""

    def __init__(self, spec: ModelSpec, weights: Path, projector: Path, n_ctx: int) -> None:
        import llama_cpp
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import MTMDChatHandler

        _quiet_llama_cpp()
        self.name = weights.stem
        started = time.monotonic()
        # `guess_chat_format_from_gguf_metadata` returns None for both of these, so the handler
        # is chosen here rather than sniffed. One handler covers both: it reads the chat
        # template out of the GGUF metadata itself, and `Gemma4ChatHandler` is an empty
        # subclass of it. What differs per model is the wire format (`finquery.local.wire`).
        self._handler = MTMDChatHandler(clip_model_path=str(projector), verbose=False)
        self._llama = Llama(
            model_path=str(weights),
            n_ctx=n_ctx,
            n_gpu_layers=-1,
            # Flash attention plus a q8_0 KV cache is what keeps 32k of context cheap inside
            # the Metal working set of a 24 GB Mac. Measured numbers are in
            # docs/adr/0006-local-gemma-4-through-llama-cpp.md.
            flash_attn=True,
            type_k=llama_cpp.GGML_TYPE_Q8_0,
            type_v=llama_cpp.GGML_TYPE_Q8_0,
            verbose=False,
        )
        self.load_seconds = round(time.monotonic() - started, 2)
        self.spec = spec
        self.n_ctx = n_ctx

    def stream(self, **kwargs: Any) -> Iterator[dict[str, Any]]:
        from llama_cpp._utils import suppress_stdout_stderr

        # The handler is called directly rather than through `create_chat_completion`, which has
        # no `**kwargs` and so cannot pass `enable_thinking` down to the chat template.
        # The prompt is rendered and evaluated inside this call, and llama.cpp's multimodal code
        # prints the whole rendered prompt to stderr while doing it, which `verbose=False` does
        # not reach. The redirect covers only that window, not the token loop.
        # TODO: global fd redirect, so a log line written by another task during this window is
        # lost; per-slot generation is serialized and this is a local single-user app, but a
        # proper fix is a `verbosity` field on mtmd_context_params upstream.
        with suppress_stdout_stderr(disable=False):
            chunks = self._handler(llama=self._llama, stream=True, **kwargs)  # type: ignore[arg-type]
        return iter(chunks)

    def context_tokens(self) -> int:
        return int(self._llama.n_tokens)

    @property
    def model(self) -> Any:
        return self._llama._model.model  # noqa: SLF001 - the low-level handle the adapter API needs

    @property
    def ctx(self) -> Any:
        return self._llama._ctx.ctx  # noqa: SLF001

    def reset(self) -> None:
        self._llama.reset()

    def close(self) -> None:
        """Give the weights and the KV cache back, so the next model has room."""
        self._llama.close()


#: Loads one model. Blocking, so it is always called in a worker thread.
Loader = Callable[[ModelSpec, Path, Path, int], Slot]


def load_slot(spec: ModelSpec, weights: Path, projector: Path, n_ctx: int) -> Slot:
    return LlamaSlot(spec, weights, projector, n_ctx)


@dataclass
class ModelStatus:
    """What the Settings models card shows for one local model."""

    key: str
    seat: ModelRole
    name: str
    label: str
    ready: bool
    """Its files are on disk."""
    loaded: bool
    """It is the model loaded right now. True for at most one model."""
    load_seconds: float | None
    n_ctx: int


class LocalStack:
    """The local provider: the model files, the one loaded model and the adapter registry."""

    def __init__(
        self,
        settings: Settings,
        *,
        downloads: DownloadManager | None = None,
        adapters: AdapterRegistry | None = None,
        load: Loader = load_slot,
        models: dict[str, ModelSpec] | None = None,
    ) -> None:
        self.models = models if models is not None else LOCAL_MODELS
        self.n_ctx = settings.local_n_ctx
        self.downloads = downloads or DownloadManager(
            settings.models_dir,
            models=self.models,
            parked_dirs=[settings.parked_models_dir] if settings.parked_models_dir else [],
        )
        self.adapters = adapters or AdapterRegistry(settings.models_dir)
        self._load = load
        #: The one loaded GGUF and the spec it was loaded from. Nothing else is ever resident.
        self._slot: Slot | None = None
        self._loaded: ModelSpec | None = None
        #: The model the next `slot` call should load, set by `take_seat` before the load.
        self._wanted: ModelSpec | None = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()
        self.swapping: str | None = None
        """The key of the model being loaded right now, so the models card can say so."""
        # llama.cpp is not reentrant, so every call into it goes through one thread. A single
        # worker also gives `drain` its meaning: work queued behind the abandoned token pull of
        # a cancelled turn cannot start until that pull has returned.
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="finquery-local")

    async def run(self, seat: ModelRole, call: Callable[[], T]) -> T:
        """Run one blocking llama.cpp call on the model's thread.

        Cancelling the awaiting task does not stop the call; it runs to completion and `drain`
        is how a caller waits for that. `seat` says which role the caller is running as; there
        is one thread either way, because there is one loaded model.
        """
        return await asyncio.wrap_future(self._worker.submit(call))

    def drain(self, seat: ModelRole, timeout: float = 60) -> None:
        """Block until the model's thread is idle. Called while the lock is still held, so the
        next turn never reaches llama.cpp while a cancelled one is still inside it."""
        self._worker.submit(lambda: None).result(timeout)

    def resolve(self, spec: ModelSpec) -> Model:
        """One local model to a Pydantic AI model. Loads nothing yet.

        The one thing it does check is that the files are there, because that is the only
        failure a user can act on and the chat endpoint turns it into a 503 with this text.
        """
        from finquery.local.model import LlamaCppModel

        # The caller names a model from the catalog; the stack answers with its own object for
        # that key, which is what a test with stand-in specs swaps and what `loaded_spec`
        # compares seats against.
        spec = self.models.get(spec.key, spec)
        if not self.downloads.ready(spec.key):
            raise ProviderNotAvailable(f"{spec.label} is not downloaded yet: {self.download_summary(spec.key)}")
        return LlamaCppModel(spec, self)

    def download_summary(self, key: str) -> str:
        rows = [row for row in self.downloads.progress() if row.key == key and row.state != "ready"]
        if not rows:
            return "open Settings and start the download"
        done = sum(row.downloaded for row in rows)
        total = sum(row.size for row in rows)
        if any(row.state == "error" for row in rows):
            return next(f"download failed: {row.error}" for row in rows if row.state == "error")
        return f"{done * 100 // max(total, 1)}% of {total / 1e9:.1f} GB, watch it in Settings"

    def loaded_spec(self, seat: ModelRole) -> ModelSpec | None:
        """The loaded model, if it is the one for this seat, and None otherwise.

        So `loaded_spec("fast")` answers "is the sub-agent model the one in memory", which is
        what a chat on a bigger model makes false.
        """
        return self._loaded if self._loaded is not None and self._loaded.seat == seat else None

    def status(self) -> list[ModelStatus]:
        """One row per catalog model, `loaded` true for at most one of them."""
        return [
            ModelStatus(
                key=spec.key,
                seat=spec.seat,
                name=spec.name,
                label=spec.label,
                ready=self.downloads.ready(spec.key),
                loaded=self._loaded is spec and self._slot is not None,
                load_seconds=self._slot.load_seconds if self._loaded is spec and self._slot is not None else None,
                n_ctx=self.n_ctx,
            )
            for spec in self.models.values()
        ]

    def take_seat(self, spec: ModelSpec) -> None:
        """Make `spec` the loaded model, swapping out whatever else is loaded.

        Blocking, and called with the lock held, so nothing can start a turn on the model being
        unloaded. The order is the point: drain first, so the abandoned token pull of a
        cancelled turn has returned before the weights it was reading are freed; then unload,
        so two GGUFs are never resident at the same time; then load, which `slot` does.
        """
        if self._loaded is spec:
            return
        self.swapping = spec.key
        self.unload()
        self._wanted = spec

    def unload(self) -> None:
        """Free the loaded model, so the next use loads one again at the current `n_ctx`.

        Blocking, and the first half of a swap: drain first, so the abandoned token pull of a
        cancelled turn has returned before the weights it was reading are freed. A turn never
        calls this by itself: it asks for its model and `take_seat` does the unloading under
        the lock. The seat argument went with the pair check of ticket 68; there is one model
        to free.
        """
        self._wanted = None
        if self._slot is None or self._loaded is None:
            return
        self.drain(self._loaded.seat)
        slot, self._slot, self._loaded = self._slot, None, None
        slot.close()

    def slot(self, seat: ModelRole) -> Slot:
        """The loaded model, downloading and loading it first if nothing is. Blocking.

        `seat` is the role the caller runs as: `take_seat` has already put the right model in
        memory, so this only has the first load left to do. A caller that asks for a seat the
        loaded model does not fill never reaches llama.cpp, because loading the other model
        behind its back would leave the run that holds the lock reading freed weights.
        """
        if self._slot is not None:
            if self.loaded_spec(seat) is None:
                raise ProviderNotAvailable(
                    f"{self._loaded.label if self._loaded else 'another model'} is loaded, "
                    f"so nothing can run on the {seat} seat until it is given up"
                )
            return self._slot
        with self._load_lock:
            if self._slot is not None:
                return self._slot
            spec = self._wanted or LOCAL_FAST
            if spec.seat != seat:
                raise ProviderNotAvailable(f"nothing has taken the {seat} seat yet")
            self._wanted = spec
            self.downloads.ensure(spec.key)
            self.swapping = spec.key
            try:
                self._slot = self._load(
                    spec,
                    self.downloads.path(spec, spec.weights),
                    self.downloads.path(spec, spec.projector),
                    self.n_ctx,
                )
                self._loaded = spec
            finally:
                self.swapping = None
            return self._slot

    @asynccontextmanager
    async def holding(self, seat: ModelRole, spec: ModelSpec | None = None) -> AsyncIterator[Slot]:
        """Serialize work on the loaded llama context, re-entrant within one asyncio task.

        Re-entrancy is what lets a sub-agent run inside `with_adapter` without deadlocking on
        the lock the adapter already took. `spec` is the model the caller needs loaded, and
        that is what makes the swap happen, under the same lock. A nested hold cannot swap:
        the run around it is holding the model it asked for.
        """
        if _held.get():
            if spec is not None and self._loaded is not spec:
                raise ProviderNotAvailable(
                    f"{spec.label} cannot be loaded inside a run on "
                    f"{self._loaded.label if self._loaded else 'another model'}"
                )
            yield await self.run(seat, lambda: self.slot(seat))
            return
        await asyncio.to_thread(self._lock.acquire)
        token = _held.set(True)
        try:
            if spec is not None:
                await asyncio.to_thread(self.take_seat, spec)
            yield await self.run(seat, lambda: self.slot(seat))
        finally:
            _held.reset(token)
            self._lock.release()

    @asynccontextmanager
    async def with_adapter(self, name: AdapterName, spec: ModelSpec = LOCAL_FAST) -> AsyncIterator[Slot]:
        """Hold the seat of `spec` with one sub-agent's adapter attached.

        A missing adapter file is not an error: the run goes ahead on the base weights and the
        audit note is published to `adapter_note()`, from where the model puts it on the
        response metadata. A sub-agent asks for this by setting `finquery_adapter` in its model
        settings, never by calling here directly.

        In the app `spec` is always the fast slot, because that is where the shipped adapters
        are trained for and the only seat `LlamaCppModel._hold` attaches one on. It is a
        parameter because the benchmark can ask for an adapter over a chat model, and attaching
        that to the fast seat would score E4B while the run claimed to be scoring the 12B.
        """
        async with self.holding(spec.seat, spec) as loaded:
            with self.adapters.attached_to(name, loaded) as note:
                with audited(note.text if note is not None else None):
                    yield loaded
