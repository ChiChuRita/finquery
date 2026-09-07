"""What one local model's chat wire format has that the other's does not.

`finquery.local.gemma` and `finquery.local.qwen` each turn one model's single text stream into
thinking parts, text parts and tool calls. The two are not variations on one format: Gemma 4
writes channel markers and its own argument DSL, Qwen writes `<think>` blocks and XML-ish
parameter tags, and their chat templates take different arguments. This module is the shape
they have in common, so `finquery.local.model` can pick one from the model spec and stay free
of model specifics. Since ticket 67 every catalog entry is Gemma; the Qwen format stays for the
benchmark candidates (`bench/finquery_bench/candidates.py`, Qwen3.8 27B), which are never in
the catalog.

Nothing here imports llama.cpp or either wire-format module, so both stay testable without a
model and the registry (`finquery.local.model.WIRE_FORMATS`) has somewhere to point.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

WireName = Literal["gemma", "qwen"]


class ParsedCall(Protocol):
    """A tool call one wire format's parser recovered from the stream."""

    @property
    def name(self) -> str: ...

    @property
    def args(self) -> dict[str, Any]: ...


Event = tuple[Literal["thinking", "text"], str] | tuple[Literal["tool_call"], ParsedCall]


class Splitter(Protocol):
    """Raw text deltas in, thinking, text and tool-call events out."""

    def feed(self, delta: str) -> Sequence[Event]: ...

    def finish(self) -> Sequence[Event]:
        """Flush whatever was held back because it could still have become a marker."""
        ...


class SplitterFactory(Protocol):
    def __call__(self, *, in_thought: bool) -> Splitter: ...


@dataclass(frozen=True)
class Sampling:
    """One model card's recommended sampling settings."""

    temperature: float
    top_p: float
    top_k: int
    min_p: float
    presence_penalty: float
    repeat_penalty: float


@dataclass(frozen=True)
class WireFormat:
    """One model's chat template and token stream, as far as the request builder cares."""

    splitter: SplitterFactory
    stop: list[str]
    sampling: Sampling
    reasoning_key: str
    """The assistant-message key this chat template reads past thinking from."""
    thought_open_at_start: bool
    """Whether the generation prompt already opens the thought channel with thinking on, so
    the model writes reasoning with no opening marker for the splitter to see."""
    template_kwargs: dict[str, Any] = field(default_factory=dict)
    """Arguments this template takes beyond `enable_thinking`."""


def split_at_marker(buffer: str, markers: Sequence[str]) -> tuple[str, str | None, str]:
    """Split on the earliest marker, holding back a tail that could still become one.

    Returns the content before the marker, the marker (or None if none is complete yet) and
    the remainder to keep buffered. `finquery.local.gemma` carries its own copy of this from
    ticket 16 and was deliberately left alone; new wire formats use this one.
    """
    best: tuple[int, str] | None = None
    for marker in markers:
        index = buffer.find(marker)
        if index != -1 and (best is None or index < best[0]):
            best = (index, marker)
    if best is not None:
        index, marker = best
        return buffer[:index], marker, buffer[index + len(marker) :]

    # No complete marker: keep the longest suffix that is a proper prefix of one.
    for size in range(min(len(buffer), max(len(m) for m in markers) - 1), 0, -1):
        tail = buffer[-size:]
        if any(m.startswith(tail) for m in markers):
            return buffer[:-size], None, tail
    return buffer, None, ""
