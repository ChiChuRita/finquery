"""Context management: what one turn sends to the model, and how it stays inside the budget.

A conversation grows without limit, a context window does not. So the prompt for a turn is
assembled from three things rather than from the whole transcript: the chat agent's system
prompt, a rolling summary of the turns that no longer fit (as a system-level note), and the
recent turns verbatim. Once the assembled history passes 60 percent of the slot's budget,
everything but the last six turns is folded into that summary by the fast slot and the
summary-through marker on the conversation moves up.

Nothing is ever deleted: turns stay in the database and in the transcript. The summary only
replaces them in the prompt, which is why it can be edited (the next turn uses the edited text)
and why the transcript can still show every message with a divider where the summary took over.

The memories of ticket 13 join the same assembly: `assemble` takes the block `memory` selected
for this turn and joins it to the summary note, so one string carries everything system-level
and one token count covers all of it.
"""

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.agent import SYSTEM_PROMPT
from finquery.memory import MemoryBlock
from finquery.settings import Settings

if TYPE_CHECKING:
    from finquery.local.runtime import LocalStack

logger = logging.getLogger(__name__)

#: Turns that are always sent verbatim, however long the conversation gets.
RECENT_TURNS = 6

#: Share of the budget the assembled history may occupy before the older turns are folded in.
COMPRESS_ABOVE = 0.6

#: A summary that grew past this is truncated: it is meant to save context, not to eat it.
MAX_SUMMARY_CHARS = 4000

CHARS_PER_TOKEN = 4
MESSAGE_OVERHEAD_TOKENS = 4

#: Also the handle tests use to recognise this step when they script the fast slot.
SUMMARY_MARKER = "Summarize the earlier turns"

SUMMARY_INSTRUCTIONS = """\
You compress the earlier part of a conversation between a user and their personal-finance
assistant, so the assistant can keep answering after the raw turns are dropped from its context.

Keep what is still needed: what the user asked about, the figures the assistant reported and the
query they came from, corrections, and anything the user said about themselves, their accounts or
their preferences. Drop greetings, repetition and anything already superseded.

Write at most twelve short lines of plain text in the language of the conversation. No headings,
no markdown, no commentary about the summary itself. When you are given a previous summary, merge
it with the new turns into one summary rather than appending to it.
"""

summary_agent: Agent[None, str] = Agent(instructions=SUMMARY_INSTRUCTIONS, name="finquery-summary")


@dataclass(frozen=True)
class TurnMessages:
    """One stored turn: its position, what the model saw, and how many messages it renders as."""

    position: int
    messages: list[ModelMessage]
    ui_count: int


@dataclass(frozen=True)
class Assembly:
    """The prompt for one turn, plus what the context badge and the divider report."""

    history: list[ModelMessage]
    instructions: str | None
    """Everything system-level this turn adds to the agent's own instructions: the rolling
    summary as a note, then the selected memories. `None` when there is neither."""
    memories: int
    """Memories the block carries, for the badge and the chip on the answer."""
    summarized_turns: int
    summarized_messages: int
    """Transcript messages the summary stands in for, so the divider knows where to go."""
    kept_turns: int
    tokens: int


def context_budget(settings: Settings, local: "LocalStack | None") -> int:
    """The working budget for one turn, in tokens.

    Both slots have the same context on both providers today (16k for the two local models, 262k
    for the two OpenRouter ones), so the budget does not depend on the slot; give this a slot
    parameter when that stops being true. The configured budget is a cap, not a raise: on the
    local provider the resident context is the hard ceiling.
    """
    if local is not None:
        return min(local.n_ctx, settings.context_budget)
    return settings.context_budget


def message_text(message: ModelMessage) -> str:
    """Everything textual in a message: prompts, thinking, answers, tool arguments and results."""
    chunks: list[str] = []
    for part in message.parts:
        content = getattr(part, "content", None)
        if isinstance(content, str):
            chunks.append(content)
        elif content is not None:
            chunks.append(str(content))
        args = getattr(part, "args", None)
        if args is not None:
            chunks.append(args if isinstance(args, str) else json.dumps(args))
    return "\n".join(chunks)


