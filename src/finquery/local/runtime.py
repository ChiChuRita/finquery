"""The loaded llama.cpp models and everything the local provider owns around them.

Both slots stay resident once loaded, each capped at the configured context so the two fit in
24 GB with Metal offload. A slot is loaded on its first use, not at startup, so the app can
start (and show download progress) before any weights exist.
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
from finquery.local.catalog import LOCAL_MODELS, AdapterName, ModelSpec
from finquery.local.downloads import DownloadManager
from finquery.providers import ModelSlot, ProviderNotAvailable
from finquery.settings import Settings

#: Slots whose lock the current asyncio task already holds, so a sub-agent run nested inside
#: an attached adapter does not deadlock on itself.
_held: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar("finquery_held_slots", default=frozenset())

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
    """A Gemma 4 GGUF loaded through llama-cpp-python with its multimodal projector."""

    def __init__(self, spec: ModelSpec, weights: Path, projector: Path, n_ctx: int) -> None:
        import llama_cpp
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import Gemma4ChatHandler

        _quiet_llama_cpp()
        self.name = weights.stem
        started = time.monotonic()
        # `guess_chat_format_from_gguf_metadata` returns None for Gemma 4, so the handler is
        # chosen here; it reads the chat template out of the GGUF metadata itself.
        self._handler = Gemma4ChatHandler(clip_model_path=str(projector), verbose=False)
        self._llama = Llama(
            model_path=str(weights),
            n_ctx=n_ctx,
            n_gpu_layers=-1,
            # Flash attention plus a q8_0 KV cache is what makes both models fit: it takes the
            # 12B's KV cache at 16k from 5.8 GB to 2.9 GB and its compute buffer from 1.2 GB to
            # 0.5 GB. Measured numbers are in docs/adr/0005-local-gemma-4-through-llama-cpp.md.
            flash_attn=True,
            type_k=llama_cpp.GGML_TYPE_Q8_0,
            type_v=llama_cpp.GGML_TYPE_Q8_0,
            verbose=False,
        )
        self.load_seconds = round(time.monotonic() - started, 2)
        self.slot = spec.slot
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


#: Loads one slot. Blocking, so it is always called in a worker thread.
Loader = Callable[[ModelSpec, Path, Path, int], Slot]


def load_slot(spec: ModelSpec, weights: Path, projector: Path, n_ctx: int) -> Slot:
    return LlamaSlot(spec, weights, projector, n_ctx)


@dataclass
class SlotStatus:
    slot: ModelSlot
    name: str
    ready: bool
    loaded: bool
    load_seconds: float | None
    n_ctx: int


class LocalStack:
    """The local provider: the model files, the resident slots and the adapter registry."""

    def __init__(
        self,
        settings: Settings,
        *,
        downloads: DownloadManager | None = None,
        adapters: AdapterRegistry | None = None,
        load: Loader = load_slot,
        models: dict[ModelSlot, ModelSpec] | None = None,
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
        self._slots: dict[ModelSlot, Slot] = {}
        self._locks = {slot: threading.Lock() for slot in self.models}
        self._load_lock = threading.Lock()
        # llama.cpp is not reentrant, so every call into one slot goes through one thread. A
        # single worker also gives `drain` its meaning: work queued behind the abandoned token
        # pull of a cancelled turn cannot start until that pull has returned.
        self._workers = {
            slot: ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"finquery-{slot}") for slot in self.models
        }

    async def run(self, slot: ModelSlot, call: Callable[[], T]) -> T:
        """Run one blocking llama.cpp call on the slot's thread.

        Cancelling the awaiting task does not stop the call; it runs to completion and `drain`
        is how a caller waits for that.
        """
        return await asyncio.wrap_future(self._workers[slot].submit(call))

    def drain(self, slot: ModelSlot, timeout: float = 60) -> None:
        """Block until the slot's thread is idle. Called while its lock is still held, so the
        next turn never reaches llama.cpp while a cancelled one is still inside it."""
        self._workers[slot].submit(lambda: None).result(timeout)

    def resolve(self, slot: ModelSlot) -> Model:
        """The provider resolver: a slot to a Pydantic AI model. Loads nothing yet.

        The one thing it does check is that the files are there, because that is the only
        failure a user can act on and the chat endpoint turns it into a 503 with this text.
        """
        from finquery.local.model import LlamaCppModel

        if not self.downloads.ready(slot):
            raise ProviderNotAvailable(f"The {slot} model is not downloaded yet: {self.download_summary(slot)}")
        return LlamaCppModel(self.models[slot], self)

    def download_summary(self, slot: ModelSlot) -> str:
        rows = [row for row in self.downloads.progress() if row.slot == slot and row.state != "ready"]
        if not rows:
            return "open Settings and start the download"
        done = sum(row.downloaded for row in rows)
        total = sum(row.size for row in rows)
        if any(row.state == "error" for row in rows):
            return next(f"download failed: {row.error}" for row in rows if row.state == "error")
        return f"{done * 100 // max(total, 1)}% of {total / 1e9:.1f} GB, watch it in Settings"

    def status(self) -> list[SlotStatus]:
        return [
            SlotStatus(
                slot=spec.slot,
                name=spec.name,
                ready=self.downloads.ready(spec.slot),
                loaded=spec.slot in self._slots,
                load_seconds=self._slots[spec.slot].load_seconds if spec.slot in self._slots else None,
                n_ctx=self.n_ctx,
            )
            for spec in self.models.values()
        ]

    def slot(self, slot: ModelSlot) -> Slot:
        """The loaded slot, downloading and loading it first if needed. Blocking."""
        if (loaded := self._slots.get(slot)) is not None:
            return loaded
        with self._load_lock:
            if (loaded := self._slots.get(slot)) is not None:
                return loaded
            spec = self.models[slot]
            self.downloads.ensure(slot)
            self._slots[slot] = self._load(
                spec,
                self.downloads.path(spec, spec.weights),
                self.downloads.path(spec, spec.projector),
                self.n_ctx,
            )
            return self._slots[slot]

    @asynccontextmanager
    async def holding(self, slot: ModelSlot) -> AsyncIterator[Slot]:
        """Serialize work on one slot's llama context, re-entrant within one asyncio task.

        Re-entrancy is what lets a sub-agent run inside `with_adapter` without deadlocking on
        the lock the adapter already took.
        """
        if slot in _held.get():
            yield await self.run(slot, lambda: self.slot(slot))
            return
        lock = self._locks[slot]
        await asyncio.to_thread(lock.acquire)
        token = _held.set(_held.get() | {slot})
        try:
            yield await self.run(slot, lambda: self.slot(slot))
        finally:
            _held.reset(token)
            lock.release()

    @asynccontextmanager
    async def with_adapter(self, name: AdapterName) -> AsyncIterator[Slot]:
        """Hold the fast slot with one sub-agent's adapter attached.

        A missing adapter file is not an error: the run goes ahead on the base weights and the
        audit note is published to `adapter_note()`, from where the model puts it on the
        response metadata. A sub-agent asks for this by setting `finquery_adapter` in its model
        settings, never by calling here directly.
        """
        async with self.holding("fast") as loaded:
            with self.adapters.attached_to(name, loaded) as note:
                token = _note.set(note.text if note is not None else None)
                try:
                    yield loaded
                finally:
                    _note.reset(token)
