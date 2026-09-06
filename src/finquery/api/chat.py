"""Chat and stop endpoints speaking the AI SDK UI message stream.

See docs/adr/0001-pydantic-ai-with-vercel-adapter.md.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import ValidationError
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.exceptions import RunCancelled
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
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
    ErrorChunk,
    MessageMetadataChunk,
    ReasoningDeltaChunk,
    ReasoningEndChunk,
    ReasoningStartChunk,
    TextDeltaChunk,
    ToolInputAvailableChunk,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from finquery.agent import ChatDeps, chat_agent
from finquery.answers import resolve_answers
from finquery.api.attachments import store_uploads, take_uploads, turn_chips
from finquery.api.conversations import get_conversation_or_404
from finquery.api.running import SDK_VERSION, RunningTurn, partial_parts, stream_response
from finquery.ask_user import ASK_USER
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
from finquery.db import Conversation, Profile, Turn, new_id, utcnow
from finquery.followups import suggest_followups
from finquery.local.gemma import MarkerFilter, strip_channel_lines, strip_markers
from finquery.memory import (
    MemoryBlock,
    absent_names,
    add_memory,
    build_memory_block,
    distill_memories,
    list_memories,
)
from finquery.onboarding import detect_language
from finquery.prose import AnswerCheck, Figures
from finquery.providers import ModelResolver, ProviderNotAvailable

logger = logging.getLogger(__name__)

router = APIRouter()

TITLE_LENGTH = 60
FOLLOWUPS_PART = "data-followups"
CONTEXT_PART = "data-context"
"""What the turn used of the model's context: tokens against the budget, the slot, how many
memories it carried and how many turns the rolling summary stands in for."""
POST_TURN_TIMEOUT = 30
"""Seconds the follow-up and distillation steps together may take after an answer."""
# The reasoning part id the narration of a tool's sub-agents streams under.
NARRATION_ID = "narration"

RETRY_FEEDBACK = "validation feedback"
"""pydantic AI's own retry prompt, quoted back by the model inside its thinking.

