"""The query sub-agent: one question in, one SQLite SELECT out.

Fast slot, one forced tool call, no free text (ADR 0002 pins every sub-agent to fast). The
prompt is built by `query_prompt`, a pure function of the request and the shape of the
profile's data: the same framing serves production and the later adapter training, so a
training row is exactly the text the model saw here plus the SQL it wrote.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from finquery.db import QUERY_VIEW, Category
from finquery.nullish import nullish
from finquery.query.guard import MAX_ROWS

TOP_COUNTERPARTIES = 30

INSTRUCTIONS = """\
You write SQLite queries over one household's bank transactions. You are given a question and
the shape of the data. Call `run_sql` exactly once.

Fill `reasoning` before you write any SQL: one short line each for the period you read out of
the question, the filters, the sign, and the grouping. Then write `sql` so that it does exactly
what those lines say. You never explain yourself outside that field, never apologize and never
answer the question in words: the SQL is the answer.
"""

VIEW_SCHEMA = f"""\
The view (the only relation you may name, already filtered to this household):

  {QUERY_VIEW}
    id            text     booking id
    booked_on     text     booking date as 'YYYY-MM-DD'; compare as text or use strftime
    amount        real     the amount in euros, negative is money out, positive is money in.
                           The only money column there is: every figure comes from it.
    description   text     the booking text from the bank, mostly upper case
    counterparty  text     the other party's name, NULL when the export carried none
    title         text     friendly merchant title, NULL until the row is enriched
    enrichment    text     short merchant description, NULL until the row is enriched
    category      text     category name, NULL when the booking is not categorized
    subcategory   text     subcategory name, NULL when unset
    account       text     account name
    source        text     'import', 'manual' or 'photo'
    import_id     text     the import the row came from, NULL for manual rows

Split parents are already excluded, so every row counts exactly once.
"""

RULES = f"""\
Rules:
- One statement, a single SELECT. No INSERT, UPDATE, DELETE, CREATE, DROP, ATTACH or PRAGMA,
  no other table or view, and never a schema prefix such as main.
- Aggregate. At most {MAX_ROWS} rows come back (a LIMIT is added for you), so answer with the
  few rows that carry the answer instead of a dump of bookings.
- Spending is negative. For a spending question filter `amount < 0` and report a positive figure
  with `ROUND(-SUM(amount), 2)`. Income is `amount > 0`.
- `amount` is in euros and is the only column a figure may come from. There is no cents column
  to divide, so never write anything like `/ 100`.
- Smallest means the smallest amount of money. On spending rows, which are negative, the
  smallest payment is `ORDER BY amount DESC` and the largest is `ORDER BY amount ASC`. Say which
  end you meant in the alias, for instance `smallest_eur`.
- Give every selected column a snake_case alias: total_eur, month, merchant, bookings.
- The category of a booking is the `category` column and nothing else. Never write a classifier:
  a `CASE WHEN description LIKE '%rewe%' THEN 'Groceries'` invents labels the household never
  chose, and the guard refuses it. Group by `coalesce(category, 'Needs review')` so the
  uncategorized bookings are one honest bucket instead of being guessed at or dropped.
- An alias must never reuse a column name of the view. `CASE ... END AS category` looks right and
  is a trap: a later `GROUP BY category` binds to the view's own column, not to your expression,
  and the result silently collapses. Call a computed group `topic` or `group_name` instead.
- Matching `description` or `counterparty` is how you pick the bookings a question is about, in
  the WHERE clause. It is never how you label them.
- The names listed under a category are its subcategories. They live in the `subcategory`
  column, never in `category`: `category IN ('Supermarket', 'Bakery')` matches nothing, and the
  whole topic is `category = 'Groceries'`.
- Every merchant you may name is in the busiest-counterparties list below. A merchant that is
  not on that list does not exist in this data: never invent one, and use the `category` column
  for a topic instead.
- Write one branch per distinct question. Two UNION ALL branches with the same WHERE clause and
  different labels are the same number twice, so delete them.
- One statement stays short. There is no JOIN to write: the view is read once.
- A month is `strftime('%Y-%m', booked_on)`. A period is `booked_on BETWEEN '2025-04-01' AND
  '2025-04-30'`. There is no date type, so never call date functions on anything else.
