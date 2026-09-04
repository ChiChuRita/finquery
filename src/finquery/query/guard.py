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

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlglot import exp

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


def validate_sql(sql: str) -> str:
    """Return the statement that may run, or raise `SqlRejected` with a fixable message."""
    text = sql.strip().removesuffix(";").strip()
    if not text:
        raise SqlRejected("The statement is empty.")
    try:
        parsed = [statement for statement in sqlglot.parse(text, read=DIALECT) if statement is not None]
    except sqlglot.ParseError as exc:
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
    for case in statement.find_all(exp.Case):
        if _invents_a_category(case):
            raise SqlRejected(INVENTED_CATEGORY)

    current = _limit_of(statement)
    if current is None or current > MAX_ROWS:
        statement = statement.limit(MAX_ROWS)
    # Rendered from the parsed tree, so the statement in the transcript is the one that ran,
    # formatted the same way whatever the model wrote.
    return statement.sql(dialect=DIALECT, pretty=True)


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
