"""Chat and stop endpoints speaking the AI SDK UI message stream.

See docs/adr/0001-pydantic-ai-with-vercel-adapter.md.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from pydantic_ai import CancellationToken
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import DataUIPart, ReasoningUIPart, UIMessage
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    DataChunk,
    MessageMetadataChunk,
    ReasoningDeltaChunk,
    ReasoningEndChunk,
    ReasoningStartChunk,
)

from finquery.agent import ChatDeps, chat_agent
from finquery.api.conversations import get_conversation_or_404
from finquery.db import Conversation, Turn, utcnow
from finquery.followups import suggest_followups
from finquery.providers import ProviderNotAvailable

router = APIRouter()

SDK_VERSION = 7
TITLE_LENGTH = 60
FOLLOWUPS_PART = "data-followups"
# The reasoning part id the narration of a tool's sub-agents streams under.
NARRATION_ID = "narration"


@dataclass
class RunningTurn:
    token: CancellationToken = field(default_factory=CancellationToken)
    finished: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class Narration:
    """What a tool says while it works, on its way into the thinking panel.

    A tool calls `say` (through `ChatDeps.narrate`) whenever a sub-agent decides something worth
    watching: the chart plan, the rows it got, each repair round. The lines of one tool call
    become one reasoning part, so the transcript shows one panel per call, and the blocks are
    kept with the tool they belong to so a reload can put them back in the same places.
    """

    queue: "asyncio.Queue[tuple[str, Any]]"
    blocks: list[tuple[int, list[str]]] = field(default_factory=list)
    """Per block: how many tool calls the turn had announced when it opened, and its lines."""
    tools: int = 0
    """Tool calls announced so far, counted by the stream loop."""
    open_id: str | None = None

    def say(self, text: str) -> None:
        line = " ".join(text.split())
        if not line:
            return
        if self.open_id is None:
            self.open_id = f"{NARRATION_ID}-{len(self.blocks)}"
            self.blocks.append((self.tools, [line]))
            self.queue.put_nowait(("note", ReasoningStartChunk(id=self.open_id)))
            self.queue.put_nowait(("note", ReasoningDeltaChunk(id=self.open_id, delta=line)))
        else:
            self.blocks[-1][1].append(line)
            self.queue.put_nowait(("note", ReasoningDeltaChunk(id=self.open_id, delta=f"\n{line}")))

    def close(self) -> BaseChunk | None:
        """End the open block. The next chunk the model produces closes it."""
        if self.open_id is None:
            return None
        chunk = ReasoningEndChunk(id=self.open_id)
        self.open_id = None
        return chunk

    def texts(self) -> list[tuple[int, str]]:
        """Each block as the tool call it followed and its text."""
        return [(tools, "\n".join(lines)) for tools, lines in self.blocks]


async def _pump(source: AsyncIterator[BaseChunk], queue: "asyncio.Queue[tuple[str, Any]]") -> None:
    """Move the agent's chunks into the shared queue, so narration can slip in between them."""
    try:
        async for chunk in source:
            await queue.put(("source", chunk))
    except Exception as exc:  # noqa: BLE001 - re-raised on the consumer side, in order
        await queue.put(("error", exc))
    else:
        await queue.put(("end", None))


def _load_history(conversation: Conversation) -> list[ModelMessage]:
    history: list[ModelMessage] = []
    for turn in conversation.turns:
        history.extend(ModelMessagesTypeAdapter.validate_json(turn.model_messages_json))
    return history


def _user_prompts(messages: Sequence[ModelMessage]) -> list[str]:
    return [
        part.content
        for message in messages
        if message.kind == "request"
        for part in message.parts
        if part.part_kind == "user-prompt" and isinstance(part.content, str)
    ]


def _assistant_text(messages: Sequence[ModelMessage]) -> str:
    return "\n".join(
        part.content
        for message in messages
        if message.kind == "response"
        for part in message.parts
        if part.part_kind == "text"
    )


def _title_from(messages: Sequence[ModelMessage]) -> str | None:
    prompts = _user_prompts(messages)
    if not prompts:
        return None
    text = " ".join(prompts[0].split())
    return text[:TITLE_LENGTH].rstrip() + ("..." if len(text) > TITLE_LENGTH else "")


