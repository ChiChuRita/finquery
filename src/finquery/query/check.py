"""Does the result answer the question? The two judgements that follow a statement.

Valid SQL that answers the wrong question is the failure the guard cannot see: the benchmark of
ticket 38 has the small models writing SQL that runs 93 to 97 percent of the time and returning
the right figure about half of it. So a result is judged before it is handed over:

- `degenerate_reason` is code and costs nothing: no rows, figures that are all NULL, or a single
  zero on a question that names a merchant or a category the household really has. What it
  returns is the reason one rewrite is asked with.
- `check_result` is one forced tool call on the fast slot: the question, the household, the
  statement and up to ten of its rows go in, `ok` or `revise` with a one-sentence reason and the
  intent to answer instead comes back. Never SQL: the query sub-agent writes the SQL.

`runner.run_query` orchestrates both, with at most one rewrite and at most three model calls per
query. See ticket 40.
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.nullish import nullish
from finquery.query.subagent import QueryContext, is_euro_column, profile_facts

CHECK_TOOL = "judge_result"
"""The one tool the check pass may call. Forced and single, like every sub-agent's."""

CHECK_MARKER = "Judge whether this result answers the question"
"""The last line of the check prompt. What a scripted model recognizes the pass by."""

CHECKING = "Checking the result"
"""The narration line while the check runs. The chart repairs narrate the same way."""

REWRITING = "Rewriting: {reason}"
"""The narration line when the sub-agent is sent back, whatever asked for the rewrite."""

CHECK_ROWS = 10
"""How many result rows the check sees. A judgement needs the shape of the result, not a dump."""

INSTRUCTIONS = """\
You judge whether a SQL result answers the question a household asked about its own bank
transactions. You never write SQL, you never state a figure and you never answer the question
yourself. Call `judge_result` exactly once.

Answer `ok` when the statement asked what the question asked. A small, an empty or a surprising
result is still ok when the statement is right: the data is allowed to hold no answer.

Answer `revise` when the statement answers a different question. Then say in one sentence what
it answered instead, and write the corrected intent in plain words, never as SQL.
"""

REVISE_WHEN = """\
Revise when:
- the period is not the one the question names, or the statement narrowed a question that named
  no period to one year or one month of the data;
- the sign is wrong: spending rows are negative and income positive, and a spending total is
  reported as a positive figure;
- a subcategory name was used as a category, or a list of merchants stands in for a topic the
  household has a category for;
- the grouping is not what was asked: one row per booking where the question asks per month, per
  merchant or per category, one number where it compares two periods, or a total where it asks
  for a breakdown;
- a ranking is sorted the wrong way round: the smallest payment is the one nearest zero, the
  largest is the one furthest from it;
- a figure looks like cents rather than euros, or like a count where euros were asked for;
- only part of the question is answered.
"""

CAUSES = """\
Look for the cause before you write the same filter again: a LIKE term spelled differently from
the booking text (match a shorter fragment of the name, case-insensitively, over description and
counterparty together); a period outside {first} to {last}, which is all the data there is; a
name used in `category` that is really a subcategory, or a topic that is a category rather than
a list of merchants; the sign, since spending is negative and income positive. Never widen the
match to every merchant you were shown: when the data carries none of it, no rows is the honest
answer and one statement that shows it is enough.
"""

NO_ROWS = "the statement returned no rows, so nothing in the data matched it"
ALL_NULL = "every figure it returned is empty, so nothing in the data matched it"
SINGLE_ZERO = "it returned a single zero, though the question names something this data carries"


class Verdict(BaseModel):
    """What the check pass answers: the result stands, or here is what to ask instead."""

    verdict: str = Field(
        description="`ok` when the statement answers the question, `revise` when it answers a different one."
    )
    reason: str = Field(default="", description="One sentence: what the statement answered instead. Empty on ok.")
    intent: str = Field(
        default="", description="What to ask instead, in plain words and never SQL. Empty on ok."
    )

    # A free string, and every field optional, so the schema itself cannot fail validation: a
    # rejected output costs another model call, and the ceiling of three per query is the point.
    @field_validator("verdict", "reason", "intent", mode="before")
    @staticmethod
    def _text(value: object) -> str:
        return "" if nullish(value) is None else str(value)

    @property
    def revise(self) -> bool:
        """Only a clear revise rewrites. Anything else leaves the result the sub-agent found."""
        return self.verdict.strip().casefold().startswith(("revise", "wrong", "no"))

    def why(self) -> str:
        """The one sentence the rewrite is asked with, and the line the panel shows."""
        return " ".join(self.reason.split()) or "the statement does not answer the question that was asked"


