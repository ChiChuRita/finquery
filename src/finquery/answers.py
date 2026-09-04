"""What a Question card's answers do, applied in code before the model runs again.

The card is `ask_user` (ADR 0008): the run ends with the call pending and resumes when the
browser sends the answers back as the tool's output. Between those two halves this module
does what the answers mean, deterministically, and writes one line about it into the tool
result. The model's job on the second half is to say what happened and ask the next question,
never to work out the change itself.

Two kinds are applied here. `category_rule`: every answer becomes a category rule for that
merchant. `duplicate_decision`: the bookings the user kept are inserted from the columns the
card showed and categorized, the ones they removed never existed. A card says which kind it is
through `AskUser.apply`, so a new kind is an entry in `APPLIERS` and touches nothing on the
model path. A card that declares nothing is a categorization card, which is what the seeded
review conversation and every `review_batch` card are.

The two kinds ticket 08 brings, `mapping_confirmation` and `transaction_draft`, are in
`ApplyKind` with no entry here on purpose: their answers are acted on by a tool the model calls
(`import_file(confirmed=true)`, `add_transaction(ref)`), so they are passed through untouched.
They have to declare a kind all the same, or the fallback above would offer their Confirm and
Discard answers to `set_rule` as category names.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session, sessionmaker

from finquery.ask_user import ASK_USER, ApplyKind, AskAnswer, AskAnswers, AskRow, AskUser, unwrap_card
from finquery.categorize import apply_answers as apply_category_rules
from finquery.ingest.duplicates import apply_answers as apply_duplicate_decisions
from finquery.providers import ModelResolver

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApplyContext:
    """What an applier gets: the card, the answers, and the fast slot if it needs one.

    `resolve_model` is here because keeping a duplicate candidate inserts a booking, and a new
    booking is categorized: that is the one applier which runs a sub-agent.
    """

    session: Session
    profile_id: str
    rows: Sequence[AskRow]
    answers: Sequence[AskAnswer]
    resolve_model: ModelResolver
    model_settings: ModelSettings | None = None


Applier = Callable[[ApplyContext], Awaitable[str | None]]
"""Applies one card's answers and returns the line saying what it did, or None for nothing."""


async def _category_rules(ctx: ApplyContext) -> str | None:
    return apply_category_rules(ctx.session, ctx.profile_id, ctx.rows, ctx.answers)


async def _duplicate_decisions(ctx: ApplyContext) -> str | None:
    return await apply_duplicate_decisions(
        ctx.session,
        ctx.profile_id,
        ctx.rows,
        ctx.answers,
        resolve_model=ctx.resolve_model,
        model_settings=ctx.model_settings,
    )


APPLIERS: dict[ApplyKind, Applier] = {
    "category_rule": _category_rules,
    "duplicate_decision": _duplicate_decisions,
}


async def resolve_answers(
    session_factory: sessionmaker[Session],
    profile_id: str,
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
    card_input: dict[str, object],
    output: dict[str, object],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> str | None:
    try:
        # Tolerant of a card the model passed as its own `card` argument: see `unwrap_card`.
        card = AskUser.model_validate(unwrap_card(card_input))
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
        return await applier(
            ApplyContext(
                session=session,
                profile_id=profile_id,
                rows=card.rows,
                answers=answers.answers,
                resolve_model=resolve_model,
                model_settings=model_settings,
            )
        )
