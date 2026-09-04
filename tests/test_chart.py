"""Drawing a chart: the plan, the query behind it, the self-check and the repairs.

Every test drives the chat endpoint. The chat model is scripted to call the `chart` tool and
then to report what came back, and the fast slot behind the tool answers three different forced
single tools (the plan, the SQL, the code) plus the post-turn follow-up step.
"""

import json
from collections.abc import AsyncIterator, Sequence

import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from finquery.chart.subagent import EXAMPLES

from .conftest import (
    Chat,
    Scripts,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
    tool_call_of,
    turn_of,
)
from .test_query import import_synthetic

MONTHLY_SQL = (
    "SELECT strftime('%Y-%m', booked_on) AS month, ROUND(-SUM(amount), 2) AS total_eur "
    "FROM transaction_view WHERE amount_cents < 0 GROUP BY month ORDER BY month"
)

MERCHANTS_SQL = (
    "SELECT coalesce(counterparty, description) AS merchant, ROUND(-SUM(amount), 2) AS total_eur "
    "FROM transaction_view WHERE amount_cents < 0 GROUP BY merchant ORDER BY total_eur DESC LIMIT 7"
)

LINE_PLAN = {
    "shape": "line",
    "title": "Ausgaben pro Monat",
    "question": "total spending per month in 2025",
    "columns": ["month", "total_eur"],
    "reason": "A month series reads best as a line.",
}

DOUGHNUT_PLAN = {
    "shape": "doughnut",
    "title": "Anteil der Haendler",
    "question": "the seven largest merchants by spending in 2025",
    "columns": ["merchant", "total_eur"],
    "reason": "A share of a whole reads as a doughnut.",
}

LINE_CODE = """\
return defineChart({
  marks: [lineY(data, { x: 'month', y: 'total_eur', stroke: palette[0], strokeWidth: 2.25 })],
  scales: {
    x: { scale: () => scalePoint().padding(0.06), axis: { ticks: { format: monthShort } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: { use: tooltip, format: (point) => eur(point.datum.total_eur) },
});"""

BAR_CODE = """\
return defineChart({
  marks: [barY(data, { x: 'month', y: 'total_eur', fill: palette[0], radius: 4 })],
  scales: {
    x: { scale: () => scaleBand().padding(0.24), axis: { ticks: { format: monthShort } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: { use: tooltip, format: (point) => eur(point.datum.total_eur) },
});"""

DOUGHNUT_CODE = """\
const slices = pie(data, { value: 'total_eur' });
return defineChart({
  marks: [
    polar({
      marks: [radialArc(slices, { innerRadius: ({ radius }) => radius * 0.6, color: 'merchant', key: 'merchant' })],
      scales: { angle: null, radius: null },
    }),
  ],
  scales: { x: null, y: null },
  color: { legend: colorLegend({ placement: 'bottom' }) },
  tooltip: { use: tooltip, format: (point) => point.datum.merchant + ': ' + eur(point.datum.total_eur) },
});"""

FOLDED_DOUGHNUT_CODE = DOUGHNUT_CODE.replace(
    "const slices = pie(data, { value: 'total_eur' });",
    "const top = data.slice(0, 5);\n"
    "const other = { merchant: 'Other', total_eur: data.slice(5).reduce((sum, row) => sum + row.total_eur, 0) };\n"
    "const slices = pie(top.concat([other]), { value: 'total_eur' });",
)


def ask_chart_then_report(request: str):
    """A chat turn that calls `chart` and then reports what the tool returned."""

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        result = _last_chart_return(messages)
        if result is None:
            yield {0: DeltaToolCall(name="chart", json_args=json.dumps({"request": request}))}
            return
        if result["error"]:
            yield f"I could not draw that: {result['error']}"
        else:
            yield f"Here is {result['title']} ({result['shape']}) over {result['row_count']} rows."

    return fn


