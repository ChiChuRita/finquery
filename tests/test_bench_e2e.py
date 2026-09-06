"""The end-to-end subset of the benchmark: which cases it runs and how a turn is scored.

No model and no network: the subset is a function of the two JSON files, the scorer is a
function of the tool results a turn produced, and the one test that runs a real chat turn drives
it with a scripted model, the way the rest of the suite does.
"""

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.settings import ModelSettings

from finquery.query.check import CHECK_TOOL
from finquery_bench.datapoints import E2E_CHART, E2E_SEED, E2E_SQL, ChartPoint, SqlPoint, e2e_subset, load
from finquery_bench.dataset import fresh_database
from finquery_bench.e2e import message, score
from finquery_bench.models import Target
from finquery_bench.run import new_conversation, run_points

from .conftest import judged
from .test_bench import READING


@pytest.fixture(scope="module")
def database():
    with fresh_database() as (session_factory, profile_id):
        yield session_factory, profile_id


def test_the_subset_is_thirty_training_cases_and_does_not_move() -> None:
    points = e2e_subset()
    assert [point.id for point in points] == [point.id for point in e2e_subset()]
    assert [point.id for point in points] == [point.id for point in load("e2e")]
    assert len([point for point in points if isinstance(point, SqlPoint)]) == E2E_SQL
    assert len([point for point in points if isinstance(point, ChartPoint)]) == E2E_CHART
    assert all(point.split == "train" for point in points), "a held-out case is not an example"
    assert [point.id for point in points] != [point.id for point in e2e_subset(E2E_SEED + 1)]


def test_the_subset_is_spread_over_the_kinds_and_the_shapes() -> None:
    points = e2e_subset()
    kinds = {point.kind for point in points if isinstance(point, SqlPoint)}
    shapes = {point.kind for point in points if isinstance(point, ChartPoint)}
    assert len(kinds) == 8, "every kind of question is asked end to end"
    assert len(shapes) >= 6


def _sql_point() -> SqlPoint:
    return next(point for point in e2e_subset() if isinstance(point, SqlPoint))


def _chart_point() -> ChartPoint:
    return next(point for point in e2e_subset() if isinstance(point, ChartPoint))


def test_a_follow_up_reaches_the_turn_with_what_was_asked_before() -> None:
    """A follow-up is not a standalone turn, and rewriting it is what is being measured."""
    plain = next(point for point in e2e_subset() if isinstance(point, SqlPoint) and not point.prefix)
    assert message(plain) == plain.question
    follow = next(point for point in e2e_subset() if isinstance(point, SqlPoint) and point.prefix)
    said = message(follow)
    assert follow.question in said
    for question in follow.prefix:
        assert question in said


def test_a_turn_that_asked_for_the_right_thing_first_scores_both() -> None:
    point = _sql_point()
    result = score(
        point,
        returns=[{"sql": "SELECT 1", "columns": ["total_eur"], "rows": point.gold.rows, "error": None}],
        requests=["total spending on groceries in 2025"],
        seconds=12.0,
    )
    assert result.set == "e2e"
    assert result.figure_match is True
    assert result.first_attempt is True
    assert result.sql_valid is True
    assert result.attempts == 1
    assert result.notes == ["request: total spending on groceries in 2025"]


def test_a_turn_that_had_to_sharpen_its_request_is_right_but_not_first() -> None:
    """The figures reached the answer, so the turn is right; the first request was not."""
    point = _sql_point()
    result = score(
        point,
        returns=[
            {"sql": "SELECT 1", "columns": ["total_eur"], "rows": [{"total_eur": 1.0}], "error": None},
            {"sql": "SELECT 2", "columns": ["total_eur"], "rows": point.gold.rows, "error": None},
        ],
        requests=["spending", "spending on groceries in 2025"],
        seconds=30.0,
    )
    assert result.figure_match is True
    assert result.first_attempt is False
    assert result.attempts == 2


