"""The benchmarks: gold that rebuilds identically, a runner that scores, a stable sample.

No model and no network here either: the runner is driven by a scripted model that answers one
statement per question, which is how "a known right and a known wrong statement" become a 1 and
a 0 without OpenRouter.
"""

import json
import re
import shutil
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.settings import ModelSettings

from finquery.query.check import CHECK_TOOL
from finquery.query.guard import execute_read_only, validate_sql
from finquery.query.subagent import EXAMPLES, EXAMPLE_SOURCES
from finquery_bench.datapoints import CHART_SET, SQL_SET, load_charts, load_sql, pick, review_sample
from finquery_bench.dataset import fresh_database
from finquery_bench.gold import GoldFailed, build, run_reference
from finquery_bench.models import Target
from finquery_bench.report import compare
from finquery_bench.run import run_points, summarize
from finquery_bench.score import columns_map, figure_match, shape_match
from finquery_bench.splits import assign

from .conftest import judged


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


def test_a_reference_whose_rows_carry_no_figure_fails_the_build(database) -> None:
    """A single NULL is not an answer: gold with no number in it scores every reply as right."""
    session_factory, profile_id = database
    with pytest.raises(GoldFailed, match="no figure"):
        run_reference(
            session_factory,
            profile_id,
            "made-up",
            "SELECT ROUND(SUM(amount), 2) AS total_eur FROM transaction_view "
            "WHERE subcategory = 'Salary'",
        )


def test_every_datapoint_is_train_or_heldout() -> None:
    """About a third of each set is held out, and every stratum of it contributes."""
    points = [*load_sql(), *load_charts()]
    assert all(point.split in ("train", "heldout") for point in points)
    for name in ("sql", "chart"):
        of_set = [point for point in points if point.set_name == name]
        heldout = [point for point in of_set if point.split == "heldout"]
        assert 0.25 <= len(heldout) / len(of_set) <= 0.4, name
        assert {point.source for point in heldout} <= {"hand", "generated", "ticket-64"}, name
        assert {point.kind for point in heldout} == {point.kind for point in of_set}, name


def test_the_split_does_not_move_when_a_datapoint_is_added() -> None:
    """The split is a hash of the id, so growing one stratum leaves the others alone."""
    items = [{"id": f"s{index:02d}", "kind": "total"} for index in range(20)]
    before = assign(items, lambda item: item["kind"])
    after = assign([*items, {"id": "s99", "kind": "entity"}], lambda item: item["kind"])
    assert {ident: after[ident] for ident in before} == before


def test_every_worked_example_of_the_query_prompt_is_a_train_datapoint_that_runs(database) -> None:
    """The nine examples in `query_prompt` are real datapoints, and they still answer them.

    An example drawn from a held-out datapoint would teach the model the answer to a question
    it is then scored on, and one that no longer runs teaches it a broken pattern in the place
    it copies from hardest. Both are caught here, against the same data the set is gold on.
    """
    session_factory, profile_id = database
    points = {point.id: point for point in load_sql()}
    statements = re.findall(r"^SQL:\n(.+?)(?=\n\nQuestion:|\s*\Z)", EXAMPLES, re.S | re.M)
    assert len(statements) == len(EXAMPLE_SOURCES)
    for ident, sql in zip(EXAMPLE_SOURCES, statements, strict=True):
        point = points[ident]
        assert point.split == "train", f"{ident} is held out of training"
        with session_factory() as session:
            rows = execute_read_only(session, validate_sql(sql), profile_id)
        assert rows.rows, ident
        assert figure_match(point.gold.rows, rows.rows, answer=point.answer), ident


READING = "period: as the question names it. sign: spending. grouping: as asked."
"""What a scripted model writes into the required `run_sql.reasoning`."""