check_agent = Agent(
    instructions=INSTRUCTIONS,
    output_type=ToolOutput(Verdict, name=CHECK_TOOL),
    name="finquery-query-check",
)


def check_prompt(
    request: str,
    context: QueryContext,
    sql: str,
    figures: list[str],
    *,
    hints: str | None = None,
    reasoning: str = "",
) -> str:
    """The whole prompt the check pass sees. Pure, like `query_prompt`, so training can rebuild it.

    The question stands on its own: the chat agent rewrites a follow-up into a request that
    carries its own period and topic, and the conversation before it, before the sub-agent ever
    sees it. What the assistant added on top is shown as what it is, a reading that can be wrong.
    """
    rows = "\n".join(figures[:CHECK_ROWS]) or "(no rows)"
    sections = [REVISE_WHEN, profile_facts(context), f"Question: {request.strip()}"]
    if hints and hints.strip():
        sections.append(f"What the assistant added, which is its reading and not the question:\n{hints.strip()}")
    if reasoning.strip():
        # What the sub-agent said it was doing, which is where a misread period or sign is
        # visible in one line rather than inside the SQL.
        sections.append(f"How the statement was meant:\n{reasoning.strip()}")
    sections += [
        f"The statement that ran:\n{sql.strip()}",
        f"What it returned:\n{rows}",
        f"{CHECK_MARKER}.",
    ]
    return "\n\n".join(sections)


async def check_result(
    model: Model,
    request: str,
    context: QueryContext,
    sql: str,
    figures: list[str],
    *,
    hints: str | None = None,
    reasoning: str = "",
    model_settings: ModelSettings | None = None,
) -> Verdict:
    """Ask the fast slot whether this result answers the question, through one forced tool."""
    result = await check_agent.run(
        check_prompt(request, context, sql, figures, hints=hints, reasoning=reasoning),
        model=model,
        model_settings=model_settings,
    )
    return result.output


def _significant(name: str) -> str:
    """The first word of a name long enough to recognize it by: `REWE Markt GmbH` is `rewe`."""
    for word in name.split():
        letters = "".join(character for character in word if character.isalpha())
        if len(letters) >= 4:
            return letters.casefold()
    return ""


def names_something(request: str, context: QueryContext) -> bool:
    """Whether the question names a category, a subcategory or a merchant this household has."""
    text = request.casefold()
    names = [name for category, subs in context.taxonomy for name in (category, *subs)]
    names += [merchant for merchant, _ in context.counterparties]
    return any(token and token in text for token in (_significant(name) for name in names))


def degenerate_reason(
    request: str, context: QueryContext, columns: list[str], rows: list[dict[str, Any]]
) -> str | None:
    """Why this result answers nothing, in code and without a model, or None when it does.

    Three shapes, all of them from the review of 2026-09-05: no rows at all (a subcategory name
    used as a category), a total that is NULL because no booking matched (a misspelled LIKE
    term or a period outside the data), and a single zero on a question that names a merchant
    or a category the household really has (usually the sign). Anything else is a real answer,
    including a small figure and an empty result to a question about something absent, which is
    why the zero rule asks whether the data carries the thing at all.
    """
    if not rows:
        return NO_ROWS
    watched = [column for column in columns if is_euro_column(column)] or columns
    if all(row.get(column) is None for row in rows for column in watched):
        return ALL_NULL
    if len(rows) == 1 and len(watched) == 1:
        value = rows[0].get(watched[0])
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value == 0:
            return SINGLE_ZERO if names_something(request, context) else None
    return None


def causes(context: QueryContext) -> str:
    """The hint a degenerate result is rewritten with: the usual causes, with the data's range."""
    return CAUSES.format(first=context.first_booked_on, last=context.last_booked_on)
