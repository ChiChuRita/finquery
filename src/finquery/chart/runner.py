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

from finquery.chart.fold import fold_rows
from finquery.chart.selfcheck import check_chart_code, data_findings
from finquery.chart.shapes import MAX_SERIES, SHAPES
from finquery.chart.subagent import ChartPlan, write_code, write_plan
from finquery.providers import ModelResolver, ProviderNotAvailable
from finquery.query import QueryOutcome, load_query_context, run_query
from finquery.query.runner import figures, is_euro_column

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
    language: str = "de"
    """The language the plan wrote the title in. The frame writes its month labels in it too."""
    plan: str = ""
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    code: str | None = None
    notes: list[str] = field(default_factory=list)
    summary: str = ""
    error: str | None = None

    @property
    def rendered(self) -> bool:
        """Whether a chart is actually on screen."""
        return self.code is not None and self.error is None

    def payload(self) -> dict[str, Any]:
        """The tool result: what the chat agent reads and what the chart card renders."""
        return {
            "request": self.request,
            "title": self.title,
            "shape": self.shape,
            "language": self.language,
            "plan": self.plan,
            "sql": self.sql,
            "row_count": len(self.rows),
            "columns": self.columns,
            "rows": self.rows,
            "figures": figures(self.columns, self.rows),
            "code": self.code,
            "notes": self.notes,
            "summary": self.summary,
            "error": self.error,
            # The one field the chat agent has to read before it writes a sentence about the
            # picture: false means there is nothing on screen, so the answer gives the figures
            # instead of describing a drawing that is not there.
            "rendered": self.rendered,
        }


# What the chat agent is told when there is no picture. `rendered: false` is the field it reads,
# and this sentence is the last thing it reads, because the review of 2026-09-04 twice caught an
# answer describing in full a chart that had never been drawn.
NO_PICTURE = (
    "No chart is on screen. Do not describe a picture, a shape, an axis or a colour: say in one "
    "line that the chart could not be drawn and why, then answer with the figures from `rows`. "
    "Write your answer as text now."
)


def _summary(plan: ChartPlan, columns: list[str], rows: list[dict[str, Any]]) -> str:
    """The last thing the model reads before it writes the sentence under a drawn chart.

    It names this chart and carries this chart's own figures, because on 2026-09-05 the prose
    under a grouped chart was the previous chart's answer repeated word for word. The figures
    are here so there is nothing to reach back for: the numbers the sentence needs are in the
    tool result the model just got, already written the German way.
    """
    return "\n".join(
        [
            f'The chart now on screen is a {plan.shape} titled "{plan.title}", drawn from these '
            f"{len(rows)} rows of the query it just ran:",
            *figures(columns, rows),
            "Write your answer as text now: one or two sentences about this chart, quoting at "
            "most the two figures that matter, and taking every figure from the rows above. "
            "Describe only this chart, never one from an earlier turn.",
        ]
    )


def _failed(request: str, reason: str, **rest: Any) -> ChartOutcome:
    return ChartOutcome(request=request, summary=f"{reason} {NO_PICTURE}", error=reason, **rest)


def _euro_last(plan: ChartPlan) -> ChartPlan:
    """The euro column of a grouped or stacked chart is the last of its three, whatever the plan said.

    Everything downstream reads those columns as position, group and figure: the query hint,
    the pair rule of the check and the fold. The plan pass asked for `month, total_eur, topic`
    on 2026-09-05, so all three read the euro column as the group and the chart was refused for
    carrying "the pair 2025-09 / 36.5 twice". The order is ours to fix, so it is fixed here.
    """
    if not SHAPES[plan.shape].crossed or len(plan.columns) != 3:
        return plan
    euros = [name for name in plan.columns if is_euro_column(name)]
    if len(euros) != 1 or plan.columns[-1] == euros[0]:
        return plan
    return plan.model_copy(update={"columns": [name for name in plan.columns if name != euros[0]] + euros})


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


# A line or an area between two points draws a trend through everything the query did not
# return: January and July joined by a stroke says something about the five months between them.
MIN_TREND_POINTS = 3


