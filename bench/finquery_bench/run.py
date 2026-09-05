"""One run: every datapoint through the real sub-agent path, scored against its gold rows.

The SQL set drives the path the app drives: `query_prompt` on the model under test, the guard,
`execute_read_only`, and one retry with the refusal in the prompt, exactly as `run_query` does
it. The retry is unrolled here rather than borrowed so the run can say whether the first
statement was the one that worked, which is the number that moves when a model gets better.

The chart set calls `run_chart` itself, because a chart is a plan, a query, generated code and a
self-check, and only the whole path is worth a score.
"""

import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from finquery.chart import run_chart
from finquery.query.guard import SqlFailed, SqlRejected, execute_read_only, validate_sql
from finquery.query.runner import ATTEMPTS
from finquery.query.subagent import QueryContext, Rejection, load_query_context, write_sql
from finquery_bench.datapoints import ChartPoint, Point, SqlPoint
from finquery_bench.models import Target
from finquery_bench.score import columns_map, figure_match, shape_match

PREFIX_HINT = "Earlier in this conversation the user asked: {questions} Answer the new question on its own."


@dataclass
class Result:
    """What one datapoint came to."""

    id: str
    set: str
    kind: str
    difficulty: int
    language: str
    question: str
    seconds: float
    figure_match: bool
    sql_valid: bool
    first_attempt: bool
    attempts: int
    sql: str | None = None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    refusals: list[str] = field(default_factory=list)
    # Charts only.
    shape: str | None = None
    shape_match: bool | None = None
    columns_map: bool | None = None
    language_ok: bool | None = None
    drawn: bool | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """A datapoint is right when its figures are right and, for a chart, its shape too."""
        return self.figure_match and self.shape_match is not False

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def _hints(point: SqlPoint) -> str | None:
    """The conversation prefix, as the chat agent would hand it to the sub-agent.

    The sub-agent never sees a transcript: the chat agent rewrites a follow-up into a request
    that stands on its own and adds what it knows as hints. A follow-up datapoint measures the
    sub-agent, so it gets the earlier questions and nothing else.
    """
    if not point.prefix:
        return None
    return PREFIX_HINT.format(questions=" ".join(f'"{question}"' for question in point.prefix))


async def run_sql_point(
    point: SqlPoint,
    *,
    target: Target,
    session_factory: sessionmaker[Session],
    profile_id: str,
    context: QueryContext,
) -> Result:
    """Write the statement, guard it, run it, and score its rows against the gold ones."""
    started = time.perf_counter()
    model = target.resolve("fast")
    rejected: Rejection | None = None
    refusals: list[str] = []
    sql: str | None = None
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    error: str | None = None
    attempts = 0
    for _ in range(ATTEMPTS):
        attempts += 1
        try:
            written = await write_sql(
                model, point.question, context, hints=_hints(point), rejected=rejected,
                model_settings=target.settings,
            )
        except Exception as exc:  # noqa: BLE001 - any model or transport failure is one message here
            error = f"no statement: {exc}"
            refusals.append(error)
            break
        try:
            validated = validate_sql(written)
            with session_factory() as session:
                result = execute_read_only(session, validated, profile_id)
        except (SqlRejected, SqlFailed) as exc:
            rejected = Rejection(sql=written, error=str(exc))
            refusals.append(str(exc))
            error = str(exc)
            continue
        except Exception as exc:  # noqa: BLE001
            # The guard itself can raise on text no parser accepts: sqlglot answers an
            # unterminated string literal with a TokenError, which `validate_sql` does not
            # turn into a refusal (qwen/qwen3.5-9b wrote one on 2026-09-05). Making that a
            # refusal is ticket 37's; a run counts it as an invalid statement and goes on.
            reason = f"the guard raised {type(exc).__name__}: {exc}"
            rejected = Rejection(sql=written, error=reason)
            refusals.append(reason)
            error = reason
            continue
        sql, columns, rows, error = validated, result.columns, result.rows, None
        break

    gold = point.gold.rows if point.gold else []
    return Result(
        id=point.id,
        set="sql",
        kind=point.kind,
        difficulty=point.difficulty,
        language=point.language,
        question=point.question,
        seconds=round(time.perf_counter() - started, 2),
        figure_match=sql is not None and figure_match(gold, rows, answer=point.answer),
        sql_valid=sql is not None,
        first_attempt=sql is not None and attempts == 1,
        attempts=attempts,
        sql=sql,
        columns=columns,
        rows=rows,
        error=error,
        refusals=refusals,
    )


