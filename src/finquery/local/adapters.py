"""LoRA adapters for the fast slot, one sub-agent at a time.

llama.cpp has no remove call: an adapter is detached by setting the context's adapter list to
nothing. A registry entry with no file on disk is a supported state, not an error: the run goes
ahead on the base weights and leaves an audit note so the answer is not silently different from
what a trained adapter would have produced.
"""

import ctypes
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from finquery.local.catalog import ADAPTER_NAMES, AdapterName, adapter_path


@dataclass(frozen=True)
class AdapterState:
    """What the Settings card shows for one adapter."""

    name: AdapterName
    path: str
    present: bool


@dataclass(frozen=True)
class AuditNote:
    """Something about how an answer was produced that the user should be able to see."""

    kind: str
    text: str


class AdapterApi(Protocol):
    """The three llama.cpp calls the registry needs, so tests can stand in for them."""

    def init(self, model: Any, path: Path) -> Any: ...
    def set(self, ctx: Any, handle: Any | None) -> None: ...
    def free(self, handle: Any) -> None: ...


class LlamaAdapterApi:
    """The low-level llama.cpp adapter calls."""

    def init(self, model: Any, path: Path) -> Any:
        from llama_cpp import llama_cpp

        handle = llama_cpp.llama_adapter_lora_init(model, str(path).encode())
        if not handle:
            raise RuntimeError(f"llama.cpp could not load the LoRA adapter at {path}")
        return handle

    def set(self, ctx: Any, handle: Any | None) -> None:
        from llama_cpp import llama_cpp

        if handle is None:
            # n=0 with no array is how llama.cpp detaches everything; there is no remove call.
            code = llama_cpp.llama_set_adapters_lora(ctx, None, 0, None)
        else:
            adapters = (llama_cpp.llama_adapter_lora_p_ctypes * 1)(handle)
            scales = (ctypes.c_float * 1)(1.0)
            code = llama_cpp.llama_set_adapters_lora(ctx, adapters, 1, scales)
        if code != 0:
            raise RuntimeError(f"llama_set_adapters_lora failed with code {code}")

    def free(self, handle: Any) -> None:
        from llama_cpp import llama_cpp

        llama_cpp.llama_adapter_lora_free(handle)


class AdapterRegistry:
    """The adapters that can be attached to the fast slot, keyed by sub-agent."""

    def __init__(self, models_dir: Path, *, api: AdapterApi | None = None) -> None:
        self._paths = {name: adapter_path(models_dir, name) for name in ADAPTER_NAMES}
        self._api = api if api is not None else LlamaAdapterApi()
        self._lock = threading.Lock()
        self._attached: AdapterName | None = None

    def states(self) -> list[AdapterState]:
        return [AdapterState(name=name, path=str(path), present=path.is_file()) for name, path in self._paths.items()]

    @property
    def attached(self) -> AdapterName | None:
        return self._attached

    @contextmanager
    def attached_to(self, name: AdapterName, llama: Any) -> Iterator[AuditNote | None]:
        """Attach the adapter for the length of one run, or fall back to the base weights.

        Yields `None` when the adapter is in use and an audit note when it is missing. The lock
        makes attach, run and detach one unit: a second run cannot swap the weights underneath.
        """
        path = self._paths[name]
        if not path.is_file():
            yield AuditNote(
                kind="adapter-fallback",
                text=f"No {name} adapter at {path}, answered on the base weights.",
            )
            return
        with self._lock:
            handle = self._api.init(llama.model, path)
            try:
                self._api.set(llama.ctx, handle)
                self._attached = name
                yield None
            finally:
                self._attached = None
                try:
                    self._api.set(llama.ctx, None)
                finally:
                    self._api.free(handle)
                llama.reset()
