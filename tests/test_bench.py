"""The benchmarks: gold that rebuilds identically, a runner that scores, a stable sample.

No model and no network here either: the runner is driven by a scripted model that answers one
statement per question, which is how "a known right and a known wrong statement" become a 1 and
a 0 without OpenRouter.
"""

import json
import shutil
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.settings import ModelSettings

from finquery_bench.datapoints import CHART_SET, SQL_SET, load_sql, pick, review_sample
from finquery_bench.dataset import fresh_database
from finquery_bench.gold import GoldFailed, build, run_reference
from finquery_bench.models import Target
from finquery_bench.report import compare
from finquery_bench.run import run_points, summarize
from finquery_bench.score import columns_map, figure_match, shape_match


@pytest.fixture(scope="module")
def database():
    """The benchmark database, built once for this module."""
    with fresh_database() as (session_factory, profile_id):
        yield session_factory, profile_id


def _copy_sets(tmp_path: Path) -> tuple[Path, Path]:
    sql = tmp_path / SQL_SET.name
    chart = tmp_path / CHART_SET.name
    shutil.copy(SQL_SET, sql)
    shutil.copy(CHART_SET, chart)
    return sql, chart


def test_gold_rows_are_reproducible(tmp_path: Path) -> None:
    """Building twice writes the same file, and the same one that is committed."""
    committed = (SQL_SET.read_text(), CHART_SET.read_text())
    sql, chart = _copy_sets(tmp_path)
    build((sql, chart))
    once = (sql.read_text(), chart.read_text())
    build((sql, chart))
    assert once == (sql.read_text(), chart.read_text())
    assert once == committed, "bench/*.json is not the file build_gold.py produces; run it and commit"


def test_every_datapoint_has_gold_figures() -> None:
    points = load_sql()
    assert len(points) >= 60
    for point in points:
        assert point.gold is not None, point.id
        assert point.gold.rows or point.answer == "none", point.id


def test_a_reference_that_answers_nothing_fails_the_build(database) -> None:
    session_factory, profile_id = database
    with pytest.raises(GoldFailed, match="no rows"):
        run_reference(
            session_factory,
            profile_id,
            "made-up",
            "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE booked_on = '1999-01-01' "
            "GROUP BY booked_on",
        )


def scripted(answers: dict[str, str]) -> FunctionModel:
    """A model that writes one prepared statement per question it recognizes."""

    def call(messages: list, _info: AgentInfo) -> ModelResponse:
        prompt = "".join(
            part.content
            for message in messages
            if message.kind == "request"
            for part in message.parts
            if part.part_kind == "user-prompt" and isinstance(part.content, str)
        )
        for question, sql in answers.items():
            if question in prompt:
                return ModelResponse(parts=[ToolCallPart(tool_name="run_sql", args={"sql": sql})])
        raise AssertionError(f"the scripted model was asked something it has no answer for: {prompt[-200:]}")

    return FunctionModel(call, model_name="scripted")


async def test_the_runner_scores_a_right_and_a_wrong_statement(database) -> None:
    session_factory, profile_id = database
    right, wrong = load_sql()[0], load_sql()[1]
    model = scripted(
        {
            right.question: right.sql,
            # The 100x failure of the review of 2026-09-05: a statement that runs and passes
            # the guard, with cents in a column called euros.
            wrong.question: "SELECT ROUND(-SUM(amount_cents), 2) AS total_eur FROM transaction_view "
            "WHERE amount_cents < 0 AND booked_on BETWEEN '2025-01-01' AND '2025-12-31'",
        }
    )
    target = Target(name="scripted", resolve=lambda _slot: model, settings=ModelSettings())
    from datetime import date

    run = await run_points(
        [right, wrong],
        target=target,
        session_factory=session_factory,
        profile_id=profile_id,
        today=date(2025, 12, 31),
        seed=1,
        set_name="sql",
    )
    scores = {result.id: result for result in run.results}
    assert scores[right.id].figure_match is True
    assert scores[right.id].sql_valid is True
    assert scores[right.id].first_attempt is True
    assert scores[wrong.id].figure_match is False
    assert scores[wrong.id].sql_valid is True
    assert run.payload()["summary"]["figure_match"] == 0.5


async def test_a_refused_statement_is_retried_and_reported(database) -> None:
    session_factory, profile_id = database
    point = load_sql()[0]
    model = scripted({point.question: "DELETE FROM transaction_view"})
    target = Target(name="scripted", resolve=lambda _slot: model, settings=ModelSettings())
    from datetime import date

    run = await run_points(
        [point],
        target=target,
        session_factory=session_factory,
        profile_id=profile_id,
        today=date(2025, 12, 31),
        seed=1,
        set_name="sql",
    )
    result = run.results[0]
    assert result.sql_valid is False
    assert result.figure_match is False
    assert result.attempts == 2, "a refused statement is written once more with the reason"
    assert "Only a SELECT may run" in result.refusals[0]


