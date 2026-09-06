"""The end-to-end subset: one whole chat turn in front of the sub-agent.

The two sub-agent sets score the model that writes the SQL or the chart. This one scores the
turn around it: the chat agent reads the user's question, decides which tool to call, writes
the request the sub-agent gets, and what comes back is held to the same figure match and shape
match. The difference between the two tables is routing and phrasing loss, which is why this is
a second table and never the primary number.

Both roles are the candidate: `target.resolve` answers `chat` and `fast` with the same model,
so a number here is about one model and not about a pair.
"""

import time
from typing import Any

from pydantic_ai.messages import ModelMessage
from sqlalchemy.orm import Session, sessionmaker

from finquery.agent import ChatDeps, chat_agent
from finquery_bench.datapoints import ChartPoint, Point
from finquery_bench.models import Target
from finquery_bench.run import Result
from finquery_bench.score import columns_map, figure_match, shape_match

QUERY_TOOL = "query"
CHART_TOOL = "chart"

PREFIX = 'Earlier in this conversation I asked: {questions}\n\nNow: "{question}"'
"""How a follow-up datapoint reaches the chat agent.

A follow-up ("And in June?") is not a turn that stands on its own, and rewriting it into a
request the sub-agent can answer is the chat agent's job, which is exactly what this subset is
here to measure. The sub-agent sets hand the earlier questions to the sub-agent as hints
(`run.PREFIX_HINT`); here they ride in on the user's own message, because that is where a
conversation would have put them.
"""


class NoWeb:
    """The web client a benchmark turn is given.

    Web lookup is off on the benchmark profile, so `lookup_merchant` is not even offered and
    nothing here should ever be called. If something does call it, the datapoint fails with
    that sentence rather than the run reaching the network from a cluster job.
    """

    async def search(self, query: str) -> list[Any]:
        raise RuntimeError(f"a benchmark turn tried to search the web for {query!r}")

    async def fetch(self, url: str) -> Any:
        raise RuntimeError(f"a benchmark turn tried to fetch {url}")


def tool_returns(messages: list[ModelMessage], name: str) -> list[dict[str, Any]]:
    """Every result the named tool gave this turn, in the order the turn got them."""
    return [
        part.content
        for message in messages
        if message.kind == "request"
        for part in message.parts
        if part.part_kind == "tool-return" and part.tool_name == name and isinstance(part.content, dict)
    ]


def _requested(messages: list[ModelMessage], name: str) -> list[str]:
    """The request the chat agent wrote for each call of the named tool.

    It is what this table is really about, so it is kept on the result: a miss whose request
    asked for the wrong period is a different failure from one whose SQL was wrong.
    """
    return [
        str(part.args_as_dict().get("request", ""))
        for message in messages
        if message.kind == "response"
        for part in message.parts
        if part.part_kind == "tool-call" and part.tool_name == name
    ]


def message(point: Point) -> str:
    """What the user says this turn: the question, with the earlier ones when it is a follow-up."""
    prefix = list(getattr(point, "prefix", []))
    if not prefix:
        return point.question
    return PREFIX.format(
        questions=" ".join(f'"{question}"' for question in prefix), question=point.question
    )


def _matching(returns: list[dict[str, Any]], gold: list[dict[str, Any]], answer: str) -> int:
    """Which call carried the expected figures, else the last one. -1 when there is none."""
    for index, payload in enumerate(returns):
        if figure_match(gold, list(payload.get("rows") or []), answer=answer):
            return index
    return len(returns) - 1


def _empty(point: Point, seconds: float, error: str, *, chart: bool) -> Result:
    """A datapoint whose turn never produced a result of the tool it was about."""
    return Result(
        id=point.id,
        set="e2e",
        kind=point.kind,
        difficulty=point.difficulty,
        language=point.language,
        question=point.question,
        seconds=round(seconds, 2),
        figure_match=False,
        sql_valid=False,
        first_attempt=False,
        attempts=0,
        error=error,
        shape_match=False if chart else None,
        columns_map=False if chart else None,
        language_ok=False if chart else None,
        drawn=False if chart else None,
    )


def score(
    point: Point,
    *,
    returns: list[dict[str, Any]],
    requests: list[str],
    seconds: float,
    called_the_other: bool = False,
) -> Result:
    """Score one finished turn from the results its tool gave it.

    A turn may call the tool more than once: the chat agent is told to sharpen a request that
    came back answering less than the question asked. So the turn is right when one of its
    calls carried the expected figures, and `first attempt` is the stricter number: the request
    it wrote first was already the right one.
    """
    chart = isinstance(point, ChartPoint)
    tool = CHART_TOOL if chart else QUERY_TOOL
    if not returns:
        other = CHART_TOOL if tool == QUERY_TOOL else QUERY_TOOL
        instead = f", it called {other}" if called_the_other else ""
        return _empty(point, seconds, f"the turn never called {tool}{instead}", chart=chart)

    gold = point.gold.rows if point.gold else []
    answer = getattr(point, "answer", "")
    index = _matching(returns, gold, answer)
    payload = returns[index]
    rows = list(payload.get("rows") or [])
    columns = list(payload.get("columns") or [])
    matched = figure_match(gold, rows, answer=answer)
    result = Result(
        id=point.id,
        set="e2e",
        kind=point.kind,
        difficulty=point.difficulty,
        language=point.language,
        question=point.question,
        seconds=round(seconds, 2),
        figure_match=matched,
        sql_valid=payload.get("sql") is not None and not payload.get("error"),
        first_attempt=matched and index == 0,
        attempts=len(returns),
        sql=payload.get("sql"),
        columns=columns,
        rows=rows,
        error=payload.get("error"),
        notes=[f"request: {request}" for request in requests],
    )
    if chart:
        assert isinstance(point, ChartPoint)
        result.shape = payload.get("shape") or None
        result.shape_match = shape_match(point.shape, point.also, str(payload.get("shape") or ""))
        result.columns_map = columns_map(point.roles, columns, rows)
        result.language_ok = payload.get("language") == point.language
        result.drawn = bool(payload.get("rendered"))
    return result


async def run_e2e_point(
    point: Point,
    *,
    target: Target,
    session_factory: sessionmaker[Session],
    profile_id: str,
    conversation_id: str,
) -> Result:
    """Run one chat turn on the question and score the tool result it produced."""
    started = time.perf_counter()
    chart = isinstance(point, ChartPoint)
    tool = CHART_TOOL if chart else QUERY_TOOL
    other = CHART_TOOL if tool == QUERY_TOOL else QUERY_TOOL
    said = message(point)
    deps = ChatDeps(
        session_factory=session_factory,
        profile_id=profile_id,
        conversation_id=conversation_id,
        resolve_model=target.resolve,
        subagent_settings=target.settings,
        web_client=NoWeb(),  # type: ignore[arg-type]
        user_message=said,
    )
    try:
        run = await chat_agent.run(
            said,
            deps=deps,
            model=target.resolve("chat"),
            model_settings=target.settings,
        )
    except Exception as exc:  # noqa: BLE001 - one turn that throws is one score, not a dead run
        return _empty(point, time.perf_counter() - started, f"the turn raised {type(exc).__name__}: {exc}", chart=chart)
    seconds = time.perf_counter() - started
    messages = run.all_messages()
    return score(
        point,
        returns=tool_returns(messages, tool),
        requests=_requested(messages, tool),
        seconds=seconds,
        called_the_other=bool(tool_returns(messages, other)),
    )
