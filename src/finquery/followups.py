"""Follow-up questions offered under a finished answer.

A small post-turn step on the fast slot (sub-agents are never on the chat slot). The result
travels to the transcript as a `data-followups` part and is stored on the assistant message.
"""

import logging

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

logger = logging.getLogger(__name__)

# Also the handle tests use to recognise this step when they script the fast slot.
FOLLOWUP_MARKER = "Suggest follow-up questions"

INSTRUCTIONS = """\
You suggest what a user of a personal-finance assistant could usefully ask next.

Write at most three short questions, one per line, each ending with a question mark, in the
language of the exchange. No numbering, no bullets, no other text. Each question must be
answerable from bank transactions and must not repeat what was just asked.

When the exchange shows the question cannot be answered from the data at all, that is exactly
when to suggest something the transactions do hold, so the user has a way forward. Answer
"No follow-ups." only when you can think of nothing a bank statement could answer.

Two worked exchanges. Three questions each, none of them the one that was just answered, and
each one a step further into the data rather than the same question in other words:

  User asked: How much did I spend on groceries in May 2025?
  Assistant answered: You spent 256,77 EUR on groceries in May 2025.
  ->
  Which supermarkets did that go to?
  How does May compare with April?
  What did I spend on groceries over the whole year?

  User asked: What is my credit score?
  Assistant answered: That is not in your bank transactions, so I cannot tell you.
  ->
  What did I spend last month?
  Which subscriptions do I pay every month?
  Where does most of my money go?
"""

followup_agent: Agent[None, str] = Agent(instructions=INSTRUCTIONS, name="finquery-followups")

MAX_SUGGESTIONS = 3
MAX_LENGTH = 90


def parse_suggestions(text: str) -> list[str]:
    """Keep the lines that are actually short questions, so prose around them is dropped."""
    suggestions: list[str] = []
    for line in text.splitlines():
        question = line.strip().lstrip("-*0123456789.)").strip()
        if question.endswith("?") and len(question) <= MAX_LENGTH and question not in suggestions:
            suggestions.append(question)
    return suggestions[:MAX_SUGGESTIONS]


LANGUAGE_NAMES = {"de": "German", "en": "English"}
"""The two languages a profile can fix its answers to. `follow` is neither and names nothing."""


def language_line(language: str) -> str:
    """What to write the questions in, when the profile has decided.

    The chips are read next to the answer, so they are in the answer's language or they are
    noise: a profile fixed to English got German suggestions under an English answer (e2e of
    2026-09-05, m3). On `follow` this says nothing and the exchange decides, as it did before.
    """
    name = LANGUAGE_NAMES.get(language)
    if name is None:
        return ""
    return (
        f"\n\nThis profile has fixed {name} as its answer language, so write the questions in "
        f"{name} whatever language the exchange below is in."
    )


async def suggest_followups(
    model: Model, settings: ModelSettings, question: str, answer: str, language: str = "follow"
) -> list[str]:
    """Three follow-ups at most. A failure here is never allowed to fail the turn."""
    if not answer.strip():
        return []
    prompt = (
        f"{FOLLOWUP_MARKER} for this exchange.{language_line(language)}"
        f"\n\nUser asked: {question}\n\nAssistant answered: {answer}"
    )
    try:
        result = await followup_agent.run(prompt, model=model, model_settings=settings)
    except Exception:
        logger.warning("follow-up suggestions failed", exc_info=True)
        return []
    return parse_suggestions(result.output)