- The data can end months before today, so a relative period is counted from the latest booking
  month, never from today's date. The household paragraph below spells out what this month, last
  month, this quarter and last quarter are; use those dates as they stand.
- When the question names no period, cover the whole range of the data. Never narrow it to the
  current year, or to any other period the question did not ask for.
- Match a merchant or a person on the booking text and the counterparty together,
  case-insensitively: `lower(description || ' ' || coalesce(counterparty, '')) LIKE '%rewe%'`.
  Never on one column alone: a PayPal payment carries PayPal as the counterparty and the
  person's name in the description, so `coalesce(counterparty, description)` misses every
  payment to a person. A topic that spans merchants is
  several LIKE terms joined with OR, at most eight. A person or a merchant the question names
  is one LIKE term for that name, and when no merchant in the list carries it the statement
  simply returns no rows: never widen the match to every merchant you were shown.
- When the question compares two periods, return one row per period rather than one number.
- A question about which merchants, categories, months or subscriptions are involved wants one
  row per merchant (`GROUP BY`), never one row per booking. Add a total with `UNION ALL` when
  the question asks for a breakdown and a total together.
- Answer the question that was asked and nothing else.
"""

EXAMPLE_SOURCES = (
    "s70-last-quarter-de",
    "s28-q4-vs-q3-en",
    "s07-subscriptions-per-month-en",
    "s08-electricity-de",
    "g007-breakdown",
    "s57-refunds-en",
    "s63-per-week-de",
    "s49-typo-en",
    "s38-top-five-en",
)
"""Which benchmark datapoints the worked examples below are drawn from.

One per pattern the small models get wrong (a relative period, two periods compared, an average
over the periods the data covers, a subcategory, the Needs review bucket, the sign of a refund,
a follow-up that inherits its period, a misspelled merchant, a ranking). Every one of them was
read by hand on 2026-09-05 (`bench/validation/2026-09-05-opus.json`) and every one is in the
train split, so nothing here is an answer the benchmark then scores the model on. A statement is
written the way this prompt's own rules ask for it, in euros, which is why an example can differ
from the reference in the file. `tests/test_bench.py` runs all nine against the data.
"""

EXAMPLES = """\
Worked examples. The reasoning comes first, and the SQL does what it says:

Question: Wie viel habe ich letztes Quartal ausgegeben?
Reasoning: last quarter is the range the household paragraph spells out, 2025-07-01 to
2025-09-30; spending, so amount < 0; no topic filter; one figure.
SQL:
SELECT ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0 AND booked_on BETWEEN '2025-07-01' AND '2025-09-30'

Question: How does this quarter compare with the last one?
Reasoning: two periods, so one row each and not one number: this quarter is 2025-10-01 to
2025-12-31, last quarter 2025-07-01 to 2025-09-30; spending; group by the period.
SQL:
SELECT CASE WHEN booked_on <= '2025-09-30' THEN 'last quarter' ELSE 'this quarter' END AS period,
       ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0 AND booked_on BETWEEN '2025-07-01' AND '2025-12-31'
GROUP BY period
ORDER BY period

Question: How much do my subscriptions cost me per month on average?
Reasoning: no period is named, so the whole range; the average is over the months the data
really covers, counted with COUNT(DISTINCT), never assumed to be twelve; category Subscriptions.
SQL:
SELECT ROUND(-SUM(amount) / (COUNT(DISTINCT strftime('%Y-%m', booked_on)) * 1.0), 2) AS per_month_eur
FROM transaction_view
WHERE amount < 0 AND category = 'Subscriptions'

Question: Wie hoch war meine Stromrechnung 2025?
Reasoning: Strom is the subcategory Electricity, so it belongs in `subcategory` and never in
`category`; spending; the year as the period.
SQL:
SELECT ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0 AND subcategory = 'Electricity' AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'

Question: Aufschluesselung meiner Ausgaben im November 2025 nach Kategorie.
Reasoning: one row per category; the bookings without one are their own bucket rather than
dropped or guessed at; November 2025; spending.
SQL:
SELECT coalesce(category, 'Needs review') AS topic, ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0 AND booked_on BETWEEN '2025-11-01' AND '2025-11-30'
GROUP BY topic
ORDER BY total_eur DESC

