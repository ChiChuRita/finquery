"""What a small model does to this app, closed at the code level.

Every case here is a failure pattern of the Qwen3.5 9B capability read
(`.scratch/finquery/qwen-capability-2026-09-05.md`), scripted with the exact SQL, the exact
tool arguments or the exact prose the review recorded. They are not Qwen's alone: the same
patterns are what the local fast model does on a hard turn, so each one is a rule in code
rather than a sentence in a prompt.

Every test drives the HTTP seam, the way the rest of the suite does.
"""

import json
from collections.abc import AsyncIterator, Sequence
from datetime import date

import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall
from sqlalchemy.orm import Session, sessionmaker

from finquery.db import Memory, Transaction
from finquery.query.guard import MAX_STATEMENT_CHARS

from .conftest import (
    Chat,
    Scripts,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
)
from .test_query import answer, import_synthetic, scripted_sql, tool_output

# --------------------------------------------------------------------------- helpers


def ask_query_then_say(request: str, sentence: str):
    """A turn that calls `query` once and then writes `sentence`, whatever came back.

    The prose is the test's, so a figure in it is a figure the model made up, which is exactly
    what the answer check is for.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if _last_tool_return(messages, "query") is None:
            yield {0: DeltaToolCall(name="query", json_args=json.dumps({"request": request}))}
            return
        yield sentence

    return fn


def _last_tool_return(messages: list[ModelMessage], tool: str) -> dict | None:
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == tool:
                return part.content if isinstance(part.content, dict) else {}
            if part.part_kind == "user-prompt":
                return None
    return None


def calls_tool(tool: str, args: dict[str, object], sentence: str):
    """A turn that calls one tool with exactly these arguments and then says one line."""

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if _last_tool_return(messages, tool) is None:
            yield {0: DeltaToolCall(name=tool, json_args=json.dumps(args))}
            return
        yield sentence

    return fn


def fast_slot(memories: Sequence[str] = (), kind: str = "fact"):
    """The fast slot for a turn that needs no sub-agent: post-turn steps only."""

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled(*memories, kind=kind)])  # type: ignore[arg-type]
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="No follow-ups.")])
        raise AssertionError("no sub-agent should run in this turn")

    return respond


def last_tool_error(chunks: list[dict[str, object]]) -> str:
    """The `error` of the turn's last tool step: a tool that refuses answers with a sentence."""
    outputs = [c["output"] for c in chunks if c["type"] == "tool-output-available"]
    assert outputs, chunks
    assert isinstance(outputs[-1], dict)
    return str(outputs[-1].get("error") or "")


# --------------------------------------------------------------------------- 1 and 2: cents


