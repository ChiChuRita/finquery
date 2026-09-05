"""The turns running right now: one task per conversation, and its chunks kept for whoever attaches.

A turn used to be the HTTP request that started it. Dropping the connection four seconds in
took the run down with it and left nothing behind, not even the question, which for a two
minute import or a twenty minute PDF is a real loss (ticket 33).

So the run is a task the app owns and the response is one subscriber. Every chunk the run
produces is appended to the turn's buffer; a subscriber replays what is already there and then
follows the live ones. A client that goes away unsubscribes and nothing else. The only things
that end a run are the run itself and Stop.

The buffer is the whole turn, which is a few hundred chunks of text: it lives as long as the
turn does and goes with it. What has to outlive the process is written to the turn row instead,
which is what `partial_parts` is for.
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi.responses import StreamingResponse
from pydantic_ai import CancellationToken
from pydantic_ai.ui import SSE_CONTENT_TYPE
from pydantic_ai.ui.vercel_ai._event_stream import VERCEL_AI_DSP_HEADERS
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    DataChunk,
    ReasoningDeltaChunk,
    ReasoningEndChunk,
    ReasoningStartChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
    ToolInputAvailableChunk,
    ToolOutputAvailableChunk,
)

SDK_VERSION = 7
"""The AI SDK protocol version both endpoints speak. See ADR 0001."""


@dataclass
class RunningTurn:
    """One turn being produced, with everyone watching it.

    `message_id` is the id the assistant message carries in the stream (the `start` chunk) and
    in the partial turn stored while it runs. They have to be the same string: the AI SDK
    replaces the message it already has when the resumed stream names it, and pushes a second
    one when it does not.
    """

    message_id: str
    token: CancellationToken = field(default_factory=CancellationToken)
    finished: asyncio.Event = field(default_factory=asyncio.Event)
    """Set when the run is over and the turn has been written, which is what Stop waits for."""
    chunks: list[BaseChunk] = field(default_factory=list)
    task: asyncio.Task[None] | None = None
    """The run itself, held so that nothing collects a task nobody is awaiting."""
    _changed: asyncio.Event = field(default_factory=asyncio.Event)

    def push(self, chunk: BaseChunk) -> None:
        self.chunks.append(chunk)
        self._wake()

    def close(self) -> None:
        self.finished.set()
        self._wake()

    def _wake(self) -> None:
        # A fresh event for the next wait: whoever is sleeping on this one is woken by it, reads
        # what arrived, and then waits on the new one.
        self._changed.set()
        self._changed = asyncio.Event()

    async def follow(self) -> AsyncIterator[BaseChunk]:
        """What is already here, then what comes, until the run ends.

        A second subscriber (a reload, a second tab, the reattach after a switch) gets the whole
        turn from its first chunk, which is why the buffer is kept rather than fanned out: the
        stream the client parses is the same stream from the same start, whenever it arrives.
        """
        index = 0
        while True:
            while index < len(self.chunks):
                yield self.chunks[index]
                index += 1
            if self.finished.is_set():
                return
            await self._changed.wait()


async def _sse(chunks: AsyncIterator[BaseChunk]) -> AsyncIterator[str]:
    """The AI SDK's wire format, which is `VercelAIEventStream.encode_event` for one chunk.

    The adapter encodes its own stream, but a reattaching client never sent a request, so there
    is no adapter for it. One helper for both endpoints keeps the two byte for byte the same.
    """
    async for chunk in chunks:
        yield f"data: {chunk.encode(SDK_VERSION)}\n\n"


def stream_response(chunks: AsyncIterator[BaseChunk]) -> StreamingResponse:
    return StreamingResponse(_sse(chunks), headers=dict(VERCEL_AI_DSP_HEADERS), media_type=SSE_CONTENT_TYPE)


def partial_parts(chunks: Sequence[BaseChunk]) -> list[dict[str, Any]]:
    """The turn so far as UI message parts, folded out of the chunks that have been streamed.

    Written to the open turn while it runs, so a process that dies mid-answer leaves the thinking
    and the tool steps it had got to rather than the question alone. It is deliberately the same
    shape `VercelAIAdapter.dump_messages` produces for a finished turn, because the transcript
    renders both with the same components.

    Transient parts (import progress) are left out: they are the counting, not the result, and
    the finished turn has never carried them.
    """
    parts: list[dict[str, Any]] = []
    # A text or reasoning block is one part that grows, so its deltas have to find it again.
    blocks: dict[tuple[str, str], dict[str, Any]] = {}
    tools: dict[str, dict[str, Any]] = {}

    def block(kind: str, block_id: str, delta: str | None = None, *, state: str | None = None) -> None:
        part = blocks.get((kind, block_id))
        if part is None:
            part = {"type": kind, "text": "", "state": "streaming"}
            blocks[(kind, block_id)] = part
            parts.append(part)
        if delta is not None:
            part["text"] += delta
        if state is not None:
            part["state"] = state

    for chunk in chunks:
        if isinstance(chunk, TextStartChunk):
            block("text", chunk.id)
        elif isinstance(chunk, TextDeltaChunk):
            block("text", chunk.id, chunk.delta)
        elif isinstance(chunk, TextEndChunk):
            block("text", chunk.id, state="done")
        elif isinstance(chunk, ReasoningStartChunk):
            block("reasoning", chunk.id)
        elif isinstance(chunk, ReasoningDeltaChunk):
            block("reasoning", chunk.id, chunk.delta)
        elif isinstance(chunk, ReasoningEndChunk):
            block("reasoning", chunk.id, state="done")
        elif isinstance(chunk, ToolInputAvailableChunk):
            call: dict[str, Any] = {
                "type": f"tool-{chunk.tool_name}",
                "toolCallId": chunk.tool_call_id,
                "state": "input-available",
                "input": chunk.input,
            }
            parts.append(call)
            tools[chunk.tool_call_id] = call
        elif isinstance(chunk, ToolOutputAvailableChunk):
            if (call := tools.get(chunk.tool_call_id)) is not None:
                call["state"] = "output-available"
                call["output"] = chunk.output
        elif isinstance(chunk, DataChunk) and not chunk.transient:
            parts.append({"type": chunk.type, "data": chunk.data})
    return parts