def test_a_turn_that_never_called_the_tool_is_a_miss_that_says_so() -> None:
    point = _sql_point()
    result = score(point, returns=[], requests=[], seconds=4.0, called_the_other=True)
    assert result.figure_match is False
    assert result.attempts == 0
    assert result.error == "the turn never called query, it called chart"
    assert result.shape_match is None, "a question has no shape to get wrong"


def test_a_chart_turn_is_scored_on_its_shape_and_its_columns() -> None:
    point = _chart_point()
    result = score(
        point,
        returns=[
            {
                "sql": "SELECT 1",
                "columns": point.gold.columns,
                "rows": point.gold.rows,
                "shape": point.shape,
                "language": point.language,
                "rendered": True,
                "error": None,
            }
        ],
        requests=["as the user asked"],
        seconds=40.0,
    )
    assert result.figure_match is True
    assert result.shape_match is True
    assert result.language_ok is True
    assert result.drawn is True
    assert result.columns_map is True


def test_a_chart_turn_that_drew_the_wrong_shape_keeps_its_figures() -> None:
    point = _chart_point()
    wrong = next(shape for shape in ("doughnut", "sankey", "line") if shape != point.shape and shape not in point.also)
    result = score(
        point,
        returns=[
            {
                "sql": "SELECT 1",
                "columns": point.gold.columns,
                "rows": point.gold.rows,
                "shape": wrong,
                "language": point.language,
                "rendered": True,
                "error": None,
            }
        ],
        requests=["as the user asked"],
        seconds=40.0,
    )
    assert result.figure_match is True
    assert result.shape_match is False
    assert result.passed is False, "a chart of the wrong shape did not answer the request"


def scripted_turn(sql: str | None) -> FunctionModel:
    """A chat model that calls `query` once with the given statement, then writes an answer.

    `None` is the turn that answers out of its own head without calling a tool, which is the
    routing loss this subset exists to measure.
    """

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        names = [tool.name for tool in info.output_tools]
        if names == [CHECK_TOOL]:
            return ModelResponse(parts=[judged()])
        if names == ["run_sql"]:
            return ModelResponse(parts=[ToolCallPart(tool_name="run_sql", args={"reasoning": READING, "sql": sql})])
        called = any(
            part.part_kind == "tool-return" for message in messages if message.kind == "request" for part in message.parts
        )
        if sql is None or called:
            return ModelResponse(parts=[TextPart(content="Du hast 100,00 EUR ausgegeben.")])
        return ModelResponse(parts=[ToolCallPart(tool_name="query", args={"request": "the question, on its own"})])

    return FunctionModel(respond, model_name="scripted")


async def test_a_scripted_turn_reaches_the_sub_agent_and_is_scored(database) -> None:
    """The whole path: the chat agent calls `query`, the sub-agent writes the gold statement."""
    from datetime import date

    session_factory, profile_id = database
    point = _sql_point()
    target = Target(name="scripted", resolve=lambda _role: scripted_turn(point.sql), settings=ModelSettings())
    run = await run_points(
        [point],
        target=target,
        session_factory=session_factory,
        profile_id=profile_id,
        today=date(2025, 12, 31),
        seed=E2E_SEED,
        set_name="e2e",
    )
    result = run.results[0]
    assert result.set == "e2e"
    assert result.figure_match is True
    assert result.sql_valid is True
    assert result.notes == ["request: the question, on its own"]
    assert run.payload()["summary"]["figure_match"] == 1.0


async def test_a_turn_that_answers_without_a_query_scores_zero(database) -> None:
    from datetime import date

    session_factory, profile_id = database
    point = _sql_point()
    target = Target(name="scripted", resolve=lambda _role: scripted_turn(None), settings=ModelSettings())
    run = await run_points(
        [point],
        target=target,
        session_factory=session_factory,
        profile_id=profile_id,
        today=date(2025, 12, 31),
        seed=E2E_SEED,
        set_name="e2e",
    )
    assert run.results[0].figure_match is False
    assert run.results[0].error == "the turn never called query"


def test_the_run_gets_its_own_conversation(database) -> None:
    session_factory, profile_id = database
    first = new_conversation(session_factory, profile_id)
    assert first and first != new_conversation(session_factory, profile_id)