def scripted_chart(
    *,
    plan: dict[str, object],
    sql: str,
    codes: Sequence[str],
    followups: Sequence[str] = (),
):
    """The fast slot behind the chart tool: one plan, one statement, one code per attempt."""
    prompts: dict[str, list[str]] = {"plan": [], "sql": [], "code": []}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="\n".join(followups) if followups else "No follow-ups.")])
        # The post-turn distillation pass shares the fast slot and remembers nothing here.
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        assert info.allow_text_output is False, "a sub-agent answers through a forced single tool"
        assert len(info.output_tools) == 1
        name = info.output_tools[0].name
        prompt = _last_user_prompt(messages)
        if name == "chart_plan":
            prompts["plan"].append(prompt)
            return ModelResponse(parts=[ToolCallPart("chart_plan", json.dumps(plan))])
        if name == "run_sql":
            prompts["sql"].append(prompt)
            return ModelResponse(parts=[ToolCallPart("run_sql", json.dumps({"sql": sql}))])
        if name == "chart_code":
            prompts["code"].append(prompt)
            code = codes[min(len(prompts["code"]), len(codes)) - 1]
            return ModelResponse(parts=[ToolCallPart("chart_code", json.dumps({"code": code}))])
        raise AssertionError(f"unexpected forced tool {name}")

    respond.prompts = prompts  # type: ignore[attr-defined]
    return respond


def _last_chart_return(messages: list[ModelMessage]) -> dict | None:
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == "chart":
                assert isinstance(part.content, dict)
                return part.content
            if part.part_kind == "user-prompt":
                return None
    return None


def _last_user_prompt(messages: list[ModelMessage]) -> str:
    return [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt" and isinstance(part.content, str)
    ][-1]


def chart_output(chunks: list[dict[str, object]]) -> dict:
    outputs = [c["output"] for c in chunks if c["type"] == "tool-output-available"]
    assert len(outputs) == 1, chunks
    assert isinstance(outputs[0], dict)
    return outputs[0]


def narration(chunks: list[dict[str, object]]) -> str:
    """The reasoning text the chart sub-agent streamed while the tool was running."""
    ids = {str(c["id"]) for c in chunks if c["type"] == "reasoning-start" and str(c["id"]).startswith("narration")}
    return "".join(str(c["delta"]) for c in chunks if c["type"] == "reasoning-delta" and c["id"] in ids)


def answer(chunks: list[dict[str, object]]) -> str:
    return "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta").strip()


async def test_a_scripted_chart_passes_the_check_and_reaches_the_transcript(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE], followups=["Und pro Kategorie?"])
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig mir die Ausgaben pro Monat als Diagramm.")

    # The chat model, the chart sub-agent, the query sub-agent, the follow-up step and the
    # distillation pass.
    assert scripts.resolved == ["fast", "fast", "fast", "fast", "fast"]
    types = [str(c["type"]) for c in chunks]
    # The plan is narrated while the tool runs: after the call, before its result.
    assert types.index("tool-input-available") < types.index("reasoning-start") < types.index("tool-output-available")
    assert types.index("tool-output-available") < types.index("text-start")
    told = narration(chunks)
    assert 'Chart plan: line, titled "Ausgaben pro Monat", over month, total_eur.' in told
    assert "Data: 12 rows over month, total_eur." in told
    assert "Self-check passed." in told

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["title"] == "Ausgaben pro Monat"
    assert output["shape"] == "line"
    assert output["columns"] == ["month", "total_eur"]
    assert output["row_count"] == 12
    assert output["rows"][0]["month"] == "2025-01"
    assert output["code"] == LINE_CODE
    assert output["notes"] == []
    # The rows come from a statement the guard admitted and SQLite ran.
    assert output["sql"].startswith("SELECT\n  STRFTIME('%Y-%m', booked_on) AS month")
    assert output["sql"].endswith("LIMIT 200")
    assert answer(chunks) == "Here is Ausgaben pro Monat (line) over 12 rows."

    # The plan pass saw the household and the shapes; the code pass saw the contract and the rows.
    plan_prompt = respond.prompts["plan"][0]  # type: ignore[attr-defined]
    assert "doughnut: a share of a whole" in plan_prompt
    assert "2025-01-01 to 2025-12-28" in plan_prompt
    assert "Request: spending per month in 2025 as a line chart" in plan_prompt
    code_prompt = respond.prompts["code"][0]  # type: ignore[attr-defined]
    assert "defineChart(spec)" in code_prompt
    assert "The query returned 12 rows:" in code_prompt
    assert "- month: 12 values, for instance '2025-01'" in code_prompt
    assert "- total_eur: numbers from " in code_prompt
    assert "shape line" in code_prompt
    # The SQL was asked for by the plan, not by the chat agent.
    assert "Question: total spending per month in 2025" in respond.prompts["sql"][0]  # type: ignore[attr-defined]

    # A reload shows the same card and the same narration, in the same order.
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    parts = detail["messages"][-1]["parts"]
    assert [p["type"] for p in parts] == ["tool-chart", "reasoning", "text", "data-context", "data-followups"]
    assert parts[0]["output"]["code"] == LINE_CODE
    assert parts[0]["output"]["rows"] == output["rows"]
    assert "Self-check passed." in parts[1]["text"]


