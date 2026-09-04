"""Chat and stop endpoints speaking the AI SDK UI message stream.

See docs/adr/0001-pydantic-ai-with-vercel-adapter.md.
"""

import asyncio
import json
import logging
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
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter, ModelResponse, ToolReturnPart
from pydantic_ai.tools import DeferredToolResults
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from pydantic_ai.ui.vercel_ai.request_types import (
    DataUIPart,
    FileUIPart,
    ReasoningUIPart,
    ToolOutputAvailablePart,
    UIMessage,
)
from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    DataChunk,
    MessageMetadataChunk,
    ReasoningDeltaChunk,
    ReasoningEndChunk,
    ReasoningStartChunk,
)
from sqlalchemy.orm import Session, sessionmaker

from finquery.agent import ChatDeps, chat_agent
from finquery.api.attachments import store_uploads, take_uploads, turn_chips
from finquery.api.conversations import get_conversation_or_404
from finquery.attachments import AttachmentRejected
from finquery.context import (
    Assembly,
    TurnMessages,
    assemble,
    estimate_tokens,
    needs_compression,
    summarize,
    turns_to_fold,
)
from finquery.db import Conversation, Turn, new_id, utcnow
from finquery.followups import suggest_followups
from finquery.memory import MemoryBlock, add_memory, build_memory_block, distill_memories, list_memories
from finquery.providers import ProviderNotAvailable

logger = logging.getLogger(__name__)

router = APIRouter()

SDK_VERSION = 7
TITLE_LENGTH = 60
FOLLOWUPS_PART = "data-followups"
CONTEXT_PART = "data-context"
"""What the turn used of the model's context: tokens against the budget, the slot, how many
memories it carried and how many turns the rolling summary stands in for."""
POST_TURN_TIMEOUT = 30
"""Seconds the follow-up and distillation steps together may take after an answer."""
# The reasoning part id the narration of a tool's sub-agents streams under.
NARRATION_ID = "narration"


@dataclass
class RunningTurn:
    token: CancellationToken = field(default_factory=CancellationToken)
    finished: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass(frozen=True)
class History:
    """The conversation as it is stored: turn by turn, plus what the last turn was made of.

    The turns stay separate because the prompt is assembled from them rather than from one flat
    list: past the threshold the older ones are replaced by the rolling summary.

    The last turn matters because a deferred tool call (`ask_user`) ends a turn with the call
    still open. When the answer arrives, the same turn continues, so it is rewritten with both
    halves instead of a second turn being appended.
    """

    turns: list[TurnMessages]
    last_turn_id: str | None = None
    last_turn_length: int = 0

    @property
    def messages(self) -> list[ModelMessage]:
        """Every stored message, whether or not this turn's prompt still carries it."""
        return [message for turn in self.turns for message in turn.messages]

    @property
    def open_tool_calls(self) -> dict[str, str]:
        """Tool calls of the last response that never got a result, id to tool name."""
        messages = self.messages
        answered = {
            part.tool_call_id
            for message in messages
            if message.kind == "request"
            for part in message.parts
            if isinstance(part, ToolReturnPart)
        }
        last = next((m for m in reversed(messages) if isinstance(m, ModelResponse)), None)
        if last is None:
            return {}
        return {call.tool_call_id: call.tool_name for call in last.tool_calls if call.tool_call_id not in answered}


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


def load_history(conversation: Conversation) -> History:
    """The stored turns of a conversation, ready to become one turn's prompt.

    Also read by the answer A/B, which reruns one turn against the history it had.
    """
    turns: list[TurnMessages] = []
    last_id: str | None = None
    last_length = 0
    for turn in conversation.turns:
        messages = list(ModelMessagesTypeAdapter.validate_json(turn.model_messages_json))
        turns.append(
            TurnMessages(
                position=turn.position,
                messages=messages,
                ui_count=len(json.loads(turn.ui_messages_json)),
            )
        )
        last_id, last_length = turn.id, len(messages)
    return History(turns=turns, last_turn_id=last_id, last_turn_length=last_length)


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


def _latest_user_text(messages: Sequence[UIMessage]) -> str:
    """The message this turn is answering, as the keyword source for memory selection."""
    for message in reversed(messages):
        if message.role == "user":
            return " ".join(part.text for part in message.parts if part.type == "text")
    return ""


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


