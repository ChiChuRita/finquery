"""The SQL guard: what the query sub-agent writes is checked, then run read-only.

Two independent locks, because a generated statement is untrusted input:

- `validate_sql` parses it with sqlglot and lets exactly one read-only SELECT over
  `transaction_view` through, with a LIMIT of at most `MAX_ROWS`. Its errors are written for
  the sub-agent to read and fix.
- `execute_read_only` runs it on a connection whose `transaction_view` is a temp view already
  filtered to one profile, with `query_only` on. SQLite resolves an unqualified name in the
  temp schema before the main one, and the guard refuses a schema-qualified name, so no WHERE
  clause can widen the profile scope and no statement can write.

See docs/adr/0004-numbers-only-from-executed-queries.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlglot import exp
from sqlglot.errors import TokenError

from finquery.db import QUERY_VIEW

DIALECT = "sqlite"
MAX_ROWS = 200

# The statement kinds that may reach SQLite. A set operation (UNION, EXCEPT, INTERSECT) is
# still one read-only statement, and comparing two periods reads well as one.
ALLOWED_STATEMENTS = (exp.Select, exp.SetOperation)

# SQLite functions that touch the file system or load code. Most builds ship them disabled;
# the guard refuses them anyway so safety does not depend on the build.
FORBIDDEN_FUNCTIONS = frozenset({"load_extension", "readfile", "writefile", "edit", "fts3_tokenizer"})

# The two columns a model reaches for when it wants to classify a booking itself.
TEXT_COLUMNS = frozenset({"description", "counterparty"})

MAX_MERCHANT_PATTERNS = 8
"""How many LIKE patterns over the booking text one statement may carry.

A topic that spans merchants (six supermarkets, four subscriptions) is a handful. Thirty is
the local fast model, asked about a person it could not find, matching every merchant it was
shown and returning the household's whole spending as the answer.
"""

EVERY_MERCHANT = (
    "This statement matches {count} merchant patterns, which is every merchant in the list and "
    "not the one the question names. A question about one person or one merchant takes one "
    f"LIKE term for that name, a topic that spans merchants at most {MAX_MERCHANT_PATTERNS}. "
    "When no booking carries that name, return no rows: the answer is then that the data holds "
    "none, never the total of everything else."
)

CENTS_COLUMN = "amount_cents"

MAX_STATEMENT_CHARS = 1500
"""How long a statement may be.

