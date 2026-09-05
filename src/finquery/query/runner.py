"""One question to rows: delegate, guard, execute, check, rewrite once.

This is what the chat agent's `query` tool calls, and what the chart sub-agent of ticket 06
calls to get its data. Nothing here talks to the model directly except through `write_sql` and
`check_result`.

Three things can send the sub-agent back, each of them once and all of them together bounded by
`MODEL_CALLS`:

- the guard or SQLite refused the statement (`Rejection`);
- the result is degenerate, which is code and free (`check.degenerate_reason`);
- the check pass says the statement answers a different question (`check.check_result`).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session, sessionmaker

from finquery.formats import eur
from finquery.providers import ModelResolver, ProviderNotAvailable
from finquery.query.check import CHECKING, REWRITING, causes, check_result, degenerate_reason
from finquery.query.guard import MAX_ROWS, Rows, SqlFailed, SqlRejected, execute_read_only, validate_sql
from finquery.query.subagent import (
    QueryContext,
    Rejection,
    Revision,
    is_euro_column,
    load_query_context,
    subcategory_parents,
    write_sql,
)

# The sub-agent writes, the guard judges. A rejected statement is sent back once with the
# reason; a second refusal is reported to the chat agent instead of looping.
ATTEMPTS = 2

MODEL_CALLS = 3
"""The ceiling one `run_query` may spend: the statement, the check, and one rewrite.

Everything ticket 40 added lives inside this number. A statement that had to be written twice
(a refusal, a degenerate result, a revise) is taken as it stands, which is why a check never
follows a rewrite and a rewrite is never rewritten.
"""

Narrator = Callable[[str], None]

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
    attempts: int = 1
    """How many statements were written for this result. More than one means a refusal, a
    degenerate result or the check pass sent the sub-agent back."""
    refusals: list[str] = field(default_factory=list)
    """What the guard or SQLite said about the statements that never ran."""
    notes: list[str] = field(default_factory=list)
    """The lines this call narrated, in order. The panel got them live; the benchmark reads
    them afterwards to say what the check did."""

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
                # A SUM over no rows is NULL: say so, rather than hand the model the word None.
                parts.append(f"{column} {'no value' if value is None else value}")
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
    check: bool = True,
    narrate: Narrator | None = None,
    context: QueryContext | None = None,
    today: date | None = None,
) -> QueryOutcome:
    """Turn a natural-language request into executed SQL and its rows.

    The slot is resolved only once there is data to query, so an empty profile is answered
    without any model at all.

    `check` off is the path as it was before ticket 40: one statement, one retry on a refusal,
    and whatever it returns. On, the result is judged before it is handed over, and a rewrite
    is asked for once. The chart tool passes it through and the benchmark turns it off with
    `--no-check`, which is how the two are measured against each other.

    `context` is for a caller that already loaded it (the chart tool, the benchmark, which pins
    `today` so a relative period lands inside the shipped year).
    """
    say: Narrator = narrate or (lambda _text: None)
    notes: list[str] = []

    def note(line: str) -> None:
        notes.append(line)
        say(line)

    if context is None:
        with session_factory() as session:
            context = load_query_context(session, profile_id, today=today)
    if context.transaction_count == 0:
        return QueryOutcome(request=request, summary=NO_DATA, error=NO_DATA)
    try:
        model = resolve_model("fast")
    except ProviderNotAvailable as exc:
        unavailable = f"The query sub-agent is unavailable: {exc}"
        return QueryOutcome(request=request, summary=unavailable, error=unavailable)

    rejected: Rejection | None = None
    revised: Revision | None = None
    refusals: list[str] = []
    calls = 0
    written = 0
    outcome: QueryOutcome | None = None

    while calls < MODEL_CALLS:
        try:
            sql = await write_sql(
                model, request, context, hints=hints, rejected=rejected, revised=revised, model_settings=model_settings
            )
        except Exception as exc:  # noqa: BLE001 - any model or transport failure is one message here
            failure = f"The query sub-agent did not return a statement: {exc}"
            # A rewrite that never arrived leaves the result that did.
            return outcome or QueryOutcome(request=request, summary=failure, error=failure, notes=notes)
        calls += 1
        written += 1
        try:
            # The taxonomy is what lets the guard answer a `category = 'Supermarket'` with the
            # category that subcategory belongs to.
            validated = validate_sql(sql, taxonomy=subcategory_parents(context))
            with session_factory() as session:
                rows = execute_read_only(session, validated, profile_id)
        except (SqlRejected, SqlFailed) as exc:
            rejected, revised = Rejection(sql=sql, error=str(exc)), None
            refusals.append(str(exc))
            if len(refusals) >= ATTEMPTS:
                break
            continue
        first = written == 1
        rejected = revised = None
        outcome = QueryOutcome(
            request=request,
            sql=validated,
            columns=rows.columns,
            rows=rows.rows,
            summary=summarize(rows),
            attempts=written,
            refusals=list(refusals),
            notes=notes,
        )
        # Only the statement written first is judged. One that already came back once has had
        # its round, and a second opinion on it would cost more than the answer is worth.
        if not check or not first:
            return outcome
        if reason := degenerate_reason(request, context, rows.columns, rows.rows):
            note(REWRITING.format(reason=reason))
            revised = Revision(sql=validated, reason=reason, advice=causes(context))
            continue
        # A hint from the assistant pins what the statement is supposed to mean (which columns,
        # which merchants, which shape the chart needs), so there is nothing left to judge.
        if hints:
            return outcome
        note(CHECKING)
        try:
            verdict = await check_result(
                model, request, context, validated, figures(rows.columns, rows.rows), model_settings=model_settings
            )
        except Exception:  # noqa: BLE001 - a check that fails leaves the result it was judging
            return outcome
        calls += 1
        if not verdict.revise:
            return outcome
        note(REWRITING.format(reason=verdict.why()))
        intent = " ".join(verdict.intent.split())
        revised = Revision(
            sql=validated, reason=verdict.why(), advice=f"Answer this instead: {intent}" if intent else ""
        )

    if outcome is not None:
        return outcome
    assert rejected is not None
    failure = f"The query was refused {len(refusals)} times, last reason: {rejected.error}"
    return QueryOutcome(
        request=request,
        sql=rejected.sql,
        summary=failure,
        error=failure,
        attempts=written,
        refusals=refusals,
        notes=notes,
    )
