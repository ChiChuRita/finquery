"""Drawing a chart: the plan, the query behind it, the self-check and the repairs.

Every test drives the chat endpoint. The chat model is scripted to call the `chart` tool and
then to report what came back, and the fast slot behind the tool answers three different forced
single tools (the plan, the SQL, the code) plus the post-turn follow-up step.
"""

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from finquery.chart.selfcheck import RULE_VALUE, check_chart_code
from finquery.chart.shapes import SHAPE_NAMES
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

# The set the chart quality pass is measured on, in the repo so a later run is the same run.
BENCHMARK = Path(__file__).resolve().parents[1] / "fixtures" / "chart-benchmark.json"

# What the code pass fills its `reasoning` field with before it writes a line of code.
CODE_REASONING = "the shape is a line, so lineY\nthe columns are month and total_eur"

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
    "language": "de",
    "title": "Ausgaben pro Monat",
    "question": "total spending per month in 2025",
    "columns": ["month", "total_eur"],
    "reasoning": "A month series reads best as a line.",
}

DOUGHNUT_PLAN = {
    "shape": "doughnut",
    "language": "de",
    "title": "Anteil der Haendler",
    "question": "the seven largest merchants by spending in 2025",
    "columns": ["merchant", "total_eur"],
    "reasoning": "A share of a whole reads as a doughnut.",
}

LINE_CODE = """\
const amounts = data.map((row) => row.total_eur);
return defineChart({
  marks: [lineY(data, { x: 'month', y: 'total_eur', stroke: palette[0], strokeWidth: 2.25 })],
  scales: {
    x: { scale: () => scalePoint().padding(0.06), axis: { ticks: { format: monthShort } } },
    y: {
      scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)]),
      nice: true,
      grid: true,
      axis: { ticks: { format: eurShort } },
    },
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


def ask_chart_then_report(request: str, keep: bool = False):
    """A chat turn that calls `chart` and then reports what the tool returned.

    `keep` is the agent's own decision about a chart worth tracking (ticket 44), so a test that
    wants a kept chart scripts the same call the model would make.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        result = _last_chart_return(messages)
        if result is None:
            arguments: dict[str, object] = {"request": request}
            if keep:
                arguments["keep"] = True
            yield {0: DeltaToolCall(name="chart", json_args=json.dumps(arguments))}
            return
        if result["error"]:
            yield f"I could not draw that: {result['error']}"
        else:
            kept = " It is on your dashboard." if result.get("kept") else ""
            yield f"Here is {result['title']} ({result['shape']}) over {result['row_count']} rows.{kept}"

    return fn