A response with nothing but thinking earns a `ModelRequest` reading "Validation feedback:
Please return text or call a tool." `_renderable` keeps that request out of the transcript, but
the next response reasons about it out loud ("the user's previous message 'Validation
feedback...' is likely a system message"), which the review of 2026-09-04 saw on three turns.
The sentence is framework plumbing, so it is dropped from the thinking the user reads, live and
stored.
"""

# One sentence, terminator included, or a last one with no terminator. A newline ends a sentence
# too: a thinking stream is mostly short lines rather than prose.
_SENTENCE = re.compile(r"[^.!?\n]*[.!?\n]+|[^.!?\n]+")
_SENTENCE_ENDS = ".!?\n"


def strip_retry_feedback(text: str) -> str:
    """Drop whole sentences that quote the framework's retry prompt."""
    if RETRY_FEEDBACK not in text.casefold():
        return text
    return "".join(part for part in _SENTENCE.findall(text) if RETRY_FEEDBACK not in part.casefold())


class TextFilter:
    """`MarkerFilter` plus the bare channel-name lines OpenRouter leaves in an answer.

    A line has to be judged whole, so a delta is released only up to its last newline and the
    tail waits for the next one; `flush` releases it when the text part ends. That whole line is
    also what the answer check judges, so a figure no query returned never reaches the reader
    (`finquery.prose`).
    """

    def __init__(self, check: AnswerCheck | None = None) -> None:
        self._markers = MarkerFilter()
        self._held = ""
        self._check = check or AnswerCheck()
        self._started = False

    def feed(self, delta: str) -> str:
        buffer = self._held + self._markers.feed(delta)
        cut = buffer.rfind("\n") + 1
        ready, self._held = buffer[:cut], buffer[cut:]
        return self._release(ready)

    def flush(self) -> str:
        held, self._held = self._held + self._markers.flush(), ""
        return self._release(held)

    def _release(self, text: str) -> str:
        cleaned = self._check.clean(strip_channel_lines(text))
        if self._started:
            return cleaned
        # Every answer of the 9B review began with two blank lines, which is where the thought
        # channel ended rather than anything the model meant to write.
        cleaned = cleaned.lstrip()
        self._started = bool(cleaned)
        return cleaned


class ThinkingFilter:
    """What the text stream's `MarkerFilter` does, for the reasoning stream, plus the retry prompt.

    Chat-template tokens are held back across delta boundaries by `MarkerFilter`. The retry
    sentence has to be judged whole, so a delta is released only up to the last sentence end and
    the tail waits for the next one; `flush` releases it when the block ends.
    """

    def __init__(self) -> None:
        self._markers = MarkerFilter()
        self._held = ""

    def feed(self, delta: str) -> str:
        buffer = self._held + self._markers.feed(delta)
        cut = max((buffer.rfind(end) for end in _SENTENCE_ENDS), default=-1) + 1
        ready, self._held = buffer[:cut], buffer[cut:]
        return strip_retry_feedback(ready)

    def flush(self) -> str:
        held, self._held = self._held + self._markers.flush(), ""
        return strip_retry_feedback(held)


@dataclass(frozen=True)
class History:
    """The conversation as it is stored: turn by turn, each with the id it is stored under.

    The turns stay separate because the prompt is assembled from them rather than from one flat
    list: past the threshold the older ones are replaced by the rolling summary, and a turn
    parked on a Question card is resumed from where that turn ended rather than from the end of
    the conversation.

    A deferred tool call (`ask_user`) ends a turn with the call still open. When the answer
    arrives, that same turn continues, so it is rewritten with both halves instead of a second
    turn being appended. The user may have typed something else in between, so the turn a card
    belongs to is looked up rather than assumed to be the last one (ticket 29).
    """

    turns: list[TurnMessages]
    turn_ids: list[str] = field(default_factory=list)

    @property
    def messages(self) -> list[ModelMessage]:
        """Every stored message, whether or not this turn's prompt still carries it."""
        return [message for turn in self.turns for message in turn.messages]

    @property
    def open_tool_calls(self) -> dict[str, ToolCallPart]:
        """Tool calls of any turn that never got a result, by call id.

        The call itself, not just its name: what the answers to a Question card mean is in the
        call's own arguments (`AskUser.apply`), and that is what `finquery.answers` acts on.

        Every turn, not only the newest: a card the user answers after typing something else is
        an open call two turns back, and the run it parked is still the run that resumes.
        """
        return {call.tool_call_id: call for _, call in self._open_calls()}

    def turn_of(self, call_id: str) -> int | None:
        """Which turn holds that open call, as an index into `turns`."""
        return next((index for index, call in self._open_calls() if call.tool_call_id == call_id), None)

    def _open_calls(self) -> list[tuple[int, ToolCallPart]]:
        """Every call still waiting for a result, with the turn it was made in.

        A result always lands in the turn its call was made in, so a turn is judged on its own
        messages. Only the last response of a turn can still be open: an earlier one was
        answered before the turn could go on.
        """
        found: list[tuple[int, ToolCallPart]] = []
        for index, turn in enumerate(self.turns):
            answered = {
                part.tool_call_id
                for message in turn.messages
                if message.kind == "request"
                for part in message.parts
                if isinstance(part, ToolReturnPart)
            }
            last = next((m for m in reversed(turn.messages) if isinstance(m, ModelResponse)), None)
            if last is None:
                continue
            found.extend((index, call) for call in last.tool_calls if call.tool_call_id not in answered)
        return found


CARD_TOOLS = ("review_batch", "review_duplicates", "import_file", "extract_transaction")
"""The tools that hand the assistant a whole `card` to pass to `ask_user` unchanged.

Named here as well as in the system prompt because the prompt is a request and this is a
guarantee: see `card_the_model_did_not_ask`.
"""


def card_the_model_did_not_ask(produced: Sequence[ModelMessage]) -> dict[str, object] | None:
    """The Question card a tool built and the model wrote about instead of showing.

    `review_batch` returning a queue has to be followed by a card, and the fast model instead
    ended a turn with "There is one merchant left to categorize" and no card below it, which is
    where the demo's review step dies (e2e of 2026-09-05, M1). The card is already built, by the
    same `categorize.review_card` the seeded review conversation uses, so the server shows it
    rather than asking the model again.

    None when the model did call `ask_user` (the run then ends parked on that call anyway), and
    None when no tool of this turn handed one over.
    """
    if any(part.part_kind == "tool-call" and part.tool_name == ASK_USER for m in produced for part in m.parts):
        return None
    cards = [
        part.content["card"]
        for message in produced
        for part in message.parts
        if part.part_kind == "tool-return"
        and part.tool_name in CARD_TOOLS
        and isinstance(part.content, dict)
        and isinstance(part.content.get("card"), dict)
    ]
    return cards[-1] if cards else None


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
    """The stored turns of a conversation, ready to become one turn's prompt."""
    turns: list[TurnMessages] = []
    turn_ids: list[str] = []
    for turn in conversation.turns:
        turns.append(
            TurnMessages(
                position=turn.position,
                messages=list(ModelMessagesTypeAdapter.validate_json(turn.model_messages_json)),
                ui_count=len(json.loads(turn.ui_messages_json)),
            )
        )
        turn_ids.append(turn.id)
    return History(turns=turns, turn_ids=turn_ids)


def _tool_outputs(messages: Sequence[UIMessage], wanted: Mapping[str, ToolCallPart]) -> dict[str, object]:
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


TURN_FAILED = (
    "This turn could not be finished. Your message is still here, so ask again, or pick the "
    "other model in the composer."
)
"""What the transcript says when a run ends in an exception rather than an answer.

The framework's own text ("Stream function must return at least one item") is what reached the
user before, and there is nothing a person can do with it. The detail goes to the server log,
where it belongs, and the partial turn keeps the question with its interrupted marker.
"""

ALREADY_RUNNING = "This chat is still answering. Wait for that turn to finish, or press Stop first."
"""Why a second message is refused while a turn of the same conversation runs.

One turn per conversation: two would interleave in one transcript and the second would be
assembled from a history the first is still writing. The composer is closed while a chat is
answering, in the tab that started the turn and in any other, so this is the tab that has not
noticed yet, and it reaches the reader as this sentence (`lib/api.refusalSentence`).
"""

ALREADY_ANSWERED = "That question has already been answered. Reload the chat to see what it did."
"""Why a second answer to the same Question card is refused.

The card disables itself once it is answered, so this is the other tab, or a browser that never
saw the first answer land. The run it would resume is over: replaying the answers would apply
them twice (a duplicate inserted again, a rule stored again), which is the one thing worse than
saying no.
"""


def _carries_tool_output(messages: Sequence[UIMessage]) -> bool:
    """True when the browser sent this request to answer a tool call rather than to say something."""
    return any(
        isinstance(part, ToolOutputAvailablePart)
        for message in messages
        if message.role == "assistant"
        for part in message.parts
    )


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


def _found_nothing(messages: Sequence[ModelMessage]) -> list[str]:
    """The requests of this turn whose query came back with no rows at all.

    What the turn proved absent. A memory about a person the data does not have survives every
    later conversation and steers it (§10 of the 9B review), so it is never written.
    """
    return [
        str(part.content.get("request") or "")
        for message in messages
        if message.kind == "request"
        for part in message.parts
        if part.part_kind == "tool-return"
        and part.tool_name in ("query", "chart")
        and isinstance(part.content, dict)
        and _held_nothing(part.content.get("rows"))
    ]


def _held_nothing(rows: object) -> bool:
    """No rows at all, or the one row a SUM over nothing returns, whose every value is NULL."""
    if not isinstance(rows, list) or not rows:
        return True
    return all(value is None for row in rows if isinstance(row, dict) for value in row.values())


def _assistant_text(messages: Sequence[ModelMessage]) -> str:
    return "\n".join(
        part.content
        for message in messages
        if message.kind == "response"
        for part in message.parts
        if part.part_kind == "text"
    )


def _shorten(text: str) -> str | None:
    """A conversation title out of the message that opened it."""
    text = " ".join(text.split())
    if not text:
        return None
    return text[:TITLE_LENGTH].rstrip() + ("..." if len(text) > TITLE_LENGTH else "")


def _title_from(messages: Sequence[ModelMessage]) -> str | None:
    prompts = _user_prompts(messages)
    return _shorten(prompts[0]) if prompts else None


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


def _refused_cards(messages: Sequence[ModelMessage]) -> set[str]:
    """The `ask_user` calls the server refused to park the run on.

    A card with nothing answerable on it is sent back as a retry (`ask_user.NOTHING_TO_ANSWER`).
    That call was never drawn and never will be, so leaving it in the transcript would put a
    dead question above the card the model then got right.
    """
    return {
        part.tool_call_id
        for message in messages
        if message.kind == "request"
        for part in message.parts
        if part.part_kind == "retry-prompt" and part.tool_name == ASK_USER
    }


def _renderable(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Drop what only exists to make the model try again.

    A response with nothing but thinking earns a retry prompt, which is a `ModelRequest` the
    dump turns into a user text part: the transcript would show "Validation feedback: Please
    return text or call a tool" as if the user had typed it. The model history keeps it, the
    UI messages do not. A retry that belongs to a tool call keeps its `tool_name` and stays,
    because that one renders as the tool step's error: a refused `set_rule` or changeset is
    something the user should see.

    A refused Question card is the exception, and it goes with its retry: see `_refused_cards`.
    """
    refused = _refused_cards(messages)
    kept: list[ModelMessage] = []
    for message in messages:
        parts = [
            part
            for part in message.parts
            if not (part.part_kind in {"retry-prompt", "tool-call"} and part.tool_call_id in refused)
        ]
        if message.kind == "request" and parts and all(
            part.part_kind == "retry-prompt" and part.tool_name is None for part in parts
        ):
            continue
        if not parts:
            continue
        kept.append(replace(message, parts=parts) if len(parts) != len(message.parts) else message)
    return kept


def collect_figures(messages: Sequence[ModelMessage], figures: Figures | None = None) -> Figures:
    """Every figure these messages carry: what their tools returned, what the user wrote.

    The conversation, not only the turn: quoting back the total of the question before this one
    is reading a figure a query did produce, and a follow-up does it all the time.
    """
    figures = figures or Figures()
    for message in messages:
        for part in message.parts:
            if part.part_kind == "tool-return":
                figures.add_result(part.content)
            elif part.part_kind == "user-prompt" and isinstance(part.content, str):
                figures.add_message(part.content)
    return figures


def _clean_text(messages: Sequence[ModelMessage], check: AnswerCheck) -> None:
    """Take the chat template's own tokens out of what a response carries, text and thinking.

    The stream is filtered on its way to the browser (`MarkerFilter`, `ThinkingFilter`); this is
    the same vocabulary applied to what gets stored, so a reload does not bring `<turn|>` or the
    framework's retry sentence back. The answer check runs here for the same reason: a figure
    that was rewritten on the way out must not come back with the transcript.
    """
    first = True
    for message in messages:
        if message.kind != "response":
            continue
        for part in message.parts:
            if part.part_kind == "text":
                part.content = check.clean(strip_markers(part.content))
                if first:
                    # The answer opens where the model's thought channel closed, which on Qwen is
                    # two blank lines. The stream drops them, and so does the stored copy.
                    part.content, first = part.content.lstrip(), False
            elif part.part_kind == "thinking":
                # The thinking panel survives a reload, so it is cleaned with the same
                # vocabulary the live stream is filtered with (`ThinkingFilter`).
                part.content = strip_retry_feedback(strip_markers(part.content))


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
    model_key: str,
    metadata: dict[str, object] | None = None,
    data_parts: Sequence[DataUIPart] = (),
    attachments: Sequence[FileUIPart] = (),
    replaces: str | None = None,
    narration: Sequence[tuple[int, str]] = (),
    language: str = "en",
    figures: Figures | None = None,
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

    Also used by the review conversation, which seeds a turn nobody streamed.

    Returns the id of the stored turn. It rides the assistant message's metadata as well, so a
    chart card can name the turn it was drawn in whether the transcript was streamed or reloaded
    (`finquery.api.charts`, `finquery.api.dashboard`).
    """
    turn_id = new_id()
    metadata = {**(metadata or {}), "turn_id": turn_id}
    if notes := _audit_notes(messages):
        metadata["audit_notes"] = notes
    interrupted = bool(metadata.get("interrupted"))
    # The same figures the stream judged against (the caller passes them when it has them), plus
    # whatever this turn produced, so the stored answer and the streamed one agree.
    check = AnswerCheck(figures=collect_figures(messages, figures), language=language)
    _clean_text(messages, check)
    if check.rewritten:
        logger.warning(
            "%s figure(s) in the stored answer of conversation %s came from no query and were "
            "replaced with what the tools returned",
            check.rewritten,
            conversation_id,
        )
        metadata["figures_rewritten"] = check.rewritten
    ui_messages = _one_assistant_message(
        VercelAIAdapter.dump_messages(_renderable(messages), sdk_version=SDK_VERSION)
    )
    # Every fragment says which catalog entry produced it, so switching the conversation to
    # another model never relabels a turn that is already on screen (story 10).
    for message in ui_messages:
        if message.role == "assistant":
            message.metadata = {**(message.metadata or {}), "model_key": model_key}
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
        # A rewritten turn keeps its place in the transcript. It is the same turn: the open turn
        # this run started from, or the turn a Question card parked, which the user may have
        # typed past before answering it.
        position = len(conversation.turns)
        if replaces is not None and (previous := session.get(Turn, replaces)) is not None:
            position = previous.position
            conversation.turns.remove(previous)
        conversation.turns.append(
            Turn(
                id=turn_id,
                position=position,
                model_key=model_key,
                interrupted=interrupted,
                finished=True,
                model_messages_json=ModelMessagesTypeAdapter.dump_json(messages).decode(),
                ui_messages_json=json.dumps([m.model_dump(by_alias=True, mode="json") for m in ui_messages]),
            )
        )
        if conversation.title == "New chat" and (title := _title_from(messages)):
            conversation.title = title
        conversation.updated_at = utcnow()
        session.commit()
    return turn_id


def open_turn(
    session_factory: sessionmaker[Session],
    conversation_id: str,
    *,
    model_key: str,
    ui_messages: Sequence[UIMessage],
) -> str | None:
    """Write the turn down before the model is asked anything, without its end marker.

    Two things are lost when a run dies before `persist_turn`: the question the user asked and
    any sign that it was ever asked. A reload during the answer showed the transcript as it was
    before the message was typed, and a server restarted mid-turn left the same hole. So the
    turn exists from the start, holding the user's message, and `finished` is false until the
    run writes it out. Whatever is still open on the next startup was interrupted by definition:
    see `close_open_turns`.

    Returns the id of the open turn, which is what `persist_turn(replaces=...)` rewrites, or
    None when the conversation is gone.
    """
    turn_id = new_id()
    with session_factory() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return None
        conversation.turns.append(
            Turn(
                id=turn_id,
                position=len(conversation.turns),
                model_key=model_key,
                finished=False,
                model_messages_json="[]",
                ui_messages_json=json.dumps([m.model_dump(by_alias=True, mode="json") for m in ui_messages]),
            )
        )
        # The title too, so a conversation whose first turn never finished is still the question
        # that was asked rather than "New chat" in the sidebar for good.
        if conversation.title == "New chat" and (title := _shorten(_latest_user_text(ui_messages))):
            conversation.title = title
        conversation.updated_at = utcnow()
        session.commit()
    return turn_id


def reopen_turn(session_factory: sessionmaker[Session], turn_id: str) -> None:
    """Take the end marker off the turn a Question card answer is about to continue.

    The resumed half rewrites that turn, so from here until it does, the turn is running and is
    recovered like any other open turn if the process dies first.
    """
    with session_factory() as session:
        if (turn := session.get(Turn, turn_id)) is not None:
            turn.finished = False
            session.commit()


PARTIAL_SECONDS = 3.0
"""How long a turn may stream before the open turn row is brought up to date again.

Every tool boundary is written whatever the clock says; between them this is the ceiling, so a
process that dies in the middle of a long answer leaves the paragraph it had written rather
than the question alone. One row, one write: the whole turn is a single column.
"""


def persist_partial(
    session_factory: sessionmaker[Session],
    turn_id: str,
    *,
    message_id: str,
    model_key: str,
    parts: Sequence[dict[str, Any]],
) -> None:
    """Write the turn so far into the open turn, replacing what was written for it before.

    Only the UI messages: the model messages of a turn are what the next prompt is assembled
    from, and half a run is not something to assemble a prompt from. `persist_turn` writes both
    families when the run ends.

    The assistant message keeps `message_id` from the first write to the last, which is the id
    the stream names in its `start` chunk. A browser that reloads mid-turn therefore has the
    same message the reattached stream is about, and replaces it rather than drawing the turn
    twice.
    """
    if not parts:
        return
    with session_factory() as session:
        turn = session.get(Turn, turn_id)
        if turn is None or turn.finished:
            return
        messages = [m for m in json.loads(turn.ui_messages_json) if m.get("id") != message_id]
        messages.append(
            {"id": message_id, "role": "assistant", "parts": list(parts), "metadata": {"model_key": model_key}}
        )
        # `default=str` for the one thing a tool result can carry that JSON cannot: a date. The
        # wire encoder handles those itself, and this is the same objects taking the other road.
        turn.ui_messages_json = json.dumps(messages, default=str)
        session.commit()


def _interrupt(turn: Turn) -> None:
    """Mark one open turn as the interrupted turn it is, so the transcript can say so.

    The assistant side of an interrupted turn may be missing entirely (the run died before it
    wrote anything), and an assistant message is where the transcript hangs the Stopped marker,
    so an empty one is appended for it to hang on. The sentence under it is the browser's
    (`chat-view.InterruptedTurn`), the way a stopped tool step's sentence is.
    """
    turn.interrupted = True
    turn.finished = True
    ui_messages = json.loads(turn.ui_messages_json)
    if ui_messages and ui_messages[-1].get("role") == "assistant":
        last = ui_messages[-1]
        last["metadata"] = {**(last.get("metadata") or {}), "interrupted": True, "turn_id": turn.id}
    else:
        ui_messages.append(
            {
                "id": f"interrupted-{turn.id}",
                "role": "assistant",
                "parts": [],
                "metadata": {"model_key": turn.model_key, "interrupted": True, "turn_id": turn.id},
            }
        )
    turn.ui_messages_json = json.dumps(ui_messages)


def close_open_turns(session_factory: sessionmaker[Session]) -> int:
    """Every turn still without its end marker was interrupted. Run once, at startup.

    A turn is only open while its run is: the run either writes the turn out or closes it on the
    way down. So a turn found open when the process starts belongs to a process that is no
    longer here, and the running-turn registry it was in is empty by construction. Without this
    the conversation would open on a question with nothing under it and no way to tell whether
    an answer was still coming.
    """
    with session_factory() as session:
        open_turns = list(session.scalars(select(Turn).where(Turn.finished.is_(False))).all())
        for turn in open_turns:
            _interrupt(turn)
        session.commit()
    if open_turns:
        logger.warning("%s turn(s) were interrupted by a restart", len(open_turns))
    return len(open_turns)


def close_turn_if_open(session_factory: sessionmaker[Session], turn_id: str | None) -> None:
    """The same recovery, for a run that ends without persisting: the browser hung up.

    A client that reloads or navigates away mid-answer has its request cancelled, and neither
    `on_complete` nor `on_cancel` runs for that: the run is simply dropped. The turn stays as
    the question with the interrupted marker, which is what the next load of the conversation
    shows instead of nothing at all.
    """
    if turn_id is None:
        return
    with session_factory() as session:
        turn = session.get(Turn, turn_id)
        if turn is None or turn.finished:
            return
        _interrupt(turn)
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
    request: Request,
    conversation_id: str,
    turns: Sequence[TurnMessages],
    summary: str | None,
    through: int,
    memory: MemoryBlock,
    resolve: ModelResolver,
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
        # Sub-agents are pinned to the fast slot of the entry's provider, whatever the
        # conversation runs on.
        model = resolve("fast")
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
        model_key = state.models.key_of(conversation.model_key or conversation.model_slot)
        # The conversation owns the profile: every tool in this turn stays inside it.
        profile_id = conversation.profile_id
        stored = load_history(conversation)
        summary, summary_through = conversation.summary, conversation.summary_through
    # Chat on the conversation's catalog entry, sub-agents on the fast slot of that entry's
    # provider. Nothing below this line knows which provider that is. See finquery.catalog.
    resolve = state.models.resolver(model_key)

    running: dict[str, RunningTurn] = state.running_turns
    if conversation_id in running:
        raise HTTPException(status_code=409, detail=ALREADY_RUNNING)

    try:
        model = resolve("chat")
    except ProviderNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # The id of the assistant message this run streams under, chosen here because the partial
    # turn is stored under it too: see `persist_partial`.
    message_id = f"turn-{new_id()}"
    try:
        adapter = await VercelAIAdapter.from_request(
            request, agent=chat_agent, sdk_version=SDK_VERSION, server_message_id=message_id
        )
    except ValidationError as exc:
        return Response(content=exc.json(), media_type="application/json", status_code=422)

    # A client-side tool answering an open call resumes the run that asked, so the request
    # carries a tool result rather than a new prompt: nothing of the client's is appended to
    # the history, and the pending turn is rewritten with both halves.
    open_calls = stored.open_tool_calls
    answers = _tool_outputs(adapter.run_input.messages, open_calls)
    # The turn being answered, which is not always the last one: the user may have asked
    # something else before coming back to the card (ticket 29). Its own run is what resumes,
    # so the prompt ends where that turn ended and the answers of any older card in the same
    # request are left for their own turn.
    card_turn = max((index for call_id in answers if (index := stored.turn_of(call_id)) is not None), default=None)
    if card_turn is not None:
        answers = {call_id: output for call_id, output in answers.items() if stored.turn_of(call_id) == card_turn}
    elif _carries_tool_output(adapter.run_input.messages):
        # Answers for a call this conversation has already closed: a second browser tab on the
        # same card, or a card answered twice. Nothing to resume and nothing to apply again.
        raise HTTPException(status_code=409, detail=ALREADY_ANSWERED)
    if answers:
        # What the answers mean happens here, in code, before the model is asked to continue:
        # the rules of a Question card are stored, a kept duplicate is inserted and
        # categorized, the rows of a reviewed extraction are committed, and the result says
        # what was applied.
        answers = await resolve_answers(
            state.session_factory,
            profile_id,
            conversation_id,
            open_calls,
            answers,
            resolve_model=resolve,
            model_settings=state.subagent_settings,
        )
    results = DeferredToolResults(calls=dict(answers)) if answers else None
    # The half of a turn that resumes from an answered card has nothing to work out: the answers
    # are applied, so it says what happened and asks the next question. It runs with reasoning
    # off for that reason, and because the fast model collapsed into a repetition loop when it
    # was left to think at this boundary (review of 2026-09-04).
    turn_settings = state.subagent_settings if answers else None
    # The server owns the history: only the newest client message is appended to it.
    adapter.run_input.messages = [] if answers else adapter.run_input.messages[-1:]

    # Attachments are taken out of the message before the agent is given it: the bytes are
    # stored per conversation and read by `import_file`, and only chips travel into the
    # transcript. The position they are stored under is the turn being written, which a
    # rewritten turn keeps, so answering a card does not lose the chip.
    turn_position = stored.turns[card_turn].position if card_turn is not None else len(stored.turns)
    try:
        uploads = take_uploads(adapter.run_input.messages)
        # A turn with nothing in it is not a turn: an empty box, a message of only spaces, or a
        # request whose parts are gone. Without this the framework answers "Processed history
        # cannot be empty." into the stream, and a message of spaces spends a model call.
        if not answers and not uploads and not _latest_user_text(adapter.run_input.messages).strip():
            raise HTTPException(
                status_code=422,
                detail="Type a question about your transactions, or drop a file in to import it.",
            )
        with state.session_factory() as session:
            if uploads:
                store_uploads(session, profile_id, conversation_id, turn_position, uploads)
            chips = turn_chips(session, conversation_id, turn_position)
    except AttachmentRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # The turn exists from here on, without its end marker, so a reload or a restart during the
    # answer still finds the question. Answering a card reopens the turn that card parked
    # instead, since that is the turn this run rewrites.
    if card_turn is not None:
        replaces = stored.turn_ids[card_turn]
        reopen_turn(state.session_factory, replaces)
    else:
        replaces = open_turn(
            state.session_factory, conversation_id, model_key=model_key, ui_messages=adapter.run_input.messages
        )

    # Narration is pushed into the same queue the agent's chunks travel through, so a
    # sub-agent's line reaches the client while the tool is still running.
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    narration = Narration(queue=queue)
    if card_turn is not None:
        # The pending half of the turn already has tool steps; new narration follows them.
        narration.tools = sum(
            len(m.tool_calls) for m in stored.turns[card_turn].messages if isinstance(m, ModelResponse)
        )

    # What the user wrote this turn. It is the keyword source for memory selection, the language
    # this answer is checked in, and what `apply_simple_edit` reads to tell an amount the user
    # named from one the model filled in by itself. A turn resumed from a Question card brings
    # no new message, so it is the message that opened the turn being answered.
    question = _latest_user_text(adapter.run_input.messages)
    if not question:
        question = next(reversed(_user_prompts(stored.messages)), "")

    deps = ChatDeps(
        session_factory=state.session_factory,
        profile_id=profile_id,
        conversation_id=conversation_id,
        resolve_model=resolve,
        subagent_settings=state.subagent_settings,
        narrate=narration.say,
        web_client=state.web_client,
        user_message=question,
    )

    # The one place memory enters the prompt: the block is handed to the assembly, which joins
    # it to the rolling summary and hands both back as this turn's run instructions. A turn
    # resumed from a Question card brings no new message, so its memories are selected for the
    # prompt the pending turn started with.
    with state.session_factory() as session:
        memory_block = build_memory_block(session, profile_id, question)
        # The profile's own answer language, so the follow-up chips are written in the language
        # the answer above them is written in (`finquery.followups.language_line`).
        profile = session.get(Profile, profile_id)
        answer_language = profile.answer_language if profile else "follow"
    # The prompt ends where the turn being written ends. For a typed message that is the whole
    # conversation; for an answered card it is the turn that card parked, because the run
    # resumes from the response the call is on and the framework looks for that call on the
    # last response it is given. Anything the user asked in between stays in the transcript and
    # in every later prompt, it is simply not part of the run being resumed.
    if card_turn is None:
        prompt = await _prompt_for(
            request, conversation_id, stored.turns, summary, summary_through, memory_block, resolve
        )
    else:
        # The rolling summary may already stand in for the turn the card is on, and a prompt
        # with the pending call summarized away is a prompt the run cannot resume from at all.
        # So the marker is read one turn short of the card for this run only, and nothing is
        # compressed here: this run already happened, and moving the marker the rest of the
        # conversation is assembled from is not its business.
        through = min(summary_through, stored.turns[card_turn].position - 1)
        prompt = assemble(stored.turns[: card_turn + 1], summary, through, memory_block)
    history = prompt.history
    # Where the turn being written starts in the run's messages. Answering a deferred call
    # continues the turn that parked, so it starts where that turn started, not at the end of
    # the prompt. That turn is never folded away: it is the last one the assembly was given.
    turn_start = len(history) if card_turn is None else max(0, len(history) - len(stored.turns[card_turn].messages))
    # A resumed run streams into the browser's newest message, and a card the user came back to
    # is not on it. The output chunk for that call would then have nowhere to land ("No tool
    # invocation found for tool call ID ..."), so it is left out: the browser put the answers on
    # the card itself before it sent them, and reads the `applied` line back with the stored turn.
    answered_elsewhere = set(answers) if card_turn is not None and card_turn < len(stored.turns) - 1 else set()

    turn = RunningTurn(message_id=message_id)
    running[conversation_id] = turn
    # The turn so far is written into its own row as it goes, so a process that stops mid-answer
    # leaves what it had. A turn being rewritten from a Question card further up the transcript
    # is the one exception: its partial half would be drawn in the middle of the transcript,
    # where the reattached stream (which lands on the newest message) would draw it again.
    partials = card_turn is None or card_turn == len(stored.turns) - 1
    # Stored on the assistant UI message and echoed to the client at the end of the turn.
    metadata: dict[str, object] = {"model_key": model_key}
    # The language a replaced figure is explained in: the profile's own choice when it made one,
    # otherwise the language of the question, the same rule the answer itself follows.
    prose_language = answer_language if answer_language in ("de", "en") else (detect_language(question) or "en")
    # What this turn's answer may state. It is fed the tool results as they come back, so a
    # figure that is in none of them never reaches the reader.
    check = AnswerCheck(figures=collect_figures(stored.messages), language=prose_language)
    check.figures.add_message(question)
    thinking_started: float | None = None
    thinking_total = 0.0
    # Whether this run wrote its turn out. A browser that hangs up mid-answer takes the request
    # task down with it, so neither `on_complete` nor `on_cancel` gets to run and the open turn
    # is closed as interrupted instead.
    written = False

    # The adapter feeds the client's message in through message_history, so new_messages() would
    # miss it. Everything after the server-side history is what this request produced; the turn
    # being persisted can start earlier when a pending call is being answered.
    async def on_complete(result: AgentRunResult) -> AsyncIterator[BaseChunk]:
        # A model that ends its last thinking block by simply finishing leaves it open, and an
        # unclosed block would be a turn with no duration at all after a reload.
        close_thinking()
        messages = result.all_messages()
        turn_messages, produced = messages[turn_start:], messages[len(history) :]
        # Two post-turn steps on the fast slot, side by side: neither is worth waiting for twice.
        # Nobody is waiting on either, and a model that loops on one of them would otherwise
        # hold the finished answer hostage, so the whole pair is on a clock.
        # Neither step is worth an answer either: the suggestions and what was worth
        # remembering are both extras, and the sentence the user is reading is not. Anything
        # they raise (a fast slot that is not available, a memory that will not store) is
        # logged and costs the suggestions, never the turn.
        try:
            followups, _ = await asyncio.wait_for(
                asyncio.gather(_followups(produced, turn_messages), _distill(produced)), POST_TURN_TIMEOUT
            )
        except TimeoutError:
            logger.warning("post-turn steps timed out after %s s", POST_TURN_TIMEOUT)
            followups = []
        except Exception:  # noqa: BLE001 - an extra must never cost the answer
            logger.warning("a post-turn step failed", exc_info=True)
            followups = []
        # A card a tool built and the model narrated instead of showing is shown here, so the
        # run parks on it exactly as if the model had called `ask_user` itself.
        if (card := card_the_model_did_not_ask(produced)) is not None and (
            response := next((m for m in reversed(messages) if isinstance(m, ModelResponse)), None)
        ) is not None:
            call = ToolCallPart(tool_name=ASK_USER, args=card, tool_call_id=f"server-card-{new_id()}")
            response.parts.append(call)
            followups = []
            yield ToolInputAvailableChunk(tool_call_id=call.tool_call_id, tool_name=ASK_USER, input=card)
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
        nonlocal written
        written = True
        # What the reader was spared, on the turn, so the badge and a test can see it happened.
        if check.rewritten:
            metadata["figures_rewritten"] = check.rewritten
        # The turn's id goes back to the client in the metadata chunk that follows, so a chart
        # card of this turn can name it without a reload.
        metadata["turn_id"] = persist_turn(
            state.session_factory,
            conversation_id,
            turn_messages,
            model_key=model_key,
            metadata=metadata,
            data_parts=data_parts,
            attachments=chips,
            replaces=replaces,
            narration=narration.texts(),
            language=prose_language,
            figures=check.figures,
        )

    def _context_stats(produced: Sequence[ModelMessage]) -> dict[str, object]:
        """What the header badge shows: this turn's footprint against the slot's budget.

        `used` is the prompt that was sent plus what the request produced, which is where the
        next turn's history starts and therefore the number compression is decided on.
        """
        return {
            "used": prompt.tokens + estimate_tokens(produced),
            "budget": state.context_budget,
            "model_key": model_key,
            # The memories the assembly put in the prompt, which the badge and the chip on the
            # answer both read.
            "memories": prompt.memories,
            "summarized_turns": prompt.summarized_turns,
        }

    async def _followups(produced: Sequence[ModelMessage], turn: Sequence[ModelMessage]) -> list[str]:
        # A turn resumed from an answered Question card produced no user prompt of its own: it
        # starts at the tool result. Its question is the one that opened the turn, and without
        # this fallback the one turn a user most needs a next step after (the card that just
        # applied its answers) was the only turn in the app with no follow-ups.
        prompts = _user_prompts(produced) or _user_prompts(turn)
        if not prompts:
            return []
        # Sub-agents are pinned to the fast slot whatever the conversation runs on.
        return await suggest_followups(
            resolve("fast"),
            state.subagent_settings,
            prompts[-1],
            _assistant_text(produced),
            answer_language,
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
            resolve("fast"),
            state.subagent_settings,
            prompts[-1],
            answer,
            known,
            absent_names(_found_nothing(turn_messages)),
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
        """End the open thinking block and add it to the turn's total.

        A turn thinks once per model response, so a turn with a tool call thinks several
        times. What the panel showed live is the whole time the model spent thinking, so the
        blocks are summed rather than the last one winning.
        """
        nonlocal thinking_started, thinking_total
        if thinking_started is None:
            return
        thinking_total += time.monotonic() - thinking_started
        thinking_started = None
        metadata["thinking_seconds"] = round(thinking_total, 1)

    async def stream() -> AsyncIterator[BaseChunk]:
        nonlocal thinking_started
        # Gemma's own template tokens are text on OpenRouter, and the answer is what the user
        # reads, so they are taken out here for both providers.
        markers = TextFilter(check)
        thinking = ThinkingFilter()
        source = adapter.run_stream(
            message_history=history,
            # The summary and the memories ride in as one system-level note after the
            # agent's own system prompt.
            instructions=prompt.instructions,
            deferred_tool_results=results,
            model=model,
            model_settings=turn_settings,
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
                    # Whatever went wrong inside the run (a model that returned nothing, a tool
                    # that fell over, a provider that refused) leaves the framework's own
                    # exception text as the error the transcript prints. That is never a
                    # sentence anyone can act on, so it goes to the log and the user gets one
                    # that is. The question itself is kept: the turn is closed as interrupted.
                    logger.error("the turn failed", exc_info=item)
                    yield ErrorChunk(error_text=TURN_FAILED)
                    return
                # Reasoning duration is measured here because no model reports it. Narration is
                # not the model thinking, so it never enters the measurement.
                if item.type == "reasoning-start" and thinking_started is None:
                    thinking_started = time.monotonic()
                elif item.type == "reasoning-delta":
                    # The thinking panel is part of the transcript, so it gets the same filter
                    # the answer gets, plus the framework's retry sentence.
                    delta = thinking.feed(item.delta)
                    if not delta:
                        continue
                    item = item.model_copy(update={"delta": delta})
                elif item.type == "reasoning-end":
                    if tail := thinking.flush():
                        yield ReasoningDeltaChunk(id=item.id, delta=tail)
                    close_thinking()
                elif item.type == "error":
                    # The framework's own exception text, on its way to being printed in the
                    # transcript ("Stream function must return at least one item"). Nobody can
                    # act on that, so it goes to the log and one sentence goes to the reader.
                    # The question itself survives: the open turn is closed as interrupted.
                    logger.error("the turn failed: %s", item.error_text)
                    item = ErrorChunk(error_text=TURN_FAILED)
                elif item.type == "tool-output-available":
                    # Every figure this tool returned is a figure the answer may quote.
                    check.figures.add_result(item.output)
                    if item.tool_call_id in answered_elsewhere:
                        continue
                elif item.type == "tool-input-available":
                    # Which tool step a narration block belongs to, for the reload.
                    narration.tools += 1
                elif item.type == "text-delta":
                    delta = markers.feed(item.delta)
                    if not delta:
                        # The whole delta was a marker or a channel name, or the start of one
                        # still being held back until the next delta decides.
                        continue
                    # A copy rather than a new chunk: whatever else the provider put on it stays.
                    item = item.model_copy(update={"delta": delta})
                elif item.type == "text-end" and (tail := markers.flush()):
                    # Text held back for a marker or a line that never completed is still text.
                    yield TextDeltaChunk(id=item.id, delta=tail)
                yield item
        finally:
            pump.cancel()

    async def run() -> None:
        """The turn, as a task the app owns rather than as the request that asked for it.

        Nothing here is tied to the response: it appends what it produces to the turn's buffer,
        writes the turn down as it goes, and closes it. A client that hangs up stops reading the
        buffer, which is all a client can do to a turn. Stop is the one thing that ends a run.
        """
        written_at = time.monotonic()
        try:
            async for chunk in stream():
                turn.push(chunk)
                if not partials or written or replaces is None:
                    continue
                # Every tool boundary, and otherwise no more than every few seconds of text.
                boundary = chunk.type in ("tool-input-available", "tool-output-available")
                if not boundary and time.monotonic() - written_at < PARTIAL_SECONDS:
                    continue
                if parts := partial_parts(turn.chunks):
                    persist_partial(
                        state.session_factory, replaces, message_id=message_id, model_key=model_key, parts=parts
                    )
                    written_at = time.monotonic()
        except Exception:  # noqa: BLE001 - a task nobody awaits reports nothing by itself
            # `stream()` turns everything the run itself can do wrong into a chunk, so this is
            # the plumbing around it. The turn is closed either way, in the `finally` below.
            logger.exception("the turn task failed outside the stream")
        finally:
            # Out of the registry before the buffer closes, so a client whose stream has just
            # ended and asks to reattach is told 204 rather than handed a finished turn.
            running.pop(conversation_id, None)
            if not written:
                close_turn_if_open(state.session_factory, replaces)
            turn.close()

    turn.task = asyncio.create_task(run(), name=f"turn-{conversation_id}")
    return stream_response(turn.follow())


@router.get("/conversations/{conversation_id}/stream")
async def reattach(request: Request, conversation_id: str) -> Response:
    """Watch the turn this conversation is running: what it has produced, then what it produces.

    `useChat`'s own resume asks for exactly this URL when a chat is opened while a turn of it is
    running: a reload, a switch to another conversation and back, or a browser tab that was
    closed and opened again. 204 means nothing is running, which is what the SDK reads as "carry
    on with what you have".

    Reading a turn never changes it: hanging up here is one subscriber leaving.
    """
    running: dict[str, RunningTurn] = request.app.state.running_turns
    turn = running.get(conversation_id)
    if turn is None:
        return Response(status_code=204)
    return stream_response(turn.follow())


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
