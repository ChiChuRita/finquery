"""The query sub-agent: one question in, one SQLite SELECT out.

Fast slot, one forced tool call, no free text (ADR 0002 pins every sub-agent to fast). The
prompt is built by `query_prompt`, a pure function of the request and the shape of the
profile's data: the same framing serves production and the later adapter training, so a
training row is exactly the text the model saw here plus the SQL it wrote.
"""

from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from finquery.db import QUERY_VIEW, Category
from finquery.query.guard import MAX_ROWS

TOP_COUNTERPARTIES = 30

INSTRUCTIONS = """\
You write SQLite queries over one household's bank transactions. You are given a question and
the shape of the data. Call `run_sql` exactly once with a statement that answers the question.
You never explain, never apologize and never answer the question in words: the SQL is the answer.
"""

VIEW_SCHEMA = f"""\
The view (the only relation you may name, already filtered to this household):

  {QUERY_VIEW}
    id            text     booking id
    booked_on     text     booking date as 'YYYY-MM-DD'; compare as text or use strftime
    amount_cents  integer  signed cents, negative is money out, positive is money in
    amount        real     the same amount in euros (amount_cents / 100.0)
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
- Spending is negative. For a spending question filter `amount_cents < 0` and report a positive
  figure with `ROUND(-SUM(amount), 2)`. Income is `amount_cents > 0`.
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
- A month is `strftime('%Y-%m', booked_on)`. A period is `booked_on BETWEEN '2025-04-01' AND
  '2025-04-30'`. There is no date type, so never call date functions on anything else.
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

EXAMPLES = """\
Worked examples:

Question: Wie viel habe ich im Mai 2025 fuer Lebensmittel ausgegeben?
SQL:
SELECT ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount_cents < 0
  AND booked_on BETWEEN '2025-05-01' AND '2025-05-31'
  AND (lower(description || ' ' || coalesce(counterparty, '')) LIKE '%rewe%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%aldi%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%lidl%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%edeka%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%kaufland%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%netto%')

Question: How much did I spend per month in 2025?
SQL:
SELECT strftime('%Y-%m', booked_on) AS month, ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount_cents < 0 AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'
GROUP BY month
ORDER BY month

Question: Which merchants took the most money in 2025, and how often?
SQL:
SELECT coalesce(counterparty, description) AS merchant,
       ROUND(-SUM(amount), 2) AS total_eur,
       COUNT(*) AS bookings
FROM transaction_view
WHERE amount_cents < 0 AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'
GROUP BY merchant
ORDER BY total_eur DESC
LIMIT 10

Question: Welche Abos zahle ich 2025 und was kosten sie insgesamt?
SQL:
SELECT coalesce(counterparty, description) AS merchant,
       ROUND(-SUM(amount), 2) AS total_eur,
       COUNT(*) AS bookings
FROM transaction_view
WHERE amount_cents < 0
  AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'
  AND (lower(description || ' ' || coalesce(counterparty, '')) LIKE '%netflix%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%spotify%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%prime%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%adobe%')
GROUP BY merchant
UNION ALL
SELECT 'TOTAL' AS merchant, ROUND(-SUM(amount), 2) AS total_eur, COUNT(*) AS bookings
FROM transaction_view
WHERE amount_cents < 0
  AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'
  AND (lower(description || ' ' || coalesce(counterparty, '')) LIKE '%netflix%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%spotify%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%prime%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%adobe%')

Question: Wie viel habe ich 2025 pro Kategorie ausgegeben?
SQL:
SELECT coalesce(category, 'Needs review') AS topic, ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount_cents < 0 AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'
GROUP BY topic
ORDER BY total_eur DESC

Question: Compare my spending on eating out in April 2025 with May 2025.
SQL:
SELECT strftime('%Y-%m', booked_on) AS month, ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount_cents < 0
  AND booked_on BETWEEN '2025-04-01' AND '2025-05-31'
  AND (lower(description || ' ' || coalesce(counterparty, '')) LIKE '%lieferando%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%vapiano%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%doener%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%cafe%'
    OR lower(description || ' ' || coalesce(counterparty, '')) LIKE '%dean and david%')
GROUP BY month
ORDER BY month
"""


class GeneratedSql(BaseModel):
    """The statement the sub-agent wants to run."""

    sql: str = Field(description=f"One SQLite SELECT over {QUERY_VIEW}.")


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


@dataclass(frozen=True)
class Rejection:
    """A statement the guard or SQLite refused, and why. Feeds the one retry."""

    sql: str
    error: str


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


def profile_facts(context: QueryContext) -> str:
    """The household paragraph of the prompt. Pure, so training can rebuild it."""
    taxonomy = "; ".join(
        f"{name} ({', '.join(subs)})" if subs else name for name, subs in context.taxonomy
    )
    merchants = ", ".join(f"{merchant} ({count})" for merchant, count in context.counterparties)
    lines = [
        "This household:",
        f"- today is {context.today.isoformat()}",
        f"- {context.transaction_count} bookings from {context.first_booked_on} to {context.last_booked_on}",
        f"- accounts: {', '.join(context.accounts) or 'none'}",
        f"- categories: {taxonomy}",
        _category_line(context),
        f"- busiest counterparties: {merchants}",
    ]
    return "\n".join(lines)


def query_prompt(
    request: str, context: QueryContext, *, hints: str | None = None, rejected: Rejection | None = None
) -> str:
    """Build the whole prompt the query sub-agent sees. Pure function, reused by training."""
    sections = [VIEW_SCHEMA, RULES, EXAMPLES, profile_facts(context), f"Question: {request.strip()}"]
    if hints:
        sections.append(f"The assistant adds: {hints.strip()}")
    if rejected is not None:
        sections.append(
            "Your previous statement did not run. Write a different one that answers the same question.\n\n"
            f"Refused SQL:\n{rejected.sql.strip()}\n\nProblem: {rejected.error}"
        )
    return "\n\n".join(sections)


async def write_sql(
    model: Model,
    request: str,
    context: QueryContext,
    *,
    hints: str | None = None,
    rejected: Rejection | None = None,
    model_settings: ModelSettings | None = None,
) -> str:
    """Ask the fast slot for one statement through the forced `run_sql` tool."""
    result = await query_agent.run(
        query_prompt(request, context, hints=hints, rejected=rejected), model=model, model_settings=model_settings
    )
    return result.output.sql
