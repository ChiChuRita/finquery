"""The execution gate: a candidate is kept by running it, never by an opinion.

A query candidate is kept when the guard admits its statement, SQLite runs it, the writer's
second statement runs too, the two agree on every figure to the cent, and the result is not one
of the degenerate shapes `finquery.query.check` refuses in production. A chart candidate is kept
when its statement returns exactly the planned columns, the rows survive the fold, and the real
self-check passes on the real rows on the first attempt, which is the same bar
`chart.runner.run_chart` holds a model to.

Everything a drop knows is written out beside the kept rows, because a drop is worth as much as
a keep: a refused statement and its corrected twin are a repair sample, and a degenerate result
is a `revise` verdict for the check pass (`assemble.py`).

    uv run python -m training.data.gate --task query --out out/query batch.jsonl
    uv run python -m training.data.gate --task chart --out out/chart batch.jsonl

Two private helpers of the chart runner are imported on purpose (`_honest_shape`): a sample has
to be the chart production would really draw, and that function is what decides it.
"""

import argparse
import asyncio
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from finquery.chart.fold import fold_rows
from finquery.chart.runner import _honest_shape
from finquery.chart.selfcheck import check_chart_code, data_findings
from finquery.chart.subagent import ChartPlan
from finquery.query.check import degenerate_reason
from finquery.query.guard import SqlFailed, SqlRejected, execute_read_only, validate_sql
from finquery.query.subagent import QueryContext, is_euro_column, subcategory_parents
from finquery_bench.score import figure_match, figures

from training.data.households import context_of, load_households
from training.data.schema import ChartCandidate, QueryCandidate, read_batch, write_jsonl

MIN_REASONING = 30
"""How short a reasoning line may be before the gate refuses to spend a judge on it.

The prose is the judge's job (ticket 57: a rationale at partial coverage loses to no rationale
at all), but "spending" is not four lines about the period, the filters, the sign and the
grouping, and no judge should have to say so."""

GUARD_REFUSED = "guard-refused"
SQL_FAILED = "sql-failed"
CHECK_REFUSED = "check-guard-refused"
CHECK_FAILED = "check-sql-failed"
SAME_STATEMENT = "check-is-the-same-statement"
DISAGREE = "statements-disagree"
DEGENERATE = "degenerate-result"
FIGURE_MISSING = "expected-figure-missing"
THIN_REASONING = "reasoning-too-thin"
COLUMNS_UNPLANNED = "columns-not-as-planned"
EUROS_NOT_LAST = "euro-column-not-last"
NO_ROWS = "no-rows"
ROWS_IMPOSSIBLE = "rows-cannot-carry-the-shape"
SHAPE_DOWNGRADED = "shape-would-be-downgraded"
SELFCHECK_FAILED = "self-check-failed"
UNKNOWN_HOUSEHOLD = "unknown-household"

WHY = {
    GUARD_REFUSED: "the guard refused the statement",
    SQL_FAILED: "SQLite could not run the statement",
    CHECK_REFUSED: "the guard refused the check statement",
    CHECK_FAILED: "SQLite could not run the check statement",
    SAME_STATEMENT: "the check statement is the statement again, so it is no check",
    DISAGREE: "the two statements do not agree on the figures",
    DEGENERATE: "the result is one production would send back for a rewrite",
    FIGURE_MISSING: "the figure the writer expected is not in the rows",
    THIN_REASONING: "the reasoning line says too little to be judged",
    COLUMNS_UNPLANNED: "the statement does not return the planned columns",
    EUROS_NOT_LAST: "the euro column is not the last of the three",
    NO_ROWS: "the statement returned no rows, so there is nothing to draw",
    ROWS_IMPOSSIBLE: "the rows cannot carry this shape",
    SHAPE_DOWNGRADED: "production would downgrade this shape on these rows",
    SELFCHECK_FAILED: "the self-check found something on the first attempt",
    UNKNOWN_HOUSEHOLD: "no household carries that slug",
}


@dataclass
class Kept:
    """A candidate that ran, with everything the later steps need so nothing runs twice."""

    candidate: QueryCandidate | ChartCandidate
    columns: list[str]
    rows: list[dict[str, Any]]
    validated_sql: str
    check_columns: list[str] = field(default_factory=list)
    check_rows: list[dict[str, Any]] = field(default_factory=list)
    fold_note: str | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "task": self.candidate.task,
            "candidate": self.candidate.model_dump(),
            "validated_sql": self.validated_sql,
            "columns": self.columns,
            "rows": self.rows,
            "check_columns": self.check_columns,
            "check_rows": self.check_rows,
            "fold_note": self.fold_note,
        }


