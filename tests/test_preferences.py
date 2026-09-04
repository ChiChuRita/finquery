"""Preference optimization: the thumbs, the two reruns, the picks and the export.

Every test drives the HTTP seam. A turn is streamed through the chat endpoint first, because a
rating names the turn it is about: the turn's id rides the message metadata, so the browser can
rate the answer it just watched and the same id is on the message after a reload.

The reruns behind a pair are endpoints of their own and no chat turn, so they cost the scripted
fast slot exactly what they run: the chart sub-agent plus its query, or one chat request.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo

from .conftest import (
    Chat,
    Scripts,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
    script,
    tool_call_of,
    turn_of,
)
from .test_categorization import call_tools
from .test_chart import LINE_CODE, LINE_PLAN, MONTHLY_SQL, ask_chart_then_report, scripted_chart
from .test_query import import_synthetic

SECOND_LINE_CODE = LINE_CODE.replace("strokeWidth: 2.25", "strokeWidth: 3").replace(
    "padding(0.06)", "padding(0.12)"
)
"""The same shape drawn a second time: what a regenerate produces, and what a pick chooses."""


def post_turn_only():
    """The fast slot for a turn that calls no sub-agent: follow-ups and the distillation pass."""

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        assert is_followup_request(messages), "this turn should call no sub-agent"
        return ModelResponse(parts=[TextPart(content="No follow-ups.")])

    return respond


async def rate(
    client: httpx.AsyncClient, profile_id: str, turn_id: str, rating: str, target: str | None = None
) -> dict[str, Any]:
    body = {"profile_id": profile_id, "turn_id": turn_id, "rating": rating, "target": target}
    response = await client.post("/api/preferences/rating", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def records_of(client: httpx.AsyncClient, profile_id: str) -> list[dict[str, Any]]:
    response = await client.get("/api/preferences", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return response.json()


async def exported(client: httpx.AsyncClient, profile_id: str) -> list[dict[str, Any]]:
    response = await client.get("/api/preferences/export", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines() if line]


async def detail_of(client: httpx.AsyncClient, conversation_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/conversations/{conversation_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_a_rating_on_an_answer_is_stored_and_shown_again_after_a_reload(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    scripts.fast = script("Im Mai waren es 412,50 EUR.", followups=["Und im Juni?"])
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Wie viel habe ich im Mai ausgegeben?")
    turn_id = turn_of(chunks)

    record = await rate(client, profile_id, turn_id, "up")
    assert record["kind"] == "answer"
    assert record["rating"] == "up"
    assert record["paired"] is False, "a thumb is one side, only a pick is a pair"
    assert record["prompt"] == "Wie viel habe ich im Mai ausgegeben?"
    assert record["model_slot"] == "fast"

    # The transcript carries the turn id, so the thumbs come back filled in after a reload.
    detail = await detail_of(client, conversation_id)
    assert detail["messages"][-1]["metadata"]["turn_id"] == turn_id
    assert detail["ratings"] == [{"turn_id": turn_id, "target": None, "kind": "answer", "rating": "up"}]

    # The record holds what the user actually read.
    lines = await exported(client, profile_id)
    assert len(lines) == 1
    assert lines[0]["kind"] == "answer"
    assert lines[0]["chosen"]["text"] == "Im Mai waren es 412,50 EUR."
    assert lines[0]["rejected"] is None


async def test_a_thumbs_down_stores_the_answer_as_the_rejected_side_and_replaces_the_thumb_before_it(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    scripts.fast = script("Das kann ich nicht beantworten.")
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Wie viel gebe ich fuer Abos aus?")
    turn_id = turn_of(chunks)

    await rate(client, profile_id, turn_id, "up")
    record = await rate(client, profile_id, turn_id, "down")

    assert record["rating"] == "down"
    # One click corrected, not two clicks logged.
    assert len(await records_of(client, profile_id)) == 1
    lines = await exported(client, profile_id)
    assert lines[0]["chosen"] is None
    assert lines[0]["rejected"]["text"] == "Das kann ich nicht beantworten."
    assert (await detail_of(client, conversation_id))["ratings"][0]["rating"] == "down"


async def test_regenerating_a_chart_gives_a_second_one_and_the_pick_stores_both_codes(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Zeig mir die Ausgaben pro Monat als Diagramm.")
    turn_id, chart_call = turn_of(chunks), tool_call_of(chunks, "chart")
    first = [c for c in chunks if c["type"] == "tool-output-available"][0]["output"]
    assert isinstance(first, dict)

    # A thumb on the chart alone is a chart record, aimed at the tool call inside the turn.
    thumb = await rate(client, profile_id, turn_id, "up", target=chart_call)
    assert thumb["kind"] == "chart"
    assert thumb["target"] == chart_call
    assert "Chart plan: line" in thumb["prompt"]
    assert "SQL:\nSELECT" in thumb["prompt"]

    # Regenerate: the sub-agent runs again for the same request and draws the same rows
    # differently. It is not a chat turn, so nothing is appended to the conversation.
    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[SECOND_LINE_CODE])
    scripts.fast_call = respond  # type: ignore[assignment]
    response = await client.post(
        "/api/preferences/chart-alternative",
        json={"profile_id": profile_id, "turn_id": turn_id, "tool_call_id": chart_call},
    )
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["error"] is None
    assert second["code"] == SECOND_LINE_CODE
    assert second["sql"] == first["sql"], "the second chart draws the same statement"
    assert second["rows"] == first["rows"]
    assert respond.prompts["plan"][0].endswith("Request: spending per month in 2025 as a line chart")  # type: ignore[attr-defined]
    detail = await detail_of(client, conversation_id)
    assert len(detail["messages"]) == 2, "a regenerate adds no turn to the transcript"

    # The pick: the second chart wins, and the pair shares the statement behind both.
    pair = await client.post(
        "/api/preferences/pair",
        json={
            "profile_id": profile_id,
            "turn_id": turn_id,
            "target": chart_call,
            "picked": "candidate",
            "candidate": {"code": second["code"], "shape": second["shape"], "title": second["title"]},
        },
    )
    assert pair.status_code == 201, pair.text
    record = pair.json()
    assert record["kind"] == "chart"
    assert record["rating"] == "pick"
    assert record["paired"] is True
    assert record["model_slot"] == "fast", "the chart sub-agent is always on the fast slot"

    lines = await exported(client, profile_id)
    assert len(lines) == 1, "the pick replaced the thumb on the same chart"
    assert lines[0]["chosen"]["code"] == SECOND_LINE_CODE
    assert lines[0]["rejected"]["code"] == LINE_CODE
    assert lines[0]["chosen"]["sql"] == lines[0]["rejected"]["sql"] == first["sql"]

    # The card is marked after a reload, on the chart and not on the answer.
    assert (await detail_of(client, conversation_id))["ratings"] == [
        {"turn_id": turn_id, "target": chart_call, "kind": "chart", "rating": "pick"}
    ]


async def test_the_answer_ab_reruns_the_turn_read_only_and_the_pick_stores_the_pair(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    scripts.fast = script("Kurz: 412,50 EUR.")
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Wie viel habe ich im Mai ausgegeben?")
    turn_id = turn_of(chunks)
    await rate(client, profile_id, turn_id, "down")

    seen: dict[str, Any] = {}

    async def hotter(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        seen["tools"] = [tool.name for tool in info.function_tools]
        seen["temperature"] = (info.model_settings or {}).get("temperature")
        seen["messages"] = len(messages)
        yield "Ausfuehrlich: im Mai waren es 412,50 EUR, das meiste davon Miete."

    scripts.fast = hotter
    response = await client.post(
        "/api/preferences/answer-alternative", json={"profile_id": profile_id, "turn_id": turn_id}
    )
    assert response.status_code == 200, response.text
    second = response.json()
    assert second["text"].startswith("Ausfuehrlich")
    assert second["model_slot"] == "fast"
    assert second["temperature"] > 1
    # A second answer may look figures up and may change nothing.
    assert seen["tools"] == ["query"]
    assert seen["temperature"] == second["temperature"]
    assert seen["messages"] == 1, "the same history and the same user message, nothing else"
    # The rerun is not a turn: no follow-ups, nothing remembered, nothing in the transcript.
    detail = await detail_of(client, conversation_id)
    assert len(detail["messages"]) == 2
    assert (await client.get("/api/memories", params={"profile_id": profile_id})).json() == []

    pair = await client.post(
        "/api/preferences/pair",
        json={
            "profile_id": profile_id,
            "turn_id": turn_id,
            "picked": "candidate",
            "candidate": {"text": second["text"], "tools": second["tools"]},
        },
    )
    assert pair.status_code == 201, pair.text
    assert pair.json()["kind"] == "answer"
    assert pair.json()["rating"] == "pick"

    lines = await exported(client, profile_id)
    assert len(lines) == 1
    assert lines[0]["chosen"]["text"] == second["text"]
    assert lines[0]["rejected"]["text"] == "Kurz: 412,50 EUR."
    assert lines[0]["prompt"] == "Wie viel habe ich im Mai ausgegeben?"


async def test_a_turn_that_wrote_something_gets_no_answer_ab(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    scripts.fast = call_tools(("set_rule", {"pattern": "REWE", "category": "Groceries"}))
    scripts.fast_call = post_turn_only()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "REWE ist immer Groceries.")
    turn_id = turn_of(chunks)

    # The thumb itself still works: only the rerun is refused.
    assert (await rate(client, profile_id, turn_id, "down"))["rating"] == "down"
    response = await client.post(
        "/api/preferences/answer-alternative", json={"profile_id": profile_id, "turn_id": turn_id}
    )
    assert response.status_code == 409
    assert "set_rule" in response.json()["detail"]


async def test_the_export_holds_one_line_per_record_of_this_profile_only(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    other = (await client.post("/api/profiles", json={"name": "Haushalt"})).json()
    scripts.fast = script("Antwort eins.")
    first = await new_conversation(client, profile_id)
    _, chunks = await chat(first, "Frage eins?")
    first_turn = turn_of(chunks)
    scripts.fast = script("Antwort zwei.")
    second = await new_conversation(client, profile_id)
    _, chunks = await chat(second, "Frage zwei?")
    second_turn = turn_of(chunks)

    await rate(client, profile_id, first_turn, "up")
    await rate(client, profile_id, second_turn, "down")

    lines = await exported(client, profile_id)
    assert [line["kind"] for line in lines] == ["answer", "answer"]
    assert [line["prompt"] for line in lines] == ["Frage eins?", "Frage zwei?"]
    assert [line["rating"] for line in lines] == ["up", "down"]
    assert set(lines[0]) == {"kind", "rating", "prompt", "chosen", "rejected", "model_slot", "created_at"}

    # Nothing of this profile is in the other one's export, and its list is empty.
    assert await exported(client, other["id"]) == []
    assert await records_of(client, other["id"]) == []


async def test_another_profile_cannot_rate_or_rerun_this_profiles_turn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    other = (await client.post("/api/profiles", json={"name": "Haushalt"})).json()
    scripts.fast = script("Antwort.")
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Frage?")
    turn_id = turn_of(chunks)

    refused = [
        await client.post(
            "/api/preferences/rating", json={"profile_id": other["id"], "turn_id": turn_id, "rating": "up"}
        ),
        await client.post(
            "/api/preferences/pair",
            json={
                "profile_id": other["id"],
                "turn_id": turn_id,
                "picked": "original",
                "candidate": {"text": "Etwas anderes."},
            },
        ),
        await client.post(
            "/api/preferences/answer-alternative", json={"profile_id": other["id"], "turn_id": turn_id}
        ),
        await client.post(
            "/api/preferences/chart-alternative",
            json={"profile_id": other["id"], "turn_id": turn_id, "tool_call_id": "whatever"},
        ),
    ]
    assert [response.status_code for response in refused] == [404, 404, 404, 404]
    assert await records_of(client, other["id"]) == []
    assert await records_of(client, profile_id) == []


async def test_rating_a_chart_that_the_turn_never_drew_is_refused(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    scripts.fast = script("Antwort ohne Diagramm.")
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Frage?")
    turn_id = turn_of(chunks)

    response = await client.post(
        "/api/preferences/rating",
        json={"profile_id": profile_id, "turn_id": turn_id, "rating": "up", "target": "call_1"},
    )
    assert response.status_code == 404
    assert await records_of(client, profile_id) == []


async def test_regenerate_asks_again_until_the_second_chart_differs(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The sub-agent repeating itself cost the user three presses of about 45 seconds each.

    Three attempts happen inside the one press now, and "Same chart again" is only what the
    card says when all three came back identical.
    """
    await import_synthetic(client, profile_id)
    scripts.fast = ask_chart_then_report("spending per month in 2025 as a line chart")
    scripts.fast_call = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Zeig mir die Ausgaben pro Monat als Diagramm.")
    turn_id, chart_call = turn_of(chunks), tool_call_of(chunks, "chart")

    # The same definition twice, then a different one: one press, three attempts.
    repeats = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE, LINE_CODE, SECOND_LINE_CODE])
    scripts.fast_call = repeats  # type: ignore[assignment]
    second = (
        await client.post(
            "/api/preferences/chart-alternative",
            json={"profile_id": profile_id, "turn_id": turn_id, "tool_call_id": chart_call},
        )
    ).json()
    assert second["code"] == SECOND_LINE_CODE
    assert len(repeats.prompts["code"]) == 3  # type: ignore[attr-defined]

    # Three identical ones is where it stops, and the card says so instead of looping.
    same = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])
    scripts.fast_call = same  # type: ignore[assignment]
    third = (
        await client.post(
            "/api/preferences/chart-alternative",
            json={"profile_id": profile_id, "turn_id": turn_id, "tool_call_id": chart_call},
        )
    ).json()
    assert third["code"] == LINE_CODE
    assert len(same.prompts["code"]) == 3  # type: ignore[attr-defined]