async def test_a_chart_that_names_an_unknown_column_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    broken = LINE_CODE.replace("y: 'total_eur'", "y: 'spent'")
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[broken, LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Diagramm bitte.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == LINE_CODE
    assert len(output["notes"]) == 1
    assert 'reads the column "spent"' in output["notes"][0]
    assert "Repair 1 of 2" in output["notes"][0]
    # The finding and the refused code went back to the sub-agent, and only then came the repair.
    prompts = respond.prompts["code"]  # type: ignore[attr-defined]
    assert len(prompts) == 2
    assert 'reads the column "spent" in its `y` channel' in prompts[1]
    assert "y: 'spent'" in prompts[1]
    # The repair round is visible in the thinking panel.
    told = narration(chunks)
    assert 'reads the column "spent"' in told
    assert "Self-check passed after one repair." in told


async def test_a_chart_over_an_empty_column_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    # `category` exists but is NULL for every booking, so a chart keyed on it draws nothing.
    sql = (
        "SELECT strftime('%Y-%m', booked_on) AS month, category, ROUND(-SUM(amount), 2) AS total_eur "
        "FROM transaction_view WHERE amount_cents < 0 GROUP BY month ORDER BY month"
    )
    plan = {
        "shape": "bar",
        "title": "Ausgaben pro Monat",
        "question": "spending per month in 2025",
        "columns": ["month", "category", "total_eur"],
        "reason": "Bars per month read well.",
    }
    blind = BAR_CODE.replace("x: 'month'", "x: 'category'")
    respond = scripted_chart(plan=plan, sql=sql, codes=[blind, BAR_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Balken pro Monat bitte.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == BAR_CODE
    assert "is empty in every row" in output["notes"][0]
    # The repair round was told which columns do carry values.
    assert "The columns that carry values: month, total_eur." in respond.prompts["code"][1]  # type: ignore[attr-defined]


async def test_a_chart_that_never_passes_the_check_is_reported_without_a_chart(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=["return defineChart({ marks: [ }"])
    scripts.fast = ask_chart_then_report("spending per month in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Diagramm bitte.")

    output = chart_output(chunks)
    assert output["code"] is None
    assert "3 attempts failed the self-check" in output["error"]
    assert "does not compile" in output["error"]
    # One initial attempt and the two repair rounds.
    assert len(respond.prompts["code"]) == 3  # type: ignore[attr-defined]
    assert len(output["notes"]) == 3
    assert "Gave up after 3 attempts" in output["notes"][-1]
    # The rows are still there, so the assistant can answer in words.
    assert output["row_count"] == 12
    assert answer(chunks).startswith("I could not draw that:")


async def test_a_doughnut_with_too_many_slices_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_chart(
        plan=DOUGHNUT_PLAN, sql=MERCHANTS_SQL, codes=[DOUGHNUT_CODE, FOLDED_DOUGHNUT_CODE]
    )
    scripts.fast = ask_chart_then_report("the largest merchants in 2025 as a doughnut")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig die groessten Haendler als Donut.")

    output = chart_output(chunks)
    assert output["row_count"] == 7
    assert output["error"] is None
    assert output["code"] == FOLDED_DOUGHNUT_CODE
    assert "A doughnut shows at most 6 slices and this one has 7." in output["notes"][0]


async def test_a_stacked_chart_becomes_plain_bars_when_the_rows_carry_one_series(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    # `category` is NULL for every booking until ticket 07 categorizes, so the second dimension
    # the plan asked for does not exist in the rows.
    sql = (
        "SELECT strftime('%Y-%m', booked_on) AS month, category, ROUND(-SUM(amount), 2) AS total_eur "
        "FROM transaction_view WHERE amount_cents < 0 GROUP BY month, category ORDER BY month"
    )
    plan = {
        "shape": "bar_stacked",
        "title": "Ausgaben pro Monat und Kategorie",
        "question": "spending per month and category in 2025",
        "columns": ["month", "category", "total_eur"],
        "reason": "Stacked bars carry both dimensions.",
    }
    respond = scripted_chart(plan=plan, sql=sql, codes=[BAR_CODE])
    scripts.fast = ask_chart_then_report("spending per month and category in 2025 as stacked bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Kategorie bitte.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["shape"] == "bar", "an impossible series is downgraded instead of repaired"
    assert output["notes"] == [], "the downgrade happens before the code is written"
    assert "the shape becomes bar" in narration(chunks)
    # The code pass was asked for plain bars, so its example matches what it has to write.
    assert "shape bar," in respond.prompts["code"][0]  # type: ignore[attr-defined]
    # The query was told not to select a column that is NULL everywhere.
    assert "GROUP BY month, category" in respond.prompts["sql"][0]  # type: ignore[attr-defined]


# One statement per shape, over the shipped dataset, returning the columns that shape's worked
# example reads. `GROUP BY 1, 2` and not the aliases, because an alias that reuses a view column
# name (`category`) would bind to the view's own column.
SHAPE_SQL = {
    "line": MONTHLY_SQL,
    "area": (
        "SELECT strftime('%Y-%m', booked_on) AS month, ROUND(-SUM(amount), 2) AS cumulative_eur "
        "FROM transaction_view WHERE amount_cents < 0 GROUP BY 1 ORDER BY 1"
    ),
    "bar": (
        "SELECT CASE WHEN amount_cents < -20000 THEN 'Gross' ELSE 'Klein' END AS category, "
        "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
        "GROUP BY 1 ORDER BY 2 DESC"
    ),
    "bar_horizontal": MERCHANTS_SQL,
    "bar_grouped": (
        "SELECT strftime('%Y-%m', booked_on) AS month, "
        "CASE WHEN amount_cents < -20000 THEN 'Gross' ELSE 'Klein' END AS category, "
        "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
        "GROUP BY 1, 2 ORDER BY 1"
    ),
    "doughnut": MERCHANTS_SQL.replace("LIMIT 7", "LIMIT 6"),
    "sankey": (
        "SELECT 'Einkommen' AS source, "
        "CASE WHEN amount_cents < -20000 THEN 'Wohnen' ELSE 'Alltag' END AS target, "
        "ROUND(-SUM(amount), 2) AS amount_eur FROM transaction_view WHERE amount_cents < 0 "
        "GROUP BY 1, 2"
    ),
}
SHAPE_SQL["bar_stacked"] = SHAPE_SQL["bar_grouped"]


async def test_every_worked_example_in_the_prompt_passes_the_check(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The few-shot examples are the contract: what the prompt teaches has to pass the rules.

    Each example is written for the columns named in its first line, so the scripted statement
    returns those columns from the shipped dataset and the code is the example itself. The
    examples are read from the prompt rather than copied here, because a copy could pass while
    the prompt taught something the check refuses.
    """
    await import_synthetic(client, profile_id)
    for shape, example in EXAMPLES.items():
        columns, code = example.split("\n", 1)
        plan = {
            "shape": shape,
            "title": f"Beispiel {shape}",
            "question": f"the {shape} example",
            "columns": [name.strip() for name in columns.removeprefix("Columns:").split(",")],
            "reason": "The worked example.",
        }
        respond = scripted_chart(plan=plan, sql=SHAPE_SQL[shape], codes=[code])
        scripts.fast = ask_chart_then_report(f"the {shape} example")
        scripts.fast_call = respond  # type: ignore[assignment]
        conversation_id = await new_conversation(client, profile_id)

        _, chunks = await chat(conversation_id, f"Zeig das Beispiel {shape}.")

        output = chart_output(chunks)
        assert output["error"] is None, f"{shape}: {output['error']}"
        assert output["notes"] == [], f"{shape} needed a repair: {output['notes']}"
        assert output["shape"] == shape, f"{shape} was not drawn as planned"
        assert output["code"] == code


async def test_an_empty_profile_gets_no_chart_and_calls_no_sub_agent(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    def never(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        assert is_followup_request(messages), "the chart sub-agent must not run without data"
        return ModelResponse(parts=[TextPart(content="No follow-ups.")])

    scripts.fast = ask_chart_then_report("spending per month")
    scripts.fast_call = never  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig mir ein Diagramm.")

    # The chat model, the follow-up step and the distillation pass: no sub-agent.
    assert scripts.resolved == ["fast", "fast", "fast"]
    output = chart_output(chunks)
    assert output["code"] is None
    assert output["sql"] is None
    assert "no transactions yet" in output["error"]
    assert not any(character.isdigit() for character in answer(chunks))


# --------------------------------------------------------------------------- rows that cannot be drawn

STACKED_PLAN = {
    "shape": "bar_stacked",
    "title": "Ausgaben pro Monat und Kategorie",
    "question": "spending per month and category in 2025",
    "columns": ["month", "topic", "total_eur"],
    "reason": "Stacked bars carry both dimensions.",
}

# Two rows for the same month and topic, which is what a UNION of real and guessed categories
# produced in the review of 2026-09-04 and what made TanStack throw "A stack requires at most
# one value for each position and series".
DUPLICATE_PAIRS_SQL = (
    "SELECT strftime('%Y-%m', booked_on) AS month, 'Groceries' AS topic, "
    "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 GROUP BY 1 "
    "UNION ALL "
    "SELECT strftime('%Y-%m', booked_on) AS month, 'Groceries' AS topic, "
    "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 GROUP BY 1"
)

SANKEY_PLAN = {
    "shape": "sankey",
    "title": "Geldfluss 2025",
    "question": "the flow from income into the spending groups in 2025",
    "columns": ["source", "target", "amount_eur"],
    "reason": "A flow reads as a sankey.",
}

# Einkommen -> Wohnen and Wohnen -> Einkommen: the layout reports that as "circular link".
CIRCULAR_SANKEY_SQL = (
    "SELECT 'Einkommen' AS source, 'Wohnen' AS target, ROUND(-SUM(amount), 2) AS amount_eur "
    "FROM transaction_view WHERE amount_cents < 0 "
    "UNION ALL "
    "SELECT 'Wohnen' AS source, 'Einkommen' AS target, ROUND(SUM(amount), 2) AS amount_eur "
    "FROM transaction_view WHERE amount_cents > 0"
)


async def test_duplicate_pairs_stop_a_stacked_chart_before_any_code_is_written(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A stack needs one figure per position and series, and no repair round can fold two rows."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=STACKED_PLAN, sql=DUPLICATE_PAIRS_SQL, codes=[BAR_CODE])
    scripts.fast = ask_chart_then_report("spending per month and category in 2025 as stacked bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Kategorie bitte.")

    output = chart_output(chunks)
    assert output["code"] is None
    assert output["rendered"] is False
    assert "12 pairs of month and topic more than once" in output["error"]
    assert "2025-01 / Groceries" in output["error"]
    # No code pass at all: the rows decided it.
    assert respond.prompts["code"] == []  # type: ignore[attr-defined]
    # The rows are still on the card, so the answer can quote them.
    assert output["row_count"] == 24
    assert answer(chunks).startswith("I could not draw that:")
    assert "12 pairs of month and topic more than once" in narration(chunks)


async def test_a_circular_flow_stops_a_sankey_before_any_code_is_written(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=SANKEY_PLAN, sql=CIRCULAR_SANKEY_SQL, codes=[EXAMPLES["sankey"].split("\n", 1)[1]])
    scripts.fast = ask_chart_then_report("the money flow in 2025 as a sankey")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig den Geldfluss 2025 als Sankey.")

    output = chart_output(chunks)
    assert output["code"] is None
    assert output["rendered"] is False
    assert "circular flow (Einkommen -> Wohnen -> Einkommen)" in output["error"]
    assert respond.prompts["code"] == []  # type: ignore[attr-defined]
    assert answer(chunks).startswith("I could not draw that:")


async def test_a_drawn_chart_says_it_is_rendered_and_tells_the_model_to_write_text(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig mir die Ausgaben pro Monat als Diagramm.")

    output = chart_output(chunks)
    assert output["rendered"] is True
    # The tool result is the last thing the model reads before it answers, so the instruction
    # that a chart turn ends with text is on it.
    assert "Write your answer as text now" in output["summary"]


async def test_a_doughnut_whose_rest_slice_holds_the_majority_says_so_in_its_title(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A "Rest" slice with most of the money carries no information, so the caption admits it."""
    await import_synthetic(client, profile_id)
    sql = (
        "SELECT 'Rest' AS merchant, ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view "
        "WHERE amount_cents < 0 AND amount_cents < -5000 "
        "UNION ALL "
        "SELECT 'Kleinkram' AS merchant, ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view "
        "WHERE amount_cents < 0 AND amount_cents >= -5000"
    )
    respond = scripted_chart(plan=DOUGHNUT_PLAN, sql=sql, codes=[DOUGHNUT_CODE])
    scripts.fast = ask_chart_then_report("the largest merchants in 2025 as a doughnut")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig die groessten Haendler als Donut.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["title"].startswith("Anteil der Haendler (")
    assert output["title"].endswith("% in the rest slice)")
    assert "One slice holds 71 % of the total" in narration(chunks)


# --------------------------------------------------------------------------- the browser refuses one

async def test_a_chart_the_browser_could_not_draw_is_recorded_and_drawn_once_more(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The frame's error reaches the turn, and one retry replaces the card when it renders.

    The self-check judges intent against a stub, so a real layout can still throw. What must
    never happen is the transcript keeping a chart that was never on screen.
    """
    await import_synthetic(client, profile_id)
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Zeig mir die Ausgaben pro Monat als Diagramm.")
    turn_id, chart_call = turn_of(chunks), tool_call_of(chunks, "chart")
    assert chart_output(chunks)["rendered"] is True

    # The card reports what the frame said, and the server draws the same request again.
    redrawn = LINE_CODE.replace("strokeWidth: 2.25", "strokeWidth: 3")
    second = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[redrawn])
    scripts.fast_call = second  # type: ignore[assignment]
    response = await client.post(
        "/api/charts/render-failure",
        json={
            "profile_id": profile_id,
            "turn_id": turn_id,
            "tool_call_id": chart_call,
            "message": "TypeError: A stack requires at most one value for each position and series",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retried"] is True
    assert body["chart"]["code"] == redrawn
    assert body["chart"]["rendered"] is True

    # The turn now carries the chart that really drew, in both message families.
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    part = next(p for p in detail["messages"][-1]["parts"] if p["type"] == "tool-chart")
    assert part["output"]["code"] == redrawn
    assert len(detail["messages"]) == 2, "a retry adds no turn to the transcript"

    # And that is the one retry this chart gets: what a retry drew is not retried again.
    def never(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise AssertionError("one retry per chart, whether or not the first one drew")

    scripts.fast_call = never  # type: ignore[assignment]
    again = (
        await client.post(
            "/api/charts/render-failure",
            json={
                "profile_id": profile_id,
                "turn_id": turn_id,
                "tool_call_id": chart_call,
                "message": "Error: circular link",
            },
        )
    ).json()
    assert again["retried"] is False
    assert again["chart"]["rendered"] is False


async def test_a_second_failure_is_recorded_without_a_second_retry(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """One automatic retry, ever. A retry that fails too leaves an honest failed card."""
    await import_synthetic(client, profile_id)
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Zeig mir die Ausgaben pro Monat als Diagramm.")
    turn_id, chart_call = turn_of(chunks), tool_call_of(chunks, "chart")

    body = {
        "profile_id": profile_id,
        "turn_id": turn_id,
        "tool_call_id": chart_call,
        "message": "Error: circular link",
    }
    # The retry writes code that does not compile, so it fails the self-check three times.
    failing = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=["return defineChart({ marks: [ }"])
    scripts.fast_call = failing  # type: ignore[assignment]
    first = (await client.post("/api/charts/render-failure", json=body)).json()
    assert first["retried"] is False
    assert first["chart"]["code"] is None
    assert first["chart"]["rendered"] is False
    assert "circular link" in first["chart"]["error"]
    assert first["chart"]["rows"], "the rows stay on the card so the answer can quote them"

    def never(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        raise AssertionError("a chart is retried once, not once per report")

    scripts.fast_call = never  # type: ignore[assignment]
    again = (await client.post("/api/charts/render-failure", json=body)).json()
    assert again["retried"] is False
    assert again["chart"]["rendered"] is False

    # The stored turn says so too, so a reload shows the failure and never the drawing.
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    part = next(p for p in detail["messages"][-1]["parts"] if p["type"] == "tool-chart")
    assert part["output"]["code"] is None
    assert part["output"]["rendered"] is False


async def test_another_profile_cannot_report_a_render_failure(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    other = (await client.post("/api/profiles", json={"name": "Haushalt"})).json()
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Zeig mir die Ausgaben pro Monat als Diagramm.")

    refused = await client.post(
        "/api/charts/render-failure",
        json={
            "profile_id": other["id"],
            "turn_id": turn_of(chunks),
            "tool_call_id": tool_call_of(chunks, "chart"),
            "message": "Error: circular link",
        },
    )
    assert refused.status_code == 404, refused.text