Question: Did I get any refunds in 2025?
Reasoning: a refund is money coming back, so amount > 0; a salary is money in too and is not a
refund, so leave the large amounts out; one row per booking with its date and text.
SQL:
SELECT booked_on, description, ROUND(amount, 2) AS amount_eur
FROM transaction_view
WHERE amount > 0 AND amount < 1000 AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'
ORDER BY booked_on

Question: Und pro Woche?
The assistant adds: Earlier in this conversation the user asked: "Wie viel habe ich im Mai 2025
ausgegeben?" Answer the new question on its own.
Reasoning: the follow-up keeps May 2025 from the question before it; per week is
strftime('%Y-%W'); spending; one row per week.
SQL:
SELECT strftime('%Y-%W', booked_on) AS week, ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0 AND booked_on BETWEEN '2025-05-01' AND '2025-05-31'
GROUP BY week
ORDER BY week

Question: How much did I spend at Edeak?
Reasoning: Edeak is EDEKA as the user typed it, and the merchant list carries EDEKA, so match
the name the data uses over description and counterparty together; spending; no period named,
so the whole range.
SQL:
SELECT ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0 AND lower(description || ' ' || coalesce(counterparty, '')) LIKE '%edeka%'

Question: Which merchants took the most money in 2025? Show me the top five.
Reasoning: one row per merchant, never one per booking; spending; sort by the total and cut at
five.
SQL:
SELECT coalesce(counterparty, description) AS merchant,
       ROUND(-SUM(amount), 2) AS total_eur,
       COUNT(*) AS bookings
FROM transaction_view
WHERE amount < 0 AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'
GROUP BY merchant
ORDER BY total_eur DESC
LIMIT 5
"""


class GeneratedSql(BaseModel):
    """What the sub-agent answers with: how it read the question, then the statement.

    `reasoning` comes first so a small model commits to an interpretation before it writes any
    SQL, and so the retry and the check pass can hold it to what it said. It carries no default
    obligation on the caller: a model that leaves it empty still gets its statement run.
    """

    reasoning: str = Field(
        default="",
        description=(
            "First, before any SQL: one short line each for the period you read out of the "
            "question, the filters, the sign, and the grouping."
        ),
    )
    sql: str = Field(description=f"One SQLite SELECT over {QUERY_VIEW}, doing exactly what the reasoning says.")

    @field_validator("reasoning", mode="before")
    @staticmethod
    def _text(value: object) -> str:
        return "" if nullish(value) is None else str(value)


@dataclass(frozen=True)
class QueryContext:
    """The shape of one profile's data. Everything the prompt says about the household."""

    today: date
    transaction_count: int
    first_booked_on: str | None
    last_booked_on: str | None
    categorized_count: int
    accounts: tuple[str, ...]
    taxonomy: tuple[tuple[str, tuple[str, ...]], ...]
    counterparties: tuple[tuple[str, int], ...]


def is_euro_column(name: str) -> bool:
    """The columns this prompt tells the model to write euros into: `amount` and every `*_eur`.

    The alias rule above is what makes this readable: a figure column is named for what it is,
    so the tool result can format it as money and the check can tell a figure from a count.
    """
    return name == "amount" or name.endswith("_eur")


@dataclass(frozen=True)
class Rejection:
    """A statement the guard or SQLite refused, and why. Feeds the one retry."""

    sql: str
    error: str
    reasoning: str = ""
    """What the sub-agent said it was doing. Handed back so the retry corrects a reading rather
    than starting from nothing."""


@dataclass(frozen=True)
class Revision:
    """A statement that ran and did not answer the question. Feeds the one rewrite.

    The other half of `Rejection`: nothing was wrong with the SQL, so the prompt says so and
    hands over the reason (a degenerate result, or the check pass's one sentence) and what to
    ask instead. See `finquery.query.check` and ticket 40.
    """

    sql: str
    reason: str
    advice: str = ""
    reasoning: str = ""


query_agent = Agent(
    instructions=INSTRUCTIONS,
    output_type=ToolOutput(GeneratedSql, name="run_sql"),
    name="finquery-query",
)


