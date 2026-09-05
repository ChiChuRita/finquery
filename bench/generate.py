"""Draft more datapoints with a hosted model, and keep only the ones that really answer.

    uv run python bench/generate.py --set sql   --n 10 --kind entity
    uv run python bench/generate.py --set chart --n 6  --shape doughnut

A strong hosted model is asked for a question and the statement that answers it, given the same
view schema and household facts the sub-agents get. Nothing it writes is trusted: every candidate
goes through the guard and is executed against the fresh benchmark database, and only one that
runs and returns rows is appended, tagged `generated`, with the rows it returned as its gold. A
chart candidate has one check more: the column roles it claims have to describe the columns the
statement really returned, which is the same `columns_map` a run is scored with.

This is the second half of the loop the README describes: validate the hand-written set first,
then grow it. Generated datapoints carry `source: "generated"` so a run can leave them out, and
they are as good as the model that drafted them until somebody has judged them one by one the
way `bench/validation/` records.
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput

from finquery.chart.shapes import SHAPE_MENU, SHAPE_NAMES
from finquery.chart.subagent import PLAN_RULES
from finquery.query.subagent import EXAMPLES, RULES, VIEW_SCHEMA, load_query_context, profile_facts
from finquery.settings import Settings
from finquery_bench.datapoints import CHART_SET, KINDS, SQL_SET, load_charts, load_sql, read, write
from finquery_bench.dataset import fresh_database
from finquery_bench.gold import GoldFailed, run_reference
from finquery_bench.models import resolve_target
from finquery_bench.score import columns_map

INSTRUCTIONS = """\
You write benchmark datapoints for a personal-finance assistant that answers questions about one
household's bank transactions with SQL. Call `datapoints` exactly once with the whole batch.

Every datapoint is a question a real person would type into a chat with their bank statements,
plus the SQLite statement that answers it exactly. The statement is the gold answer, so it has to
be right: it will be executed, and a datapoint whose statement returns no rows is thrown away.
"""

ASK = """\
Write {n} new datapoints of kind `{kind}`, in this mix of languages: half German, half English,
the way a German household types (umlauts written out, the occasional English word).

Rules for the questions:
- Ask about this household's real data: the merchants, categories and period below, and nothing
  else. A question about data that is not there is not a datapoint.
- Vary the difficulty: 1 is one filter and one aggregate, 2 is two things at once, 3 is what a
  small model gets wrong (relative periods, averages, exclusions, subcategories against
  categories, a merchant spelled the way a person types it).
- One reading only. A question a careful reader could answer with two different figures is not a
  datapoint: name the period, say whether you mean a category or one of its subcategories, and
  say how many rows you want back when you ask for a ranking.
- Ask for exactly the figures the statement returns, and let the statement return exactly the
  figures the question asks for. A count nobody asked about makes the datapoint wrong.
- Do not repeat any of the questions already in the set, listed at the end.
- No question about a chart, an import, a category rule or anything but the figures.
{extra}
Rules for the SQL: exactly the rules the assistant itself is held to, below.

Today is {today}.
"""

FOLLOW_UP = """\
- A follow-up only means something after the turn before it. Put the earlier questions of the
  conversation in `prefix`, oldest first, and write the follow-up the way a person types one:
  three words that inherit the period, the filter or the ordering. The statement is the whole
  answer to the follow-up, with everything it inherited written out.
"""

CHART_ASK = """\
Write {n} new chart datapoints of shape `{shape}`, in this mix of languages: half German, half
English, the way a German household types (umlauts written out, the occasional English word).

A chart datapoint is a request a person types into the chat ("show me ... as a bar chart"), the
statement that returns the rows the chart is drawn from, and what the drawing has to be.

- `prompt` is the request. Half of them name the shape, half leave it to the assistant; when it
  is left open, list in `also` every other shape that would answer the request just as honestly,
  and leave `also` empty when the request names the shape.
- `roles` is what the columns of your statement are, in order, one word each: `position` for a
  month or a day, `label` for a category or a merchant name, `series` for the group of a grouped
  or stacked bar, `source` and `target` for the two ends of a sankey link, and `value` for the
  euro figure, which is always the last column. Those six words are the whole vocabulary: a
  sankey's roles are `source`, `target`, `value` however you name the columns themselves.
- `covers` is two or three words on what this request exercises.
- One reading only, and ask for exactly the columns the shape needs.
- Do not repeat any of the requests already in the set, listed at the end.

