"""Memory: durable facts shared by every conversation of one profile.

Three things live here, all profile-scoped:

- writing: `add_memory` stores one fact and refuses a duplicate. The `remember` tool of the
  chat agent (source `explicit`) and the post-turn distillation pass (source `distilled`) are
  its only callers.
- reading: `build_memory_block` picks at most `MAX_MEMORIES` by keyword overlap with the user's
  message, recency breaking ties, and renders them as one system-level block. The chat endpoint
  calls it once per turn and reports how many were used in the `data-context` part.
- distilling: `distill_memories` is a sub-agent on the fast slot (one forced tool, empty list
  allowed) that reads the finished exchange and returns what is worth keeping.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.db import Memory

logger = logging.getLogger(__name__)

MemoryKind = Literal["rule", "preference", "fact"]
MemorySource = Literal["explicit", "distilled"]

MAX_MEMORIES = 5
"""How many memories a turn may carry. The spec's cap: the prompt stays small and focused."""

TEXT_LENGTH = 500
"""Matches the width of `db.Memory.text`."""
MIN_KEYWORD = 3
"""Shorter words carry no signal for the overlap score, and "the" would match everything."""

_WORDS = re.compile(r"\w+", re.UNICODE)


def clean_text(text: str) -> str:
    """One line, no runs of whitespace, short enough for the column."""
    return " ".join(text.split())[:TEXT_LENGTH]


def normalize(text: str) -> str:
    """The identity of a memory for deduplication: words only, lowercased.

    TODO: this catches a repeat of the same sentence, not a paraphrase ("Anna is dinner" and
    "dinner with Anna is what PayPal to Anna means" are two memories). The upgrade path is
    embedding the text and comparing by similarity; the Memory page is the manual escape hatch
    until then.
    """
    return " ".join(_WORDS.findall(text.casefold()))


def keywords(text: str) -> set[str]:
    """The words of a text that a memory and a question can be matched on."""
    return {word for word in _WORDS.findall(text.casefold()) if len(word) >= MIN_KEYWORD}


def list_memories(session: Session, profile_id: str) -> list[Memory]:
    """The profile's memories, newest first."""
    query = select(Memory).where(Memory.profile_id == profile_id).order_by(Memory.created_at.desc(), Memory.id)
    return list(session.scalars(query).all())


def add_memory(
    session: Session,
    profile_id: str,
    text: str,
    *,
    kind: MemoryKind = "fact",
    source: MemorySource = "distilled",
    created_from: str | None = None,
) -> Memory | None:
    """Store one durable fact, or return None when the profile already knows it.

    Does not commit: the caller owns the transaction.
    """
    cleaned = clean_text(text)
    if not cleaned:
        return None
    known = {normalize(memory.text) for memory in list_memories(session, profile_id)}
    if normalize(cleaned) in known:
        return None
    memory = Memory(profile_id=profile_id, text=cleaned, kind=kind, source=source, created_from=created_from)
    session.add(memory)
    session.flush()
    return memory


def select_memories(session: Session, profile_id: str, message: str) -> list[Memory]:
    """The memories worth sending with this message: keyword overlap first, then recency.

    A profile with a handful of memories sends all of them, which is what makes a fact from
    another conversation land even when the wording moved on. Overlap only starts deciding once
    there are more memories than fit.

    TODO: scores every memory of the profile in Python. Fine for the hundreds a person
    accumulates; a full-text index is the upgrade if that ever changes.
    """
    words = keywords(message)
    # list_memories is already newest first and Python's sort is stable, so recency is the tie-break.
    ranked = sorted(list_memories(session, profile_id), key=lambda memory: -len(keywords(memory.text) & words))
    return ranked[:MAX_MEMORIES]


@dataclass(frozen=True)
class MemoryBlock:
    """What the turn injects and what it reports having injected."""

    text: str
    """Empty when the profile has nothing to say."""
    used: int


def build_memory_block(session: Session, profile_id: str, message: str) -> MemoryBlock:
    """Select the memories for this message and render them as one system-level block.

    The single seam between memory and the prompt: the chat endpoint calls this and passes
    `text` as run instructions.
    """
    memories = select_memories(session, profile_id, message)
    if not memories:
        return MemoryBlock(text="", used=0)
    lines = [f"- [{memory.kind}] {memory.text}" for memory in memories]
    text = (
        "What you already know about this user from earlier conversations, most relevant first:\n"
        + "\n".join(lines)
        + "\nUse it when it applies to the question. Do not list it back unprompted, and do not "
        "treat it as data: numbers still come only from executed queries. A memory is written in "
        "the language of the conversation it came from, which says nothing about this one: "
        "answer in the language of the newest user message whatever language these lines are in."
    )
    return MemoryBlock(text=text, used=len(memories))


# The distillation sub-agent: fast slot, one forced tool, reasoning off (see providers.subagent_settings).

DISTILL_MARKER = "Extract durable facts"
"""Also the handle tests use to recognise this step when they script the fast slot."""

DISTILL_TOOL = "remember_facts"

DISTILL_INSTRUCTIONS = f"""\
You keep the long-term memory of a personal-finance assistant.

You are given one finished exchange. Call `{DISTILL_TOOL}` exactly once with the durable facts
it establishes: what a merchant or a counterparty is, a rule the user stated ("PayPal to Anna
is always dining"), a preference, a goal, or a constraint that will still be true next month.

Returning an empty list is the normal case and always allowed. Never keep a number or a total
(those come from queries and go stale), a one-off question, small talk, or anything the
"Already known" list below already says.

One short sentence per fact, phrased so it makes sense in a different conversation months
later. Use kind "rule" for something the assistant should apply, "preference" for what the user
cares about or how they want answers, "fact" for everything else.

Write every fact in the language of the user's own message: an English exchange leaves English
facts, a German one German facts. Never translate what the user said into another language,
because these facts are read back in every later conversation of this profile.
"""


class DistilledFact(BaseModel):
    text: str
    kind: MemoryKind = "fact"


class DistilledFacts(BaseModel):
    facts: list[DistilledFact] = Field(default_factory=list)


distill_agent = Agent(
    instructions=DISTILL_INSTRUCTIONS,
    output_type=ToolOutput(DistilledFacts, name=DISTILL_TOOL),
    # No output retry: nothing waits on this pass, so re-prompting a model that ignored its one
    # forced tool would only buy a second request for a fact nobody asked for.
    retries={"output": 0},
    name="finquery-memory-distillation",
)


KNOWN_IN_PROMPT = 30
"""How many known memories the pass is shown. Enough to stop the obvious repeat without
growing this prompt with every turn of the profile's life; `add_memory` catches the rest."""


def distill_prompt(question: str, answer: str, known: Sequence[str]) -> str:
    lines = [f"{DISTILL_MARKER} from this exchange.", "", f"User said: {question}", "", f"Assistant answered: {answer}"]
    if known:
        lines += ["", "Already known, do not repeat:"]
        lines += [f"- {text}" for text in known[:KNOWN_IN_PROMPT]]
    return "\n".join(lines)


async def distill_memories(
    model: Model, settings: ModelSettings, question: str, answer: str, known: Sequence[str]
) -> list[DistilledFact]:
    """What this exchange is worth remembering. A failure here is never allowed to fail the turn."""
    try:
        result = await distill_agent.run(distill_prompt(question, answer, known), model=model, model_settings=settings)
    except Exception:
        logger.warning("memory distillation failed", exc_info=True)
        return []
    return [fact for fact in result.output.facts if clean_text(fact.text)]