@dataclass
class Dropped:
    """A candidate that did not run, and exactly why. Half of these become repair samples."""

    candidate: QueryCandidate | ChartCandidate
    code: str
    detail: str = ""
    findings: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    validated_sql: str = ""
    verdict: dict[str, Any] | None = None
    """What a judge said about this drop, when one has seen it (`judge_pack.py`). A `revise`
    verdict is what turns a drop that ran into a check-pass sample and a rewrite sample."""

    def payload(self) -> dict[str, Any]:
        payload = {
            "task": self.candidate.task,
            "candidate": self.candidate.model_dump(),
            "reason": self.code,
            "why": WHY[self.code],
            "detail": self.detail,
            "findings": self.findings,
            "columns": self.columns,
            "rows": self.rows,
            "validated_sql": self.validated_sql,
        }
        if self.verdict is not None:
            payload["verdict"] = self.verdict
        return payload


@dataclass
class Result:
    """What one run of the gate came to."""

    kept: list[Kept] = field(default_factory=list)
    dropped: list[Dropped] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.kept) + len(self.dropped)


def _run(session_factory, profile_id: str, context: QueryContext, sql: str):  # noqa: ANN001, ANN202
    """One statement through the production guard and the profile-scoped view."""
    validated = validate_sql(sql, taxonomy=subcategory_parents(context))
    with session_factory() as session:
        return validated, execute_read_only(session, validated, profile_id)


def _normalized(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.strip().removesuffix(";")).casefold()


def gate_query(candidate: QueryCandidate, session_factory, profile_id: str, context: QueryContext) -> Kept | Dropped:  # noqa: ANN001
    """Run one question's two statements and keep it only when they agree on a real result."""
    if len(candidate.reasoning.strip()) < MIN_REASONING:
        return Dropped(candidate, THIN_REASONING, detail=candidate.reasoning.strip())
    if _normalized(candidate.sql) == _normalized(candidate.expected.check_sql):
        return Dropped(candidate, SAME_STATEMENT)
    try:
        validated, rows = _run(session_factory, profile_id, context, candidate.sql)
    except SqlRejected as exc:
        return Dropped(candidate, GUARD_REFUSED, detail=str(exc))
    except SqlFailed as exc:
        return Dropped(candidate, SQL_FAILED, detail=str(exc))
    try:
        _checked, check_rows = _run(session_factory, profile_id, context, candidate.expected.check_sql)
    except SqlRejected as exc:
        return Dropped(candidate, CHECK_REFUSED, detail=str(exc), validated_sql=validated)
    except SqlFailed as exc:
        return Dropped(candidate, CHECK_FAILED, detail=str(exc), validated_sql=validated)

    reason = degenerate_reason(candidate.question, context, rows.columns, rows.rows)
    if reason is not None:
        return Dropped(
            candidate,
            DEGENERATE,
            detail=reason,
            columns=rows.columns,
            rows=rows.rows,
            validated_sql=validated,
        )
    # The benchmark's own rule, in the benchmark's own words: every figure of the second
    # statement comes back in the first, to the cent, and the first is not a dump of the table.
    if not figure_match(check_rows.rows, rows.rows):
        return Dropped(
            candidate,
            DISAGREE,
            detail=(
                f"the statement returns {figures(rows.rows)} and the check statement "
                f"{figures(check_rows.rows)}"
            ),
            columns=rows.columns,
            rows=rows.rows,
            validated_sql=validated,
        )
    if candidate.expected.figure is not None:
        wanted = f"{round(float(candidate.expected.figure), 2):.2f}"
        if wanted not in figures(rows.rows):
            return Dropped(
                candidate,
                FIGURE_MISSING,
                detail=f"expected {wanted}, the rows carry {figures(rows.rows)}",
                columns=rows.columns,
                rows=rows.rows,
                validated_sql=validated,
            )
    return Kept(
        candidate=candidate,
        columns=rows.columns,
        rows=rows.rows,
        validated_sql=validated,
        check_columns=check_rows.columns,
        check_rows=check_rows.rows,
    )


def plan_of(candidate: ChartCandidate) -> ChartPlan:
    """The candidate's plan as the production model would have answered it."""
    return ChartPlan(
        reasoning=candidate.reasoning_plan,
        shape=candidate.shape,
        language=candidate.language,
        title=candidate.plan.title,
        question=candidate.plan.question,
        columns=list(candidate.plan.columns),
    )


