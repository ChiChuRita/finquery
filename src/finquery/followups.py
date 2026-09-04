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
answerable from bank transactions and must not repeat what was just asked. If nothing sensible
follows, answer "No follow-ups."
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


async def suggest_followups(model: Model, settings: ModelSettings, question: str, answer: str) -> list[str]:
    """Three follow-ups at most. A failure here is never allowed to fail the turn."""
    if not answer.strip():
        return []
    prompt = f"{FOLLOWUP_MARKER} for this exchange.\n\nUser asked: {question}\n\nAssistant answered: {answer}"
    try:
        result = await followup_agent.run(prompt, model=model, model_settings=settings)
    except Exception:
        logger.warning("follow-up suggestions failed", exc_info=True)
        return []
    return parse_suggestions(result.output)