async def test_cents_summed_as_a_euro_column_are_refused(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """B1: `ROUND(-SUM(amount_cents), 2) AS total_eur` published 90.762,00 for 907,62 EUR."""
    await import_synthetic(client, profile_id)
    cents = (
        "SELECT COALESCE(category, 'Needs review') AS topic, ROUND(-SUM(amount_cents), 2) AS total_eur "
        "FROM transaction_view WHERE amount_cents < 0 AND booked_on >= '2025-04-01' "
        "AND booked_on <= '2025-06-30' GROUP BY category"
    )
    euros = (
        "SELECT COALESCE(category, 'Needs review') AS topic, ROUND(-SUM(amount), 2) AS total_eur "
        "FROM transaction_view WHERE amount < 0 AND booked_on BETWEEN '2025-04-01' AND '2025-06-30' "
        "GROUP BY topic"
    )
    respond = scripted_sql(cents, euros)
    scripts.fast = ask_query_then_say("spending per category last quarter", "Done.")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Wie haben sich meine Ausgaben im letzten Quartal verteilt?")

    output = tool_output(chunks)
    assert output["error"] is None
    prompts = respond.prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2, "the statement was refused and rewritten"
    assert "integer cents" in prompts[1]
    assert "ROUND(-SUM(amount), 2)" in prompts[1]
    # Every euro figure that came back is a euro figure: the whole quarter is under 20.000 EUR.
    assert all(row["total_eur"] < 20000 for row in output["rows"])


async def test_cents_divided_by_a_hundred_are_refused(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """B5: `ROUND(-amount_cents / 100, 2)` published 10.560,00 for a 10.560,82 EUR transfer."""
    await import_synthetic(client, profile_id)
    truncating = (
        "SELECT description, ROUND(-amount_cents / 100, 2) AS amount, booked_on "
        "FROM transaction_view WHERE amount_cents < 0 ORDER BY amount_cents ASC LIMIT 1"
    )
    euros = (
        "SELECT description, ROUND(-amount, 2) AS largest_eur, booked_on "
        "FROM transaction_view WHERE amount < 0 ORDER BY amount ASC LIMIT 1"
    )
    respond = scripted_sql(truncating, euros)
    scripts.fast = ask_query_then_say("the single largest expense", "Done.")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Was war meine groesste einzelne Ausgabe?")

    output = tool_output(chunks)
    assert output["error"] is None
    assert "amount_cents" not in (output["sql"] or "")
    prompts = respond.prompts  # type: ignore[attr-defined]
    assert "throws the cents away" in prompts[1]
    # The figure is the booking to the cent, not the euros of an integer division.
    rows = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()["rows"]
    largest_cents = -min(row["amount_cents"] for row in rows)
    assert round(output["rows"][0]["largest_eur"] * 100) == largest_cents


async def test_a_sign_test_over_cents_still_runs(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The rule is about figures, not about the column: a comparison never prints cents."""
    await import_synthetic(client, profile_id)
    sql = (
        "SELECT CASE WHEN amount_cents < -20000 THEN 'gross' ELSE 'klein' END AS size_group, "
        "COUNT(*) AS bookings FROM transaction_view WHERE amount_cents < 0 GROUP BY size_group"
    )
    respond = scripted_sql(sql)
    scripts.fast = ask_query_then_say("how many large and small payments", "Done.")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Wie viele grosse und kleine Zahlungen habe ich?")

    assert tool_output(chunks)["error"] is None
    assert len(respond.prompts) == 1, "admitted the first time"  # type: ignore[attr-defined]


async def test_a_division_by_a_hundred_is_made_real(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """SQLite divides two integers as integers, so the guard writes the divisor as a decimal."""
    await import_synthetic(client, profile_id)
    respond = scripted_sql("SELECT COUNT(*) / 100 AS hundreds FROM transaction_view")
    scripts.fast = ask_query_then_say("bookings in hundreds", "Done.")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How many hundreds of bookings do I have?")

    output = tool_output(chunks)
    assert "/ 100.0" in output["sql"]
    assert output["rows"] == [{"hundreds": 4.33}], "433 / 100 is not 4"


# --------------------------------------------------------------------------- 4: subcategories


async def test_a_subcategory_used_as_a_category_is_refused_with_its_parent(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Six statements of the review filtered `category IN ('Supermarket', 'Bakery', ...)`."""
    await import_synthetic(client, profile_id)
    subcategories = (
        "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view "
        "WHERE amount < 0 AND category IN ('Supermarket', 'Bakery', 'Drugstore')"
    )
    parent = (
        "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view "
        "WHERE amount < 0 AND category = 'Groceries'"
    )
    respond = scripted_sql(subcategories, parent)
    scripts.fast = ask_query_then_say("total grocery spending", "Done.")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "How much did I spend on groceries?")

    assert tool_output(chunks)["error"] is None
    prompts = respond.prompts  # type: ignore[attr-defined]
    assert len(prompts) == 2
    assert "Supermarket is a subcategory of Groceries" in prompts[1]
    assert "category = 'Groceries'" in prompts[1]
    # The prompt itself cannot be read as a list of category values any more.
    assert "category Groceries / subcategories: Supermarket" in prompts[0]


# --------------------------------------------------------------------------- 5: runaway SQL


async def test_a_cross_join_is_refused(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A5's fourth attempt joined the view to a relation it had made up."""
    await import_synthetic(client, profile_id)
    invented = (
        "SELECT ROUND(-SUM(t.amount), 2) AS total_eur FROM transaction_view AS t "
        "CROSS JOIN transaction_view AS s WHERE t.amount < 0"
    )
    good = "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount < 0"
    respond = scripted_sql(invented, good)
    scripts.fast = ask_query_then_say("weekly grocery average", "Done.")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "What do I spend on groceries per week?")

    assert tool_output(chunks)["error"] is None
    assert "join without a condition" in respond.prompts[1]  # type: ignore[attr-defined]


async def test_a_runaway_statement_is_refused_on_its_length(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A5 spent one of its fifteen attempts on 9294 characters of UNION branches."""
    await import_synthetic(client, profile_id)
    branches = " UNION ALL ".join(
        f"SELECT {week} AS week, ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount < 0"
        for week in range(1, 40)
    )
    good = (
        "SELECT strftime('%Y-%W', booked_on) AS week, ROUND(-SUM(amount), 2) AS total_eur "
        "FROM transaction_view WHERE amount < 0 GROUP BY week"
    )
    assert len(branches) > MAX_STATEMENT_CHARS
    respond = scripted_sql(branches, good)
    scripts.fast = ask_query_then_say("spending per week", "Done.")
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "What do I spend per week?")

    assert tool_output(chunks)["error"] is None
    assert f"the limit is {MAX_STATEMENT_CHARS}" in respond.prompts[1]  # type: ignore[attr-defined]


async def test_the_query_budget_ends_a_runaway_turn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A5 called `query` fifteen times over 256 seconds. The sixth call is answered without a model."""
    await import_synthetic(client, profile_id)
    counted = "SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view WHERE amount < 0"

    async def keeps_asking(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        results = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolReturnPart) and part.tool_name == "query"
        ]
        if results and isinstance(results[-1].content, dict) and results[-1].content.get("error"):
            yield "I could not work that out from the data."
            return
        yield {0: DeltaToolCall(name="query", json_args=json.dumps({"request": "grocery spending"}))}

    respond = scripted_sql(counted)
    scripts.fast = keeps_asking
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "What do I spend on groceries per week on average?")

    calls = [c for c in chunks if c["type"] == "tool-input-available" and c["toolName"] == "query"]
    assert len(calls) == 6, "five queries ran, the sixth was refused"
    assert len(respond.prompts) == 5, "the sub-agent was not asked a sixth time"  # type: ignore[attr-defined]
    assert "five queries" in last_tool_error(chunks)
    assert answer(chunks) == "I could not work that out from the data."


# --------------------------------------------------------------------------- 8: the changeset


async def some_bookings(client: httpx.AsyncClient, profile_id: str, text: str) -> list[str]:
    rows = (await client.get("/api/transactions", params={"profile_id": profile_id, "q": text})).json()["rows"]
    assert rows, text
    return [row["id"] for row in rows]


async def test_a_changeset_with_null_for_every_nested_field_is_proposed(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """G1: two attempts, two empty turns. The model sent `legs: null` and burned its retries."""
    await import_synthetic(client, profile_id)
    ids = await some_bookings(client, profile_id, "netflix")
    scripts.fast = calls_tool(
        "propose_changeset",
        {
            "kind": "recategorize",
            "title": "Netflix-Buchungen als Leisure umkategorisieren",
            "transaction_ids": ids,
            "category": "Leisure",
            "subcategory": None,
            "where": None,
            "description": None,
            "amount_cents": None,
            "booked_on": None,
            "legs": None,
            "taxonomy": None,
        },
        "I have proposed moving those bookings to Leisure.",
    )
    scripts.fast_call = fast_slot()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Recategorize all Netflix bookings as Leisure.")

    calls = [c for c in chunks if c["type"] == "tool-input-available"]
    assert [c["toolName"] for c in calls] == ["propose_changeset"], "no retry was needed"
    card = tool_output(chunks)
    assert card["kind"] == "recategorize"
    assert card["status"] == "proposed"
    assert card["total"] == len(ids)
    assert answer(chunks) == "I have proposed moving those bookings to Leisure."
    # Nothing was written: a proposal is inert until the user applies it.
    rows = (await client.get("/api/transactions", params={"profile_id": profile_id, "q": "netflix"})).json()["rows"]
    assert all(row["category"] is None for row in rows)


async def test_a_filter_that_selects_everything_is_refused(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """An empty `where` object is the other half of the same hazard: it matches every booking."""
    await import_synthetic(client, profile_id)
    ids = await some_bookings(client, profile_id, "netflix")

    async def first_everything(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        calls = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolCallPart) and part.tool_name == "propose_changeset"
        ]
        if not calls:
            yield {
                0: DeltaToolCall(
                    name="propose_changeset",
                    json_args=json.dumps(
                        {"kind": "recategorize", "title": "Netflix to Leisure", "where": {}, "category": "Leisure"}
                    ),
                )
            }
            return
        if len(calls) == 1:
            yield {
                0: DeltaToolCall(
                    name="propose_changeset",
                    json_args=json.dumps(
                        {
                            "kind": "recategorize",
                            "title": "Netflix to Leisure",
                            "transaction_ids": ids,
                            "category": "Leisure",
                        }
                    ),
                )
            }
            return
        yield "I have proposed moving those bookings to Leisure."

    scripts.fast = first_everything
    scripts.fast_call = fast_slot()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Recategorize all Netflix bookings as Leisure.")

    card = tool_output(chunks)
    assert card["total"] == len(ids), "the second call named the rows"


# --------------------------------------------------------------------------- 9: the edit


async def test_an_edit_never_zeroes_an_amount_the_user_did_not_name(
    client: httpx.AsyncClient,
    scripts: Scripts,
    chat: Chat,
    profile_id: str,
    session_factory: sessionmaker[Session],
) -> None:
    """G2, verbatim: a category-only request came with `amount_cents: 0` and destroyed a booking."""
    await import_synthetic(client, profile_id)
    rows = (await client.get("/api/transactions", params={"profile_id": profile_id, "q": "vapiano"})).json()["rows"]
    ids = [row["id"] for row in rows]
    booking = rows[0]
    before = booking["amount_cents"]
    assert before != 0

    async def zeroes_then_corrects(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        calls = [
            part
            for message in messages
            for part in message.parts
            if isinstance(part, ToolCallPart) and part.tool_name == "apply_simple_edit"
        ]
        if not calls:
            yield {
                0: DeltaToolCall(
                    name="apply_simple_edit",
                    json_args=json.dumps(
                        {
                            "transaction_id": ids[0],
                            "title": "Set the VAPIANO booking to Dining > Restaurant",
                            "category": "Dining",
                            "subcategory": "Restaurant",
                            "description": booking["description"],
                            "amount_cents": 0,
                            "booked_on": booking["booked_on"],
                        }
                    ),
                )
            }
            return
        if len(calls) == 1:
            yield {
                0: DeltaToolCall(
                    name="apply_simple_edit",
                    json_args=json.dumps(
                        {
                            "transaction_id": ids[0],
                            "title": "Set the VAPIANO booking to Dining > Restaurant",
                            "category": "Dining",
                            "subcategory": "Restaurant",
                        }
                    ),
                )
            }
            return
        result = _last_tool_return(messages, "apply_simple_edit") or {}
        yield str(result.get("say"))

    scripts.fast = zeroes_then_corrects
    scripts.fast_call = fast_slot()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Set the VAPIANO booking to Dining.")

    # The amount is untouched, and the category is what was asked for.
    with session_factory() as session:
        row = session.get(Transaction, ids[0])
        assert row is not None
        assert row.amount_cents == before
    edited = (await client.get("/api/transactions", params={"profile_id": profile_id, "q": "vapiano"})).json()
    changed = next(row for row in edited["rows"] if row["id"] == ids[0])
    assert changed["category"] == "Dining" and changed["subcategory"] == "Restaurant"
    # The answer names the fields that changed, and no others.
    assert "category, subcategory" in answer(chunks)
    assert "amount" not in answer(chunks)


async def test_an_edit_that_names_the_amount_still_writes_it(
    client: httpx.AsyncClient,
    scripts: Scripts,
    chat: Chat,
    profile_id: str,
    session_factory: sessionmaker[Session],
) -> None:
    """The rule is about a field the user did not name, not about editing an amount."""
    await import_synthetic(client, profile_id)
    ids = await some_bookings(client, profile_id, "vapiano")
    scripts.fast = calls_tool(
        "apply_simple_edit",
        {"transaction_id": ids[0], "title": "Correct the VAPIANO amount", "amount_cents": -4230},
        "Corrected.",
    )
    scripts.fast_call = fast_slot()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    await chat(conversation_id, "That VAPIANO booking was 42,30 EUR, not what it says.")

    with session_factory() as session:
        row = session.get(Transaction, ids[0])
        assert row is not None and row.amount_cents == -4230
