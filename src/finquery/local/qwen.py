"""The Qwen3.5 wire format: think blocks, and tool calls written as parameter tags.

Qwen3.5 puts everything in one text stream too, but its markers are XML-ish rather than Gemma
4's channel tokens. With thinking on, the chat template ends the generation prompt on an open
`<think>`, so the model starts inside the thought channel and closes it itself:

    reasoning </think>

    answer<|im_end|>

and a tool call is the format the template's own instructions demand of it, one tag per
parameter rather than a JSON object:

    <tool_call>
    <function=query>
    <parameter=question>
    groceries in May
    </parameter>
    <parameter=limit>
    20
    </parameter>
    </function>
    </tool_call>

That is what vLLM calls the `qwen3_coder` tool-call format; parsing it is ours (ADR 0006).
Nothing here touches llama.cpp, so the splitter and the parser can be exercised without
loading a model.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from finquery.local.wire import Event, split_at_marker

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"
TOOL_CALL_OPEN = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"
TURN_CLOSE = "<|im_end|>"

#: Stop strings for `create_completion`. End of turn is normally a special token, but a model
#: that spells it out should still stop.
STOP = [TURN_CLOSE]

TEMPLATE_MARKERS = (THINK_OPEN, THINK_CLOSE, TOOL_CALL_OPEN, TOOL_CALL_CLOSE, TURN_CLOSE)
"""Every chat-template token that can appear in the stream. None of them is text to read."""

_FUNCTION = re.compile(r"<function=(?P<name>[^>\s]+)>")
_PARAMETER = re.compile(r"<parameter=(?P<key>[^>\s]+)>\n?(?P<value>.*?)\n?</parameter>", re.DOTALL)


@dataclass(frozen=True)
class ToolCall:
    """A parsed `<tool_call>` block."""

    name: str
    args: dict[str, Any]
    raw: str


def strip_markers(text: str) -> str:
    """Remove every chat-template token from a finished piece of text."""
    for marker in TEMPLATE_MARKERS:
        text = text.replace(marker, "")
    return text


class StreamSplitter:
    """Turn raw Qwen3.5 text deltas into thinking, text and tool-call events.

    Markers straddle token boundaries, so a delta is only released once it cannot still turn
    out to be the start of one. Pass `in_thought=True` when the prompt already opened the
    thought channel, which the template does whenever thinking is enabled.
    """

    _MARKERS: dict[str, tuple[str, ...]] = {
        "text": (THINK_OPEN, TOOL_CALL_OPEN, TURN_CLOSE),
        "thought": (THINK_CLOSE, TURN_CLOSE),
        "tool_call": (TOOL_CALL_CLOSE,),
    }

    def __init__(self, *, in_thought: bool = False) -> None:
        self._mode: Literal["text", "thought", "tool_call"] = "thought" if in_thought else "text"
        self._buffer = ""
        self._call = ""
        self._started = False

    def feed(self, delta: str) -> list[Event]:
        self._buffer += delta
        events: list[Event] = []
        while self._buffer:
            content, marker, rest = split_at_marker(self._buffer, self._MARKERS[self._mode])
            self._buffer = rest
            events.extend(self._content(content))
            if marker is None:
                break
            events.extend(self._close(marker))
            self._switch(marker)
        return events

    def finish(self) -> list[Event]:
        """Flush whatever is held back; a block cut off mid-marker is emitted as it stands."""
        buffer, self._buffer = self._buffer, ""
        events = self._content(buffer)
        if self._mode == "tool_call" and (call := self._finish_call()) is not None:
            events.append(("tool_call", call))
        self._mode = "text"
        return events

    def _content(self, content: str) -> list[Event]:
        """Route text between markers to the channel the splitter is currently in."""
        if self._mode == "tool_call":
            self._call += content
            return []
        if not self._started:
            # The template writes a newline after `<think>` and two after `</think>`, so a
            # block opens on whitespace the model did not write.
            content = content.lstrip()
            if not content:
                return []
            self._started = True
        return [("thinking" if self._mode == "thought" else "text", content)]

    def _close(self, marker: str) -> list[Event]:
        if marker == TOOL_CALL_CLOSE and (call := self._finish_call()) is not None:
            return [("tool_call", call)]
        return []

    def _finish_call(self) -> ToolCall | None:
        body, self._call = self._call, ""
        if not body.strip():
            return None
        try:
            return parse_tool_call(body)
        except ValueError:
            # A call cut short by Stop or a malformed one is dropped rather than crashing the turn.
            return None

    def _switch(self, marker: str) -> None:
        self._started = False
        if marker == THINK_OPEN:
            self._mode = "thought"
        elif marker == TOOL_CALL_OPEN:
            self._mode = "tool_call"
        else:
            # THINK_CLOSE, TOOL_CALL_CLOSE and TURN_CLOSE all land back in plain text.
            self._mode = "text"


def parse_tool_call(body: str) -> ToolCall:
    """Parse the `<function=...>` block from inside a `<tool_call>`."""
    head = _FUNCTION.search(body)
    if head is None:
        raise ValueError(f"not a Qwen3.5 tool call: {body!r}")
    args = {match["key"]: parse_argument(match["value"]) for match in _PARAMETER.finditer(body, head.end())}
    return ToolCall(name=head["name"], args=args, raw=body)


def parse_argument(text: str) -> Any:
    """One `<parameter>` body, as the tool's own schema will want it.

    The template writes objects and arrays as JSON and everything else as plain text, so those
    two are the only ones decoded here. A scalar stays a string on purpose: Pydantic reads
    "20" as 20 for an int field, while an int handed to a string field is a validation error.
    """
    stripped = text.strip()
    if stripped[:1] in ("{", "["):
        try:
            return json.loads(stripped)
        except ValueError:
            return text
    return text
