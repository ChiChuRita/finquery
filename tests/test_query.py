"""Answering questions with SQL: the query tool, the guard and the profile scope.

Every test drives the chat endpoint. The chat model is scripted to call the `query` tool and
then to answer from the rows it got back, and the sub-agent behind the tool is scripted to
return one statement, which is how the fast slot answers a forced single tool.
"""

import json
from collections.abc import AsyncIterator, Sequence
from datetime import date

import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall
from sqlalchemy.orm import Session, sessionmaker

from finquery.db import create_profile, ensure_account
from finquery.formats import eur
from finquery.memory import MemoryKind
from finquery.query.check import CHECK_TOOL

from .conftest import (
    SYNTHETIC,
    Chat,
    Scripts,
    distilled,
    is_check_request,
    is_distillation_request,
    is_followup_request,
    new_conversation,
)
from .test_data_model import add_transaction
from .test_import import upload

SPARKASSE = SYNTHETIC / "sparkasse-2025.csv"


async def import_synthetic(client: httpx.AsyncClient, profile_id: str) -> None:
    """The shipped dataset, committed through the Import endpoints like a user would."""
    preview = (await client.post("/api/imports/preview", files=upload(SPARKASSE))).json()
    committed = await client.post(
        "/api/imports",
        files=upload(SPARKASSE),
        data={
            "profile_id": profile_id,
            "mapping": json.dumps(preview["mapping"]),
            "account_name": preview["account_name"],
        },
    )
    assert committed.status_code == 201, committed.text


