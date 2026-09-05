"""The Gemma 4 wire format: thought channel, tool calls, and the argument DSL.

Gemma 4 puts everything in one text stream. With thinking on, the chat template opens a model
turn and the model writes

    <|channel>thought\\n reasoning <channel|> answer

and a tool call looks like

    <|tool_call>call:query{question:<|"|>groceries in May<|"|>,limit:20}<tool_call|>

Nothing here touches llama.cpp, so the splitter and the argument parser are the two pieces
that can be exercised without loading a model.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

THOUGHT_OPEN = "<|channel>"
THOUGHT_CLOSE = "<channel|>"
TOOL_CALL_OPEN = "<|tool_call>"
TOOL_CALL_CLOSE = "<tool_call|>"
TURN_CLOSE = "<turn|>"

# The template writes strings with its own quote marker; a model that falls back to JSON
# quoting is accepted too, since both are unambiguous.
QUOTE = '<|"|>'

#: Stop strings for `create_completion`. The end-of-turn marker is normally a special token,
#: but a model that spells it out should still stop.
STOP = [TURN_CLOSE, "<|turn>"]

TEMPLATE_MARKERS = (THOUGHT_OPEN, THOUGHT_CLOSE, TOOL_CALL_OPEN, TOOL_CALL_CLOSE, TURN_CLOSE, "<|turn>")
"""Every token of the chat template. None of them is ever text the user should read.

The local provider's `StreamSplitter` consumes them, but OpenRouter serves the same Gemma
models and hands the end-of-turn marker back as plain text at the end of a message, so the
chat path filters them out for both providers. See `MarkerFilter`.
"""

_CALL_HEAD = re.compile(r"\s*call\s*:\s*(?P<name>[A-Za-z_][A-Za-z0-9_.-]*)\s*")
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class ToolCall:
    """A parsed `<|tool_call>` block."""

    name: str
    args: dict[str, Any]
    raw: str


Event = tuple[Literal["thinking", "text"], str] | tuple[Literal["tool_call"], ToolCall]


def _split_at_marker(buffer: str, markers: tuple[str, ...]) -> tuple[str, str | None, str]:
    """Split on the earliest marker, holding back a tail that could still become one.

    Returns the content before the marker, the marker (or None if none is complete yet) and
    the remainder to keep buffered.
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


CHANNEL_NAMES = frozenset({"thought", "thinking"})
"""The words that follow `<|channel>` in the template.

OpenRouter serves the same models and swallows the angle-bracket tokens, which are special
tokens, but hands the channel's *name* back as ordinary text, so an answer arrives with a bare
`thought` line in it. Nothing the user should read is ever one of these words alone on a line.
"""


def strip_channel_lines(text: str) -> str:
    """Drop lines that are nothing but a channel name."""
    if not any(name in text.casefold() for name in CHANNEL_NAMES):
        return text
    kept = [line for line in text.split("\n") if line.strip().casefold() not in CHANNEL_NAMES]
    return "\n".join(kept)


def strip_markers(text: str) -> str:
    """Remove every chat-template token from a finished piece of text."""
    for marker in TEMPLATE_MARKERS:
        text = text.replace(marker, "")
    return strip_channel_lines(text)


class MarkerFilter:
    """Strip chat-template tokens out of streamed text, safely across delta boundaries.

    A marker straddles token boundaries (`<tur` then `n|>`), so a tail that could still become
    one is held back until the next delta decides. `flush` releases what is left when the text
    part ends, so a stray `<` at the end of an answer is not eaten.
    """

    def __init__(self) -> None:
        self._held = ""

    def feed(self, delta: str) -> str:
        buffer = self._held + delta
        out: list[str] = []
        while buffer:
            content, marker, rest = _split_at_marker(buffer, TEMPLATE_MARKERS)
            out.append(content)
            buffer = rest
            if marker is None:
                break
        self._held = buffer
        return "".join(out)

    def flush(self) -> str:
        held, self._held = self._held, ""
        return held


