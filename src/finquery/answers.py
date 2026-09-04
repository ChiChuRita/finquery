"""What a Question card's answers do, applied in code before the model runs again.

The card is `ask_user` (ADR 0008): the run ends with the call pending and resumes when the
browser sends the answers back as the tool's output. Between those two halves this module
does what the answers mean, deterministically, and writes one line about it into the tool
result. The model's job on the second half is to say what happened and ask the next question,
never to work out the change itself.

One kind is applied here, `category_rule`: every answer becomes a category rule for that
merchant. A card says which kind it is through `AskUser.apply`, so ticket 10 (duplicate
decisions) adds an entry to `APPLIERS` and touches nothing on the model path. A card that
declares nothing is a categorization card, which is what the seeded review conversation and
every `review_batch` card are.

The two kinds ticket 08 brings, `mapping_confirmation` and `transaction_draft`, are in
`ApplyKind` with no entry here on purpose: their answers are acted on by a tool the model calls
(`import_file(confirmed=true)`, `add_transaction(ref)`), so they are passed through untouched.
They have to declare a kind all the same, or the fallback above would offer their Confirm and
Discard answers to `set_rule` as category names.
"""

import logging
from collections.abc import Callable, Mapping, Sequence

from pydantic import ValidationError
from pydantic_ai.messages import ToolCallPart
from sqlalchemy.orm import Session, sessionmaker

from finquery.ask_user import ASK_USER, ApplyKind, AskAnswer, AskAnswers, AskRow, AskUser
from finquery.categorize import apply_answers as apply_category_rules

logger = logging.getLogger(__name__)

Applier = Callable[[Session, str, Sequence[AskRow], Sequence[AskAnswer]], str | None]
"""Applies one card's answers and returns the line saying what it did, or None for nothing."""

APPLIERS: dict[ApplyKind, Applier] = {"category_rule": apply_category_rules}


def resolve_answers(
    session_factory: sessionmaker[Session],
    profile_id: str,
    calls: Mapping[str, ToolCallPart],
    outputs: Mapping[str, object],
) -> dict[str, object]:
    """The tool results the resumed run is given: the user's answers plus what was applied.

    `calls` are the tool calls the server left open, `outputs` what the browser sent for them.
    An output that is not a Question card, or a card nothing acts on, is passed through
    untouched.
    """
    resolved: dict[str, object] = {}
    for call_id, output in outputs.items():
        call = calls.get(call_id)
        line = None
        if call is not None and call.tool_name == ASK_USER and isinstance(output, dict):
            line = _apply(session_factory, profile_id, call.args_as_dict(), output)
        resolved[call_id] = {**output, "applied": line} if line and isinstance(output, dict) else output
    return resolved


def _apply(
    session_factory: sessionmaker[Session],
    profile_id: str,
    card_input: dict[str, object],
    output: dict[str, object],
) -> str | None:
    try:
        card = AskUser.model_validate(card_input)
        answers = AskAnswers.model_validate(output)
    except ValidationError:
        # A card the model malformed, or an output that is not one: the model gets it as it is.
        logger.warning("a Question card answer could not be read, so nothing was applied")
        return None
    if not answers.answers:
        return None
    applier = APPLIERS.get(card.apply.kind if card.apply else "category_rule")
    if applier is None:
        # A kind whose answers a tool of the model's acts on, not the server: pass it through.
        return None
    with session_factory() as session:
        return applier(session, profile_id, card.rows, answers.answers)