async def run_chart_point(
    point: ChartPoint,
    *,
    target: Target,
    session_factory: sessionmaker[Session],
    profile_id: str,
) -> Result:
    """Plan, query, write and check one chart, and score the drawing and its rows."""
    started = time.perf_counter()
    try:
        outcome = await run_chart(
            resolve_model=target.resolve,
            model_settings=target.settings,
            session_factory=session_factory,
            profile_id=profile_id,
            request=point.prompt,
        )
    except Exception as exc:  # noqa: BLE001 - one datapoint that throws is one score, not a dead run
        return Result(
            id=point.id,
            set="chart",
            kind=point.shape,
            difficulty=point.difficulty,
            language=point.language,
            question=point.prompt,
            seconds=round(time.perf_counter() - started, 2),
            figure_match=False,
            sql_valid=False,
            first_attempt=False,
            attempts=1,
            error=f"the chart path raised {type(exc).__name__}: {exc}",
            shape_match=False,
            columns_map=False,
            language_ok=False,
            drawn=False,
        )
    gold = point.gold.rows if point.gold else []
    repaired = any(note.startswith(("Repair", "Gave up")) for note in outcome.notes)
    return Result(
        id=point.id,
        set="chart",
        kind=point.shape,
        difficulty=point.difficulty,
        language=point.language,
        question=point.prompt,
        seconds=round(time.perf_counter() - started, 2),
        figure_match=bool(outcome.rows) and figure_match(gold, outcome.rows),
        sql_valid=outcome.sql is not None,
        first_attempt=outcome.rendered and not repaired,
        attempts=len(outcome.notes) + 1,
        sql=outcome.sql,
        columns=outcome.columns,
        rows=outcome.rows,
        error=outcome.error,
        shape=outcome.shape or None,
        shape_match=shape_match(point.shape, point.also, outcome.shape),
        columns_map=columns_map(point.roles, outcome.columns, outcome.rows),
        language_ok=outcome.language == point.language,
        drawn=outcome.rendered,
        notes=list(outcome.notes),
    )


@dataclass
class Run:
    """A whole run: what was scored, on what, and how it went."""

    model: str
    set: str
    started_at: str
    seconds: float
    seed: int
    results: list[Result]

    def payload(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "set": self.set,
            "started_at": self.started_at,
            "seconds": round(self.seconds, 1),
            "seed": self.seed,
            "n": len(self.results),
            "summary": summarize(self.results),
            "results": [result.payload() for result in self.results],
        }


def _share(results: list[Result], field_name: str) -> float | None:
    values = [bool(getattr(result, field_name)) for result in results if getattr(result, field_name) is not None]
    return round(sum(values) / len(values), 3) if values else None


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(q * (len(ordered) - 1))))
    return round(ordered[index], 1)


def summarize(results: list[Result]) -> dict[str, Any]:
    """The numbers the markdown table is written from, overall and per group."""
    seconds = [result.seconds for result in results]
    summary: dict[str, Any] = {
        "n": len(results),
        "figure_match": _share(results, "figure_match"),
        "sql_valid": _share(results, "sql_valid"),
        "first_attempt": _share(results, "first_attempt"),
        "shape_match": _share(results, "shape_match"),
        "columns_map": _share(results, "columns_map"),
        "language_ok": _share(results, "language_ok"),
        "drawn": _share(results, "drawn"),
        "median_seconds": _quantile(seconds, 0.5),
        "p90_seconds": _quantile(seconds, 0.9),
        "total_seconds": round(sum(seconds), 1),
    }
    summary["by_kind"] = _grouped(results, lambda result: result.kind)
    summary["by_difficulty"] = _grouped(results, lambda result: str(result.difficulty))
    summary["by_language"] = _grouped(results, lambda result: result.language)
    return summary


def _grouped(results: list[Result], key) -> dict[str, dict[str, Any]]:  # noqa: ANN001
    groups: dict[str, list[Result]] = {}
    for result in results:
        groups.setdefault(key(result), []).append(result)
    measures = ("figure_match", "sql_valid", "first_attempt", "shape_match", "columns_map", "language_ok", "drawn")
    return {
        name: {
            "n": len(group),
            **{measure: _share(group, measure) for measure in measures},
            "median_seconds": _quantile([result.seconds for result in group], 0.5),
        }
        for name, group in sorted(groups.items())
    }


async def run_points(
    points: list[Point],
    *,
    target: Target,
    session_factory: sessionmaker[Session],
    profile_id: str,
    today: date,
    seed: int,
    set_name: str,
    on_result=None,  # noqa: ANN001 - a progress line, nothing more
) -> Run:
    """Run every datapoint in order, one after the other, so the latencies are honest."""
    with session_factory() as session:
        context = load_query_context(session, profile_id, today=today)
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    started = time.perf_counter()
    results: list[Result] = []
    for point in points:
        if isinstance(point, SqlPoint):
            result = await run_sql_point(
                point, target=target, session_factory=session_factory, profile_id=profile_id, context=context
            )
        else:
            result = await run_chart_point(
                point, target=target, session_factory=session_factory, profile_id=profile_id
            )
        results.append(result)
        if on_result is not None:
            on_result(result)
    return Run(
        model=target.name,
        set=set_name,
        started_at=started_at,
        seconds=time.perf_counter() - started,
        seed=seed,
        results=results,
    )