def _audit_notes(messages: Sequence[ModelMessage]) -> list[dict[str, object]]:
    """Notes a model attached to its response about how the answer was produced.

    The local provider uses this to say that a sub-agent ran on the base weights because its
    LoRA adapter was missing. They ride the turn metadata, so the client sees them live and a
    reload still shows them.
    """
    return [
        note
        for message in messages
        if message.kind == "response" and message.metadata
        for note in message.metadata.get("audit_notes", [])
    ]


def _one_assistant_message(ui_messages: list[UIMessage]) -> list[UIMessage]:
    """Fold a turn's model responses into one assistant message, the way the stream shows it.

    A tool call ends a model response, so a turn with tools dumps as several assistant
    messages. The live transcript renders the whole turn as one message (thinking, tool steps,
    answer), and turn metadata such as the thinking duration and the follow-up part belong to
    that one message, so a reload has to see the same shape.
    """
    folded: list[UIMessage] = []
    for message in ui_messages:
        if folded and message.role == "assistant" and folded[-1].role == "assistant":
            folded[-1].parts.extend(message.parts)
            continue
        folded.append(message)
    return folded


def _insert_narration(parts: list[Any], narration: list[tuple[int, str]]) -> None:
    """Put each tool's narration back where the live stream showed it: after that tool's step.

    The narration is not part of the model's messages, so the dump cannot carry it. Live, a block
    arrives while its tool is running, which is after the tool part and before whatever the model
    thought or said next. Blocks are inserted from the back so the earlier positions still hold.
    """
    tool_parts = [index for index, part in enumerate(parts) if part.type.startswith("tool-")]
    for tools, text in reversed(narration):
        # `tools` counts the calls announced when the block opened, so the last of them owns it.
        after = tool_parts[tools - 1] + 1 if 0 < tools <= len(tool_parts) else len(parts)
        parts.insert(after, ReasoningUIPart(text=text, state="done"))


def _persist_turn(
    request: Request,
    conversation_id: str,
    new_messages: list[ModelMessage],
    slot: str,
    metadata: dict[str, object],
    followups: list[str],
    narration: list[tuple[int, str]] | None = None,
) -> None:
    if notes := _audit_notes(new_messages):
        metadata["audit_notes"] = notes
    interrupted = bool(metadata.get("interrupted"))
    ui_messages = _one_assistant_message(VercelAIAdapter.dump_messages(new_messages, sdk_version=SDK_VERSION))
    if ui_messages and ui_messages[-1].role == "assistant":
        ui_messages[-1].metadata = {**(ui_messages[-1].metadata or {}), **metadata}
        if narration:
            _insert_narration(ui_messages[-1].parts, narration)
        if followups:
            ui_messages[-1].parts.append(DataUIPart(type=FOLLOWUPS_PART, data={"suggestions": followups}))
    with request.app.state.session_factory() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return
        conversation.turns.append(
            Turn(
                position=len(conversation.turns),
                model_slot=slot,
                interrupted=interrupted,
                model_messages_json=ModelMessagesTypeAdapter.dump_json(new_messages).decode(),
                ui_messages_json=json.dumps([m.model_dump(by_alias=True, mode="json") for m in ui_messages]),
            )
        )
        if conversation.title == "New chat" and (title := _title_from(new_messages)):
            conversation.title = title
        conversation.updated_at = utcnow()
        session.commit()