def gate_chart(candidate: ChartCandidate, session_factory, profile_id: str, context: QueryContext) -> Kept | Dropped:  # noqa: ANN001
    """Run the statement, fold the rows, and hold the code to the production self-check."""
    if min(len(candidate.reasoning_plan.strip()), len(candidate.reasoning_code.strip())) < MIN_REASONING:
        return Dropped(candidate, THIN_REASONING)
    columns = list(candidate.plan.columns)
    euros = [name for name in columns if is_euro_column(name)]
    if len(columns) > 2 and (len(euros) != 1 or columns[-1] != euros[0]):
        return Dropped(candidate, EUROS_NOT_LAST, detail=", ".join(columns))
    try:
        validated, rows = _run(session_factory, profile_id, context, candidate.sql)
    except SqlRejected as exc:
        return Dropped(candidate, GUARD_REFUSED, detail=str(exc))
    except SqlFailed as exc:
        return Dropped(candidate, SQL_FAILED, detail=str(exc))
    if not rows.rows:
        return Dropped(candidate, NO_ROWS, validated_sql=validated)
    if rows.columns != columns:
        return Dropped(
            candidate,
            COLUMNS_UNPLANNED,
            detail=f"planned {', '.join(columns)}, returned {', '.join(rows.columns)}",
            validated_sql=validated,
        )

    folded = fold_rows(candidate.shape, rows.columns, rows.rows, language=candidate.language)
    impossible = data_findings(candidate.shape, rows.columns, folded.rows)
    if impossible:
        return Dropped(
            candidate,
            ROWS_IMPOSSIBLE,
            findings=list(impossible),
            columns=rows.columns,
            rows=folded.rows,
            validated_sql=validated,
        )
    plan, downgrade = _honest_shape(plan_of(candidate), rows.columns, folded.rows)
    if downgrade is not None:
        return Dropped(
            candidate,
            SHAPE_DOWNGRADED,
            detail=downgrade,
            columns=rows.columns,
            rows=folded.rows,
            validated_sql=validated,
        )
    result = asyncio.run(check_chart_code(candidate.code, folded.rows, plan.shape))
    if not result.ok:
        return Dropped(
            candidate,
            SELFCHECK_FAILED,
            findings=list(result.findings),
            columns=rows.columns,
            rows=folded.rows,
            validated_sql=validated,
        )
    return Kept(
        candidate=candidate,
        columns=rows.columns,
        rows=folded.rows,
        validated_sql=validated,
        fold_note=folded.note,
    )


def run_gate(candidates: list[Any]) -> Result:
    """Every candidate against its own household, one database open per household."""
    result = Result()
    known = load_households()
    opened: dict[str, tuple[Any, str, QueryContext]] = {}
    try:
        for candidate in candidates:
            slug = candidate.household
            if slug not in known:
                result.dropped.append(Dropped(candidate, UNKNOWN_HOUSEHOLD, detail=slug))
                continue
            if slug not in opened:
                session_factory, profile_id, context, _entry = context_of(slug)
                opened[slug] = (session_factory, profile_id, context)
            session_factory, profile_id, context = opened[slug]
            gate = gate_query if isinstance(candidate, QueryCandidate) else gate_chart
            outcome = gate(candidate, session_factory, profile_id, context)  # type: ignore[operator]
            (result.kept if isinstance(outcome, Kept) else result.dropped).append(outcome)  # type: ignore[arg-type]
    finally:
        for session_factory, _profile_id, _context in opened.values():
            session_factory.kw["bind"].dispose()
    return result


def _table(title: str, counts: Counter, total: int) -> list[str]:
    if not counts:
        return []
    lines = [f"| {title} | rows | share |", "| --- | ---: | ---: |"]
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0]))):
        lines.append(f"| {name} | {count} | {round(100 * count / total)} % |")
    return [*lines, ""]


def report(result: Result) -> str:
    """The one page that says what a batch came to, by household, kind, language and reason."""
    total = result.total or 1
    kept = [item.candidate for item in result.kept]
    lines = [
        "# Gate report",
        "",
        f"{len(result.kept)} of {result.total} candidates kept "
        f"({round(100 * len(result.kept) / total)} %), {len(result.dropped)} dropped.",
        "",
    ]
    if kept:
        lines += _table("household", Counter(item.household for item in kept), len(kept))
        lines += _table("kind", Counter(getattr(item, "kind", "") for item in kept), len(kept))
        lines += _table("language", Counter(item.language for item in kept), len(kept))
        lines += _table("difficulty", Counter(str(item.difficulty) for item in kept), len(kept))
    if result.dropped:
        lines += ["## Why the rest was dropped", ""]
        lines += _table("reason", Counter(item.code for item in result.dropped), len(result.dropped))
        lines += ["One line per drop:", ""]
        for item in result.dropped:
            detail = item.detail or "; ".join(item.findings)
            lines.append(f"- `{item.candidate.id}` {WHY[item.code]}: {detail}"[:400])
        lines.append("")
    return "\n".join(lines)


def write_out(result: Result, out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = {
        "kept": write_jsonl(out / "kept.jsonl", [item.payload() for item in result.kept]),
        "dropped": write_jsonl(out / "dropped.jsonl", [item.payload() for item in result.dropped]),
    }
    (out / "report.md").write_text(report(result), encoding="utf-8")
    written["report"] = out / "report.md"
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run candidates against their household and keep what survives.")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--task", choices=("query", "chart"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    candidates: list[Any] = []
    for path in args.files:
        candidates.extend(read_batch(path, args.task))
    result = run_gate(candidates)
    written = write_out(result, args.out)
    print(f"{len(result.kept)} kept, {len(result.dropped)} dropped, written to {args.out}")
    for item in result.dropped:
        print(f"  dropped {item.candidate.id}: {WHY[item.code]}", file=sys.stderr)
    return 0 if result.kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
