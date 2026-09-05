"""Draft more SQL datapoints with a hosted model, and keep only the ones that really answer.

    uv run python bench/generate.py --n 10 --kind entity --model google/gemini-3.8-flash

A strong hosted model is asked for a question and the statement that answers it, given the same
view schema and household facts the query sub-agent gets. Nothing it writes is trusted: every
candidate goes through the guard and is executed against the fresh benchmark database, and only
one that runs and returns rows is appended to `bench/sql-benchmark.json`, tagged `generated`,
with the rows it returned as its gold.

This is the second half of the loop the README describes: validate the hand-written sample
first, then grow the set. Generated datapoints carry `source: "generated"` so a run can leave
them out, and they are as good as the model that drafted them until somebody reads them on the
validation page.
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput

from finquery.query.subagent import EXAMPLES, RULES, VIEW_SCHEMA, load_query_context, profile_facts
from finquery.settings import Settings
from finquery_bench.datapoints import KINDS, SQL_SET, load_sql, read, write
from finquery_bench.dataset import fresh_database
from finquery_bench.gold import GoldFailed, run_reference
from finquery_bench.models import resolve_target

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
- Do not repeat any of the questions already in the set, listed at the end.
- No question about a chart, an import, a category rule or anything but the figures.

Rules for the SQL: exactly the rules the assistant itself is held to, below.

Today is {today}.
"""


class Drafted(BaseModel):
    """One drafted datapoint."""

    question: str = Field(description="What the user types, German or English")
    language: str = Field(description="de or en")
    difficulty: int = Field(description="1, 2 or 3")
    tags: list[str] = Field(default_factory=list, description="Two or three words about what it exercises")
    why: str = Field(description="One line on what makes this question hard")
    sql: str = Field(description="One SQLite SELECT over transaction_view that answers it exactly")


class Batch(BaseModel):
    datapoints: list[Drafted]


drafter = Agent(instructions=INSTRUCTIONS, output_type=ToolOutput(Batch, name="datapoints"), name="finquery-bench-generate")


def prompt(*, n: int, kind: str, facts: str, today: str, existing: list[str]) -> str:
    questions = "\n".join(f"- {question}" for question in existing)
    return "\n\n".join(
        [
            ASK.format(n=n, kind=kind, today=today),
            VIEW_SCHEMA,
            RULES,
            EXAMPLES,
            facts,
            f"Questions already in the set, none of which you may write again:\n{questions}",
        ]
    )


def _identifier(kind: str, index: int, taken: set[str]) -> str:
    number = index
    while f"g{number:03d}-{kind}" in taken:
        number += 1
    return f"g{number:03d}-{kind}"


async def ask(target, text: str) -> Batch:  # noqa: ANN001 - a Target, but the import is the runner's
    """The one model call: a batch of drafted datapoints."""
    result = await drafter.run(text, model=target.resolve("fast"), model_settings=target.settings)
    return result.output


def draft(args: argparse.Namespace) -> int:
    settings = Settings()
    target = resolve_target(args.model, None, settings)
    existing = load_sql()
    payload = read(SQL_SET)

    # The database is built synchronously, before any event loop exists: loading it categorizes
    # the year, which is a coroutine of its own.
    with fresh_database() as (session_factory, profile_id):
        with session_factory() as session:
            context = load_query_context(session, profile_id, today=date.fromisoformat(payload["today"]))
        text = prompt(
            n=args.n,
            kind=args.kind,
            facts=profile_facts(context),
            today=payload["today"],
            existing=[point.question for point in existing],
        )
        batch = asyncio.run(ask(target, text))

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
                    "language": "de" if drafted.language.lower().startswith("de") else "en",
                    "question": drafted.question.strip(),
                    "tags": [*drafted.tags, "generated"],
                    "why": drafted.why.strip(),
                    "source": "generated",
                    "sql": " ".join(drafted.sql.split()),
                    "gold": gold,
                }
            )

    if not kept:
        print("nothing kept: every drafted statement was refused or answered nothing", file=sys.stderr)
        return 1
    if args.dry_run:
        print(json.dumps(kept, ensure_ascii=False, indent=2))
        return 0
    payload["datapoints"] = [*payload["datapoints"], *kept]
    write(SQL_SET, payload)
    print(f"kept {len(kept)} of {len(batch.datapoints)} drafted, appended to {SQL_SET.name}")
    for point in kept:
        print(f"  {point['id']}  {point['question'][:80]}")
    print("Read them on the validation page before trusting them: bench/README.md")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench/generate.py", description=__doc__)
    parser.add_argument("--n", type=int, default=8, help="how many to draft")
    parser.add_argument("--kind", default="entity", choices=KINDS)
    parser.add_argument("--model", default="google/gemini-3.8-flash", help="an OpenRouter id or a slot")
    parser.add_argument("--dry-run", action="store_true", help="print what would be kept, write nothing")
    return draft(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