def _honest_shape(
    plan: ChartPlan, columns: list[str], rows: list[dict[str, Any]]
) -> tuple[ChartPlan, str | None]:
    """Downgrade a shape the rows cannot carry, rather than asking for the impossible.

    Two cases, both decided by the rows and neither repairable by writing the code again:

    - a grouped or stacked chart needs two dimensions that really cross, and the query can come
      back without them (asking for `category` while nothing is categorized returns NULLs, or
      grouping by one column only leaves one row per period);
    - a trend needs enough points to be a trend, and two periods being compared are two bars.

    Either way the chart becomes plain bars, and the reason is narrated.
    """
    if plan.shape in {"line", "area"} and len(rows) < MIN_TREND_POINTS:
        return (
            plan.model_copy(update={"shape": PLAIN_BARS}),
            f"{len(rows)} points are a comparison and not a trend, so the shape becomes "
            f"{PLAIN_BARS}.",
        )
    if not SHAPES[plan.shape].crossed:
        return plan, None
    grouping = _grouping_columns(columns, rows)
    crossed = len(grouping) > 1 and len(rows) > len({str(row[grouping[0]]) for row in rows})
    if crossed:
        return plan, None
    return (
        plan.model_copy(update={"shape": PLAIN_BARS}),
        f"The rows carry only one series, so the shape becomes {PLAIN_BARS}.",
    )


# What a query calls the bucket everything else was folded into. A doughnut whose rest slice
# holds most of the money carries no information, and the review of 2026-09-04 saw one at 90
# percent, so the share goes into the caption where the user reads it. The folding itself is
# `finquery.chart.fold`, which the dashboard runs again on every load.
REST_LABELS = ("rest", "other", "others", "sonstige", "sonstiges", "andere", "uebrige", "übrige")
REST_MAJORITY = 0.5


def _rest_share(shape: str, columns: list[str], rows: list[dict[str, Any]]) -> str | None:
    """The share of a doughnut's rest slice, as a percentage, when it holds the majority."""
    if shape != "doughnut" or len(columns) < 2 or len(rows) < 2:
        return None
    label_column, value_column = columns[0], columns[1]
    values = [row.get(value_column) for row in rows]
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in values):
        return None
    total = sum(float(value) for value in values)  # type: ignore[arg-type]
    if total <= 0:
        return None
    for row in rows:
        if str(row.get(label_column) or "").strip().casefold() not in REST_LABELS:
            continue
        share = float(row[value_column]) / total  # type: ignore[arg-type]
        if share > REST_MAJORITY:
            return f"{round(share * 100)} %"
    return None