def ask_query_then_report(request: str, hints: str | None = None):
    """A chat turn that calls `query` and then reports whatever the tool returned.

    The second step reads the tool result out of the message history, so any figure in the
    answer provably comes from the executed query and not from the script.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        result = _last_tool_return(messages)
        if result is None:
            args = {"request": request} | ({"hints": hints} if hints else {})
            yield {0: DeltaToolCall(name="query", json_args=json.dumps(args))}
            return
        if result["error"]:
            yield f"I could not answer that: {result['error']}"
        elif result["rows"]:
            first = result["rows"][0]
            yield "Result: " + ", ".join(f"{key}={value}" for key, value in first.items())
        else:
            yield "The data holds no answer for that."

    return fn


def scripted_sql(
    *statements: str,
    followups: Sequence[str] = (),
    memories: Sequence[str] = (),
    memory_kind: MemoryKind = "fact",
    checks: Sequence[dict[str, str]] = (),
):
    """The sub-agent's forced single tool call, one statement per attempt.

    Both post-turn steps run on the same slot and are not streamed either, so they land here
    too. They get their own answer and never count as an attempt.

    The check pass of ticket 40 shares the slot as well and answers `ok` unless the test wrote
    a verdict for it in `checks`, so a scripted statement stands as it is written. Its prompts
    are on `respond.judgements`, the statements' on `respond.prompts`.
    """
    prompts: list[str] = []
    judgements: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="\n".join(followups) if followups else "No follow-ups.")])
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled(*memories, kind=memory_kind)])
        if is_check_request(messages):
            judgements.append(_last_user_prompt(messages))
            assert [tool.name for tool in info.output_tools] == [CHECK_TOOL]
            assert info.allow_text_output is False
            verdict = checks[len(judgements) - 1] if len(judgements) <= len(checks) else {"verdict": "ok"}
            return ModelResponse(parts=[ToolCallPart(CHECK_TOOL, json.dumps(verdict))])
        prompts.append(_last_user_prompt(messages))
        assert [tool.name for tool in info.output_tools] == ["run_sql"]
        assert info.allow_text_output is False
        assert info.function_tools == []
        sql = statements[min(len(prompts), len(statements)) - 1]
        return ModelResponse(parts=[ToolCallPart("run_sql", json.dumps({"sql": sql}))])

    respond.prompts = prompts  # type: ignore[attr-defined]
    respond.judgements = judgements  # type: ignore[attr-defined]
    return respond


def _last_tool_return(messages: list[ModelMessage]) -> dict | None:
    """The query result of the turn being answered, ignoring earlier turns."""
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == "query":
                assert isinstance(part.content, dict)
                return part.content
            if part.part_kind == "user-prompt":
                return None
    return None


def _last_user_prompt(messages: list[ModelMessage]) -> str:
    prompts = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt" and isinstance(part.content, str)
    ]
    return prompts[-1]


def tool_parts(chunks: list[dict[str, object]]) -> list[dict[str, object]]:
    return [c for c in chunks if str(c["type"]).startswith("tool-")]


def tool_output(chunks: list[dict[str, object]]) -> dict:
    outputs = [c["output"] for c in chunks if c["type"] == "tool-output-available"]
    assert len(outputs) == 1, chunks
    assert isinstance(outputs[0], dict)
    return outputs[0]


def answer(chunks: list[dict[str, object]]) -> str:
    return "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta").strip()


async def test_scripted_sql_executes_and_its_rows_reach_the_transcript(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    sql = (
        "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view "
        "WHERE amount_cents < 0 AND booked_on BETWEEN '2025-05-01' AND '2025-05-31' "
        "AND lower(coalesce(counterparty, description)) LIKE '%rewe%'"
    )
    respond = scripted_sql(sql, followups=["Und im Vergleich zum April?"])
    # The conversation runs on quality; the sub-agent is pinned to fast either way.
    scripts.quality = ask_query_then_report("groceries at REWE in May 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id, "quality")

    _, chunks = await chat(conversation_id, "Wie viel habe ich im Mai bei REWE ausgegeben?")

    # The chat model on quality, then the sub-agent and both post-turn steps on fast.
    assert scripts.resolved == ["quality", "fast", "fast", "fast"]
    # The tool step is announced, resolved, and only then does the answer start.
    types = [str(c["type"]) for c in chunks]
    assert types.index("tool-input-available") < types.index("tool-output-available") < types.index("text-start")
    assert [c["input"] for c in tool_parts(chunks) if c["type"] == "tool-input-available"] == [
        {"request": "groceries at REWE in May 2025"}
    ]

    output = tool_output(chunks)
    assert output["error"] is None
    assert output["request"] == "groceries at REWE in May 2025"
    # The guard re-renders the statement it admitted and appends the automatic limit.
    assert output["sql"].startswith("SELECT\n  ROUND(-SUM(amount), 2) AS total_eur\nFROM transaction_view")
    assert "'%rewe%'" in output["sql"]
    assert output["sql"].endswith("LIMIT 200")
    assert output["row_count"] == 1
    assert output["columns"] == ["total_eur"]
    total = output["rows"][0]["total_eur"]
    assert total > 0, "spending is reported as a positive figure"
    assert output["summary"] == f"One row: total_eur = {total}"
    # The same figure written the way the answer should quote it: the rows stay numeric for
    # the transcript's table, the figures are for the model.
    assert output["figures"] == [f"total_eur {eur(round(total * 100))} EUR"]
    assert "," in output["figures"][0] and "." not in output["figures"][0].split(",")[1]
    # The number in the prose is the number the query returned.
    assert answer(chunks) == f"Result: total_eur={total}"

    # The sub-agent saw the schema, the profile's date range and the taxonomy.
    prompt = respond.prompts[0]  # type: ignore[attr-defined]
    assert "transaction_view" in prompt
    assert "2025-01-01 to 2025-12-28" in prompt
    # One line per category, with its subcategories marked as such: a 9B model reads
    # `Groceries (Supermarket, Bakery)` as a list of category values (ticket 37).
    assert "category Groceries / subcategories: Supermarket, Bakery, Drugstore" in prompt
    assert "no booking is categorized yet" in prompt
    assert "REWE Markt GmbH" in prompt
    assert "Question: groceries at REWE in May 2025" in prompt
    # A merchant is matched on the booking text and the counterparty together: a PayPal payment
    # carries PayPal as the counterparty and the person in the description.
    assert "lower(description || ' ' || coalesce(counterparty, '')) LIKE" in prompt
    assert "coalesce(counterparty, description)) LIKE" not in prompt

    # A reload shows one assistant message with the same tool step, its SQL and its rows.
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    # Thinking, tool step, answer and the post-turn parts are one message, live and on reload.
    assert [p["type"] for p in detail["messages"][-1]["parts"]] == [
        "tool-query",
        # The check pass narrates into the thinking panel, so the tool step is followed by one
        # reasoning block, live and on reload (ticket 40).
        "reasoning",
        "text",
        "data-context",
        "data-followups",
    ]
    assert detail["messages"][-1]["parts"][-1]["data"] == {"suggestions": ["Und im Vergleich zum April?"]}
    part = detail["messages"][-1]["parts"][0]
    assert part["state"] == "output-available"
    assert part["input"] == {"request": "groceries at REWE in May 2025"}
    assert part["output"]["sql"] == output["sql"]
    assert part["output"]["rows"] == [{"total_eur": total}]


async def test_a_follow_up_question_is_a_second_query_in_the_same_conversation(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    months = (
        "SELECT strftime('%Y-%m', booked_on) AS month, ROUND(-SUM(amount), 2) AS total_eur "
        "FROM transaction_view WHERE amount_cents < 0 "
        "AND strftime('%Y-%m', booked_on) IN ('2025-04', '2025-05') GROUP BY month ORDER BY month"
    )
    scripts.fast = ask_query_then_report("total spending in April 2025 compared with May 2025")
    scripts.fast_call = scripted_sql(months)  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    await chat(conversation_id, "Wie viel habe ich im Mai insgesamt ausgegeben?")
    _, chunks = await chat(conversation_id, "und im Vergleich zum April?")

    output = tool_output(chunks)
    assert output["columns"] == ["month", "total_eur"]
    assert [row["month"] for row in output["rows"]] == ["2025-04", "2025-05"]
    assert output["summary"] == "2 rows with columns month, total_eur."
    # Two turns, each with its own executed statement in the transcript.
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    steps = [p for m in detail["messages"] for p in m["parts"] if p["type"] == "tool-query"]
    assert len(steps) == 2


async def test_a_write_attempt_is_refused_and_the_sub_agent_retries(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    good = "SELECT COUNT(*) AS bookings FROM transaction_view"
    respond = scripted_sql("DELETE FROM transaction_view WHERE amount_cents < 0", good)
    scripts.fast = ask_query_then_report("how many bookings are there")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How many bookings do I have?")

    output = tool_output(chunks)
    assert output["error"] is None
    assert output["sql"] == "SELECT\n  COUNT(*) AS bookings\nFROM transaction_view\nLIMIT 200"
    assert output["rows"] == [{"bookings": 433}]
    # The refusal went back to the sub-agent with the reason, and only then came the retry.
    prompts = respond.prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    assert "Only a SELECT may run, not DELETE." in prompts[1]
    assert "Refused SQL:\nDELETE FROM transaction_view" in prompts[1]
    # Nothing was written.
    assert (await client.get("/api/transactions", params={"profile_id": profile_id})).json()["total"] == 433


async def test_sql_that_stays_invalid_is_reported_without_a_number(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_sql('SELECT COUNT(*) FROM "transaction"', "SELECT nope FROM transaction_view")
    scripts.fast = ask_query_then_report("how many bookings are there")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How many bookings do I have?")

    output = tool_output(chunks)
    assert output["row_count"] == 0
    assert output["rows"] == []
    assert "refused 2 times" in output["error"]
    assert "no such column: nope" in output["error"]
    # The statement that was refused is still visible in the step.
    assert output["sql"] == "SELECT nope FROM transaction_view"
    assert answer(chunks) == f"I could not answer that: {output['error']}"
    prompts = respond.prompts  # type: ignore[attr-defined]
    assert "transaction may not be read" in prompts[1]
    assert (await client.get("/api/transactions", params={"profile_id": profile_id})).json()["total"] == 433


async def test_an_empty_profile_is_answered_without_calling_the_sub_agent(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    def never(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        # Both post-turn steps share this slot; nothing else may reach it.
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        assert is_followup_request(messages), "the query sub-agent must not run without data"
        return ModelResponse(parts=[TextPart(content="No follow-ups.")])

    scripts.fast = ask_query_then_report("total spending in May 2025")
    scripts.fast_call = never  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much did I spend in May?")

    # The chat model and the two post-turn steps, and no fourth resolution for the sub-agent:
    # the tool answered before any model was involved.
    assert scripts.resolved == ["fast", "fast", "fast"]
    output = tool_output(chunks)
    assert output["sql"] is None
    assert output["row_count"] == 0
    assert "no transactions yet" in output["error"]
    assert not any(character.isdigit() for character in answer(chunks))


async def test_the_profile_scope_cannot_be_widened(
    client: httpx.AsyncClient,
    scripts: Scripts,
    chat: Chat,
    session_factory: sessionmaker[Session],
    profile_id: str,
) -> None:
    await import_synthetic(client, profile_id)
    with session_factory() as session:
        other = create_profile(session, "Housemate")
        account = ensure_account(session, other.id, "Other bank")
        add_transaction(
            session, other.id, account.id, booked_on=date(2025, 5, 4), amount_cents=-999999, description="NOT MINE"
        )
        session.commit()
    assert other.id != profile_id

    # First a schema prefix, then a predicate that tries to reach past the profile filter.
    respond = scripted_sql(
        "SELECT COUNT(*) AS bookings FROM main.transaction_view",
        "SELECT COUNT(*) AS bookings, ROUND(SUM(amount), 2) AS total_eur FROM transaction_view "
        "WHERE profile_id IS NOT NULL OR 1 = 1",
    )
    scripts.fast = ask_query_then_report("count every booking")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How many bookings are stored?")

    output = tool_output(chunks)
    assert "Do not prefix a relation with a schema" in respond.prompts[1]  # type: ignore[attr-defined]
    own = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()
    assert output["rows"] == [
        {"bookings": own["total"], "total_eur": round(sum(row["amount_cents"] for row in own["rows"]) / 100, 2)}
    ]
    assert output["rows"][0]["bookings"] == 433, "the other profile's booking is not visible"


async def test_a_row_dump_is_capped_at_two_hundred_rows(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast = ask_query_then_report("list every booking")
    scripts.fast_call = scripted_sql("SELECT booked_on, amount, description FROM transaction_view")  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Show me everything.")

    output = tool_output(chunks)
    assert output["sql"].endswith("LIMIT 200")
    assert output["row_count"] == 200
    assert "200 row limit was reached" in output["summary"]


async def test_a_category_classifier_in_the_sql_is_refused_and_the_sub_agent_regroups(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The blocker of the second review: the sub-agent labelling bookings itself.

    `CASE WHEN description LIKE '%rewe%' THEN 'Groceries'` puts model guesses next to the
    household's own categories and nothing on screen tells the two apart, so the guard refuses
    it and says what to write instead.
    """
    await import_synthetic(client, profile_id)
    invented = (
        "SELECT CASE WHEN lower(coalesce(counterparty, description)) LIKE '%rewe%' THEN 'Groceries' "
        "ELSE 'Sonstiges' END AS topic, ROUND(-SUM(amount), 2) AS total_eur "
        "FROM transaction_view WHERE amount_cents < 0 GROUP BY topic"
    )
    honest = (
        "SELECT coalesce(category, 'Needs review') AS topic, ROUND(-SUM(amount), 2) AS total_eur "
        "FROM transaction_view WHERE amount_cents < 0 GROUP BY topic ORDER BY total_eur DESC"
    )
    respond = scripted_sql(invented, honest)
    scripts.fast = ask_query_then_report("spending per category in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Wie viel habe ich pro Kategorie ausgegeben?")

    output = tool_output(chunks)
    assert output["error"] is None
    # Nothing is categorized in a freshly imported profile, so every euro is one honest bucket.
    assert [row["topic"] for row in output["rows"]] == ["Needs review"]
    prompts = respond.prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    assert "invents a categorization" in prompts[1]
    assert "coalesce(category, 'Needs review')" in prompts[1]
    assert "THEN 'Groceries'" in prompts[1], "the refused statement goes back with the reason"