def persist_turn(
    session_factory: sessionmaker[Session],
    conversation_id: str,
    messages: list[ModelMessage],
    *,
    slot: str,
    metadata: dict[str, object] | None = None,
    data_parts: Sequence[DataUIPart] = (),
    attachments: Sequence[FileUIPart] = (),
    replaces: str | None = None,
    narration: Sequence[tuple[int, str]] = (),
) -> str:
    """Store one turn as both message families: what the model sees and what the UI renders.

    The data parts the client saw streamed are appended to the turn's assistant message, so
    streaming a part and storing it is one code path and a reloaded transcript renders exactly
    what the live one did. `attachments` are the same idea on the user's side: the file parts
    were taken out of the request so the bytes would stay out of the prompt, and these chips put
    them back into the transcript.

    `replaces` rewrites an existing turn instead of appending one. That is how a turn which
    ended on a pending `ask_user` call becomes whole once the answer arrives: the messages of
    both halves are dumped together, so the tool part carries its output and the reload shows
    the answered card.

    Also used by the Import page's review conversation, which seeds a turn nobody streamed.

    Returns the id of the stored turn. It rides the assistant message's metadata as well, so a
    rating can name the turn it is about whether the transcript was streamed or reloaded
    (`finquery.preferences`).
    """
    turn_id = new_id()
    metadata = {**(metadata or {}), "turn_id": turn_id}
    if notes := _audit_notes(messages):
        metadata["audit_notes"] = notes
    interrupted = bool(metadata.get("interrupted"))
    ui_messages = _one_assistant_message(
        VercelAIAdapter.dump_messages(_renderable(messages), sdk_version=SDK_VERSION)
    )
    if ui_messages and ui_messages[-1].role == "assistant":
        ui_messages[-1].metadata = {**(ui_messages[-1].metadata or {}), **metadata}
        if narration:
            _insert_narration(ui_messages[-1].parts, narration)
        ui_messages[-1].parts.extend(data_parts)
    if attachments and (user := next((m for m in ui_messages if m.role == "user"), None)) is not None:
        user.parts.extend(attachments)
    with session_factory() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return turn_id
        if replaces is not None and (previous := session.get(Turn, replaces)) is not None:
            conversation.turns.remove(previous)
        conversation.turns.append(
            Turn(
                id=turn_id,
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
    return turn_id


def _store_summary(request: Request, conversation_id: str, summary: str, through: int) -> None:
    with request.app.state.session_factory() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return
        conversation.summary = summary
        conversation.summary_through = through
        session.commit()


async def _prompt_for(
    request: Request,
    conversation_id: str,
    turns: Sequence[TurnMessages],
    summary: str | None,
    through: int,
    memory: MemoryBlock,
) -> Assembly:
    """This turn's prompt, compressed first when the history has grown past the threshold.

    Compression happens before the answer rather than after it, so the turn that crosses the
    threshold is already the one that runs small. It costs one fast-slot call on that turn.

    The selected memories go through `assemble` with everything else, so they are inside the
    number the compression decision and the badge are both read from. A turn resumed from a
    Question card comes through here too, so a pending card is answered with the same prompt
    shape as a typed message.
    """
    state = request.app.state
    assembly = assemble(turns, summary, through, memory)
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
    return assemble(turns, text, folded[-1].position, memory)


@router.post("/conversations/{conversation_id}/chat")
async def chat(request: Request, conversation_id: str) -> Response:
    state = request.app.state
    with state.session_factory() as session:
        conversation = get_conversation_or_404(session, conversation_id)
        slot = conversation.model_slot
        # The conversation owns the profile: every tool in this turn stays inside it.
        profile_id = conversation.profile_id
        stored = load_history(conversation)
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

    # A client-side tool answering an open call resumes the run that asked, so the request
    # carries a tool result rather than a new prompt: nothing of the client's is appended to
    # the history, and the pending turn is rewritten with both halves.
    answers = _tool_outputs(adapter.run_input.messages, stored.open_tool_calls)
    results = DeferredToolResults(calls=dict(answers)) if answers else None
    replaces = stored.last_turn_id if answers else None
    # The server owns the history: only the newest client message is appended to it.
    adapter.run_input.messages = [] if answers else adapter.run_input.messages[-1:]

    # Attachments are taken out of the message before the agent is given it: the bytes are
    # stored per conversation and read by `import_file`, and only chips travel into the
    # transcript. The position they are stored under is the turn being written, which a
    # rewritten turn keeps, so answering a card does not lose the chip.
    turn_position = max(0, len(stored.turns) - 1) if answers else len(stored.turns)
    try:
        uploads = take_uploads(adapter.run_input.messages)
        with state.session_factory() as session:
            if uploads:
                store_uploads(session, profile_id, conversation_id, turn_position, uploads)
            chips = turn_chips(session, conversation_id, turn_position)
    except AttachmentRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Narration is pushed into the same queue the agent's chunks travel through, so a
    # sub-agent's line reaches the client while the tool is still running.
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    narration = Narration(queue=queue)
    if answers:
        # The pending half of the turn already has tool steps; new narration follows them.
        narration.tools = sum(
            len(m.tool_calls) for m in stored.turns[-1].messages if isinstance(m, ModelResponse)
        )

    deps = ChatDeps(
        session_factory=state.session_factory,
        profile_id=profile_id,
        conversation_id=conversation_id,
        resolve_model=state.resolve_model,
        subagent_settings=state.subagent_settings,
        narrate=narration.say,
        web_client=state.web_client,
    )

    # The one place memory enters the prompt: the block is handed to the assembly, which joins
    # it to the rolling summary and hands both back as this turn's run instructions. A turn
    # resumed from a Question card brings no new message, so its memories are selected for the
    # prompt the pending turn started with.
    question = _latest_user_text(adapter.run_input.messages)
    if not question:
        question = next(reversed(_user_prompts(stored.messages)), "")
    with state.session_factory() as session:
        memory_block = build_memory_block(session, profile_id, question)
    prompt = await _prompt_for(request, conversation_id, stored.turns, summary, summary_through, memory_block)
    history = prompt.history
    # Where the turn being written starts in the run's messages. Answering a deferred call
    # continues the pending turn, so it starts where that turn started, not at the end of the
    # prompt. Compression never folds the pending turn away: it is the newest one.
    turn_start = max(0, len(history) - stored.last_turn_length) if answers else len(history)

    turn = RunningTurn()
    running[conversation_id] = turn
    # Stored on the assistant UI message and echoed to the client at the end of the turn.
    metadata: dict[str, object] = {"model_slot": slot}
    thinking_started: float | None = None

    # The adapter feeds the client's message in through message_history, so new_messages() would
    # miss it. Everything after the server-side history is what this request produced; the turn
    # being persisted can start earlier when a pending call is being answered.
    async def on_complete(result: AgentRunResult) -> AsyncIterator[BaseChunk]:
        messages = result.all_messages()
        turn_messages, produced = messages[turn_start:], messages[len(history) :]
        # Two post-turn steps on the fast slot, side by side: neither is worth waiting for twice.
        # Nobody is waiting on either, and a model that loops on one of them would otherwise
        # hold the finished answer hostage, so the whole pair is on a clock.
        try:
            followups, _ = await asyncio.wait_for(
                asyncio.gather(_followups(produced), _distill(produced)), POST_TURN_TIMEOUT
            )
        except TimeoutError:
            logger.warning("post-turn steps timed out after %s s", POST_TURN_TIMEOUT)
            followups = []
        data_parts = [DataUIPart(type=CONTEXT_PART, data=_context_stats(produced))]
        if followups:
            data_parts.append(DataUIPart(type=FOLLOWUPS_PART, data={"suggestions": followups}))
        store(turn_messages, data_parts)
        for part in data_parts:
            yield DataChunk(type=part.type, data=part.data)
        yield MessageMetadataChunk(message_metadata=metadata)

    async def on_cancel(cancelled: RunCancelled) -> AsyncIterator[BaseChunk]:
        metadata["interrupted"] = True
        close_thinking()
        messages = cancelled.all_messages()
        # A turn that was cut off gets no follow-ups and nothing distilled: the answer they
        # would build on does not exist. What it was given is still reported.
        part = DataUIPart(type=CONTEXT_PART, data=_context_stats(messages[len(history) :]))
        store(messages[turn_start:], [part])
        yield DataChunk(type=part.type, data=part.data)
        yield MessageMetadataChunk(message_metadata=metadata)

    def store(turn_messages: list[ModelMessage], data_parts: Sequence[DataUIPart]) -> None:
        # The turn's id goes back to the client in the metadata chunk that follows, so the
        # thumbs on this answer can name the turn they rate without a reload.
        metadata["turn_id"] = persist_turn(
            state.session_factory,
            conversation_id,
            turn_messages,
            slot=slot,
            metadata=metadata,
            data_parts=data_parts,
            attachments=chips,
            replaces=replaces,
            narration=narration.texts(),
        )

    def _context_stats(produced: Sequence[ModelMessage]) -> dict[str, object]:
        """What the header badge shows: this turn's footprint against the slot's budget.

        `used` is the prompt that was sent plus what the request produced, which is where the
        next turn's history starts and therefore the number compression is decided on.
        """
        return {
            "used": prompt.tokens + estimate_tokens(produced),
            "budget": state.context_budget,
            "slot": slot,
            # The memories the assembly put in the prompt, which the badge and the chip on the
            # answer both read.
            "memories": prompt.memories,
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

    async def _distill(turn_messages: Sequence[ModelMessage]) -> None:
        """Keep what this exchange established, so the next conversation starts knowing it."""
        prompts = _user_prompts(turn_messages)
        answer = _assistant_text(turn_messages)
        if not prompts or not answer.strip():
            return
        with state.session_factory() as session:
            known = [memory.text for memory in list_memories(session, profile_id)]
        facts = await distill_memories(
            state.resolve_model("fast"), state.subagent_settings, prompts[-1], answer, known
        )
        if not facts:
            return
        with state.session_factory() as session:
            for fact in facts:
                # add_memory drops anything the profile already knows, so a repeated exchange
                # does not grow the list.
                add_memory(
                    session,
                    profile_id,
                    fact.text,
                    kind=fact.kind,
                    source="distilled",
                    created_from=conversation_id,
                )
            session.commit()

    def close_thinking() -> None:
        nonlocal thinking_started
        if thinking_started is not None:
            metadata["thinking_seconds"] = round(time.monotonic() - thinking_started, 1)
            thinking_started = None

    async def stream() -> AsyncIterator[BaseChunk]:
        nonlocal thinking_started
        source = adapter.run_stream(
            message_history=history,
            # The summary and the memories ride in as one system-level note after the
            # agent's own system prompt.
            instructions=prompt.instructions,
            deferred_tool_results=results,
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