async def run_chart(
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    session_factory: sessionmaker[Session],
    profile_id: str,
    request: str,
    hints: str | None = None,
    narrate: Narrator | None = None,
    check: bool = True,
) -> ChartOutcome:
    """Plan a chart, get its rows through the query sub-agent, write it and check it.

    `check` is the query's own check pass (ticket 40), passed through so the benchmark can
    measure a chart run with it and without it. The plan already pins what the statement has to
    return, so what it changes here is the rewrite a degenerate result asks for.
    """
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
    plan = _euro_last(plan)
    say(plan.as_text())

    # What the query needs to know on top of whatever the assistant said.
    shaped = f"Return exactly these columns, in this order: {', '.join(plan.columns)}."
    if plan.shape == "sankey":
        # A flow layout rejects a negative or missing value, and signs must not be mixed:
        # spending and income both travel as positive amounts along the flow.
        shaped += (
            f" Every row is one flow: a source name, a target name and a positive euro amount. "
            f"Report spending as `ROUND(-SUM(amount), 2)`, never mix a negative and a positive "
            f"figure in {plan.columns[-1]}, and leave no row without a source or a target. No "
            f"row may carry the same name in {plan.columns[0]} and {plan.columns[1]}: a total "
            f"row is a flow from a name into itself, which a sankey refuses."
        )
    elif len(plan.columns) > 2:
        # A grouped chart needs a real second dimension, so the statement has to group by both
        # columns. Selecting a column that is NULL for every booking (`category` before anything
        # is categorized) or grouping by only one of them silently produces a single series.
        position, group = plan.columns[0], plan.columns[1]
        shaped += (
            f" `GROUP BY {position}, {group}`, so there is one row per "
            f"combination and never two rows with the same pair: a stacked bar needs one value "
            f"per position and series. Build {group} from the `category` column with "
            f"`coalesce(category, 'Needs review') AS {group}` so an uncategorized "
            f"booking is an honest bucket, and never from a CASE over the booking text."
        )
        # A chart has six colours, and folding the tail into one group is arithmetic this app
        # does itself (`chart.fold.fold_rows`). Asking the statement for it is what cost the
        # stacked bars three rounds on 2026-09-05: the CASE relabelled the small categories
        # 'Other' while the statement still grouped by the month alone, so every month came
        # back with several 'Other' rows and the stack could not be drawn at all.
        shaped += (
            f" Return every group under its own name: never rename one to 'Other' or 'Sonstige', "
            f"never fold the small ones together and never put a LIMIT on the groups. This app "
            f"keeps the largest {MAX_SERIES - 1} and sums the rest itself, after the query, "
            f"because a chart has {MAX_SERIES} colours. When the question names the groups it "
            f"wants, select only those."
        )
    outcome = await run_query(
        resolve_model=resolve_model,
        model_settings=model_settings,
        session_factory=session_factory,
        profile_id=profile_id,
        request=plan.question,
        hints=f"{hints.strip()} {shaped}" if hints else shaped,
        check=check,
        narrate=say,
        context=context,
    )
    if outcome.error is not None:
        say(f"No chart: {outcome.error}")
        return _failed(
            request,
            outcome.error,
            title=plan.title,
            shape=plan.shape,
            language=plan.language,
            plan=plan.as_text(),
            sql=outcome.sql,
        )
    if not outcome.rows:
        reason = "The query behind the chart returned no rows, so there is nothing to draw."
        say(reason)
        return _failed(
            request,
            reason,
            title=plan.title,
            shape=plan.shape,
            language=plan.language,
            plan=plan.as_text(),
            sql=outcome.sql,
            columns=outcome.columns,
        )
    say(f"Data: {len(outcome.rows)} rows over {', '.join(outcome.columns)}.")

    # The fold: arithmetic and not a judgement, so it is not left to the query or to a repair
    # round. It runs before the rows are judged, because the rows it produces are the rows the
    # chart draws and the card shows. The dashboard runs the same function over the same
    # statement's rows on every load, which is how a pinned chart keeps drawing this fold.
    folded = fold_rows(plan.shape, outcome.columns, outcome.rows, language=plan.language)
    if folded.note is not None:
        say(folded.note)
        outcome = QueryOutcome(
            request=outcome.request,
            sql=outcome.sql,
            columns=outcome.columns,
            rows=folded.rows,
            summary=outcome.summary,
        )

    # What the rows make impossible, judged before a single line of code is written: no repair
    # round can fold two rows for the same month and category into one, or straighten a
    # circular flow, so the honest answer is the reason and the figures.
    if impossible := data_findings(plan.shape, outcome.columns, outcome.rows):
        reason = f"The chart could not be drawn from these rows: {' '.join(impossible)}"
        say(reason)
        return _failed(
            request,
            reason,
            title=plan.title,
            shape=plan.shape,
            language=plan.language,
            plan=plan.as_text(),
            sql=outcome.sql,
            columns=outcome.columns,
            rows=outcome.rows,
        )

    plan, downgrade = _honest_shape(plan, outcome.columns, outcome.rows)
    if downgrade is not None:
        say(downgrade)

    if (share := _rest_share(plan.shape, outcome.columns, outcome.rows)) is not None:
        plan = plan.model_copy(update={"title": f"{plan.title} ({share} in the rest slice)"})
        say(f"One slice holds {share} of the total, so the title says so.")

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
                language=plan.language,
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
                language=plan.language,
                plan=plan.as_text(),
                sql=outcome.sql,
                columns=outcome.columns,
                rows=outcome.rows,
                code=code,
                notes=notes,
                summary=_summary(plan, outcome.columns, outcome.rows),
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