@router.post("/conversations/{conversation_id}/chat")
async def chat(request: Request, conversation_id: str) -> Response:
    state = request.app.state
    with state.session_factory() as session:
        conversation = get_conversation_or_404(session, conversation_id)
        slot = conversation.model_slot
        # The conversation owns the profile: every tool in this turn stays inside it.
        profile_id = conversation.profile_id
        history = _load_history(conversation)

    running: dict[str, RunningTurn] = state.running_turns
    if conversation_id in running:
        raise HTTPException(status_code=409, detail="A turn is already running for this conversation")

    try:
        model = state.resolve_model(slot)
    except ProviderNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        adapter = await VercelAIAdapter.from_request(request, agent=chat_agent, sdk_version=SDK_VERSION)
    except ValidationError as exc:
        return Response(content=exc.json(), media_type="application/json", status_code=422)
    # The server owns the history: only the newest client message is appended to it.
    adapter.run_input.messages = adapter.run_input.messages[-1:]

    # Narration is pushed into the same queue the agent's chunks travel through, so a
    # sub-agent's line reaches the client while the tool is still running.
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    narration = Narration(queue=queue)
    deps = ChatDeps(
        session_factory=state.session_factory,
        profile_id=profile_id,
        resolve_model=state.resolve_model,
        subagent_settings=state.subagent_settings,
        narrate=narration.say,
    )
    turn = RunningTurn()
    running[conversation_id] = turn
    # Stored on the assistant UI message and echoed to the client at the end of the turn.
    metadata: dict[str, object] = {"model_slot": slot}
    thinking_started: float | None = None

    # The adapter feeds the client's message in through message_history, so new_messages() would
    # miss it. Everything after the server-side history is this turn.
    async def on_complete(result: AgentRunResult) -> AsyncIterator[BaseChunk]:
        turn_messages = result.all_messages()[len(history) :]
        followups = await _followups(turn_messages)
        _persist_turn(
            request, conversation_id, turn_messages, slot, metadata, followups, narration.texts()
        )
        if followups:
            yield DataChunk(type=FOLLOWUPS_PART, data={"suggestions": followups})
        yield MessageMetadataChunk(message_metadata=metadata)

    async def on_cancel(cancelled: RunCancelled) -> AsyncIterator[BaseChunk]:
        metadata["interrupted"] = True
        close_thinking()
        # A turn that was cut off gets no follow-ups: the answer it would build on does not exist.
        _persist_turn(
            request,
            conversation_id,
            cancelled.all_messages()[len(history) :],
            slot,
            metadata,
            [],
            narration.texts(),
        )
        yield MessageMetadataChunk(message_metadata=metadata)

    async def _followups(turn_messages: Sequence[ModelMessage]) -> list[str]:
        prompts = _user_prompts(turn_messages)
        if not prompts:
            return []
        # Sub-agents are pinned to the fast slot whatever the conversation runs on.
        return await suggest_followups(
            state.resolve_model("fast"), state.subagent_settings, prompts[-1], _assistant_text(turn_messages)
        )

    def close_thinking() -> None:
        nonlocal thinking_started
        if thinking_started is not None:
            metadata["thinking_seconds"] = round(time.monotonic() - thinking_started, 1)
            thinking_started = None

    async def stream() -> AsyncIterator[BaseChunk]:
        nonlocal thinking_started
        source = adapter.run_stream(
            message_history=history,
            model=model,
            deps=deps,
            cancellation_token=turn.token,
            on_complete=on_complete,
            on_cancel=on_cancel,
        )
        pump = asyncio.create_task(_pump(source, queue))
        try:
            while True:
                kind, item = await queue.get()
                if kind == "note":
                    yield item
                    continue
                # Anything the model produces closes the narration block before it.
                if (end := narration.close()) is not None:
                    yield end
                if kind == "end":
                    return
                if kind == "error":
                    raise item
                # Reasoning duration is measured here because no model reports it. Narration is
                # not the model thinking, so it never enters the measurement.
                if item.type == "reasoning-start" and thinking_started is None:
                    thinking_started = time.monotonic()
                elif item.type == "reasoning-end":
                    close_thinking()
                elif item.type == "tool-input-available":
                    # Which tool step a narration block belongs to, for the reload.
                    narration.tools += 1
                yield item
        finally:
            pump.cancel()
            running.pop(conversation_id, None)
            turn.finished.set()

    return adapter.streaming_response(stream())


@router.post("/conversations/{conversation_id}/stop")
async def stop(request: Request, conversation_id: str) -> dict[str, bool]:
    running: dict[str, RunningTurn] = request.app.state.running_turns
    turn = running.get(conversation_id)
    if turn is None:
        return {"stopped": False}
    turn.token.cancel()
    # Wait for the partial turn to be persisted so a reload right after stop shows it.
    try:
        await asyncio.wait_for(turn.finished.wait(), timeout=10)
    except TimeoutError:
        pass
    return {"stopped": True}