def estimate_tokens(messages: Sequence[ModelMessage], instructions: str | None = None) -> int:
    """Approximate the tokens these messages occupy in a model's context.

    Ceiling: four characters per token plus a fixed overhead per message. That is within about
    fifteen percent for German and English prose and it is never asked to be exact, because the
    only decision it drives has a 40 percent margin above it.

    It is deliberately the number the badge shows too. A provider-reported count arrives with
    the response (OpenRouter sends one, the local model reports one), which is after the
    compression decision has already been made, so using it for the badge would put a second,
    disagreeing number on screen. Upgrade path when exactness matters: expose `tokenize` on the
    local stack's `Slot` and branch here per provider.
    """
    texts = [instructions] if instructions else []
    texts.extend(message_text(message) for message in messages)
    return sum(len(text) // CHARS_PER_TOKEN + MESSAGE_OVERHEAD_TOKENS for text in texts)


def summary_note(summary: str) -> str:
    return (
        "Earlier turns of this conversation were replaced by this summary. Treat it as something "
        f"you remember, not as something the user said:\n\n{summary}"
    )


def assemble(
    turns: Sequence[TurnMessages],
    summary: str | None,
    summary_through: int,
    memory: MemoryBlock | None = None,
) -> Assembly:
    """Build one turn's prompt: the system-level note, then the turns after the marker.

    The note is the whole non-transcript part of the prompt: the rolling summary and the
    memories selected for this turn. Both travel as run instructions and both are counted, so
    the badge reports what the model was actually sent and compression is decided on that same
    number.
    """
    summarized = [turn for turn in turns if turn.position <= summary_through]
    kept = [turn for turn in turns if turn.position > summary_through]
    note = summary_note(summary) if summary and summarized else None
    memory_text = memory.text if memory and memory.text else None
    instructions = "\n\n".join(filter(None, [note, memory_text])) or None
    history = [message for turn in kept for message in turn.messages]
    return Assembly(
        history=history,
        instructions=instructions,
        memories=memory.used if memory else 0,
        summarized_turns=len(summarized),
        summarized_messages=sum(turn.ui_count for turn in summarized),
        kept_turns=len(kept),
        # The agent adds its own system prompt, so only the note travels as run instructions,
        # but the model is sent both and the badge counts what the model is sent.
        # Two-line rule: whatever joins `instructions` is counted here too.
        tokens=estimate_tokens(history, "\n".join(filter(None, [SYSTEM_PROMPT, instructions]))),
    )


def needs_compression(assembly: Assembly, budget: int) -> bool:
    """True when the history is over the threshold and there is something older than the last six."""
    return assembly.tokens > COMPRESS_ABOVE * budget and assembly.kept_turns > RECENT_TURNS


def turns_to_fold(turns: Sequence[TurnMessages], summary_through: int) -> list[TurnMessages]:
    """The turns compression folds into the summary: everything after the marker but the last six."""
    kept = [turn for turn in turns if turn.position > summary_through]
    return kept[:-RECENT_TURNS]


def transcript(turns: Sequence[TurnMessages]) -> str:
    """The turns as plain text for the summarizer to read."""
    blocks: list[str] = []
    for turn in turns:
        for message in turn.messages:
            role = "User" if message.kind == "request" else "Assistant"
            if text := message_text(message).strip():
                blocks.append(f"{role}: {text}")
    return "\n\n".join(blocks)


async def summarize(
    model: Model, settings: ModelSettings, previous: str | None, turns: Sequence[TurnMessages]
) -> str | None:
    """Fold `turns` into `previous` on the fast slot. `None` means nothing was compressed.

    A failure here must never fail the turn: the conversation simply keeps sending its full
    history until the next turn tries again.
    """
    if not turns:
        return None
    prompt = f"{SUMMARY_MARKER} of this conversation."
    if previous:
        prompt += f"\n\nPrevious summary:\n{previous}"
    prompt += f"\n\nTurns to fold in:\n{transcript(turns)}"
    try:
        result = await summary_agent.run(prompt, model=model, model_settings=settings)
    except Exception:
        logger.warning("rolling summary failed", exc_info=True)
        return None
    return clean_summary(result.output)


def clean_summary(text: str) -> str | None:
    summary = "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip())
    return summary[:MAX_SUMMARY_CHARS] or None
