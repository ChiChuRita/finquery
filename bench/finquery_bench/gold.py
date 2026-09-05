"""Gold rows: the reference SQL of every datapoint, run through the real guard.

Gold is code, not a model. A datapoint's expected figure is whatever its reference statement
returns against a fresh database holding the synthetic year, so it is exact, it is reproducible,
and a statement that stops answering its question fails the build instead of quietly becoming
the new truth.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from finquery.query.guard import SqlFailed, SqlRejected, execute_read_only, validate_sql
from finquery_bench.datapoints import CHART_SET, NO_ANSWER, SQL_SET, read, write
from finquery_bench.dataset import fresh_database
from finquery_bench.score import figures


class GoldFailed(RuntimeError):
    """A reference statement was refused, failed, or answered nothing. The build stops."""


@dataclass(frozen=True)
class Built:
    """One set's worth of gold: how many datapoints, and how many rows they came to."""

    path: Path
    datapoints: int
    rows: int


def run_reference(
    session_factory: sessionmaker[Session], profile_id: str, ident: str, sql: str, *, answer: str = ""
) -> dict[str, Any]:
    """Run one reference statement through the guard. Raise with the id when it says nothing."""
    try:
        validated = validate_sql(sql)
    except SqlRejected as exc:
        raise GoldFailed(f"{ident}: the guard refused the reference SQL: {exc}") from exc
    try:
        with session_factory() as session:
            rows = execute_read_only(session, validated, profile_id)
    except SqlFailed as exc:
        raise GoldFailed(f"{ident}: SQLite could not run the reference SQL: {exc}") from exc
    # No rows and rows that carry no figure are the same failure: a datapoint whose gold holds
    # no number is scored against nothing, so every answer passes it. The judging of 2026-09-05
    # found one, a generated statement that filtered on a subcategory no booking carries and
    # came back as a single NULL.
    if answer != NO_ANSWER and not figures(rows.rows):
        empty = "returned no rows" if not rows.rows else "returned rows with no figure in them"
        raise GoldFailed(
            f"{ident}: the reference SQL {empty}, so this datapoint has no expected "
            f"figure. Fix the statement, or mark the datapoint answer: \"{NO_ANSWER}\" when the "
            f"honest answer really is that the data holds nothing."
        )
    return {"columns": rows.columns, "rows": rows.rows}


def build(paths: tuple[Path, ...] = (SQL_SET, CHART_SET)) -> list[Built]:
    """Recompute the gold rows of every set and write them back into the files."""
    built: list[Built] = []
    with fresh_database() as (session_factory, profile_id):
        for path in paths:
            payload = read(path)
            items = payload["datapoints"] if "datapoints" in payload else payload["prompts"]
            rows = 0
            for item in items:
                gold = run_reference(
                    session_factory,
                    profile_id,
                    item["id"],
                    item["sql"],
                    answer=item.get("answer", ""),
                )
                item["gold"] = gold
                rows += len(gold["rows"])
            write(path, payload)
            built.append(Built(path=path, datapoints=len(items), rows=rows))
    return built
