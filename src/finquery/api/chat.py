"""Chat and stop endpoints speaking the AI SDK UI message stream.

See docs/adr/0001-pydantic-ai-with-vercel-adapter.md.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from pydantic_ai import CancellationToken
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import DataUIPart
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk, MessageMetadataChunk

from finquery.agent import chat_agent
from finquery.api.conversations import get_conversation_or_404
from finquery.context import (
    Assembly,
    TurnMessages,
    assemble,
    estimate_tokens,
    needs_compression,
    summarize,
    turns_to_fold,
)
from finquery.db import Conversation, Turn, utcnow
from finquery.followups import suggest_followups
from finquery.providers import ProviderNotAvailable

logger = logging.getLogger(__name__)

router = APIRouter()

SDK_VERSION = 7
TITLE_LENGTH = 60
FOLLOWUPS_PART = "data-followups"
CONTEXT_PART = "data-context"


@dataclass
class RunningTurn:
    token: CancellationToken = field(default_factory=CancellationToken)
    finished: asyncio.Event = field(default_factory=asyncio.Event)


def _stored_turns(conversation: Conversation) -> list[TurnMessages]:
    return [
        TurnMessages(
            position=turn.position,
            messages=list(ModelMessagesTypeAdapter.validate_json(turn.model_messages_json)),
            ui_count=len(json.loads(turn.ui_messages_json)),
        )
        for turn in conversation.turns
    ]


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


def _persist_turn(
    request: Request,
    conversation_id: str,
    new_messages: list[ModelMessage],
    slot: str,
    metadata: dict[str, object],
    parts: Sequence[DataUIPart],
) -> None:
    """Store the turn, with the data parts the client saw appended to its assistant message.

    Streaming a part and storing it is one code path, so a reloaded transcript renders exactly
    what the live one did.
    """
    if notes := _audit_notes(new_messages):
        metadata["audit_notes"] = notes
    interrupted = bool(metadata.get("interrupted"))
    ui_messages = VercelAIAdapter.dump_messages(new_messages, sdk_version=SDK_VERSION)
    if ui_messages and ui_messages[-1].role == "assistant":
        ui_messages[-1].metadata = {**(ui_messages[-1].metadata or {}), **metadata}
        ui_messages[-1].parts.extend(parts)
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


def _store_summary(request: Request, conversation_id: str, summary: str, through: int) -> None:
    with request.app.state.session_factory() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return
        conversation.summary = summary
        conversation.summary_through = through
        session.commit()


async def _prompt_for(
    request: Request, conversation_id: str, turns: Sequence[TurnMessages], summary: str | None, through: int
) -> Assembly:
    """This turn's prompt, compressed first when the history has grown past the threshold.

    Compression happens before the answer rather than after it, so the turn that crosses the
    threshold is already the one that runs small. It costs one fast-slot call on that turn.
    """
    state = request.app.state
    assembly = assemble(turns, summary, through)
    if not needs_compression(assembly, state.context_budget):
        return assembly
    folded = turns_to_fold(turns, through)
    try:
        # Sub-agents are pinned to the fast slot whatever the conversation runs on.
        model = state.resolve_model("fast")
    except ProviderNotAvailable:
        logger.warning("cannot compress: the fast slot is unavailable", exc_info=True)
        return assembly
    text = await summarize(model, state.subagent_settings, summary, folded)
    if text is None:
        return assembly
    _store_summary(request, conversation_id, text, folded[-1].position)
    return assemble(turns, text, folded[-1].position)


@router.post("/conversations/{conversation_id}/chat")
async def chat(request: Request, conversation_id: str) -> Response:
    state = request.app.state
    with state.session_factory() as session:
        conversation = get_conversation_or_404(session, conversation_id)
        slot = conversation.model_slot
        turns = _stored_turns(conversation)
        summary, summary_through = conversation.summary, conversation.summary_through

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

    prompt = await _prompt_for(request, conversation_id, turns, summary, summary_through)
    history = prompt.history

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
        parts = [DataUIPart(type=CONTEXT_PART, data=_context_stats(turn_messages))]
        if followups:
            parts.append(DataUIPart(type=FOLLOWUPS_PART, data={"suggestions": followups}))
        _persist_turn(request, conversation_id, turn_messages, slot, metadata, parts)
        for part in parts:
            yield DataChunk(type=part.type, data=part.data)
        yield MessageMetadataChunk(message_metadata=metadata)

    async def on_cancel(cancelled: RunCancelled) -> AsyncIterator[BaseChunk]:
        metadata["interrupted"] = True
        close_thinking()
        turn_messages = cancelled.all_messages()[len(history) :]
        # A turn that was cut off gets no follow-ups: the answer it would build on does not exist.
        part = DataUIPart(type=CONTEXT_PART, data=_context_stats(turn_messages))
        _persist_turn(request, conversation_id, turn_messages, slot, metadata, [part])
        yield DataChunk(type=part.type, data=part.data)
        yield MessageMetadataChunk(message_metadata=metadata)

    def _context_stats(turn_messages: Sequence[ModelMessage]) -> dict[str, object]:
        """What the header badge shows: this turn's footprint against the slot's budget.

        `used` is the prompt that was sent plus what the turn produced, which is where the next
        turn's history starts and therefore the number compression is decided on.
        """
        return {
            "used": prompt.tokens + estimate_tokens(turn_messages),
            "budget": state.context_budget,
            "slot": slot,
            # Ticket 13 selects memories into the same prompt and reports how many here.
            "memories": 0,
            "summarized_turns": prompt.summarized_turns,
        }

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
        try:
            async for chunk in adapter.run_stream(
                message_history=history,
                # The rolling summary rides in as a system-level note after the system prompt.
                instructions=prompt.instructions,
                model=model,
                cancellation_token=turn.token,
                on_complete=on_complete,
                on_cancel=on_cancel,
            ):
                # Reasoning duration is measured here because no model reports it.
                if chunk.type == "reasoning-start" and thinking_started is None:
                    thinking_started = time.monotonic()
                elif chunk.type == "reasoning-end":
                    close_thinking()
                yield chunk
        finally:
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