def test_figure_match_is_to_the_cent() -> None:
    gold = [{"total_eur": 2114.2}]
    assert figure_match(gold, [{"anything": 2114.2}])
    assert figure_match(gold, [{"total_eur": 2114.20, "bookings": 7}]), "an extra column is not a miss"
    assert not figure_match(gold, [{"total_eur": 2114.19}])
    assert not figure_match(gold, [{"total_eur": 211420}]), "cents printed as euros is the 100x failure"
    assert not figure_match(gold, [])
    assert not figure_match(gold, [{"total_eur": 2114.2}] * 40), "a dump is not an answer"


def test_a_datapoint_with_no_answer_wants_no_rows() -> None:
    gold = [{"total_eur": None, "bookings": 0}]
    assert figure_match(gold, [], answer="none")
    assert figure_match(gold, [{"total_eur": 0, "bookings": 0}], answer="none")
    assert not figure_match(gold, [{"total_eur": 28535.89}], answer="none")


def test_shape_and_columns() -> None:
    assert shape_match("bar", ["bar_horizontal"], "bar_horizontal")
    assert not shape_match("bar", [], "doughnut")
    rows = [{"month": "2025-01", "topic": "Groceries", "total_eur": 550.0}]
    assert columns_map(["position", "series", "value"], ["month", "topic", "total_eur"], rows)
    assert not columns_map(["position", "value"], ["month", "topic", "total_eur"], rows)
    assert not columns_map(["position", "series", "value"], ["month", "total_eur", "topic"], rows)


def test_compare_names_the_datapoints_that_changed_hands() -> None:
    def run(model: str, matches: dict[str, bool]) -> dict:
        results = [
            {
                "id": ident,
                "set": "sql",
                "kind": "total",
                "difficulty": 1,
                "language": "en",
                "question": f"question {ident}",
                "seconds": 1.0,
                "figure_match": match,
                "sql_valid": True,
                "first_attempt": True,
                "attempts": 1,
                "shape_match": None,
                "columns_map": None,
                "language_ok": None,
                "drawn": None,
                "error": None,
            }
            for ident, match in matches.items()
        ]
        return {
            "model": model,
            "set": "sql",
            "started_at": "2026-09-05T00:00:00+00:00",
            "seconds": 3.0,
            "seed": 7,
            "n": len(results),
            "summary": summarize([type("R", (), result)() for result in results]),  # type: ignore[misc]
            "results": results,
        }

    left = run("old", {"a": True, "b": True, "c": False})
    right = run("new", {"a": True, "b": False, "c": True})
    text = compare(left, right)
    assert "1 right in both" in text
    assert "0 wrong in both" in text
    assert "1 only right in new" in text
    assert "1 only right in old" in text
    assert "`c`" in text and "`b`" in text


def test_the_review_sample_is_stable_for_a_seed() -> None:
    first = [point.id for point in review_sample(7)]
    assert first == [point.id for point in review_sample(7)]
    assert len(first) == 30
    assert len([ident for ident in first if ident.startswith("s")]) == 20
    assert first != [point.id for point in review_sample(8)]


def test_the_review_sample_is_spread_over_the_kinds() -> None:
    points = review_sample(7)
    sql_kinds = {point.kind for point in points if point.set_name == "sql"}
    shapes = {point.kind for point in points if point.set_name == "chart"}
    assert len(sql_kinds) == 8, "every kind of question is reviewed"
    assert len(shapes) >= 6


def test_the_committed_sample_matches_its_seed() -> None:
    """The page's sample.json is what `finquery-bench sample --seed <its seed>` writes."""
    path = Path(__file__).resolve().parents[1] / "bench" / "validate" / "sample.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [point["id"] for point in payload["datapoints"]] == [
        point.id for point in review_sample(payload["seed"])
    ]


def test_a_short_run_takes_a_seeded_sample() -> None:
    points = load_sql()
    picked = [point.id for point in pick(list(points), n=5, seed=3)]
    assert len(picked) == 5
    assert picked == [point.id for point in pick(list(points), n=5, seed=3)]
    assert picked != [point.id for point in pick(list(points), n=5, seed=4)]
    assert picked == [point.id for point in points if point.id in set(picked)], "file order is kept"
