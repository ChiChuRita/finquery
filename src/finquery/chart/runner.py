"""One chart request to a checked chart definition: plan, query, write, check, repair.

This is what the chat agent's `chart` tool calls. Nothing here renders: the browser runtime does
that (`docs/chart-runtime.md`). Every step that a user should be able to watch is narrated, and
the narration reaches the transcript as reasoning text.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session, sessionmaker

from finquery.chart.selfcheck import check_chart_code
from finquery.chart.shapes import SHAPES
from finquery.chart.subagent import ChartPlan, write_code, write_plan
from finquery.providers import ModelResolver, ProviderNotAvailable
from finquery.query import load_query_context, run_query

# One attempt plus two repair rounds. A third failure is reported instead of looping.
ATTEMPTS = 3

# What a shape falls back to when the rows cannot carry it.
PLAIN_BARS = "bar"

NO_DATA = "This profile has no transactions yet, so there is nothing to chart. Import a bank statement first."

Narrator = Callable[[str], None]


@dataclass(frozen=True)
class ChartOutcome:
    """What the chart tool returns: a checked definition and the query behind it, or why not."""

    request: str
    title: str = ""
    shape: str = ""
    plan: str = ""
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    code: str | None = None
    notes: list[str] = field(default_factory=list)
    summary: str = ""
    error: str | None = None

    def payload(self) -> dict[str, Any]:
        """The tool result: what the chat agent reads and what the chart card renders."""
        return {
            "request": self.request,
            "title": self.title,
            "shape": self.shape,
            "plan": self.plan,
            "sql": self.sql,
            "row_count": len(self.rows),
            "columns": self.columns,
            "rows": self.rows,
            "code": self.code,
            "notes": self.notes,
            "summary": self.summary,
            "error": self.error,
        }


def _failed(request: str, reason: str, **rest: Any) -> ChartOutcome:
    return ChartOutcome(request=request, summary=reason, error=reason, **rest)


def _grouping_columns(columns: list[str], rows: list[dict[str, Any]]) -> list[str]:
    """The columns that could carry a category: no NULL, more than one value, no figures."""
    grouping: list[str] = []
    for column in columns:
        values = [row.get(column) for row in rows]
        if any(value is None for value in values):
            continue
        if any(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values):
            continue
        if len({str(value) for value in values}) > 1:
            grouping.append(column)
    return grouping


def _honest_shape(plan: ChartPlan, columns: list[str], rows: list[dict[str, Any]]) -> ChartPlan:
    """Downgrade a shape the rows cannot carry, rather than asking for the impossible.

    A grouped or stacked chart needs two dimensions that really cross. The query can come back
    without them (asking for `category` while nothing is categorized returns NULLs, or grouping
    by one column only leaves one row per period), and no repair round can invent the missing
    dimension, so the chart becomes plain bars instead of an error.
    """
    if not SHAPES[plan.shape].series:
        return plan
    grouping = _grouping_columns(columns, rows)
    crossed = len(grouping) > 1 and len(rows) > len({str(row[grouping[0]]) for row in rows})
    return plan if crossed else plan.model_copy(update={"shape": PLAIN_BARS})


async def run_chart(
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    session_factory: sessionmaker[Session],
    profile_id: str,
    request: str,
    hints: str | None = None,
    narrate: Narrator | None = None,
) -> ChartOutcome:
    """Plan a chart, get its rows through the query sub-agent, write it and check it."""
    say: Narrator = narrate or (lambda _text: None)

    with session_factory() as session:
        context = load_query_context(session, profile_id)
    if context.transaction_count == 0:
        return _failed(request, NO_DATA)
    try:
        model = resolve_model("fast")
    except ProviderNotAvailable as exc:
        return _failed(request, f"The chart sub-agent is unavailable: {exc}")

    try:
        plan = await write_plan(model, request, context, hints=hints, model_settings=model_settings)
    except Exception as exc:  # noqa: BLE001 - any model or transport failure is one message here
        return _failed(request, f"The chart sub-agent did not return a plan: {exc}")
    say(plan.as_text())

    # What the query needs to know on top of whatever the assistant said.
    shaped = f"Return exactly these columns, in this order: {', '.join(plan.columns)}."
    if plan.shape == "sankey":
        # A flow layout rejects a negative or missing value, and signs must not be mixed:
        # spending and income both travel as positive amounts along the flow.
        shaped += (
            f" Every row is one flow: a source name, a target name and a positive euro amount. "
            f"Report spending as `ROUND(-SUM(amount), 2)`, never mix a negative and a positive "
            f"figure in {plan.columns[-1]}, and leave no row without a source or a target."
        )
    elif len(plan.columns) > 2:
        # A grouped chart needs a real second dimension, so the statement has to group by both
        # columns. Selecting a column that is NULL for every booking (`category` before anything
        # is categorized) or grouping by only one of them silently produces a single series.
        shaped += (
            f" `GROUP BY {plan.columns[0]}, {plan.columns[1]}`, so there is one row per "
            f"combination and no row where {plan.columns[1]} is NULL. When the taxonomy is not "
            f"filled, build {plan.columns[1]} as a CASE expression over the merchants, repeat it "
            f"in the GROUP BY, and add a WHERE that keeps only the bookings it names."
        )
    outcome = await run_query(
        resolve_model=resolve_model,
        model_settings=model_settings,
        session_factory=session_factory,
        profile_id=profile_id,
        request=plan.question,
        hints=f"{hints.strip()} {shaped}" if hints else shaped,
    )
    if outcome.error is not None:
        say(f"No chart: {outcome.error}")
        return _failed(request, outcome.error, title=plan.title, shape=plan.shape, plan=plan.as_text(), sql=outcome.sql)
    if not outcome.rows:
        reason = "The query behind the chart returned no rows, so there is nothing to draw."
        say(reason)
        return _failed(
            request,
            reason,
            title=plan.title,
            shape=plan.shape,
            plan=plan.as_text(),
            sql=outcome.sql,
            columns=outcome.columns,
        )
    say(f"Data: {len(outcome.rows)} rows over {', '.join(outcome.columns)}.")

    honest = _honest_shape(plan, outcome.columns, outcome.rows)
    if honest.shape != plan.shape:
        say(f"The rows carry only one series, so the shape becomes {honest.shape}.")
        plan = honest

    notes: list[str] = []
    code: str | None = None
    findings = ""
    for attempt in range(ATTEMPTS):
        try:
            code = await write_code(
                model,
                plan,
                outcome.columns,
                outcome.rows,
                previous_code=code if attempt else None,
                findings=findings if attempt else None,
                model_settings=model_settings,
            )
        except Exception as exc:  # noqa: BLE001
            return _failed(
                request,
                f"The chart sub-agent did not return code: {exc}",
                title=plan.title,
                shape=plan.shape,
                plan=plan.as_text(),
                sql=outcome.sql,
                columns=outcome.columns,
                rows=outcome.rows,
                notes=notes,
            )
        result = await check_chart_code(code, outcome.rows, plan.shape)
        last = attempt == ATTEMPTS - 1
        if result.ok or (last and not result.fatal):
            if result.ok:
                rounds = "one repair" if attempt == 1 else f"{attempt} repairs"
                passed = "Self-check passed." if attempt == 0 else f"Self-check passed after {rounds}."
            else:
                # Only polish is left after the last round. A chart with a legend nobody needs
                # still answers the question, and no chart at all does not.
                passed = f"Shown with one rule unmet: {'; '.join(result.findings)}"
                notes.append(passed)
            say(passed)
            return ChartOutcome(
                request=request,
                title=plan.title,
                shape=plan.shape,
                plan=plan.as_text(),
                sql=outcome.sql,
                columns=outcome.columns,
                rows=outcome.rows,
                code=code,
                notes=notes,
                summary=(
                    f"A {plan.shape} chart titled \"{plan.title}\" is now shown to the user, drawn "
                    f"from {len(outcome.rows)} rows of the executed query."
                ),
            )
        findings = result.instructions()
        note = f"Repair {attempt + 1} of {ATTEMPTS - 1}: {'; '.join(result.findings)}"
        if attempt == ATTEMPTS - 1:
            note = f"Gave up after {ATTEMPTS} attempts: {'; '.join(result.findings)}"
        notes.append(note)
        say(note)

    reason = (
        f"The chart could not be drawn: {ATTEMPTS} attempts failed the self-check, last reason: "
        f"{findings.strip()}"
    )
    return _failed(
        request,
        reason,
        title=plan.title,
        shape=plan.shape,
        plan=plan.as_text(),
        sql=outcome.sql,
        columns=outcome.columns,
        rows=outcome.rows,
        notes=notes,
    )
