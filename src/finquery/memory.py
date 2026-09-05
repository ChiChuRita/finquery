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
from collections.abc import Sequence, Set
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

An order for this one turn is not a durable fact, however firmly it was put. "Recategorize all
Netflix rows as Leisure", "split this booking", "answer in more detail", "make it a bar chart":
those were carried out when they were said and keeping them would make every later
conversation obey an instruction nobody repeated. Keep the standing rule behind an order only
when the user phrased it as one ("Netflix is always Leisure", "I always want short answers").

One short sentence per fact, phrased so it makes sense in a different conversation months
later. Use kind "rule" for something the assistant should apply, "preference" for what the user
cares about or how they want answers, "fact" for everything else.

Store only what will still be true next month: what a merchant is, who a person is, how the
household wants something categorized. Never store a figure, a total, a month's spending, a
count, a date, or a restatement of the question that was just asked. If the only durable content
of the turn is a number, store nothing. Never store anything about a person or a merchant this
turn could not find in the data: a query that returned no rows proves there is nothing to know.

Two facts is the most any one exchange leaves behind, and none is the usual number.

Write every fact in the language of the user's own message: an English exchange leaves English
facts, a German one German facts. Never translate what the user said into another language,
because these facts are read back in every later conversation of this profile.

Fill `reasoning` first, one very short line per candidate: what the turn established, and
whether it will still be true next month. Then answer with the facts that survive it, which is
usually none.

Three worked exchanges:

  User: How much did I spend at REWE last month?
  Assistant: You spent 75,20 EUR at REWE in August 2026.
  reasoning: the turn established one figure, and a figure goes stale with the next booking
  facts: none

  User: PayPal to Anna is always dinner, by the way.
  Assistant: Noted, PayPal payments to Anna Weber are now filed as Dining > Restaurant.
  reasoning: a standing rule about a merchant, stated as one, still true next month
  facts: rule "PayPal payments to Anna Weber are dinner"

  User: Recategorize all my Netflix bookings as Leisure.
  Assistant: I have proposed moving 16 Netflix bookings to Leisure.
  reasoning: an order for this turn, carried out when it was said, not a standing rule
  facts: none
"""

MAX_DISTILLED = 2
"""How many facts one turn may leave behind.