def scripted(answers: dict[str, str], judgements: list[str] | None = None) -> FunctionModel:
    """A model that writes one prepared statement per question it recognizes.

    It says `ok` to every check pass of ticket 40 and, when the test hands one in, writes the
    prompts it judged into `judgements`, which is how a run says whether the pass ran at all.
    """

    def call(messages: list, info: AgentInfo) -> ModelResponse:
        prompt = "".join(
            part.content
            for message in messages
            if message.kind == "request"
            for part in message.parts
            if part.part_kind == "user-prompt" and isinstance(part.content, str)
        )
        if [tool.name for tool in info.output_tools] == [CHECK_TOOL]:
            if judgements is not None:
                judgements.append(prompt)
            return ModelResponse(parts=[judged()])
        for question, sql in answers.items():
            if question in prompt:
                return ModelResponse(parts=[ToolCallPart(tool_name="run_sql", args={"reasoning": READING, "sql": sql})])
        raise AssertionError(f"the scripted model was asked something it has no answer for: {prompt[-200:]}")

    return FunctionModel(call, model_name="scripted")


async def test_the_runner_scores_a_right_and_a_wrong_statement(database) -> None:
    session_factory, profile_id = database
    right, wrong = load_sql()[0], load_sql()[1]
    model = scripted(
        {
            right.question: right.sql,
            # A statement that runs and passes the guard and answers the wrong question: half
            # the year, in a column called total. (The 100x failure of the review of
            # 2026-09-05, `SUM(amount_cents) AS total_eur`, no longer reaches this point: the
            # guard refuses cents in a figure since ticket 37.)
            wrong.question: "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view "
            "WHERE amount < 0 AND booked_on BETWEEN '2025-01-01' AND '2025-06-30'",
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


async def test_no_check_leaves_a_statement_to_stand_and_the_run_says_so(database) -> None:
    """`--no-check` is the path before ticket 40, which is what a before and after needs."""
    from datetime import date

    session_factory, profile_id = database
    point = load_sql()[0]
    judgements: list[str] = []
    target = Target(
        name="scripted", resolve=lambda _slot: scripted({point.question: point.sql}, judgements), settings=ModelSettings()
    )
    arguments = dict(
        target=target,
        session_factory=session_factory,
        profile_id=profile_id,
        today=date(2025, 12, 31),
        seed=1,
        set_name="sql",
    )

    without = await run_points([point], check=False, **arguments)  # type: ignore[arg-type]
    assert judgements == [], "no model judged the result"
    assert without.payload()["check"] is False

    with_check = await run_points([point], check=True, **arguments)  # type: ignore[arg-type]
    assert len(judgements) == 1, "the check pass ran once"
    assert with_check.payload()["check"] is True
    assert without.results[0].figure_match == with_check.results[0].figure_match is True


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
    sample = review_sample(7)
    first = [point.id for point in sample]
    assert first == [point.id for point in review_sample(7)]
    assert len(first) == 30
    assert len([point for point in sample if point.set_name == "sql"]) == 20
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


def test_a_benchmark_candidate_resolves_like_a_catalog_model_and_stays_out_of_the_catalog(tmp_path: Path) -> None:
    """A candidate is scored through the same stack as the catalog's models, without being one.

    Qwen3.8 27B never was one; Gemma 4 12B was the shipped chat model until ticket 73 and kept
    its key when it moved here, which is what makes every run recorded on `local:gemma-4-12b`
    resolve while the app neither lists nor downloads it. Neither one's files are in this test's
    models folder, so the runner says so in the app's own words; a name nobody defined lists
    what would have worked, candidates included.
    """
    from finquery.catalog import Catalog

    from .conftest import make_settings
    from finquery.providers import ProviderNotAvailable
    from finquery_bench.candidates import LOCAL_GEMMA_12B, QWEN38_27B
    from finquery_bench.models import resolve_target

    settings = make_settings(provider="local", models_dir=tmp_path / "models")
    with pytest.raises(ProviderNotAvailable, match="Qwen3.8 27B .* not downloaded"):
        resolve_target("local:qwen3.8-27b", None, settings)
    with pytest.raises(ProviderNotAvailable, match="Gemma 4 12B .* not downloaded"):
        resolve_target("local:gemma-4-12b", None, settings)
    with pytest.raises(RuntimeError, match="local:qwen3.8-27b"):
        resolve_target("local:nonsense", None, settings)
    catalog_keys = [entry.key for entry in Catalog(settings).entries]
    assert QWEN38_27B.key not in catalog_keys
    assert LOCAL_GEMMA_12B.key not in catalog_keys
