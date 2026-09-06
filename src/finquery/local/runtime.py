"""The loaded llama.cpp models and everything the local provider owns around them.

There are two seats in memory, each capped at the configured context so the two fit in 24 GB
with Metal offload. The `fast` seat holds Gemma 4 E4B and stays resident: every adapter attaches
there and a sub-agent runs behind almost every turn. The `chat` seat holds one of the two local
chat models, and choosing the other swaps it: drain the running one, unload it, load the new one
at the same context size. Three models do not fit and are never loaded together.

A seat is filled on its first use, not at startup, so the app can start (and show download
progress) before any weights exist. See docs/adr/0013-model-catalog-across-providers.md.
"""

import asyncio
import contextvars
import ctypes
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic_ai.models import Model

from finquery.local.adapters import AdapterRegistry
from finquery.local.catalog import LOCAL_FAST, LOCAL_MODELS, AdapterName, ModelSpec
from finquery.local.downloads import DownloadManager
from finquery.providers import MODEL_ROLES, ModelRole, ProviderNotAvailable
from finquery.settings import Settings

#: Seats whose lock the current asyncio task already holds, so a sub-agent run nested inside
#: an attached adapter does not deadlock on itself.
_held: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar("finquery_held_seats", default=frozenset())

#: Set while a run is falling back to base weights, so the model can attach the note to the
#: response it produces without the sub-agent having to thread it through by hand.
_note: contextvars.ContextVar[str | None] = contextvars.ContextVar("finquery_adapter_note", default=None)

T = TypeVar("T")


def adapter_note() -> str | None:
    """The audit note for the run in progress, if it fell back to the base weights."""
    return _note.get()


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
        """Free the weights. Called when the other chat model takes the seat."""
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
            # Flash attention plus a q8_0 KV cache is what makes both models fit inside the
            # Metal working set of a 24 GB Mac. Measured numbers are in
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
        """Give the weights and the KV cache back, so the other chat model has room."""
        self._llama.close()


#: Loads one seat. Blocking, so it is always called in a worker thread.
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
    """It is the model in its seat right now."""
    load_seconds: float | None
    n_ctx: int


class LocalStack:
    """The local provider: the model files, the two seats and the adapter registry."""

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
        #: The model in each seat. At most one per seat, which is what keeps a third GGUF from
        #: ever being resident.
        self._seats: dict[ModelRole, Slot] = {}
        self._wanted: dict[ModelRole, ModelSpec] = {}
        self._locks = {seat: threading.Lock() for seat in MODEL_ROLES}
        self._load_lock = threading.Lock()
        self.swapping: str | None = None
        """The key of the chat model being loaded right now, so the models card can say so."""
        # llama.cpp is not reentrant, so every call into one seat goes through one thread. A
        # single worker also gives `drain` its meaning: work queued behind the abandoned token
        # pull of a cancelled turn cannot start until that pull has returned.
        self._workers = {
            seat: ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"finquery-{seat}") for seat in MODEL_ROLES
        }

    async def run(self, seat: ModelRole, call: Callable[[], T]) -> T:
        """Run one blocking llama.cpp call on the seat's thread.

        Cancelling the awaiting task does not stop the call; it runs to completion and `drain`
        is how a caller waits for that.
        """
        return await asyncio.wrap_future(self._workers[seat].submit(call))

    def drain(self, seat: ModelRole, timeout: float = 60) -> None:
        """Block until the seat's thread is idle. Called while its lock is still held, so the
        next turn never reaches llama.cpp while a cancelled one is still inside it."""
        self._workers[seat].submit(lambda: None).result(timeout)

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
        """Which model is in this seat, or None while it is empty."""
        return self._wanted.get(seat) if seat in self._seats else None

    def status(self) -> list[ModelStatus]:
        return [
            ModelStatus(
                key=spec.key,
                seat=spec.seat,
                name=spec.name,
                label=spec.label,
                ready=self.downloads.ready(spec.key),
                loaded=self.loaded_spec(spec.seat) is spec,
                load_seconds=self._seats[spec.seat].load_seconds if self.loaded_spec(spec.seat) is spec else None,
                n_ctx=self.n_ctx,
            )
            for spec in self.models.values()
        ]

    def take_seat(self, spec: ModelSpec) -> None:
        """Make `spec` the model in its seat, swapping out whatever is there.

        Blocking, and called with the seat's lock held, so nothing can start a turn on the model
        being unloaded. The order is the point: drain first, so the abandoned token pull of a
        cancelled turn has returned before the weights it was reading are freed; then unload,
        so the two chat models are never resident at the same time; then load.
        """
        seat = spec.seat
        current = self.loaded_spec(seat)
        if current is spec:
            return
        self.swapping = spec.key
        if current is not None:
            self.drain(seat)
            self._seats.pop(seat).close()
        self._wanted[seat] = spec

    def slot(self, seat: ModelRole) -> Slot:
        """The model in one seat, downloading and loading it first if needed. Blocking."""
        if (loaded := self._seats.get(seat)) is not None:
            return loaded
        with self._load_lock:
            if (loaded := self._seats.get(seat)) is not None:
                return loaded
            spec = self._wanted.get(seat) or LOCAL_FAST
            if spec.seat != seat:
                raise ProviderNotAvailable(f"nothing has taken the {seat} seat yet")
            self._wanted[seat] = spec
            self.downloads.ensure(spec.key)
            self.swapping = spec.key
            try:
                self._seats[seat] = self._load(
                    spec,
                    self.downloads.path(spec, spec.weights),
                    self.downloads.path(spec, spec.projector),
                    self.n_ctx,
                )
            finally:
                self.swapping = None
            return self._seats[seat]

    @asynccontextmanager
    async def holding(self, seat: ModelRole, spec: ModelSpec | None = None) -> AsyncIterator[Slot]:
        """Serialize work on one seat's llama context, re-entrant within one asyncio task.

        Re-entrancy is what lets a sub-agent run inside `with_adapter` without deadlocking on
        the lock the adapter already took. `spec` is the model the caller needs in the seat; on
        the chat seat that is what makes the swap happen, under the same lock.
        """
        if seat in _held.get():
            yield await self.run(seat, lambda: self.slot(seat))
            return
        lock = self._locks[seat]
        await asyncio.to_thread(lock.acquire)
        token = _held.set(_held.get() | {seat})
        try:
            if spec is not None:
                await asyncio.to_thread(self.take_seat, spec)
            yield await self.run(seat, lambda: self.slot(seat))
        finally:
            _held.reset(token)
            lock.release()

    @asynccontextmanager
    async def with_adapter(self, name: AdapterName, spec: ModelSpec = LOCAL_FAST) -> AsyncIterator[Slot]:
        """Hold the seat of `spec` with one sub-agent's adapter attached.

        A missing adapter file is not an error: the run goes ahead on the base weights and the
        audit note is published to `adapter_note()`, from where the model puts it on the
        response metadata. A sub-agent asks for this by setting `finquery_adapter` in its model
        settings, never by calling here directly.

        In the app `spec` is always the fast slot, because every sub-agent runs there (ADR 0002
        and 0013) and that is where the shipped adapters are trained for. It is a parameter
        because the benchmark can ask for an adapter over a chat model, and attaching that to
        the fast seat would score E4B while the run claimed to be scoring the 12B.
        """
        async with self.holding(spec.seat, spec) as loaded:
            with self.adapters.attached_to(name, loaded) as note:
                token = _note.set(note.text if note is not None else None)
                try:
                    yield loaded
                finally:
                    _note.reset(token)