def load_query_context(session: Session, profile_id: str, *, today: date | None = None) -> QueryContext:
    """Read the profile's data range, taxonomy and busiest counterparties."""
    stats = (
        session.execute(
            text(
                f"""
                SELECT count(*)         AS bookings,
                       min(booked_on)   AS first_booked_on,
                       max(booked_on)   AS last_booked_on,
                       count(category)  AS categorized
                FROM {QUERY_VIEW}
                WHERE profile_id = :profile_id
                """
            ),
            {"profile_id": profile_id},
        )
        .mappings()
        .one()
    )
    accounts = session.execute(
        text(f"SELECT DISTINCT account FROM {QUERY_VIEW} WHERE profile_id = :profile_id ORDER BY account"),
        {"profile_id": profile_id},
    ).scalars()
    counterparties = session.execute(
        text(
            f"""
            SELECT coalesce(counterparty, description) AS merchant, count(*) AS bookings
            FROM {QUERY_VIEW}
            WHERE profile_id = :profile_id
            GROUP BY merchant
            ORDER BY bookings DESC, merchant
            LIMIT :limit
            """
        ),
        {"profile_id": profile_id, "limit": TOP_COUNTERPARTIES},
    ).all()
    categories = session.scalars(
        select(Category)
        .options(selectinload(Category.subcategories))
        .where(Category.profile_id == profile_id)
        .order_by(Category.position)
    ).all()
    return QueryContext(
        today=today or date.today(),
        transaction_count=stats["bookings"],
        first_booked_on=stats["first_booked_on"],
        last_booked_on=stats["last_booked_on"],
        categorized_count=stats["categorized"],
        accounts=tuple(accounts),
        taxonomy=tuple(
            (category.name, tuple(sub.name for sub in category.subcategories)) for category in categories
        ),
        counterparties=tuple((merchant, count) for merchant, count in counterparties),
    )


def subcategory_parents(context: QueryContext) -> dict[str, str]:
    """Each subcategory name, folded, to the category it belongs to.

    What the guard needs to tell a statement that filtered `category = 'Supermarket'` which
    category it meant. A name that is also a category, or that two categories share, is left
    out: there is no single parent to name.
    """
    categories = {name.casefold() for name, _ in context.taxonomy}
    parents: dict[str, str] = {}
    ambiguous: set[str] = set()
    for name, subs in context.taxonomy:
        for sub in subs:
            key = sub.casefold()
            if key in categories:
                continue
            if key in parents and parents[key] != name:
                ambiguous.add(key)
            parents[key] = name
    return {key: parent for key, parent in parents.items() if key not in ambiguous}