The 9B review of 2026-09-05 distilled 27 memories in one afternoon, most of them one-off
figures, several of them wrong, and they steered later turns for the rest of the run. A turn
that really establishes three durable things can say the third one again.
"""

# A figure, a decimal, a year or a written date: all of them are a snapshot of one moment, and a
# memory is read back months later.
_NOT_DURABLE = re.compile(
    r"\d{1,3}(?:[.,]\d{3})+|\d+[.,]\d+|\b\d{4}\b|\d{1,2}[./]\d{1,2}[./]\d{2,4}|\d+\s*(?:EUR|€|Euros?)",
    re.IGNORECASE,
)
_NAME = re.compile(r"\b[^\W\d_][^\W\d_-]{2,}", re.UNICODE)


def is_durable(fact: "DistilledFact") -> bool:
    """Whether this fact will still be true next month.

    An amount or a date makes it a snapshot: "the user's net savings ... amount to 83.64 EUR"
    was wrong the moment the next booking landed, and was wrong when it was written. A rule is
    the exception, because "over 100 EUR always needs a receipt" is a standing instruction.
    """
    return fact.kind == "rule" or _NOT_DURABLE.search(fact.text) is None


def absent_names(requests: Sequence[str]) -> set[str]:
    """The names a query asked about and found nothing for, folded.

    A capitalized word of the request, which is how a person or a merchant is written in both
    languages, minus the word the request opens with. The chat model wrote an explicit memory
    about "Max Schulz" in the very turn that proved this household has never paid anyone of that
    name, and then cited it as evidence two turns later.
    """
    names: set[str] = set()
    for request in requests:
        words = _NAME.findall(request.strip())
        names.update(word.casefold() for word in words[1:] if word[:1].isupper())
    return names


def worth_keeping(
    facts: Sequence["DistilledFact"], absent: Set[str], known: Sequence[str] = ()
) -> list["DistilledFact"]:
    """The facts of one turn that may be stored: durable, about something real, new, at most two."""
    return [fact for fact, reason in _judged(facts, absent, known) if reason is None][:MAX_DISTILLED]


def _judged(
    facts: Sequence["DistilledFact"], absent: Set[str], known: Sequence[str] = ()
) -> list[tuple["DistilledFact", str | None]]:
    """Every fact with the reason it may not be stored, or None when it may."""
    seen = {normalize(text) for text in known}
    judged: list[tuple[DistilledFact, str | None]] = []
    for fact in facts:
        cleaned = clean_text(fact.text)
        if not cleaned:
            judged.append((fact, "it is empty"))
            continue
        if not is_durable(fact):
            logger.info("a distilled fact was dropped as a one-off figure or date: %s", fact.text)
            judged.append((fact, "it carries a figure or a date, which is a snapshot of one moment"))
            continue
        if absent & {word.casefold() for word in _NAME.findall(fact.text)}:
            logger.info("a distilled fact was dropped: this turn found no such row: %s", fact.text)
            judged.append((fact, "this turn looked that name up in the data and found no row for it"))
            continue
        if normalize(cleaned) in seen:
            judged.append((fact, "this profile already knows it, word for word"))
            continue
        seen.add(normalize(cleaned))
        judged.append((fact, None))
    return judged


def refusal_prompt(answer: "DistilledFacts", refused: list[tuple["DistilledFact", str]]) -> str:
    """A distillation whose every fact was refused, handed back with why (ticket 42).

    Storing nothing is the right answer to most turns, and this is the message that says so
    with the model's own sentence in front of it, rather than leaving the pass to write the
    same figure into the profile on the next turn.
    """
    lines = "\n".join(f'- "{fact.text}": {reason}' for fact, reason in refused)
    return (
        "\n\nNone of what you just answered can be stored. This is a correction of that answer, "
        "not a new question about the exchange.\n\n"
        f"Your reasoning was:\n{answer.reasoning.strip()}\n\n"
        f"What was refused:\n{lines}\n\n"
        "Answer again with the corrected reasoning and only the facts that are left. An empty "
        "list is the right answer whenever nothing durable is left, and it is the usual one."
    )


class DistilledFact(BaseModel):
    text: str
    kind: MemoryKind = "fact"


class DistilledFacts(BaseModel):
    """What one turn leaves behind, and the reading that decided it.

    `reasoning` is first because the decision this pass gets wrong is durability, and a model
    that writes the fact before it has asked itself the question keeps the figure it just read
    (ticket 42).
    """

    reasoning: str = Field(
        description=(
            "One very short line per candidate, written before the facts: what the turn "
            "established, and whether it is still true next month. No prose."
        )
    )
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
    model: Model,
    settings: ModelSettings,
    question: str,
    answer: str,
    known: Sequence[str],
    absent: Set[str] = frozenset(),
) -> list[DistilledFact]:
    """What this exchange is worth remembering. A failure here is never allowed to fail the turn.

    `absent` is what this turn's queries looked for and did not find, so a fact about a person
    the data does not have is dropped rather than stored and read back forever.

    A pass whose every fact was refused is handed the refusals once. Nothing waits on this, so
    the second call costs a turn nothing, and what it buys is the difference between a model
    that learns "a figure is not a memory" inside the turn and one that writes the next figure
    the same way.
    """
    prompt = distill_prompt(question, answer, known)
    try:
        result = await distill_agent.run(prompt, model=model, model_settings=settings)
    except Exception:
        logger.warning("memory distillation failed", exc_info=True)
        return []
    judged = _judged(result.output.facts, absent, known)
    kept = [fact for fact, reason in judged if reason is None]
    refused = [(fact, reason) for fact, reason in judged if reason is not None]
    if kept or not refused:
        return kept[:MAX_DISTILLED]
    try:
        second = await distill_agent.run(
            f"{prompt}{refusal_prompt(result.output, refused)}", model=model, model_settings=settings
        )
    except Exception:
        logger.warning("the second memory distillation failed", exc_info=True)
        return []
    return worth_keeping(second.output.facts, absent, known)