A question about this household is a few hundred characters of SQL. The 9B review of
2026-09-05 produced a 9294-character statement with 106 UNION branches and a made-up relation
in it: past this length the model is no longer answering the question, it is flailing.
"""

CENTS_AS_EUROS = (
    f"`{CENTS_COLUMN}` is integer cents, so a figure computed from it is a hundred times the "
    "euro amount, and dividing it by 100 throws the cents away because SQLite divides integers. "
    "The euro column is `amount`: write `ROUND(-SUM(amount), 2)` for a spending total and "
    f"`ROUND(amount, 2)` for one booking. Never select, sum or divide `{CENTS_COLUMN}`."
)

CROSS_JOIN = (
    "A join without a condition multiplies the bookings by each other, so every figure it "
    f"returns is wrong. Read {QUERY_VIEW} once, and compare two periods or two topics with a "
    "GROUP BY or with UNION ALL instead."
)

TOO_LONG = (
    "This statement is {length} characters, and the limit is {limit}. A question about one "
    "household is answered by one aggregate over a handful of conditions: write that, and if the "
    "question cannot be answered that way, return the rows that come closest."
)

SUBCATEGORY_AS_CATEGORY = (
    "{name} is a subcategory of {parent}, not a category, so `category = '{name}'` matches "
    "nothing. Filter the parent with `category = '{parent}'`, or the subcategory column with "
    "`subcategory = '{name}'`."
)

INVENTED_CATEGORY = (
    "A CASE over description or counterparty that returns a label of its own invents a "
    "categorization. The category of a booking is the `category` column and nothing else: group "
    "by it and show a booking without one as the bucket 'Needs review' "
    "(`coalesce(category, 'Needs review')`). Match description or counterparty in a WHERE clause "
    "to pick the bookings a question is about, never to label them."
)


class SqlRejected(ValueError):
    """The generated SQL is not a single read-only SELECT over the allowed view."""


class SqlFailed(ValueError):
    """The generated SQL passed the guard but SQLite could not run it."""


@dataclass(frozen=True)
class Rows:
    """What a query returned: the column names in order and one dict per row."""

    columns: list[str]
    rows: list[dict[str, Any]]


def _limit_of(statement: exp.Query) -> int | None:
    limit = statement.args.get("limit")
    if limit is None:
        return None
    expression = limit.expression
    if isinstance(expression, exp.Literal) and expression.is_int:
        return int(expression.name)
    # A non-literal limit (an expression or a placeholder) counts as no limit at all.
    return None


def validate_sql(sql: str, *, taxonomy: Mapping[str, str] | None = None) -> str:
    """Return the statement that may run, or raise `SqlRejected` with a fixable message.

    `taxonomy` maps each subcategory name (case-folded) to the category it belongs to, which is
    what lets the guard tell a model that wrote `category = 'Supermarket'` which category it
    means. A caller with no taxonomy at hand (the dashboard's own statements) simply passes none.
    """
    text = sql.strip().removesuffix(";").strip()
    if not text:
        raise SqlRejected("The statement is empty.")
    if len(text) > MAX_STATEMENT_CHARS:
        raise SqlRejected(TOO_LONG.format(length=len(text), limit=MAX_STATEMENT_CHARS))
    try:
        parsed = [statement for statement in sqlglot.parse(text, read=DIALECT) if statement is not None]
    except (sqlglot.ParseError, TokenError) as exc:
        # A `TokenError` is what an unterminated string literal raises, and a model writing a
        # LIKE pattern gets one wrong now and then. Uncaught it leaves the tool as an exception
        # and takes the turn with it; here it is a refusal the sub-agent fixes on its retry.
        raise SqlRejected(f"SQLite cannot parse this: {exc}") from exc
    if len(parsed) != 1:
        raise SqlRejected(f"Send exactly one statement, not {len(parsed)}.")

    statement = parsed[0]
    if not isinstance(statement, ALLOWED_STATEMENTS):
        raise SqlRejected(f"Only a SELECT may run, not {statement.key.upper()}.")

    known = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)} | {QUERY_VIEW}
    for table in statement.find_all(exp.Table):
        if table.db or table.catalog:
            raise SqlRejected(f"Do not prefix a relation with a schema: write {QUERY_VIEW}, not {table.sql(DIALECT)}.")
        # A table-valued function (pragma_table_info(...), json_each(...)) parses as a table
        # with no name, so an unnamed source is refused with whatever it looked like.
        if table.name.lower() not in known:
            source = table.name or table.sql(DIALECT)
            raise SqlRejected(f"{source} may not be read. The only relation you may name is {QUERY_VIEW}.")
    for function in statement.find_all(exp.Anonymous):
        if str(function.this).lower() in FORBIDDEN_FUNCTIONS:
            raise SqlRejected(f"The function {function.this} may not be called.")
    for join in statement.find_all(exp.Join):
        # A comma join and an explicit CROSS JOIN both arrive here without a condition.
        if join.args.get("on") is None and not join.args.get("using"):
            raise SqlRejected(CROSS_JOIN)
    for case in statement.find_all(exp.Case):
        if _invents_a_category(case):
            raise SqlRejected(INVENTED_CATEGORY)
    if (patterns := _merchant_patterns(statement)) > MAX_MERCHANT_PATTERNS:
        raise SqlRejected(EVERY_MERCHANT.format(count=patterns))
    for select in statement.find_all(exp.Select):
        if _cents_as_a_figure(select):
            raise SqlRejected(CENTS_AS_EUROS)
    if (mistaken := _subcategory_as_category(statement, taxonomy or {})) is not None:
        name, parent = mistaken
        raise SqlRejected(SUBCATEGORY_AS_CATEGORY.format(name=name, parent=parent))
    _real_division(statement)

    current = _limit_of(statement)
    if current is None or current > MAX_ROWS:
        statement = statement.limit(MAX_ROWS)
    # Rendered from the parsed tree, so the statement in the transcript is the one that ran,
    # formatted the same way whatever the model wrote.
    return statement.sql(dialect=DIALECT, pretty=True)


def _merchant_patterns(statement: exp.Expression) -> int:
    """How many LIKE terms over description or counterparty the statement carries."""
    return sum(
        1
        for like in statement.find_all(exp.Like, exp.ILike)
        if any(column.name.lower() in TEXT_COLUMNS for column in like.this.find_all(exp.Column))
    )


def _cents_as_a_figure(select: exp.Select) -> bool:
    """True when a selected expression turns `amount_cents` into a number the answer would quote.

    The two worst numeric failures of the 9B review are one rule: `ROUND(-SUM(amount_cents), 2)
    AS total_eur` published 90.762,00 EUR for 907,62 EUR, and `-amount_cents / 100` published
    10.560,00 EUR for 10.560,82 EUR. Both are cents where euros belong, so a selected column
    that is `amount_cents` bare, inside an aggregate or divided by anything is refused.

    A comparison is untouched, because the sign test (`CASE WHEN amount_cents < -20000 THEN ...`)
    reads the column without ever printing it, and so is a threshold in the WHERE clause: this
    looks at the selected expressions only.
    """
    for projection in select.expressions:
        expression = projection.unalias() if isinstance(projection, exp.Alias) else projection
        if isinstance(expression, exp.Column) and expression.name.lower() == CENTS_COLUMN:
            return True
        for column in expression.find_all(exp.Column):
            if column.name.lower() != CENTS_COLUMN:
                continue
            node: exp.Expression = column
            while node is not expression and node.parent is not None:
                node = node.parent
                if isinstance(node, exp.Predicate):
                    # A comparison, so this column decides which rows count and is never printed.
                    break
                if isinstance(node, (exp.AggFunc, exp.Div)):
                    return True
    return False


def _subcategory_as_category(
    statement: exp.Expression, taxonomy: Mapping[str, str]
) -> tuple[str, str] | None:
    """The first subcategory name a `category =` or `category IN (...)` compares against.

    Six statements of the 9B review filtered `category IN ('Supermarket', 'Bakery',
    'Drugstore')`, which matches nothing and costs a round trip every time. The guard knows the
    profile's taxonomy, so the refusal names the category those subcategories belong to.
    """
    if not taxonomy:
        return None
    literals: list[exp.Expression] = []
    for equality in statement.find_all(exp.EQ):
        if _is_category_column(equality.this):
            literals.append(equality.expression)
        elif _is_category_column(equality.expression):
            literals.append(equality.this)
    for member in statement.find_all(exp.In):
        if _is_category_column(member.this):
            literals.extend(member.expressions)
    for literal in literals:
        if isinstance(literal, exp.Literal) and literal.is_string:
            if (parent := taxonomy.get(literal.name.casefold())) is not None:
                return literal.name, parent
    return None


def _is_category_column(expression: exp.Expression) -> bool:
    return isinstance(expression, exp.Column) and expression.name.lower() == "category"


def _real_division(statement: exp.Expression) -> None:
    """Make `/ 100` real division, in place.

    SQLite divides two integers as integers, so `something / 100` silently drops the cents. The
    prompt writes `100.0` everywhere; this is the same for a statement that did not.
    """
    for division in statement.find_all(exp.Div):
        divisor = division.expression
        if isinstance(divisor, exp.Literal) and divisor.is_int:
            division.set("expression", exp.Literal.number(f"{divisor.name}.0"))


def _invents_a_category(case: exp.Case) -> bool:
    """True when this CASE turns a description or counterparty match into a label of its own.

    The single rule behind ADR 0004 for categories: a category is data the user owns, not
    something the model derives from the booking text. `CASE WHEN description LIKE '%rewe%'
    THEN 'Groceries'` is indistinguishable in a chart from the profile's own categories, and
    the review of 2026-09-04 saw it disagree with the real figures by two orders of magnitude.
    Matching the same columns is still fine as a filter; only turning a match into a string is
    refused.
    """
    conditions = [branch.this for branch in case.args.get("ifs", []) if branch.this is not None]
    # `CASE description WHEN 'X' THEN ...` puts the column on the CASE itself.
    if (operand := case.this) is not None:
        conditions.append(operand)
    matches_text = any(
        column.name.lower() in TEXT_COLUMNS
        for condition in conditions
        for column in condition.find_all(exp.Column)
    )
    if not matches_text:
        return False
    results = [branch.args.get("true") for branch in case.args.get("ifs", [])]
    results.append(case.args.get("default"))
    return any(isinstance(result, exp.Literal) and result.is_string for result in results)


def execute_read_only(session: Session, sql: str, profile_id: str) -> Rows:
    """Run validated SQL against one profile's slice of the query view.

    The profile filter is a temp view that shadows the real one for this connection only. It
    has to be created with the id inlined because SQLite forbids parameters in a view.
    """
    connection = session.connection()
    scope = f"CREATE TEMP VIEW {QUERY_VIEW} AS SELECT * FROM main.{QUERY_VIEW} WHERE profile_id = '{_quote(profile_id)}'"
    try:
        connection.exec_driver_sql(scope)
        connection.exec_driver_sql("PRAGMA query_only = ON")
        # TODO: no statement timeout. SQLite is synchronous here, so a pathological query would
        # block the process; add an interrupt on a progress handler if that ever bites.
        result = connection.exec_driver_sql(sql)
        columns = [str(key) for key in result.keys()]
        rows = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    except SQLAlchemyError as exc:
        raise SqlFailed(str(getattr(exc, "orig", None) or exc)) from exc
    finally:
        connection.exec_driver_sql("PRAGMA query_only = OFF")
        connection.exec_driver_sql(f"DROP VIEW IF EXISTS temp.{QUERY_VIEW}")
        connection.commit()
    # Two columns of the same name would collide in the row dicts; keep the headers honest.
    return Rows(columns=list(dict.fromkeys(columns)), rows=rows)


def _quote(value: str) -> str:
    return value.replace("'", "''")