def _category_line(context: QueryContext) -> str:
    if context.categorized_count == 0:
        return (
            "- no booking is categorized yet: `category` and `subcategory` are NULL everywhere, so never "
            "filter on them. Recognize a topic by its merchants instead."
        )
    if context.categorized_count < context.transaction_count:
        return (
            f"- only {context.categorized_count} of {context.transaction_count} bookings have a category, so a "
            "category filter alone misses the rest. Group by `coalesce(category, 'Needs review')` so the rest "
            "is visible as its own bucket, and never label a booking from its text."
        )
    return "- every booking has a category, so filter on `category` or `subcategory` with the names above."


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _months_before(month: date, count: int) -> date:
    """The first of the month `count` months before this one."""
    index = month.year * 12 + month.month - 1 - count
    return date(index // 12, index % 12 + 1, 1)


def _last_day(month: date) -> date:
    return _months_before(month, -1) - timedelta(days=1)


def periods(last_booked_on: str | None) -> list[str]:
    """This month, last month, this quarter and last quarter, counted from the newest booking.

    The 9B review read "letztes Quartal" as the quarter today falls in, over data that ended
    three days earlier, and it never said which months it had used. There is nothing for a model
    to work out here, so the prompt does the arithmetic and hands it the dates.
    """
    if not last_booked_on:
        return []
    latest = _month_start(date.fromisoformat(last_booked_on))
    previous = _months_before(latest, 1)
    quarter = date(latest.year, (latest.month - 1) // 3 * 3 + 1, 1)
    before = _months_before(quarter, 3)
    return [
        f"- the newest booking is in {latest:%Y-%m}, so this month is "
        f"{latest.isoformat()} to {_last_day(latest).isoformat()} and last month is "
        f"{previous.isoformat()} to {_last_day(previous).isoformat()}",
        f"- this quarter is {quarter.isoformat()} to {_last_day(_months_before(quarter, -2)).isoformat()} "
        f"and last quarter is {before.isoformat()} to {_last_day(_months_before(before, -2)).isoformat()}",
    ]


def taxonomy_lines(context: QueryContext) -> list[str]:
    """The categories, one per line, with their subcategories marked as such.

    `Groceries (Supermarket, Bakery, Drugstore)` on one long line is what a 9B model reads as a
    list of alternative category values, six times in the review of 2026-09-05. One line per
    category, and the word subcategories in front of the names, cannot be read that way.
    """
    lines = ["- categories, one per line. Only the name in front of the colon goes in `category`:"]
    for name, subs in context.taxonomy:
        detail = f"subcategories: {', '.join(subs)}" if subs else "no subcategories"
        lines.append(f"    category {name} / {detail}")
    return lines


def profile_facts(context: QueryContext) -> str:
    """The household paragraph of the prompt. Pure, so training can rebuild it."""
    merchants = ", ".join(f"{merchant} ({count})" for merchant, count in context.counterparties)
    lines = [
        "This household:",
        f"- today is {context.today.isoformat()}",
        f"- {context.transaction_count} bookings from {context.first_booked_on} to {context.last_booked_on}",
        *periods(context.last_booked_on),
        f"- accounts: {', '.join(context.accounts) or 'none'}",
        *taxonomy_lines(context),
        _category_line(context),
        f"- busiest counterparties: {merchants}",
    ]
    return "\n".join(lines)


def _correction(opening: str, *, reasoning: str, sql: str, label: str, problem: str, advice: str = "") -> str:
    """The retry section: what you said, what you wrote, what is wrong, what to hand back.

    A correction, not a fresh start. The model reads its own reading of the question next to the
    finding, so the round that follows fixes the line that was wrong instead of writing an
    unrelated statement, which is what the review of 2026-09-05 saw a 9B model do (ticket 42).
    """
    parts = [f"{opening} Correct it: keep what was right and change only what the problem names."]
    if reasoning.strip():
        parts.append(f"Your reasoning was:\n{reasoning.strip()}")
    parts.append(f"{label}:\n{sql.strip()}")
    parts.append(f"Problem: {problem}")
    if advice.strip():
        parts.append(advice.strip())
    parts.append("Answer with the corrected reasoning and the corrected statement.")
    return "\n\n".join(parts)


def query_prompt(
    request: str,
    context: QueryContext,
    *,
    hints: str | None = None,
    rejected: Rejection | None = None,
    revised: Revision | None = None,
) -> str:
    """Build the whole prompt the query sub-agent sees. Pure function, reused by training."""
    sections = [VIEW_SCHEMA, RULES, EXAMPLES, profile_facts(context), f"Question: {request.strip()}"]
    if hints:
        sections.append(f"The assistant adds: {hints.strip()}")
    if rejected is not None:
        sections.append(
            _correction(
                "Your previous statement did not run.",
                reasoning=rejected.reasoning,
                sql=rejected.sql,
                label="Refused SQL",
                problem=rejected.error,
            )
        )
    if revised is not None:
        sections.append(
            _correction(
                "Your previous statement ran, but it did not answer the question.",
                reasoning=revised.reasoning,
                sql=revised.sql,
                label="Previous SQL",
                problem=revised.reason,
                advice=revised.advice,
            )
        )
    return "\n\n".join(sections)


async def write_sql(
    model: Model,
    request: str,
    context: QueryContext,
    *,
    hints: str | None = None,
    rejected: Rejection | None = None,
    revised: Revision | None = None,
    model_settings: ModelSettings | None = None,
) -> GeneratedSql:
    """Ask the fast slot for one statement through the forced `run_sql` tool.

    Both fields come back: the statement to run, and the reading of the question it says it
    wrote, which the retry, the rewrite and the check pass all get to see.
    """
    result = await query_agent.run(
        query_prompt(request, context, hints=hints, rejected=rejected, revised=revised),
        model=model,
        model_settings=model_settings,
    )
    return result.output
