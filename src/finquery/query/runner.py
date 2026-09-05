"""One question to rows: delegate, guard, execute, retry once.

This is what the chat agent's `query` tool calls, and what the chart sub-agent of ticket 06
calls to get its data. Nothing here talks to the model directly except through `write_sql`.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session, sessionmaker

from finquery.formats import eur
from finquery.providers import ModelResolver, ProviderNotAvailable
from finquery.query.guard import MAX_ROWS, Rows, SqlFailed, SqlRejected, execute_read_only, validate_sql
from finquery.query.subagent import Rejection, load_query_context, write_sql

# The sub-agent writes, the guard judges. A rejected statement is sent back once with the
# reason; a second refusal is reported to the chat agent instead of looping.
ATTEMPTS = 2

NO_DATA = "This profile has no transactions yet, so there is nothing to query. Import a bank statement first."


@dataclass(frozen=True)
class QueryOutcome:
    """What the query tool returns: the executed SQL and its rows, or why there are none."""

    request: str
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    error: str | None = None

    def payload(self) -> dict[str, Any]:
        """The tool result: what the chat agent reads and what the transcript renders."""
        return {
            "request": self.request,
            "sql": self.sql,
            "row_count": len(self.rows),
            "columns": self.columns,
            "rows": self.rows,
            "figures": figures(self.columns, self.rows),
            "summary": self.summary,
            "error": self.error,
        }


FIGURE_LINES = 25
"""How many rows are written out as figures. A longer result is a table the answer summarizes."""


def is_euro_column(name: str) -> bool:
    """The columns the SQL sub-agent is told to write euros into: `amount` and every `*_eur`."""
    return name == "amount" or name.endswith("_eur")


def figures(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    """The rows as lines the answer can copy, every euro figure already written the German way.

    `rows` stays numeric for the transcript's table. This is the same data for the model, which
    otherwise copies `13800.0` out of a row and writes it into a German sentence; the review of
    2026-09-04 and the local fast model both did.
    """
    lines: list[str] = []
    for row in rows[:FIGURE_LINES]:
        parts: list[str] = []
        for column in columns:
            value = row.get(column)
            if is_euro_column(column) and isinstance(value, (int, float)) and not isinstance(value, bool):
                parts.append(f"{column} {eur(round(value * 100))} EUR")
            else:
                parts.append(f"{column} {value}")
        lines.append(", ".join(parts))
    return lines


def summarize(rows: Rows) -> str:
    """One line the chat agent can read before it looks at the rows."""
    if not rows.rows:
        return "The query returned no rows, so the data holds no answer to this question."
    if len(rows.rows) == 1 and len(rows.columns) == 1:
        column = rows.columns[0]
        return f"One row: {column} = {rows.rows[0][column]}"
    summary = f"{len(rows.rows)} rows with columns {', '.join(rows.columns)}."
    if len(rows.rows) >= MAX_ROWS:
        summary += f" The {MAX_ROWS} row limit was reached, so this is a slice and not the whole result."
    return summary


async def run_query(
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    session_factory: sessionmaker[Session],
    profile_id: str,
    request: str,
    hints: str | None = None,
) -> QueryOutcome:
    """Turn a natural-language request into executed SQL and its rows.

    The slot is resolved only once there is data to query, so an empty profile is answered
    without any model at all.
    """
    with session_factory() as session:
        context = load_query_context(session, profile_id)
    if context.transaction_count == 0:
        return QueryOutcome(request=request, summary=NO_DATA, error=NO_DATA)
    try:
        model = resolve_model("fast")
    except ProviderNotAvailable as exc:
        unavailable = f"The query sub-agent is unavailable: {exc}"
        return QueryOutcome(request=request, summary=unavailable, error=unavailable)

    rejected: Rejection | None = None
    for _ in range(ATTEMPTS):
        try:
            sql = await write_sql(
                model, request, context, hints=hints, rejected=rejected, model_settings=model_settings
            )
        except Exception as exc:  # noqa: BLE001 - any model or transport failure is one message here
            failure = f"The query sub-agent did not return a statement: {exc}"
            return QueryOutcome(request=request, summary=failure, error=failure)
        try:
            validated = validate_sql(sql)
            with session_factory() as session:
                rows = execute_read_only(session, validated, profile_id)
        except (SqlRejected, SqlFailed) as exc:
            rejected = Rejection(sql=sql, error=str(exc))
            continue
        return QueryOutcome(
            request=request, sql=validated, columns=rows.columns, rows=rows.rows, summary=summarize(rows)
        )

    assert rejected is not None
    failure = f"The query was refused {ATTEMPTS} times, last reason: {rejected.error}"
    return QueryOutcome(request=request, sql=rejected.sql, summary=failure, error=failure)
