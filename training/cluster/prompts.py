"""The prompts an adapter is trained on and evaluated with, built by the product's own code.

Every prompt here comes out of `finquery.query.subagent` and `finquery.chart.subagent`, and
every message list and tool schema comes out of `finquery.local.model`, which is what the local
provider hands the chat template. Nothing is copied: a change to a sub-agent's rules, to its
worked examples or to its output model reaches the training data and the quick evaluation on
the next run, which is the whole point of the sub-agents' prompt builders being pure functions.

Two things are deliberately not the same as production, and both make the evaluation harder
rather than easier. There is no GBNF grammar here, so a model that writes a malformed tool call
is simply scored as a miss instead of being constrained into a well-formed one. And generation
is greedy, so a quick evaluation of the same checkpoint twice gives the same number.
"""

import asyncio
import dataclasses
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]


def add_repo_to_path() -> None:
    """Put the product and the benchmark on `sys.path`.

    The training environment does not install `finquery`: doing so would pull in the CUDA build
    of llama-cpp-python, an eleven minute compile nothing in this directory uses. See the
    comment at the top of `pyproject.toml`.
    """
    for path in (REPO / "src", REPO / "bench"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


add_repo_to_path()

from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.messages import ModelResponse, ToolCallPart  # noqa: E402
from pydantic_ai.models import ModelRequestParameters  # noqa: E402
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402

from finquery.chart.subagent import (  # noqa: E402
    ChartCode,
    ChartPlan,
    code_agent,
    code_prompt,
    plan_agent,
    plan_prompt,
)
from finquery.local import gemma  # noqa: E402
from finquery.local.model import LOCAL_PROFILE, _render_messages, _render_tools  # noqa: E402
from finquery.query.subagent import (  # noqa: E402
    GeneratedSql,
    QueryContext,
    Rejection,
    Revision,
    query_agent,
    query_prompt,
)

QUERY_TOOL = "run_sql"
PLAN_TOOL = "chart_plan"
CODE_TOOL = "chart_code"

#: A well-formed answer per sub-agent, so the capture run below finishes instead of retrying.
#: Its content is thrown away: only the request the framework built on the way there is kept.
CANNED: dict[str, dict[str, Any]] = {
    QUERY_TOOL: {"reasoning": "x", "sql": "SELECT 1 AS total_eur"},
    PLAN_TOOL: {
        "reasoning": "x",
        "shape": "bar",
        "language": "en",
        "title": "x",
        "question": "x",
        "columns": ["month", "total_eur"],
    },
    CODE_TOOL: {"reasoning": "x", "code": "return defineChart({});"},
}


@dataclass(frozen=True)
class Request:
    """One sub-agent call as the local provider would send it: messages, tools, forced tool."""

    tool: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]

    def with_answer(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        """The same messages with the assistant turn that answers them appended."""
        call = {"id": "call_0", "type": "function", "function": {"name": self.tool, "arguments": arguments}}
        return [*self.messages, {"role": "assistant", "content": "", "tool_calls": [call]}]


def _capture(agent: Agent, tool: str, prompt: str) -> Request:
    """Run one sub-agent against a stand-in model and keep the request it was sent.

    The framework decides what the tool schema looks like (the output model, the Google schema
    transformer the local profile carries) and `finquery.local.model` decides how the messages
    and the tools are rendered. Both are read here rather than rebuilt, so the training prompt
    and the production prompt cannot drift apart.
    """
    kept: dict[str, Any] = {}

    def stand_in(messages: list[Any], info: AgentInfo) -> ModelResponse:
        transformer = LOCAL_PROFILE["json_schema_transformer"]
        output_tools = [
            dataclasses.replace(
                definition,
                parameters_json_schema=transformer(definition.parameters_json_schema, strict=None).walk(),
            )
            for definition in info.output_tools
        ]
        params = ModelRequestParameters(
            function_tools=list(info.function_tools),
            output_tools=output_tools,
            allow_text_output=info.allow_text_output,
        )
        kept["messages"] = _render_messages(messages, params, "reasoning")
        kept["tools"], _ = _render_tools(params)
        return ModelResponse(parts=[ToolCallPart(tool, CANNED[tool])])

    asyncio.run(agent.run(prompt, model=FunctionModel(stand_in)))
    return Request(tool=tool, messages=kept["messages"], tools=kept["tools"])


def query_request(
    request: str,
    context: QueryContext,
    *,
    hints: str | None = None,
    rejected: Rejection | None = None,
    revised: Revision | None = None,
) -> Request:
    """The query sub-agent's request, first attempt or repair round."""
    return _capture(
        query_agent, QUERY_TOOL, query_prompt(request, context, hints=hints, rejected=rejected, revised=revised)
    )


def plan_request(request: str, context: QueryContext, *, hints: str | None = None) -> Request:
    """The chart sub-agent's planning pass."""
    return _capture(plan_agent, PLAN_TOOL, plan_prompt(request, context, hints=hints))


def code_request(
    plan: ChartPlan,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    previous: ChartCode | None = None,
    findings: str | None = None,
) -> Request:
    """The chart sub-agent's code pass, first attempt or repair round."""
    return _capture(code_agent, CODE_TOOL, code_prompt(plan, columns, rows, previous=previous, findings=findings))


# The chat template arguments the local provider passes for a sub-agent call: thinking off,
# because a grammar-constrained answer has no room for a thought channel, and Gemma 4's own
# `preserve_thinking` from `finquery.local.model.WIRE_FORMATS`.
TEMPLATE_KWARGS = {"enable_thinking": False, "preserve_thinking": True}


def render(tokenizer: Any, request: Request) -> str:
    """The generation prompt for this request, through the base model's own chat template."""
    return tokenizer.apply_chat_template(
        request.messages,
        tools=request.tools,
        add_generation_prompt=True,
        tokenize=False,
        **TEMPLATE_KWARGS,
    )


def render_pair(tokenizer: Any, request: Request, arguments: dict[str, Any]) -> tuple[str, str]:
    """The prompt and the completion of one training sample, split where generation begins.

    TRL trains a prompt-completion dataset with the loss on the completion only, which is what
    this pair is for. The split is not computed from token counts: the whole conversation is
    rendered, the prompt is rendered again with the generation prompt on, and the completion is
    what the first leaves over the second. A template whose two renderings do not agree would
    put the loss in the wrong place, silently, so it is an error and not a warning.
    """
    prompt = render(tokenizer, request)
    whole = tokenizer.apply_chat_template(
        request.with_answer(arguments), tools=request.tools, tokenize=False, **TEMPLATE_KWARGS
    )
    if not whole.startswith(prompt):
        raise RuntimeError(
            "the chat template does not render the answered conversation as the generation "
            "prompt plus the answer, so the completion cannot be split off. Prompt ends with "
            f"{prompt[-80:]!r}, the whole conversation has {whole[len(prompt) - 80 : len(prompt) + 80]!r} there."
        )
    return prompt, whole[len(prompt) :]


def parse_call(text: str, tool: str) -> dict[str, Any] | None:
    """The arguments of the named tool call in a generated answer, or None if there is none.

    Parsed by the product's own Gemma 4 splitter, so a call this returns is a call the app
    would have acted on and a call it drops is one the app would have dropped.
    """
    splitter = gemma.StreamSplitter(in_thought=False)
    events = [*splitter.feed(text), *splitter.finish()]
    for kind, payload in events:
        if kind == "tool_call" and payload.name == tool:
            return dict(payload.args)
    # A template that already opened the tool-call block leaves the model nothing to open, so
    # the raw body arrives with no marker around it.
    try:
        call = gemma.parse_tool_call(text)
    except ValueError:
        return None
    return dict(call.args) if call.name == tool else None


def parse_sql(text: str) -> GeneratedSql | None:
    args = parse_call(text, QUERY_TOOL)
    if args is None:
        return None
    try:
        return GeneratedSql.model_validate(args)
    except Exception:  # noqa: BLE001 - a malformed answer is a miss, not a dead run
        return None


def parse_plan(text: str) -> ChartPlan | None:
    args = parse_call(text, PLAN_TOOL)
    if args is None:
        return None
    try:
        return ChartPlan.model_validate(args)
    except Exception:  # noqa: BLE001
        return None


def parse_code(text: str) -> ChartCode | None:
    args = parse_call(text, CODE_TOOL)
    if args is None:
        return None
    try:
        return ChartCode.model_validate(args)
    except Exception:  # noqa: BLE001
        return None
