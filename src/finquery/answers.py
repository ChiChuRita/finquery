"""What a Question card's answers do, applied in code before the model runs again.

The card is `ask_user` (ADR 0008): the run ends with the call pending and resumes when the
browser sends the answers back as the tool's output. Between those two halves this module
does what the answers mean, deterministically, and writes one line about it into the tool
result. The model's job on the second half is to say what happened and ask the next question,
never to work out the change itself.

Two kinds are applied here. `category_rule` turns every answer into a category rule for that
merchant. `extraction_review` commits the bookings of a statement extraction the user accepted,
through the same commit a CSV import uses, and categorizes them. A card says which kind it is
through `AskUser.apply`, so ticket 10 (duplicate decisions) adds an entry to `APPLIERS` and
touches nothing on the model path. A card that declares nothing is a categorization card, which
is what the seeded review conversation and every `review_batch` card are.

The two kinds ticket 08 brings, `mapping_confirmation` and `transaction_draft`, are in
`ApplyKind` with no entry here on purpose: their answers are acted on by a tool the model calls
(`import_file(confirmed=true)`, `add_transaction(ref)`), so they are passed through untouched.
They have to declare a kind all the same, or the fallback above would offer their Confirm and
Discard answers to `set_rule` as category names.

An applier may be async, because committing an extraction categorizes what it wrote and that
asks the fast slot. `resolve_answers` is therefore awaited from the chat endpoint, before the
resumed half of the run starts.
"""

import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session, sessionmaker

from finquery.ask_user import ASK_USER, ApplyKind, AskAnswer, AskAnswers, AskRow, AskUser
from finquery.categorize import apply_answers as apply_category_rules
from finquery.extract.review import apply_review
from finquery.providers import ModelResolver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Answered:
    """One answered card: where to write, whose data, and what was chosen.

    An applier gets the whole context rather than four positional arguments, because the two
    kinds need different parts of it: category rules need only the session and the profile,
    committing an extraction needs the conversation the file was attached to and the fast slot
    for the categorization that follows.
    """

    session: Session
    profile_id: str
    conversation_id: str
    rows: Sequence[AskRow]
    answers: Sequence[AskAnswer]
    resolve_model: ModelResolver
    model_settings: ModelSettings | None = None


Applier = Callable[[Answered], str | None | Awaitable[str | None]]
"""Applies one card's answers and returns the line saying what it did, or None for nothing."""


def _category_rules(answered: Answered) -> str | None:
    return apply_category_rules(answered.session, answered.profile_id, answered.rows, answered.answers)


def _extraction_review(answered: Answered) -> Awaitable[str | None]:
    return apply_review(
        answered.session,
        answered.profile_id,
        answered.conversation_id,
        answered.rows,
        answered.answers,
        resolve_model=answered.resolve_model,
        model_settings=answered.model_settings,
    )


APPLIERS: dict[ApplyKind, Applier] = {
    "category_rule": _category_rules,
    "extraction_review": _extraction_review,
}


async def resolve_answers(
    session_factory: sessionmaker[Session],
    profile_id: str,
    conversation_id: str,
    calls: Mapping[str, ToolCallPart],
    outputs: Mapping[str, object],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
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
            line = await _apply(
                session_factory,
                profile_id,
                conversation_id,
                call.args_as_dict(),
                output,
                resolve_model=resolve_model,
                model_settings=model_settings,
            )
        resolved[call_id] = {**output, "applied": line} if line and isinstance(output, dict) else output
    return resolved


async def _apply(
    session_factory: sessionmaker[Session],
    profile_id: str,
    conversation_id: str,
    card_input: dict[str, object],
    output: dict[str, object],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
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
        applied = applier(
            Answered(
                session=session,
                profile_id=profile_id,
                conversation_id=conversation_id,
                rows=card.rows,
                answers=answers.answers,
                resolve_model=resolve_model,
                model_settings=model_settings,
            )
        )
        return await applied if inspect.isawaitable(applied) else applied