The shapes, and the rules the assistant plans one with:

{menu}

{plan_rules}

Rules for the SQL: exactly the rules the assistant itself is held to, below.

Today is {today}.
"""


class Drafted(BaseModel):
    """One drafted SQL datapoint."""

    question: str = Field(description="What the user types, German or English")
    language: str = Field(description="de or en")
    difficulty: int = Field(description="1, 2 or 3")
    prefix: list[str] = Field(default_factory=list, description="Earlier questions of the conversation, oldest first")
    tags: list[str] = Field(default_factory=list, description="Two or three words about what it exercises")
    why: str = Field(description="One line on what makes this question hard")
    sql: str = Field(description="One SQLite SELECT over transaction_view that answers it exactly")


class Batch(BaseModel):
    datapoints: list[Drafted]


class DraftedChart(BaseModel):
    """One drafted chart datapoint."""

    prompt: str = Field(description="What the user types, German or English")
    language: str = Field(description="de or en")
    difficulty: int = Field(description="1, 2 or 3")
    also: list[str] = Field(default_factory=list, description="Shapes that would answer the request as well")
    roles: list[str] = Field(
        description=(
            "One of position, label, series, source, target, value per column, in order, and "
            "always the word `value` for the euro column, never the column's own name."
        )
    )
    covers: list[str] = Field(default_factory=list, description="Two or three words about what it exercises")
    why: str = Field(description="One line on what makes this request hard")
    sql: str = Field(description="One SQLite SELECT over transaction_view returning exactly those columns")


class ChartBatch(BaseModel):
    datapoints: list[DraftedChart]


drafter = Agent(instructions=INSTRUCTIONS, output_type=ToolOutput(Batch, name="datapoints"), name="finquery-bench-generate")

chart_drafter = Agent(
    instructions=INSTRUCTIONS,
    output_type=ToolOutput(ChartBatch, name="datapoints"),
    name="finquery-bench-generate-chart",
)


def prompt(*, n: int, kind: str, facts: str, today: str, existing: list[str]) -> str:
    questions = "\n".join(f"- {question}" for question in existing)
    return "\n\n".join(
        [
            ASK.format(n=n, kind=kind, today=today, extra=FOLLOW_UP if kind == "follow-up" else ""),
            VIEW_SCHEMA,
            RULES,
            EXAMPLES,
            facts,
            f"Questions already in the set, none of which you may write again:\n{questions}",
        ]
    )


def chart_prompt(*, n: int, shape: str, facts: str, today: str, existing: list[str]) -> str:
    requests = "\n".join(f"- {request}" for request in existing)
    return "\n\n".join(
        [
            CHART_ASK.format(n=n, shape=shape, today=today, menu=SHAPE_MENU, plan_rules=PLAN_RULES),
            VIEW_SCHEMA,
            RULES,
            EXAMPLES,
            facts,
            f"Requests already in the set, none of which you may write again:\n{requests}",
        ]
    )


def _identifier(kind: str, index: int, taken: set[str]) -> str:
    number = index
    while f"g{number:03d}-{kind}" in taken:
        number += 1
    return f"g{number:03d}-{kind}"


async def ask(agent, target, text: str):  # noqa: ANN001, ANN201 - a Target, but the import is the runner's
    """The one model call: a batch of drafted datapoints."""
    result = await agent.run(text, model=target.resolve("fast"), model_settings=target.settings)
    return result.output


def _language(drafted: str) -> str:
    return "de" if drafted.lower().startswith("de") else "en"


def draft_sql(args: argparse.Namespace, target, session_factory, profile_id, payload) -> list[dict[str, Any]]:  # noqa: ANN001
    existing = load_sql()
    with session_factory() as session:
        context = load_query_context(session, profile_id, today=date.fromisoformat(payload["today"]))
    text = prompt(
        n=args.n,
        kind=args.kind,
        facts=profile_facts(context),
        today=payload["today"],
        existing=[point.question for point in existing],
    )
    batch = asyncio.run(ask(drafter, target, text))
    taken = {point.id for point in existing}
    kept: list[dict[str, Any]] = []
    for index, drafted in enumerate(batch.datapoints, start=1):
        ident = _identifier(args.kind, len(kept) + index, taken)
        try:
            gold = run_reference(session_factory, profile_id, ident, drafted.sql)
        except GoldFailed as exc:
            print(f"dropped: {drafted.question[:70]} - {exc}", file=sys.stderr)
            continue
        taken.add(ident)
        kept.append(
            {
                "id": ident,
                "kind": args.kind,
                "difficulty": max(1, min(3, drafted.difficulty)),
                "language": _language(drafted.language),
                "question": drafted.question.strip(),
                "prefix": [line.strip() for line in drafted.prefix],
                "tags": [*drafted.tags, "generated"],
                "why": drafted.why.strip(),
                "source": "generated",
                "sql": " ".join(drafted.sql.split()),
                "gold": gold,
            }
        )
    print(f"kept {len(kept)} of {len(batch.datapoints)} drafted", file=sys.stderr)
    return kept


def draft_chart(args: argparse.Namespace, target, session_factory, profile_id, payload) -> list[dict[str, Any]]:  # noqa: ANN001
    existing = load_charts()
    with session_factory() as session:
        context = load_query_context(session, profile_id, today=date.fromisoformat(payload["today"]))
    text = chart_prompt(
        n=args.n,
        shape=args.shape,
        facts=profile_facts(context),
        today=payload["today"],
        existing=[point.prompt for point in existing],
    )
    batch = asyncio.run(ask(chart_drafter, target, text))
    taken = {point.id for point in existing}
    kept: list[dict[str, Any]] = []
    for index, drafted in enumerate(batch.datapoints, start=1):
        ident = _identifier(args.shape, len(kept) + index, taken)
        try:
            gold = run_reference(session_factory, profile_id, ident, drafted.sql)
        except GoldFailed as exc:
            print(f"dropped: {drafted.prompt[:70]} - {exc}", file=sys.stderr)
            continue
        # The roles are what a run is scored on, so they have to describe the rows that came
        # back, not the rows the drafter meant to ask for.
        if not columns_map(drafted.roles, gold["columns"], gold["rows"]):
            print(f"dropped: {drafted.prompt[:70]} - the roles do not describe {gold['columns']}", file=sys.stderr)
            continue
        taken.add(ident)
        kept.append(
            {
                "id": ident,
                "prompt": drafted.prompt.strip(),
                "language": _language(drafted.language),
                "shape": args.shape,
                "also": [name for name in drafted.also if name in SHAPE_NAMES and name != args.shape],
                "roles": list(drafted.roles),
                "difficulty": max(1, min(3, drafted.difficulty)),
                "covers": [*drafted.covers, "generated"],
                "why": drafted.why.strip(),
                "source": "generated",
                "sql": " ".join(drafted.sql.split()),
                "gold": gold,
            }
        )
    print(f"kept {len(kept)} of {len(batch.datapoints)} drafted", file=sys.stderr)
    return kept


def draft(args: argparse.Namespace) -> int:
    settings = Settings()
    target = resolve_target(args.model, None, settings)
    path = SQL_SET if args.set == "sql" else CHART_SET
    key = "datapoints" if args.set == "sql" else "prompts"
    payload = read(path)

    # The database is built synchronously, before any event loop exists: loading it categorizes
    # the year, which is a coroutine of its own.
    with fresh_database() as (session_factory, profile_id):
        maker = draft_sql if args.set == "sql" else draft_chart
        kept = maker(args, target, session_factory, profile_id, payload)

    if not kept:
        print("nothing kept: every drafted statement was refused or answered nothing", file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps(kept, ensure_ascii=False, indent=2))
        return 0
    payload[key] = [*payload[key], *kept]
    write(path, payload)
    print(f"appended {len(kept)} to {path.name}")
    for point in kept:
        print(f"  {point['id']}  {point.get('question', point.get('prompt', ''))[:80]}")
    print("Judge them one by one before trusting them: bench/README.md")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/generate.py", description=__doc__)
    parser.add_argument("--set", default="sql", choices=("sql", "chart"))
    parser.add_argument("--n", type=int, default=8, help="how many to draft")
    parser.add_argument("--kind", default="entity", choices=KINDS, help="the kind of question, --set sql")
    parser.add_argument("--shape", default="bar", choices=SHAPE_NAMES, help="the shape of the chart, --set chart")
    parser.add_argument("--model", default="google/gemini-3.8-flash", help="an OpenRouter id or a slot")
    parser.add_argument("--dry-run", action="store_true", help="print what would be kept, write nothing")
    return draft(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
