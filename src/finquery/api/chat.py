"""Chat and stop endpoints speaking the AI SDK UI message stream.

See docs/adr/0001-pydantic-ai-with-vercel-adapter.md.
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from pydantic_ai import CancellationToken
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse, ToolReturnPart
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import DataUIPart, ToolOutputAvailablePart, UIMessage
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk, DataChunk, MessageMetadataChunk
from sqlalchemy.orm import Session, sessionmaker

from finquery.agent import ChatDeps, chat_agent
from finquery.api.conversations import get_conversation_or_404
from finquery.db import Conversation, Turn, utcnow
from finquery.followups import suggest_followups
from finquery.providers import ProviderNotAvailable

router = APIRouter()

SDK_VERSION = 7
TITLE_LENGTH = 60
FOLLOWUPS_PART = "data-followups"


@dataclass
class RunningTurn:
    token: CancellationToken = field(default_factory=CancellationToken)
    finished: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(frozen=True)
class History:
    """The conversation as the agent sees it, plus what the last turn was made of.

    The last turn matters because a deferred tool call (`ask_user`) ends a turn with the call
    still open. When the answer arrives, the same turn continues, so it is rewritten with both
    halves instead of a second turn being appended.
    """

    messages: list[ModelMessage]
    last_turn_id: str | None = None
    last_turn_length: int = 0

    @property
    def open_tool_calls(self) -> dict[str, str]:
        """Tool calls of the last response that never got a result, id to tool name."""
        answered = {
            part.tool_call_id
            for message in self.messages
            if message.kind == "request"
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        }
        last = next((m for m in reversed(self.messages) if isinstance(m, ModelResponse)), None)
        if last is None:
            return {}
        return {call.tool_call_id: call.tool_name for call in last.tool_calls if call.tool_call_id not in answered}


def _load_history(conversation: Conversation) -> History:
    messages: list[ModelMessage] = []
    last_id: str | None = None
    last_length = 0
    for turn in conversation.turns:
        turn_messages = ModelMessagesTypeAdapter.validate_json(turn.model_messages_json)
        messages.extend(turn_messages)
        last_id, last_length = turn.id, len(turn_messages)
    return History(messages=messages, last_turn_id=last_id, last_turn_length=last_length)


def _tool_outputs(messages: Sequence[UIMessage], wanted: dict[str, str]) -> dict[str, object]:
    """The results the browser sent for tool calls the server left open.

    A client-side tool answers on the next request: `useChat` puts the output on the assistant
    message it belongs to and sends that message. Anything that does not match an open call of
    this conversation is ignored, so a stale or invented output cannot resolve anything.
    """
    return {
        part.tool_call_id: part.output
        for message in messages
        if message.role == "assistant"
        for part in message.parts
        if isinstance(part, ToolOutputAvailablePart) and part.tool_call_id in wanted
    }


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


def _renderable(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Drop the requests that only exist to make the model try again.

    A response with nothing but thinking earns a retry prompt, which is a `ModelRequest` the
    dump turns into a user text part: the transcript would show "Validation feedback: Please
    return text or call a tool" as if the user had typed it. The model history keeps it, the
    UI messages do not. A retry that belongs to a tool call keeps its `tool_name` and stays,
    because that one renders as the tool step's error.
    """
    return [
        message
        for message in messages
        if not (
            message.kind == "request"
            and message.parts
            and all(part.part_kind == "retry-prompt" and part.tool_name is None for part in message.parts)
        )
    ]


def persist_turn(
    session_factory: sessionmaker[Session],
    conversation_id: str,
    messages: list[ModelMessage],
    *,
    slot: str,
    metadata: dict[str, object] | None = None,
    followups: Sequence[str] = (),
    replaces: str | None = None,
) -> None:
    """Store one turn as both message families: what the model sees and what the UI renders.

    `replaces` rewrites an existing turn instead of appending one. That is how a turn which
    ended on a pending `ask_user` call becomes whole once the answer arrives: the messages of
    both halves are dumped together, so the tool part carries its output and the reload shows
    the answered card.

    Also used by the Import page's review conversation, which seeds a turn nobody streamed.
    """
    metadata = dict(metadata or {})
    if notes := _audit_notes(messages):
        metadata["audit_notes"] = notes
    interrupted = bool(metadata.get("interrupted"))
    ui_messages = _one_assistant_message(
        VercelAIAdapter.dump_messages(_renderable(messages), sdk_version=SDK_VERSION)
    )
    if ui_messages and ui_messages[-1].role == "assistant":
        ui_messages[-1].metadata = {**(ui_messages[-1].metadata or {}), **metadata}
        if followups:
            ui_messages[-1].parts.append(DataUIPart(type=FOLLOWUPS_PART, data={"suggestions": list(followups)}))
    with session_factory() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return
        if replaces is not None and (previous := session.get(Turn, replaces)) is not None:
            conversation.turns.remove(previous)
        conversation.turns.append(
            Turn(
                position=len(conversation.turns),
                model_slot=slot,
                interrupted=interrupted,
                model_messages_json=ModelMessagesTypeAdapter.dump_json(messages).decode(),
                ui_messages_json=json.dumps([m.model_dump(by_alias=True, mode="json") for m in ui_messages]),
            )
        )
        if conversation.title == "New chat" and (title := _title_from(messages)):
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

    # A client-side tool answering an open call resumes the run that asked, so the request
    # carries a tool result rather than a new prompt: nothing of the client's is appended to
    # the history, and the pending turn is rewritten with both halves.
    answers = _tool_outputs(adapter.run_input.messages, history.open_tool_calls)
    results = DeferredToolResults(calls=dict(answers)) if answers else None
    replaces = history.last_turn_id if answers else None
    turn_start = len(history.messages) - history.last_turn_length if answers else len(history.messages)
    # The server owns the history: only the newest client message is appended to it.
    adapter.run_input.messages = [] if answers else adapter.run_input.messages[-1:]

    deps = ChatDeps(
        session_factory=state.session_factory,
        profile_id=profile_id,
        resolve_model=state.resolve_model,
        subagent_settings=state.subagent_settings,
    )
    turn = RunningTurn()
    running[conversation_id] = turn
    # Stored on the assistant UI message and echoed to the client at the end of the turn.
    metadata: dict[str, object] = {"model_slot": slot}
    thinking_started: float | None = None

    # The adapter feeds the client's message in through message_history, so new_messages() would
    # miss it. Everything after the server-side history is this turn.
    async def on_complete(result: AgentRunResult) -> AsyncIterator[BaseChunk]:
        turn_messages = result.all_messages()[turn_start:]
        followups = await _followups(turn_messages)
        store(turn_messages, followups)
        if followups:
            yield DataChunk(type=FOLLOWUPS_PART, data={"suggestions": followups})
        yield MessageMetadataChunk(message_metadata=metadata)

    async def on_cancel(cancelled: RunCancelled) -> AsyncIterator[BaseChunk]:
        metadata["interrupted"] = True
        close_thinking()
        # A turn that was cut off gets no follow-ups: the answer it would build on does not exist.
        store(cancelled.all_messages()[turn_start:], [])
        yield MessageMetadataChunk(message_metadata=metadata)

    def store(turn_messages: list[ModelMessage], followups: list[str]) -> None:
        persist_turn(
            state.session_factory,
            conversation_id,
            turn_messages,
            slot=slot,
            metadata=metadata,
            followups=followups,
            replaces=replaces,
        )

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
                message_history=history.messages,
                deferred_tool_results=results,
                model=model,
                deps=deps,
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