async def test_a_case_that_does_not_label_the_booking_text_still_runs(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The rule is about labelling, not about CASE: a bucket over the amount is arithmetic."""
    await import_synthetic(client, profile_id)
    sql = (
        "SELECT CASE WHEN amount_cents < -20000 THEN 'gross' ELSE 'klein' END AS size_group, "
        "COUNT(*) AS bookings FROM transaction_view WHERE amount_cents < 0 GROUP BY size_group"
    )
    respond = scripted_sql(sql)
    scripts.fast = ask_query_then_report("how many large and small payments there are")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Wie viele grosse und kleine Zahlungen habe ich?")

    output = tool_output(chunks)
    assert output["error"] is None
    assert len(respond.prompts) == 1, "no retry: the statement was admitted the first time"  # type: ignore[attr-defined]
    assert {row["size_group"] for row in output["rows"]} == {"gross", "klein"}


async def test_a_statement_matching_every_merchant_is_refused_and_the_sub_agent_narrows(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Asked about a person it could not find, the local fast model matched every merchant it
    had been shown and returned the household's whole spending as the answer. The guard refuses
    a statement with more LIKE terms than any topic needs and says what to write instead."""
    await import_synthetic(client, profile_id)
    merchants = ["rewe", "aldi", "lidl", "edeka", "kaufland", "netto", "netflix", "spotify", "adobe", "vodafone"]
    match = " OR ".join(f"lower(coalesce(counterparty, description)) LIKE '%{name}%'" for name in merchants)
    everything = f"SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 AND ({match})"
    one = (
        "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount_cents < 0 "
        "AND lower(coalesce(counterparty, description)) LIKE '%max schulz%'"
    )
    respond = scripted_sql(everything, one)
    scripts.fast = ask_query_then_report("PayPal payments to Max Schulz in 2025")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much did I send my flatmate in 2025?")

    output = tool_output(chunks)
    assert output["error"] is None
    assert "'%max schulz%'" in output["sql"]
    prompts = respond.prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    assert "matches 10 merchant patterns" in prompts[1]
    assert "return no rows" in prompts[1]