class StreamSplitter:
    """Turn raw Gemma 4 text deltas into thinking, text and tool-call events.

    Markers straddle token boundaries, so a delta is only released once it cannot still turn
    out to be the start of one. Pass `in_thought=True` when the prompt already opened the
    thought channel, which the template does after a tool response with thinking on.
    """

    _MARKERS: dict[str, tuple[str, ...]] = {
        "text": (THOUGHT_OPEN, TOOL_CALL_OPEN, TURN_CLOSE),
        "thought": (THOUGHT_CLOSE, TURN_CLOSE),
        "tool_call": (TOOL_CALL_CLOSE,),
    }

    def __init__(self, *, in_thought: bool = False) -> None:
        self._mode: Literal["text", "thought", "tool_call"] = "thought" if in_thought else "text"
        self._buffer = ""
        self._call = ""
        self._label = ""
        self._labelled = in_thought

    def feed(self, delta: str) -> list[Event]:
        self._buffer += delta
        events: list[Event] = []
        while self._buffer:
            content, marker, rest = _split_at_marker(self._buffer, self._MARKERS[self._mode])
            self._buffer = rest
            events.extend(self._content(content, final=False))
            if marker is None:
                break
            events.extend(self._close(marker))
            self._switch(marker)
        return events

    def finish(self) -> list[Event]:
        """Flush whatever is held back; a block cut off mid-marker is emitted as it stands."""
        buffer, self._buffer = self._buffer, ""
        events = self._content(buffer, final=True)
        if self._mode == "tool_call" and (call := self._finish_call()) is not None:
            events.append(("tool_call", call))
        self._mode = "text"
        return events

    def _content(self, content: str, *, final: bool) -> list[Event]:
        """Route text between markers to the channel the splitter is currently in."""
        if self._mode == "tool_call":
            self._call += content
            return []
        if self._mode == "thought":
            content = self._strip_label(content, final=final)
            return [("thinking", content)] if content else []
        return [("text", content)] if content else []

    def _close(self, marker: str) -> list[Event]:
        """Flush the block the marker ends before switching channel."""
        if self._mode == "thought":
            return self._content("", final=True)
        if marker == TOOL_CALL_CLOSE and (call := self._finish_call()) is not None:
            return [("tool_call", call)]
        return []

    def _strip_label(self, content: str, *, final: bool) -> str:
        """Hold back the channel name line ("thought") that follows the open marker."""
        if self._labelled:
            return content
        self._label += content
        if "\n" not in self._label and not final:
            return ""
        self._labelled = True
        held, self._label = self._label, ""
        label, _, rest = held.partition("\n")
        return rest if label.strip() == "thought" else held

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
        if marker == THOUGHT_OPEN:
            self._mode = "thought"
            self._label = ""
            self._labelled = False
        elif marker == TOOL_CALL_OPEN:
            self._mode = "tool_call"
        else:
            # THOUGHT_CLOSE, TOOL_CALL_CLOSE and TURN_CLOSE all land back in plain text.
            self._mode = "text"


def parse_tool_call(body: str) -> ToolCall:
    """Parse `call:name{...}` from inside a `<|tool_call>` block."""
    head = _CALL_HEAD.match(body)
    if head is None:
        raise ValueError(f"not a Gemma 4 tool call: {body!r}")
    args_text = body[head.end() :].strip()
    args = parse_arguments(args_text) if args_text else {}
    return ToolCall(name=head.group("name"), args=args, raw=body)


def parse_arguments(text: str) -> dict[str, Any]:
    """Parse the Gemma 4 argument object: bare keys, `<|"|>`-quoted strings, JSON-ish values."""
    value, end = _parse_value(text, 0)
    if not isinstance(value, dict):
        raise ValueError(f"tool call arguments must be an object, got {text!r}")
    if text[end:].strip():
        raise ValueError(f"trailing characters in tool call arguments: {text[end:]!r}")
    return value


def _skip_space(text: str, i: int) -> int:
    while i < len(text) and text[i].isspace():
        i += 1
    return i


def _parse_value(text: str, i: int) -> tuple[Any, int]:  # noqa: C901
    i = _skip_space(text, i)
    if i >= len(text):
        raise ValueError("unexpected end of tool call arguments")
    char = text[i]
    if text.startswith(QUOTE, i):
        end = text.find(QUOTE, i + len(QUOTE))
        if end == -1:
            raise ValueError("unterminated string in tool call arguments")
        return text[i + len(QUOTE) : end], end + len(QUOTE)
    if char == '"':
        # A model that quotes with JSON instead: let json decode the escapes.
        decoded, end = json.JSONDecoder().raw_decode(text, i)
        return decoded, end
    if char == "{":
        obj: dict[str, Any] = {}
        i = _skip_space(text, i + 1)
        while i < len(text) and text[i] != "}":
            key, i = _parse_key(text, i)
            i = _skip_space(text, i)
            if i >= len(text) or text[i] != ":":
                raise ValueError(f"expected ':' after key {key!r} in tool call arguments")
            value, i = _parse_value(text, i + 1)
            obj[key] = value
            i = _skip_space(text, i)
            if i < len(text) and text[i] == ",":
                i = _skip_space(text, i + 1)
        if i >= len(text):
            raise ValueError("unterminated object in tool call arguments")
        return obj, i + 1
    if char == "[":
        items: list[Any] = []
        i = _skip_space(text, i + 1)
        while i < len(text) and text[i] != "]":
            value, i = _parse_value(text, i)
            items.append(value)
            i = _skip_space(text, i)
            if i < len(text) and text[i] == ",":
                i = _skip_space(text, i + 1)
        if i >= len(text):
            raise ValueError("unterminated array in tool call arguments")
        return items, i + 1
    for literal, value in (("true", True), ("false", False), ("null", None)):
        if text.startswith(literal, i):
            return value, i + len(literal)
    number = _NUMBER.match(text, i)
    if number is not None:
        raw = number.group()
        return (float(raw) if any(c in raw for c in ".eE") else int(raw)), number.end()
    # Anything else is an unquoted scalar: take it up to the next separator.
    end = i
    while end < len(text) and text[end] not in ",}]":
        end += 1
    return text[i:end].strip(), end


def _parse_key(text: str, i: int) -> tuple[str, int]:
    if text.startswith(QUOTE, i) or text[i] == '"':
        key, i = _parse_value(text, i)
        return str(key), i
    end = i
    while end < len(text) and text[end] not in ":,}":
        end += 1
    return text[i:end].strip(), end