def ask_charts_then_echo(requests: Sequence[str]):
    """One chart turn per request, each answering with the tool's own `summary`.

    Echoing the summary is how a test reads what the model was handed before it wrote a word
    about the picture.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        result = _last_chart_return(messages)
        if result is None:
            asked = sum(
                1 for message in messages for part in message.parts if part.part_kind == "user-prompt"
            )
            request = requests[min(asked, len(requests)) - 1]
            yield {0: DeltaToolCall(name="chart", json_args=json.dumps({"request": request}))}
            return
        yield str(result["summary"])

    return fn


def scripted_charts(specs: Sequence[tuple[dict[str, object], str, str]]):
    """The fast slot behind several chart turns in one conversation: one spec per turn."""
    prompts: dict[str, list[str]] = {"plan": [], "sql": [], "code": []}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="No follow-ups.")])
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        name = info.output_tools[0].name
        prompt = _last_user_prompt(messages)
        if name == "chart_plan":
            prompts["plan"].append(prompt)
            return ModelResponse(parts=[ToolCallPart("chart_plan", json.dumps(specs[len(prompts["plan"]) - 1][0]))])
        turn = max(len(prompts["plan"]) - 1, 0)
        if name == "run_sql":
            prompts["sql"].append(prompt)
            written = {"reasoning": "as the plan asks", "sql": specs[turn][1]}
            return ModelResponse(parts=[ToolCallPart("run_sql", json.dumps(written))])
        if name == "chart_code":
            prompts["code"].append(prompt)
            return ModelResponse(
                parts=[ToolCallPart("chart_code", json.dumps({"reasoning": CODE_REASONING, "code": specs[turn][2]}))]
            )
        raise AssertionError(f"unexpected forced tool {name}")

    respond.prompts = prompts  # type: ignore[attr-defined]
    return respond


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
            written = {"reasoning": "as the plan asks", "sql": sql}
            return ModelResponse(parts=[ToolCallPart("run_sql", json.dumps(written))])
        if name == "chart_code":
            prompts["code"].append(prompt)
            code = codes[min(len(prompts["code"]), len(codes)) - 1]
            return ModelResponse(
                parts=[ToolCallPart("chart_code", json.dumps({"reasoning": CODE_REASONING, "code": code}))]
            )
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


async def test_a_repair_round_shows_the_previous_answer_and_asks_for_a_correction(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A repair is a correction of an answer, not a fresh request (ticket 42).

    The second prompt has to carry the reasoning and the code of the first answer, the finding
    in the check's own words, and the instruction to say what changed. Three rounds of "it
    failed, write it again" produced the same finding three times on 2026-09-05.
    """
    await import_synthetic(client, profile_id)
    broken = LINE_CODE.replace("y: 'total_eur'", "y: 'spent'")
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[broken, LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Diagramm bitte.")

    repair = respond.prompts["code"][1]  # type: ignore[attr-defined]
    assert "Your last answer did not pass the check." in repair
    assert f"Your reasoning was:\n{CODE_REASONING}" in repair
    assert broken in repair
    assert 'reads the column "spent" in its `y` channel' in repair
    assert "The first line of the reasoning says what you changed and why" in repair
    # The reasoning of each attempt is narrated, so the panel shows what the model committed to.
    assert narration(chunks).count("the columns are month and total_eur") == 2


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
        "language": "de",
        "title": "Ausgaben pro Monat",
        "question": "spending per month in 2025",
        "columns": ["month", "category", "total_eur"],
        "reasoning": "Bars per month read well.",
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


async def test_a_doughnut_with_too_many_slices_is_folded_in_code(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Seven rows for six slices: the smallest two become one rest slice before any code runs.

    Folding is arithmetic, so it is not left to a repair round (the local fast model lost a
    twelve-category doughnut three rounds running). The first code passes, the rows the card
    shows are the rows the chart drew, and the fold is narrated in the request's language.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=DOUGHNUT_PLAN, sql=MERCHANTS_SQL, codes=[DOUGHNUT_CODE])
    scripts.fast = ask_chart_then_report("the largest merchants in 2025 as a doughnut")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig die groessten Haendler als Donut.")

    output = chart_output(chunks)
    assert output["row_count"] == 6
    assert output["error"] is None
    assert output["code"] == DOUGHNUT_CODE
    assert output["notes"] == []
    assert len(respond.prompts["code"]) == 1  # type: ignore[attr-defined]
    kept, rest = output["rows"][:-1], output["rows"][-1]
    assert rest["merchant"] == "Sonstige" and rest["total_eur"] > 0
    # The five largest stay, in order; the rest slice holds the two smallest, so it is under them.
    assert [row["total_eur"] for row in kept] == sorted((row["total_eur"] for row in kept), reverse=True)
    assert rest["total_eur"] < 2 * kept[-1]["total_eur"]
    assert "The query returned 7 slices and a doughnut shows 6, so the 2 smallest are one 'Sonstige' slice." in narration(chunks)
    # The figures the answer quotes are written the German way, rest slice included.
    assert output["figures"][-1].startswith("merchant Sonstige, total_eur ")
    assert output["figures"][-1].endswith(" EUR") and "," in output["figures"][-1]


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
        "language": "de",
        "title": "Ausgaben pro Monat und Kategorie",
        "question": "spending per month and category in 2025",
        "columns": ["month", "category", "total_eur"],
        "reasoning": "Stacked bars carry both dimensions.",
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


# One statement per set of columns a worked example was written for, over the shipped dataset.
# `GROUP BY 1, 2` and not the aliases, because an alias that reuses a view column name
# (`category`) would bind to the view's own column.
EXAMPLE_SQL = {
    # The area example over quarters: a name axis, not a period one.
    "quarter, total_eur": (
        "SELECT '2025-Q' || ((CAST(strftime('%m', booked_on) AS INTEGER) - 1) / 3 + 1) AS quarter, "
        "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
        "GROUP BY 1 ORDER BY 1"
    ),
    # The line example that carries a series: one row per month and shop, five shops.
    "month, merchant, total_eur": (
        "SELECT strftime('%Y-%m', booked_on) AS month, counterparty AS merchant, "
        "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
        "AND (counterparty LIKE 'REWE%' OR counterparty LIKE 'EDEKA%' OR counterparty "
        "LIKE 'LIDL%' OR counterparty LIKE 'ALDI%' OR counterparty LIKE 'dm %') "
        "GROUP BY 1, 2 ORDER BY 1, 2"
    ),
    # The area example with two series: a running total inside each half of the year, the half
    # as the series and the month of that half as the position.
    "month_of_half, half, cumulative_eur": (
        "WITH monthly AS (SELECT CASE WHEN booked_on < '2025-07-01' THEN 'Erstes Halbjahr' "
        "ELSE 'Zweites Halbjahr' END AS half, "
        "CAST(strftime('%m', booked_on) AS INTEGER) AS month_number, -SUM(amount) AS spent "
        "FROM transaction_view WHERE amount_cents < 0 GROUP BY 1, 2) "
        "SELECT CAST(CASE WHEN month_number > 6 THEN month_number - 6 ELSE month_number END AS TEXT) "
        "AS month_of_half, half, "
        "ROUND(SUM(spent) OVER (PARTITION BY half ORDER BY month_number), 2) AS cumulative_eur "
        "FROM monthly ORDER BY half, month_number"
    ),
    # The doughnut example over a column called `label`, which is not the one the first
    # doughnut example reads.
    "label, total_eur": (
        "SELECT CASE WHEN amount_cents < -20000 THEN 'Gross' ELSE 'Klein' END AS label, "
        "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
        "GROUP BY 1 ORDER BY 2 DESC"
    ),
}

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
        "CASE WHEN amount_cents < -20000 THEN 'Gross' ELSE 'Klein' END AS topic, "
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

    Every example of every shape, the second one of a hard shape included. Each is written for
    the columns it names, so the scripted statement returns those columns from the shipped
    dataset and the code is the example itself. The examples are read from the prompt rather
    than copied here, because a copy could pass while the prompt taught something the check
    refuses.
    """
    await import_synthetic(client, profile_id)
    written = 0
    for shape, examples in EXAMPLES.items():
        for example in examples:
            sql = EXAMPLE_SQL.get(example.columns) or SHAPE_SQL[shape]
            plan = {
                "shape": shape,
                "language": "de",
                "title": f"Beispiel {shape}",
                "question": f"the {shape} example",
                "columns": [name.strip() for name in example.columns.split(",")],
                "reasoning": "The worked example.",
            }
            respond = scripted_chart(plan=plan, sql=sql, codes=[example.code])
            scripts.fast = ask_chart_then_report(f"the {shape} example")
            scripts.fast_call = respond  # type: ignore[assignment]
            conversation_id = await new_conversation(client, profile_id)

            _, chunks = await chat(conversation_id, f"Zeig das Beispiel {shape}.")

            output = chart_output(chunks)
            assert output["error"] is None, f"{shape} ({example.columns}): {output['error']}"
            assert output["notes"] == [], f"{shape} ({example.columns}) needed a repair: {output['notes']}"
            assert output["shape"] == shape, f"{shape} was not drawn as planned"
            assert output["code"] == example.code
            written += 1
    assert written == sum(len(examples) for examples in EXAMPLES.values()) >= len(SHAPE_NAMES)


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
    "language": "de",
    "title": "Ausgaben pro Monat und Kategorie",
    "question": "spending per month and category in 2025",
    "columns": ["month", "topic", "total_eur"],
    "reasoning": "Stacked bars carry both dimensions.",
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
    "language": "de",
    "title": "Geldfluss 2025",
    "question": "the flow from income into the spending groups in 2025",
    "columns": ["source", "target", "amount_eur"],
    "reasoning": "A flow reads as a sankey.",
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
    respond = scripted_chart(plan=SANKEY_PLAN, sql=CIRCULAR_SANKEY_SQL, codes=[EXAMPLES["sankey"][0].code])
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


# "Show me where my income goes as a sankey" asked plainly returned the year's total as
# Einkommen to Einkommen beside the real flows (end-to-end test of 2026-09-05), and one row
# refused the whole graph.
SELF_LOOP_SANKEY_SQL = (
    "SELECT 'Einkommen' AS source, 'Einkommen' AS target, ROUND(SUM(amount), 2) AS amount_eur "
    "FROM transaction_view WHERE amount_cents > 0 "
    "UNION ALL "
    "SELECT 'Einkommen' AS source, "
    "CASE WHEN amount_cents < -20000 THEN 'Wohnen' ELSE 'Alltag' END AS target, "
    "ROUND(-SUM(amount), 2) AS amount_eur FROM transaction_view WHERE amount_cents < 0 GROUP BY 2"
)


async def test_a_sankey_self_loop_is_left_out_instead_of_losing_the_chart(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A row from a name into itself is a total, not a flow, so it is dropped and narrated."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(
        plan=SANKEY_PLAN, sql=SELF_LOOP_SANKEY_SQL, codes=[EXAMPLES["sankey"][0].code]
    )
    scripts.fast = ask_chart_then_report("where my income goes in 2025 as a sankey")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig mir als Sankey, wohin mein Einkommen fliesst.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["rendered"] is True
    assert len(respond.prompts["code"]) == 1, "the self loop is dropped before the code pass"  # type: ignore[attr-defined]
    assert output["row_count"] == 2
    assert all(row["source"] != row["target"] for row in output["rows"])
    assert "One row flowed from Einkommen into itself" in narration(chunks)
    assert "2 flows are drawn" in narration(chunks)
    # Both prompts say it before the rows ever come back.
    assert "a flow into itself" in respond.prompts["plan"][0]  # type: ignore[attr-defined]
    assert "the same name in source and target" in respond.prompts["sql"][0]  # type: ignore[attr-defined]


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


# --------------------------------------------------------------------------- the house rules of ticket 25

CATEGORY_SQL = (
    "SELECT CASE WHEN amount_cents < -20000 THEN 'Wohnen und Nebenkosten' "
    "WHEN amount_cents < -5000 THEN 'Groessere Ausgaben' ELSE 'Alltag' END AS category, "
    "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
    "GROUP BY 1 ORDER BY 2 DESC"
)

CATEGORY_PLAN = {
    "shape": "bar",
    "language": "en",
    "title": "Spending per category",
    "question": "spending per category in 2025",
    "columns": ["category", "total_eur"],
    "reasoning": "One figure per category reads as bars.",
}

# The `bar` worked example, which names every category and tilts the long ones.
CATEGORY_CODE = EXAMPLES["bar"][0].code
# The same chart with the label rule dropped, so the layout is free to thin them away.
THINNED_CODE = CATEGORY_CODE.replace(
    "axis: { tickLabels: { rotate: tilt, thin: false } }", "axis: { tickLabels: { rotate: tilt } }"
)

# A line whose euro axis is inferred from the figures alone, so it starts wherever they do.
FLOATING_LINE_CODE = """\
return defineChart({
  marks: [lineY(data, { x: 'month', y: 'total_eur', stroke: palette[0], strokeWidth: 2.25 })],
  scales: {
    x: { scale: () => scalePoint().padding(0.06), axis: { ticks: { format: monthShort } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: { use: tooltip, format: (point) => eur(point.datum.total_eur) },
});"""

CUT_LINE_CODE = FLOATING_LINE_CODE.replace(
    "scale: scaleLinear,", "scale: scaleLinear().domain([2200, 2800]),"
)

FACTORY_LINE_CODE = FLOATING_LINE_CODE.replace(
    "scale: scaleLinear,",
    "scale: () => scaleLinear().domain([0, Math.max(...data.map((row) => row.total_eur))]),",
)


async def test_a_line_whose_euro_axis_does_not_start_at_zero_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A range of 2.200 to 2.800 EUR filling a whole card reads as a cliff (review 2026-09-04)."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[FLOATING_LINE_CODE, LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Linie bitte.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == LINE_CODE
    assert "The euro axis has to start at zero" in output["notes"][0]
    assert "Math.min(0, ...amounts)" in respond.prompts["code"][1]  # type: ignore[attr-defined]


async def test_a_domain_that_cuts_the_zero_baseline_off_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[CUT_LINE_CODE, LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Linie bitte.")

    output = chart_output(chunks)
    assert output["code"] == LINE_CODE
    assert "the domain [2200, 2800], which cuts the zero baseline off" in output["notes"][0]


async def test_a_domain_inside_a_factory_is_repaired_because_it_is_thrown_away(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """`() => scaleLinear().domain(...)` looks right and does nothing: the chart infers again."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[FACTORY_LINE_CODE, LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Linie bitte.")

    output = chart_output(chunks)
    assert output["code"] == LINE_CODE
    assert "configures a domain inside a zero-argument factory" in output["notes"][0]
    assert "without the `() =>`" in output["notes"][0]


async def test_a_category_axis_that_may_drop_labels_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Ten bars with eight labels leave two bars under blank space (review of 2026-09-04)."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=CATEGORY_PLAN, sql=CATEGORY_SQL, codes=[THINNED_CODE, CATEGORY_CODE])
    scripts.fast = ask_chart_then_report("spending per category in 2025 as bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Show me spending per category as bars.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == CATEGORY_CODE
    assert "Every bar is named by its own label and none may be dropped" in output["notes"][0]
    assert "tickLabels: { thin: false }" in output["notes"][0]
    assert "rotate: -28" in output["notes"][0], "names on the x axis also need a tilt"


async def test_a_month_axis_may_thin_its_labels(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The label rule is about names: Feb read off Jan and Mar is fine, a merchant is not."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Linie bitte.")

    output = chart_output(chunks)
    assert output["notes"] == []
    assert output["code"] == LINE_CODE


MANY_TOPICS_SQL = (
    "SELECT strftime('%Y-%m', booked_on) AS month, "
    "'Gruppe ' || (abs(amount_cents) % 8) AS topic, "
    "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
    "GROUP BY 1, 2 ORDER BY 1"
)

# Six groups over twelve months, which is what the query hint asks for: the ceiling, not over it.
SIX_TOPICS_SQL = (
    "SELECT strftime('%Y-%m', booked_on) AS month, "
    "'Gruppe ' || (abs(amount_cents) % 6) AS topic, "
    "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
    "GROUP BY 1, 2 ORDER BY 1"
)

STACKED_CODE = EXAMPLES["bar_stacked"][0].code

# The same stack, coloured by the month and the group together, so the code asks for a colour
# per bar segment however few groups the rows carry.
PAIR_COLOURED_CODE = STACKED_CODE.replace(
    "z: 'topic', color: (row) => short(row.topic)",
    "z: (row) => row.topic + ' ' + row.month, color: (row) => short(row.topic + ' ' + row.month)",
)


async def test_a_stacked_chart_folds_its_tail_into_one_group_in_code(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Seven groups over six colours: the app keeps the five largest and sums the rest.

    The query is asked for each group under its own name, because asking the statement to fold
    is what broke the stacked bars on 2026-09-05: it relabelled the small groups 'Other' while
    grouping by the month alone, so every month came back with several 'Other' rows and no
    definition could stack them. Folding is arithmetic, so it happens here, in one pass, and
    the rows the card shows are the rows the chart drew.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=STACKED_PLAN, sql=MANY_TOPICS_SQL, codes=[STACKED_CODE])
    scripts.fast = ask_chart_then_report("spending per month and group in 2025 as stacked bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Gruppe bitte.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["rendered"] is True
    assert output["code"] == STACKED_CODE
    assert len(respond.prompts["code"]) == 1, "the fold is arithmetic, not a repair round"  # type: ignore[attr-defined]

    rows = output["rows"]
    groups = {row["topic"] for row in rows}
    assert len(groups) == 6 and "Sonstige" in groups
    pairs = [(row["month"], row["topic"]) for row in rows]
    assert len(pairs) == len(set(pairs)), "one figure per month and group, which is what a stack needs"
    assert "The query returned 7 groups and a chart has 6 colours" in narration(chunks)
    assert "2 smallest are one 'Sonstige' group per month" in narration(chunks)

    # The tail is summed and not dropped: the folded rows still hold every euro the query
    # returned, which is this profile's whole spending.
    page = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()
    spent = -sum(row["amount_cents"] for row in page["rows"] if row["amount_cents"] < 0) / 100
    assert round(sum(row["total_eur"] for row in rows), 2) == round(spent, 2)

    # The statement was asked for one row per pair and for no fold of its own.
    statement = respond.prompts["sql"][0]  # type: ignore[attr-defined]
    assert "GROUP BY month, topic" in statement
    assert "never rename one to 'Other' or 'Sonstige'" in statement


async def test_a_stacked_plan_that_puts_the_euro_column_second_is_reordered(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """`month, total_eur, topic` made every reader take the euro column for the group.

    The query hint, the pair rule and the fold all read the three columns as position, group
    and figure, so the euro column goes last before the statement is even asked for.
    """
    await import_synthetic(client, profile_id)
    plan = {**STACKED_PLAN, "columns": ["month", "total_eur", "topic"]}
    respond = scripted_chart(plan=plan, sql=SIX_TOPICS_SQL, codes=[STACKED_CODE])
    scripts.fast = ask_chart_then_report("spending per month and group in 2025 as stacked bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Gruppe bitte.")

    output = chart_output(chunks)
    assert output["error"] is None and output["rendered"] is True
    assert "over month, topic, total_eur" in narration(chunks)
    statement = respond.prompts["sql"][0]  # type: ignore[attr-defined]
    assert "Return exactly these columns, in this order: month, topic, total_eur." in statement
    assert "GROUP BY month, topic" in statement


async def test_more_colours_than_the_palette_is_reported_but_still_drawn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Eleven categories over six colours painted two of them the same (review of 2026-09-05).

    The rows cannot ask for that any more, because the tail is folded before the code is
    written, but the code's own colour channel still can. The finding is not fatal: a chart
    whose seventh colour repeats still answers the question, and no chart at all does not, so
    after the last round it is shown with the note on it.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_chart(
        plan=STACKED_PLAN, sql=SIX_TOPICS_SQL, codes=[PAIR_COLOURED_CODE] * 3
    )
    scripts.fast = ask_chart_then_report("spending per month and group in 2025 as stacked bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Gruppe bitte.")

    output = chart_output(chunks)
    assert output["code"] == PAIR_COLOURED_CODE
    assert output["rendered"] is True
    assert "The palette holds 6 colours and this chart asks for 72" in output["notes"][0]
    assert "Shown with one rule unmet" in output["notes"][-1]


TWO_FIGURES_SQL = (
    "SELECT strftime('%Y-%m', booked_on) AS month, "
    "ROUND(SUM(CASE WHEN amount_cents > 0 THEN amount ELSE 0 END), 2) AS income_eur, "
    "ROUND(-SUM(CASE WHEN amount_cents < 0 THEN amount ELSE 0 END), 2) AS spending_eur "
    "FROM transaction_view GROUP BY 1 ORDER BY 1"
)

TWO_FIGURES_PLAN = {
    "shape": "bar",
    "language": "en",
    "title": "Income and spending per month",
    "question": "income and spending per month in 2025",
    "columns": ["month", "income_eur", "spending_eur"],
    "reasoning": "Two figures per month.",
}

TWO_MARKS_CODE = """\
return defineChart({
  marks: [
    barY(data, { x: 'month', y: 'income_eur', fill: palette[0], radius: 2, maxThickness: 32 }),
    barY(data, { x: 'month', y: 'spending_eur', fill: palette[1], radius: 2, maxThickness: 32 }),
  ],
  scales: {
    x: { scale: () => scaleBand().padding(0.2), axis: { ticks: { format: monthShort } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: { use: tooltip, format: (point) => eur(point.datum.income_eur) },
});"""

ONE_MARK_CODE = TWO_MARKS_CODE.replace(
    "    barY(data, { x: 'month', y: 'spending_eur', fill: palette[1], radius: 2, maxThickness: 32 }),\n",
    "",
)


async def test_two_marks_over_two_euro_columns_are_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Income drawn on top of spending stacks into a total nobody asked for (2026-09-05)."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(
        plan=TWO_FIGURES_PLAN, sql=TWO_FIGURES_SQL, codes=[TWO_MARKS_CODE, ONE_MARK_CODE]
    )
    scripts.fast = ask_chart_then_report("income and spending per month in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Chart my income and my spending per month in 2025.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == ONE_MARK_CODE
    assert "Two marks draw different euro columns (income_eur, spending_eur)" in output["notes"][0]
    assert "stack into a total nobody asked for" in output["notes"][0]


async def test_a_chart_that_was_not_drawn_tells_the_model_not_to_describe_one(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """`rendered: false` is the field, and the summary is the sentence it reads last."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=["return defineChart({ marks: [ }"])
    scripts.fast = ask_chart_then_report("spending per month in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Diagramm bitte.")

    output = chart_output(chunks)
    assert output["rendered"] is False
    assert "No chart is on screen." in output["summary"]
    assert "Do not describe a picture, a shape, an axis or a colour" in output["summary"]
    assert "Write your answer as text now." in output["summary"]
    # The reason is still its own field, so the card and the answer say the same thing.
    assert output["error"].startswith("The chart could not be drawn")


async def test_the_plan_carries_the_language_the_chart_is_written_in(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The frame writes its month labels in it, so it travels on the tool result."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=CATEGORY_PLAN, sql=CATEGORY_SQL, codes=[CATEGORY_CODE])
    scripts.fast = ask_chart_then_report("spending per category in 2025 as bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Show me spending per category as bars.")

    output = chart_output(chunks)
    assert output["language"] == "en"
    assert output["title"] == "Spending per category"



CONFIGURED_LINE_CODE = FLOATING_LINE_CODE.replace(
    "scale: scaleLinear,", "scale: scaleLinear().nice(true),"
)

CONFIGURED_BAND_CODE = LINE_CODE.replace(
    "scale: () => scalePoint().padding(0.06)", "scale: scalePoint().padding(0.06)"
)


async def test_a_configured_scale_with_no_domain_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """`scaleLinear()` keeps its own default of 0 to 1, so every bar filled the plot (2026-09-05)."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[CONFIGURED_LINE_CODE, LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Linie bitte.")

    output = chart_output(chunks)
    assert output["code"] == LINE_CODE
    assert "is a configured scale with no domain" in output["notes"][0]
    assert "keeps the scale's own default of 0 to 1" in output["notes"][0]


async def test_a_configured_category_scale_with_no_domain_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The same trap on the other axis: a band with no domain has no categories to place."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[CONFIGURED_BAND_CODE, LINE_CODE])
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat als Linie bitte.")

    output = chart_output(chunks)
    assert output["code"] == LINE_CODE
    assert "`scales.x` is a configured scale with no domain" in output["notes"][0]
    assert "pass the factory itself" in output["notes"][0]


# The stack whose axis was capped at the largest single segment, so every bar was clipped at
# the top of the plot (2026-09-05).
CAPPED_STACK_CODE = STACKED_CODE.replace(
    "y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },",
    "y: {\n"
    "      scale: scaleLinear().domain([0, Math.max(...data.map((row) => row.total_eur))]),\n"
    "      nice: true,\n"
    "      grid: true,\n"
    "      axis: { ticks: { format: eurShort } },\n"
    "    },",
)


async def test_a_stack_may_not_name_its_own_euro_domain(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A stack is taller than any one of its values, so a domain over the rows clips every bar."""
    await import_synthetic(client, profile_id)
    assert CAPPED_STACK_CODE != STACKED_CODE
    respond = scripted_chart(
        plan=STACKED_PLAN, sql=SIX_TOPICS_SQL, codes=[CAPPED_STACK_CODE, STACKED_CODE]
    )
    scripts.fast = ask_chart_then_report("spending per month and group in 2025 as stacked bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Gruppe bitte.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == STACKED_CODE
    assert "takes the bare factory `scale: scaleLinear` and names no domain" in output["notes"][0]
    assert "caps the axis below a stack's own total" in output["notes"][0]


# The UNION that forgot to select `source`, so every link had one end (2026-09-05).
HALF_FLOW_SQL = (
    "SELECT coalesce(category, 'Needs review') AS target, ROUND(-SUM(amount), 2) AS amount_eur "
    "FROM transaction_view WHERE amount_cents < 0 GROUP BY 1 "
    "UNION ALL "
    "SELECT 'Einkommen' AS target, ROUND(SUM(amount), 2) AS amount_eur "
    "FROM transaction_view WHERE amount_cents > 0"
)


async def test_a_flow_missing_one_end_stops_before_any_code_is_written(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Two columns cannot carry a link, and three code passes cannot invent the third."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(
        plan=SANKEY_PLAN, sql=HALF_FLOW_SQL, codes=[EXAMPLES["sankey"][0].code]
    )
    scripts.fast = ask_chart_then_report("the money flow in 2025 as a sankey")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig den Geldfluss 2025 als Sankey.")

    output = chart_output(chunks)
    assert output["code"] is None
    assert output["rendered"] is False
    assert "A flow needs three columns" in output["error"]
    assert "the query returned 2: target, amount_eur" in output["error"]
    assert respond.prompts["code"] == []  # type: ignore[attr-defined]
    # The rows are still on the card, so the answer can give the figures.
    assert output["row_count"] > 0


TWO_MONTHS_SQL = (
    "SELECT strftime('%Y-%m', booked_on) AS month, ROUND(-SUM(amount), 2) AS total_eur "
    "FROM transaction_view WHERE amount_cents < 0 "
    "AND strftime('%Y-%m', booked_on) IN ('2025-01', '2025-07') GROUP BY 1 ORDER BY 1"
)


async def test_two_periods_become_bars_instead_of_a_line_between_them(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A stroke from January to July says something about the five months in between."""
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=LINE_PLAN, sql=TWO_MONTHS_SQL, codes=[BAR_CODE])
    scripts.fast = ask_chart_then_report("spending in January and July 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Vergleiche Januar und Juli 2025.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["shape"] == "bar"
    assert output["notes"] == [], "the downgrade happens before the code is written"
    assert "2 points are a comparison and not a trend, so the shape becomes bar." in narration(chunks)
    # The code pass was asked for bars, so its worked example is the one it needs.
    assert "shape bar," in respond.prompts["code"][0]  # type: ignore[attr-defined]


# `z` names the groups and `color` gives back their index, so the bars are right and the legend
# reads "0" and "1" (2026-09-05).
NUMBERED_LEGEND_CODE = STACKED_CODE.replace(
    "color: (row) => short(row.topic)",
    "color: (row) => data.map((other) => other.topic).indexOf(row.topic)",
)


async def test_a_legend_labelled_by_index_instead_of_by_name_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Colour follows the entity, never its rank: a legend never reads 0 and 1."""
    await import_synthetic(client, profile_id)
    assert NUMBERED_LEGEND_CODE != STACKED_CODE
    respond = scripted_chart(
        plan=STACKED_PLAN, sql=SIX_TOPICS_SQL, codes=[NUMBERED_LEGEND_CODE, STACKED_CODE]
    )
    scripts.fast = ask_chart_then_report("spending per month and group in 2025 as stacked bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Gruppe bitte.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == STACKED_CODE
    assert "because the `color` channel gives back a number instead of a name" in output["notes"][0]


# A fold that relabels the small groups 'Other' without summing them: the query's rows are
# fine, the array the code hands the mark is not, and only the browser used to catch it.
RELABELLED_CODE = STACKED_CODE.replace(
    "const short = (name) => (name.length > 18 ? name.slice(0, 17) + '.' : name);",
    "const short = (name) => (name.length > 18 ? name.slice(0, 17) + '.' : name);\n"
    "const keep = ['Gruppe 0', 'Gruppe 1'];\n"
    "const folded = data.map((row) => ({ month: row.month, total_eur: row.total_eur, "
    "topic: keep.indexOf(row.topic) === -1 ? 'Other' : row.topic }));",
).replace("barY(data, {", "barY(folded, {")


async def test_a_fold_that_relabels_without_summing_is_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """TanStack throws "duplicate 2025-01 / Sonstiges" on it; the check says so first."""
    await import_synthetic(client, profile_id)
    assert RELABELLED_CODE != STACKED_CODE
    respond = scripted_chart(
        plan=STACKED_PLAN, sql=SIX_TOPICS_SQL, codes=[RELABELLED_CODE, STACKED_CODE]
    )
    scripts.fast = ask_chart_then_report("spending per month and group in 2025 as stacked bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Gruppe bitte.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == STACKED_CODE
    assert "of position and group more than once" in output["notes"][0]
    assert "not relabelling their rows" in output["notes"][0]


# A CASE that always falls through to its ELSE: seven categories, one name, seven bars stacked
# on a single band (2026-09-05).
ONE_NAME_SQL = (
    "SELECT 'Sonstiges' AS topic, ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view "
    "WHERE amount_cents < 0 GROUP BY strftime('%Y-%m', booked_on) ORDER BY 2 DESC"
)

ONE_NAME_PLAN = {
    "shape": "bar",
    "language": "de",
    "title": "Ausgaben nach Kategorie",
    "question": "spending per category in 2025",
    "columns": ["topic", "total_eur"],
    "reasoning": "One figure per category.",
}


async def test_rows_that_name_one_position_many_times_stop_before_any_code(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=ONE_NAME_PLAN, sql=ONE_NAME_SQL, codes=[CATEGORY_CODE])
    scripts.fast = ask_chart_then_report("spending per category in 2025 as bars")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben nach Kategorie als Balken bitte.")

    output = chart_output(chunks)
    assert output["code"] is None
    assert output["rendered"] is False
    assert "carry only 1 different values in topic" in output["error"]
    assert "Sonstiges" in output["error"]
    assert respond.prompts["code"] == []  # type: ignore[attr-defined]
    assert output["row_count"] == 12


# ------------------------------------------------------- the household questions of ticket 52

# "Compare this month with last month by category": the period is the series and the category is
# the position, so the rows come long the other way round from a month-by-category stack. The
# categories are a CASE here for the same reason as everywhere else in this file: the import
# endpoints categorize nothing.
PERIOD_COMPARE_SQL = (
    "SELECT CASE WHEN amount_cents < -20000 THEN 'Gross' ELSE 'Klein' END AS topic, "
    "CASE WHEN booked_on >= '2025-12-01' THEN 'Dieser Monat' ELSE 'Letzter Monat' END AS period, "
    "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
    "AND booked_on BETWEEN '2025-11-01' AND '2025-12-31' GROUP BY 1, 2 ORDER BY 1, 2"
)

PERIOD_COMPARE_PLAN = {
    "shape": "bar_grouped",
    "language": "de",
    "title": "Dieser Monat gegen letzten Monat",
    "question": "spending per category in this month and in last month",
    "columns": ["topic", "period", "total_eur"],
    "reasoning": "Two periods compared by category are two dimensions that cross.",
}

PERIOD_COMPARE_CODE = """\
return defineChart({
  marks: [
    barY(data, { x: 'topic', y: 'total_eur', z: 'period', color: 'period', layout: group({ padding: 0.12 }), maxThickness: 32 }),
  ],
  scales: {
    x: { scale: () => scaleBand().padding(0.2), axis: { tickLabels: { rotate: -28, thin: false } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.period + ' ' + point.datum.topic + ': ' + eur(point.datum.total_eur),
  },
});"""


async def test_a_period_comparison_draws_grouped_bars_with_the_period_as_the_series(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The grouped bar turned around, and the query hint that goes with it.

    Told to build its groups from `category`, the statement for "this month against last month"
    comes back grouped by the category twice and never carries a period at all, so the hint says
    the other thing when the series column names periods.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=PERIOD_COMPARE_PLAN, sql=PERIOD_COMPARE_SQL, codes=[PERIOD_COMPARE_CODE])
    scripts.fast = ask_chart_then_report("compare this month with last month by category")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Vergleiche diesen Monat mit dem letzten Monat nach Kategorie.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["notes"] == [], "the worked example needed no repair"
    assert output["shape"] == "bar_grouped"
    assert output["columns"] == ["topic", "period", "total_eur"]
    # One figure per category and period, both periods on both categories.
    assert {row["period"] for row in output["rows"]} == {"Dieser Monat", "Letzter Monat"}
    assert {row["topic"] for row in output["rows"]} == {"Gross", "Klein"}
    assert output["row_count"] == 4

    hint = respond.prompts["sql"][0]  # type: ignore[attr-defined]
    assert "`GROUP BY topic, period`" in hint
    assert "period names the two periods being compared" in hint
    assert "coalesce(category, 'Needs review') AS topic" in hint
    # Two periods are two colours, so the paragraph about folding a tail of groups is left out.
    assert "never put a LIMIT on the groups" not in hint


# "How much more or less than the month before": the one figure of this dataset that really
# crosses zero, so the bars are drawn on both sides of the baseline.
CHANGE_SQL = (
    "WITH monthly AS (SELECT strftime('%Y-%m', booked_on) AS month, -SUM(amount) AS spent "
    "FROM transaction_view WHERE amount_cents < 0 GROUP BY 1), "
    "stepped AS (SELECT month, spent, LAG(spent) OVER (ORDER BY month) AS before FROM monthly) "
    "SELECT month, ROUND(spent - before, 2) AS change_eur FROM stepped "
    "WHERE before IS NOT NULL ORDER BY month"
)

CHANGE_PLAN = {
    "shape": "bar",
    "language": "en",
    "title": "Change to the month before",
    "question": "the difference to the month before, per month of 2025, signed",
    "columns": ["month", "change_eur"],
    "reasoning": "A difference is signed, so the bars cross the zero line.",
}

CHANGE_CODE = """\
return defineChart({
  marks: [
    barY(data, { x: 'month', y: 'change_eur', fill: palette[0], maxThickness: 32 }),
  ],
  scales: {
    x: {
      scale: () => scaleBand().padding(0.26),
      axis: { ticks: { format: monthShort }, tickLabels: { thin: { minGap: 6, priority: 'ends' } } },
    },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => monthShort(point.datum.month) + ': ' + eur(point.datum.change_eur),
  },
});"""


async def test_a_signed_figure_per_month_is_drawn_as_bars_on_both_sides_of_zero(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Diverging bars need no rule of their own: a bar rests on zero and the sign does the rest.

    What this holds is that the check admits a euro column with both signs in it, over the real
    rows of the benchmark's own statement, and that the euro axis still names no domain.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=CHANGE_PLAN, sql=CHANGE_SQL, codes=[CHANGE_CODE])
    scripts.fast = ask_chart_then_report("how much more or less I spent than the month before")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Show me how much more or less I spent each month.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["notes"] == []
    assert output["shape"] == "bar"
    assert output["row_count"] == 11
    figures = [row["change_eur"] for row in output["rows"]]
    assert min(figures) < 0 < max(figures), "the chart this test is about is the one that crosses zero"
    assert output["code"] == CHANGE_CODE


# The reference line of ticket 52. These three run the check directly: what they are about is
# the rule and not the path, and the rows are the shape of the rows the monthly statement
# returns.
MONTHLY_ROWS = [
    {"month": "2025-01", "total_eur": 2544.04},
    {"month": "2025-02", "total_eur": 2265.34},
    {"month": "2025-03", "total_eur": 2290.77},
    {"month": "2025-04", "total_eur": 2264.74},
]

# The worked example itself, read from the prompt rather than copied, so a copy cannot pass
# while the prompt teaches something else.
RULE_EXAMPLE = EXAMPLES["line"][2]


async def test_a_reference_line_computed_from_the_rows_passes_the_check() -> None:
    assert "ruleY([mean(data, 'total_eur')])" in RULE_EXAMPLE.code
    result = await check_chart_code(RULE_EXAMPLE.code, MONTHLY_ROWS, "line")
    assert result.findings == ()


async def test_a_reference_line_with_a_typed_figure_is_refused() -> None:
    """The invariant, for the one mark that carries no channel: no figure is typed into a chart.

    Both ways of typing it: the value in the array the rule is given, and the value hidden in a
    name assigned above it. A width is not a figure, so the stroke options are left alone.
    """
    for typed in (
        "ruleY([2100])",
        "ruleY([2100], { strokeWidth: 1.5 })",
        "ruleY(data, { y: 2100 })",
    ):
        code = RULE_EXAMPLE.code.replace("ruleY([mean(data, 'total_eur')])", typed)
        result = await check_chart_code(code, MONTHLY_ROWS, "line")
        assert result.findings == (RULE_VALUE,), typed
        assert result.fatal, typed

    named = RULE_EXAMPLE.code.replace(
        "const amounts = data.map((row) => row.total_eur);",
        "const amounts = data.map((row) => row.total_eur);\nconst usual = 2100;",
    ).replace("ruleY([mean(data, 'total_eur')])", "ruleY([usual])")
    assert (await check_chart_code(named, MONTHLY_ROWS, "line")).findings == (RULE_VALUE,)

    # The same value under a name that really was computed from the rows is the right answer.
    computed = RULE_EXAMPLE.code.replace(
        "const amounts = data.map((row) => row.total_eur);",
        "const amounts = data.map((row) => row.total_eur);\nconst usual = mean(data, 'total_eur');",
    ).replace("ruleY([mean(data, 'total_eur')])", "ruleY([usual])")
    assert (await check_chart_code(computed, MONTHLY_ROWS, "line")).findings == ()


async def test_a_reference_line_on_a_doughnut_and_a_second_one_anywhere_are_refused() -> None:
    """A rule needs a euro axis to lie across, and one chart says one thing."""
    slices = [{"label": "Miete", "total_eur": 1050.0}, {"label": "Rest", "total_eur": 1494.04}]
    doughnut = EXAMPLES["doughnut"][1].code.replace(
        "  marks: [", "  marks: [\n    ruleY([mean(data, 'total_eur')]),"
    )
    findings = (await check_chart_code(doughnut, slices, "doughnut")).findings
    assert "`ruleY` does not belong in a doughnut chart. Remove that mark." in findings

    twice = RULE_EXAMPLE.code.replace(
        "ruleY([mean(data, 'total_eur')]),",
        "ruleY([mean(data, 'total_eur')]),\n    ruleY([Math.max(...data.map((row) => row.total_eur))]),",
    )
    findings = (await check_chart_code(twice, MONTHLY_ROWS, "line")).findings
    assert findings == ("A chart carries at most 1 reference line and this one draws 2. A rule "
                        "has no label of its own, so keep the one the request asks about, the "
                        "average or the limit, and drop the rest.",)


# --------------------------------------------------------------------------- two charts in a row

AREA_TURN_PLAN = {
    "shape": "area",
    "language": "en",
    "title": "Cumulative spending in 2025",
    "question": "cumulative spending per month in 2025",
    "columns": ["month", "cumulative_eur"],
    "reasoning": "A running total reads as an area.",
}

GROUPED_TURN_PLAN = {
    "shape": "bar_grouped",
    "language": "en",
    "title": "Large and small payments per month",
    "question": "large and small payments per month in 2025",
    "columns": ["month", "topic", "total_eur"],
    "reasoning": "Two groups side by side per month.",
}


async def test_the_second_chart_in_a_row_is_the_one_the_model_is_told_to_describe(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The prose under a grouped chart repeated the previous chart's answer (2026-09-05).

    The tool result is the last thing the model reads, so it names this chart and carries this
    chart's own figures: there is nothing left to reach back to an earlier turn for.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_charts(
        [
            (AREA_TURN_PLAN, SHAPE_SQL["area"], EXAMPLES["area"][0].code),
            (GROUPED_TURN_PLAN, SHAPE_SQL["bar_grouped"], EXAMPLES["bar_grouped"][0].code),
        ]
    )
    scripts.fast = ask_charts_then_echo(
        ["cumulative spending in 2025 as an area chart", "large against small payments per month in 2025"]
    )
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, first = await chat(conversation_id, "Show my cumulative spending in 2025 as an area chart.")
    _, second = await chat(conversation_id, "Now compare large and small payments per month as grouped bars.")

    one, two = chart_output(first), chart_output(second)
    assert (one["rendered"], two["rendered"]) == (True, True)
    assert one["title"] != two["title"]

    # The summary the model receives on the second turn names the second chart and carries its
    # own figures, and says the first one is not what it is writing about.
    assert two["title"] in two["summary"]
    assert one["title"] not in two["summary"]
    assert f'is a bar_grouped titled "{two["title"]}"' in two["summary"]
    assert "topic Gross" in two["summary"] and "topic Klein" in two["summary"]
    assert "Describe only this chart, never one from an earlier turn." in two["summary"]
    # And that is what the answer under the card was written from.
    assert two["title"] in answer(second) and one["title"] not in answer(second)


# ------------------------------------------------------- a line that carries several series

# The five grocery shops the shipped year really holds, which is the request ticket 50 was
# reported for: "spending at my five grocery stores per month" came back with one store.
# The bookings are imported here without the enrichment pass, so a shop is named by the text
# the bank wrote ("REWE Markt GmbH"), which is what `merchant` holds in every one of these rows.
FIVE_SHOPS = ("REWE", "EDEKA", "LIDL", "ALDI", "dm")

SHOPS_SQL = (
    "SELECT strftime('%Y-%m', booked_on) AS month, counterparty AS merchant, "
    "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
    "AND (counterparty LIKE 'REWE%' OR counterparty LIKE 'EDEKA%' OR counterparty LIKE 'LIDL%' "
    "OR counterparty LIKE 'ALDI%' OR counterparty LIKE 'dm %') GROUP BY 1, 2 ORDER BY 1, 2"
)

# Nine shops over twelve months: three more series than the palette has colours.
MANY_SHOPS_SQL = (
    "SELECT strftime('%Y-%m', booked_on) AS month, "
    "'Laden ' || (abs(amount_cents) % 9) AS merchant, "
    "ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
    "GROUP BY 1, 2 ORDER BY 1"
)

SHOPS_PLAN = {
    "shape": "line",
    "language": "de",
    "title": "Ausgaben pro Monat und Supermarkt",
    "question": "spending at the five grocery shops per month in 2025",
    "columns": ["month", "merchant", "total_eur"],
    "reasoning": "Five shops over twelve months are five lines.",
}

# The worked example of a line with a series, read from the prompt rather than copied.
SHOPS_CODE = EXAMPLES["line"][1].code


async def test_a_line_over_five_shops_draws_five_series_and_a_legend(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The chart the user asked for on 2026-09-06 and did not get.

    The shape catalogue had no multi-series line, so the check's "two marks draw different euro
    columns" finding made the repair loop drop every shop but one. One `lineY` with a `color`
    channel is the answer, and nothing here is a repair round.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_chart(plan=SHOPS_PLAN, sql=SHOPS_SQL, codes=[SHOPS_CODE])
    scripts.fast = ask_chart_then_report("spending at the five grocery shops per month in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig meine Ausgaben pro Monat bei Rewe, Edeka, Lidl, Aldi und dm als Linien.")

    output = chart_output(chunks)
    assert output["error"] is None and output["rendered"] is True
    assert output["shape"] == "line", "five shops over a year are still a line"
    assert output["code"] == SHOPS_CODE
    assert output["notes"] == [], "no repair round: a series on a line is not a finding"
    assert len(respond.prompts["code"]) == 1  # type: ignore[attr-defined]
    names = {row["merchant"] for row in output["rows"]}
    assert len(names) == 5, "five shops are five lines, and the fold leaves them alone"
    for shop in FIVE_SHOPS:
        assert any(name.upper().startswith(shop.upper()) for name in names), shop
    # One figure per month and shop, which is what one stroke per shop needs.
    pairs = [(row["month"], row["merchant"]) for row in output["rows"]]
    assert len(pairs) == len(set(pairs))
    # The legend is in the code the check admitted, because more than one series needs one.
    assert "colorLegend" in output["code"] and "color: 'merchant'" in output["code"]
    # And the statement was asked for the long rows a line with a series draws.
    statement = respond.prompts["sql"][0]  # type: ignore[attr-defined]
    assert "Return exactly these columns, in this order: month, merchant, total_eur." in statement
    assert "GROUP BY month, merchant" in statement
    assert "one per line of the chart" in statement
    # The stack's hint, which pushes the group towards the category column, is not this one's.
    assert "Build merchant from the `category` column" not in statement


async def test_a_line_over_more_shops_than_colours_leaves_the_smallest_out(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Nine shops over six colours: the three smallest go, and they are not summed into a line.

    The one fold that drops instead of summing. A seventh stroke holding the tail would be read
    as a shop nobody ever paid, so what the fold owes the user is the note naming what is gone.
    """
    await import_synthetic(client, profile_id)
    plan = {**SHOPS_PLAN, "question": "spending per month and shop in 2025"}
    respond = scripted_chart(plan=plan, sql=MANY_SHOPS_SQL, codes=[SHOPS_CODE])
    scripts.fast = ask_chart_then_report("spending per month and shop in 2025 as lines")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Ausgaben pro Monat und Laden als Linien bitte.")

    output = chart_output(chunks)
    assert output["error"] is None and output["rendered"] is True
    assert len(respond.prompts["code"]) == 1, "the fold is arithmetic, not a repair round"  # type: ignore[attr-defined]
    kept = {row["merchant"] for row in output["rows"]}
    assert len(kept) == 6
    assert "The query returned 9 series and a chart has 6 colours" in narration(chunks)
    assert "the 3 smallest are left out" in narration(chunks)
    assert "Nothing is summed into a rest line" in narration(chunks)
    # Dropped and not summed: the three smallest are named in the note and their euros are gone.
    dropped = narration(chunks).split("left out (")[1].split(")")[0].split(", ")
    assert len(dropped) == 3 and not (set(dropped) & kept)
    page = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()
    spent = -sum(row["amount_cents"] for row in page["rows"] if row["amount_cents"] < 0) / 100
    assert round(sum(row["total_eur"] for row in output["rows"]), 2) < round(spent, 2)


async def test_seven_lines_are_over_the_palette_and_the_check_says_so() -> None:
    """The ceiling is the palette, on a line exactly as on a stack, and it is polish.

    Seven strokes over six colours paints two shops the same, which is worth a note and not
    worth throwing the chart away for. The cure is the other one, though: a line has no tail to
    sum into, so the finding asks for the six largest and no seventh line.
    """
    rows = [
        {"month": f"2025-{month:02d}", "merchant": f"Laden {shop}", "total_eur": 10.0 + shop}
        for month in range(1, 4)
        for shop in range(7)
    ]
    result = await check_chart_code(SHOPS_CODE, rows, "line")
    assert result.findings == (
        "The palette holds 6 colours and this chart draws 7 of them, so two series would be "
        "painted the same. Draw the 6 largest series and leave the rest out: several series "
        "added into one more line is a line nobody spent that money at.",
    )
    assert not result.fatal, "a seventh colour still answers the question, so the chart is shown"


TWO_EURO_LINE_PLAN = {
    "shape": "line",
    "language": "en",
    "title": "Income and spending per month",
    "question": "income and spending per month in 2025",
    "columns": ["month", "income_eur", "spending_eur"],
    "reasoning": "Two figures per month.",
}

TWO_LINES_CODE = """\
const amounts = data.map((row) => row.income_eur);
return defineChart({
  marks: [
    lineY(data, { x: 'month', y: 'income_eur', stroke: palette[0], strokeWidth: 2 }),
    lineY(data, { x: 'month', y: 'spending_eur', stroke: palette[1], strokeWidth: 2 }),
  ],
  scales: {
    x: { scale: () => scalePoint().padding(0.06), axis: { ticks: { format: monthShort } } },
    y: {
      scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)]),
      nice: true,
      grid: true,
      axis: { ticks: { format: eurShort } },
    },
  },
  tooltip: { use: tooltip, format: (point) => eur(point.datum.income_eur) },
});"""

ONE_LINE_CODE = TWO_LINES_CODE.replace(
    "    lineY(data, { x: 'month', y: 'spending_eur', stroke: palette[1], strokeWidth: 2 }),\n", ""
)


async def test_two_euro_columns_on_a_line_with_no_series_are_still_repaired(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The finding that broke the five shops still holds where it was written for.

    Two strokes over two euro columns and no colour channel between them: nothing says which is
    which, so one of them is dropped. A line that carries a series is telling them apart and is
    not this case, which is the whole distinction ticket 50 turns on.
    """
    await import_synthetic(client, profile_id)
    respond = scripted_chart(
        plan=TWO_EURO_LINE_PLAN, sql=TWO_FIGURES_SQL, codes=[TWO_LINES_CODE, ONE_LINE_CODE]
    )
    scripts.fast = ask_chart_then_report("income and spending per month in 2025 as lines")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Draw my income and my spending per month as lines.")

    output = chart_output(chunks)
    assert output["error"] is None
    assert output["code"] == ONE_LINE_CODE
    assert "Two marks draw different euro columns (income_eur, spending_eur)" in output["notes"][0]
    # The euro columns were never mistaken for series names, so no month was folded away.
    assert output["row_count"] == 12

def test_the_chart_benchmark_set_covers_every_shape() -> None:
    """The set the quality pass is measured on: at least twenty prompts, both languages, all
    eight shapes, and every expected shape a shape this product can draw."""
    benchmark = json.loads(BENCHMARK.read_text())
    prompts = benchmark["prompts"]
    assert len(prompts) >= 20
    assert len({prompt["id"] for prompt in prompts}) == len(prompts)
    for prompt in prompts:
        assert prompt["shape"] in SHAPE_NAMES, prompt["id"]
        assert all(other in SHAPE_NAMES for other in prompt["also"]), prompt["id"]
        assert prompt["language"] in {"de", "en"}, prompt["id"]
        assert prompt["prompt"].strip(), prompt["id"]
    assert {prompt["shape"] for prompt in prompts} == set(SHAPE_NAMES)
    assert {prompt["language"] for prompt in prompts} == {"de", "en"}
