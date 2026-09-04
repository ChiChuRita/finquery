"""Categorization at import, and the Question card that asks about the rest.

Every test drives the app over HTTP. The categorizer sub-agent is scripted per test, so what
the three stages do is observable without a real model: which merchants ever reached the
prompt, what the counts came to, what the transactions endpoint shows afterwards, and what the
transcript holds.
"""

import json
import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from .conftest import (
    Chat,
    Scripts,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
    script,
)
from .test_query import import_synthetic

# The shipped year: 433 bookings, 39 merchants, of which six are neither a rule nor a
# dictionary hit (a landlord, an employer and four PayPal payments to friends).
TOTAL_ROWS = 433
MODEL_MERCHANTS = {
    "hausverwaltung bergmann",
    "mustermann systems",
    "anna weber",
    "jonas keller",
    "max schulz",
    "lea hoffmann",
}
GUESSES: dict[str, tuple[str, str | None, float]] = {
    "hausverwaltung bergmann": ("Housing", "Rent", 0.85),
    "mustermann systems": ("Income", "Salary", 0.9),
    "anna weber": ("Transfers", "Friends and family", 0.4),
    "jonas keller": ("Transfers", "Friends and family", 0.4),
    "max schulz": ("Transfers", "Friends and family", 0.35),
    "lea hoffmann": ("Transfers", "Friends and family", 0.4),
}

_KEY = re.compile(r"^  key: (?P<key>.+?) \|", re.MULTILINE)


def scripted_categorizer(guesses: dict[str, tuple[str, str | None, float]] = GUESSES):
    """The fast slot answering the categorizer's forced single tool, one entry per merchant.

    Every other fast-slot step of a turn shares this slot: the follow-up step, the distillation
    pass and, when a test asks a question, the query sub-agent. All of them are recognized and
    answered here, so what is left is the categorizer. `prompts` records every categorizer
    prompt, which is how a test sees whether a merchant ever reached the model at all.
    """
    prompts: list[str] = []
    queries: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="No follow-ups.")])
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        tools = [tool.name for tool in info.output_tools]
        prompt = _last_user_prompt(messages)
        if tools == ["run_sql"]:
            queries.append(prompt)
            return ModelResponse(parts=[ToolCallPart("run_sql", json.dumps({"sql": "SELECT 1 AS one"}))])
        assert tools == ["categorize"], tools
        assert info.allow_text_output is False
        prompts.append(prompt)
        merchants = [
            {
                "key": key,
                "category": guesses[key][0],
                "subcategory": guesses[key][1],
                "confidence": guesses[key][2],
                "title": key.title(),
                "description": "guessed by the model",
            }
            for key in _KEY.findall(prompt)
            if key in guesses
        ]
        return ModelResponse(parts=[ToolCallPart("categorize", json.dumps({"merchants": merchants}))])

    respond.prompts = prompts  # type: ignore[attr-defined]
    respond.queries = queries  # type: ignore[attr-defined]
    return respond


def _last_user_prompt(messages: Sequence[ModelMessage]) -> str:
    prompts = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt" and isinstance(part.content, str)
    ]
    return prompts[-1] if prompts else ""


def keys_in(prompt: str) -> set[str]:
    return set(_KEY.findall(prompt))


async def categorize(client: httpx.AsyncClient, profile_id: str, import_id: str) -> dict[str, Any]:
    response = await client.post(f"/api/imports/{import_id}/categorize", json={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return dict(response.json())


async def last_import(client: httpx.AsyncClient, profile_id: str) -> str:
    imports = (await client.get("/api/imports", params={"profile_id": profile_id})).json()
    return str(imports[0]["id"])


async def rows_of(client: httpx.AsyncClient, profile_id: str, needle: str) -> list[dict[str, Any]]:
    page = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()
    return [row for row in page["rows"] if needle.casefold() in row["description"].casefold()]


def call_tools(*calls: tuple[str, dict[str, Any]]):
    """A chat turn that makes these tool calls, then reports what came back.

    The second step reads the tool results out of the history, so anything the answer states
    provably came from the tool and not from the script.
    """

    wanted = {name for name, _ in calls}

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        # Only this turn's own tools count as done: a Question card answer already sits in the
        # history as a tool result when the run resumes, and that is what the calls react to.
        results = [(name, result) for name, result in _tool_returns(messages) if name in wanted]
        if not results:
            for index, (name, args) in enumerate(calls):
                yield {index: DeltaToolCall(name=name, json_args=json.dumps(args))}
            return
        yield "Done: " + "; ".join(
            f"{name} {result.get('matched')} matched, {result.get('updated')} updated"
            for name, result in results
        )

    return fn


def _tool_returns(messages: list[ModelMessage]) -> list[tuple[str, dict[str, Any]]]:
    """The tool results of the turn being answered, ignoring everything before the last prompt."""
    found: list[tuple[str, dict[str, Any]]] = []
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and isinstance(part.content, dict):
                found.append((part.tool_name, part.content))
            elif part.part_kind == "user-prompt":
                return list(reversed(found))
    return list(reversed(found))


def answer_card(
    conversation_id: str, message_id: str, card: dict[str, Any], output: dict[str, Any]
) -> dict[str, Any]:
    """The next chat request a browser sends after `addToolOutput` on a Question card.

    `useChat` puts the output on the assistant message the card belongs to and sends that
    message; the transport sends only the newest one, the same as for a typed message.
    """
    return {
        "id": conversation_id,
        "trigger": "submit-message",
        "messages": [
            {
                "id": message_id,
                "role": "assistant",
                "parts": [
                    {
                        "type": "tool-ask_user",
                        "toolCallId": card["toolCallId"],
                        "state": "output-available",
                        "input": card["input"],
                        "output": output,
                    }
                ],
            }
        ],
    }


def outputs_of(chunks: list[dict[str, object]]) -> list[dict[str, Any]]:
    return [c["output"] for c in chunks if c["type"] == "tool-output-available"]  # type: ignore[misc]


def answer(chunks: list[dict[str, object]]) -> str:
    return "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta").strip()


async def test_the_dictionary_categorizes_without_ever_asking_the_model(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_categorizer()
    scripts.fast_call = respond  # type: ignore[assignment]

    report = await categorize(client, profile_id, await last_import(client, profile_id))

    # One batch, and only the merchants no dictionary entry knows were in it.
    assert report["model_calls"] == 1
    assert keys_in(respond.prompts[0]) == MODEL_MERCHANTS  # type: ignore[attr-defined]
    for skipped in ("rewe", "lidl", "netflix", "spotify", "bvg", "geldautomat"):
        assert skipped not in respond.prompts[0].casefold()  # type: ignore[attr-defined]

    assert report["rows"] == TOTAL_ROWS
    assert report["merchants"] == 39
    assert report["by_rule"] == 0
    assert report["by_dictionary"] > 350
    # The landlord and the salary were confident enough; the four PayPal people were not.
    assert report["by_model"] == 24
    assert report["needs_review"] == 25
    assert report["by_dictionary"] + report["by_model"] + report["needs_review"] == TOTAL_ROWS

    page = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()
    # Every row is enriched, categorized or not.
    assert all(row["title"] for row in page["rows"])
    by_title = {row["title"] for row in page["rows"]}
    assert {"REWE", "Lidl", "Netflix", "Cash withdrawal"} <= by_title
    rewe = await rows_of(client, profile_id, "REWE SAGT DANKE")
    assert {(row["category"], row["subcategory"]) for row in rewe} == {("Groceries", "Supermarket")}
    # A PayPal payment to a person stays Needs review, which is the absence of a category.
    anna = await rows_of(client, profile_id, "ANNA WEBER")
    assert {(row["category"], row["title"]) for row in anna} == {(None, "Anna Weber")}


async def test_a_rule_beats_the_model_and_runs_before_it(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    # The user teaches the rule before the data even arrives.
    scripts.fast = call_tools(("set_rule", {"pattern": "REWE", "category": "Dining > Restaurant"}))
    respond = scripted_categorizer()
    scripts.fast_call = respond  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "REWE ist bei mir immer Dining.")
    assert outputs_of(chunks)[0]["matched"] == 0, "no bookings yet, but the rule is stored"

    await import_synthetic(client, profile_id)
    report = await categorize(client, profile_id, await last_import(client, profile_id))

    # The rule stage placed those rows, and the merchant never reached the model or the
    # dictionary: the prompt of the one batch does not mention it.
    assert report["by_rule"] == 17
    assert "rewe" not in respond.prompts[0].casefold()  # type: ignore[attr-defined]
    rewe = await rows_of(client, profile_id, "REWE SAGT DANKE")
    assert len(rewe) == 17
    assert {(row["category"], row["subcategory"]) for row in rewe} == {("Dining", "Restaurant")}
    # A merchant the dictionary knows is untouched by the rule.
    lidl = await rows_of(client, profile_id, "LIDL")
    assert {row["category"] for row in lidl} == {"Groceries"}


async def test_a_plain_language_rule_recategorizes_the_profile(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_categorizer()
    scripts.fast_call = respond  # type: ignore[assignment]
    await categorize(client, profile_id, await last_import(client, profile_id))
    assert {row["category"] for row in await rows_of(client, profile_id, "ANNA WEBER")} == {None}

    scripts.fast = call_tools(("set_rule", {"pattern": "Anna Weber", "category": "Dining", "subcategory": "Restaurant"}))
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "PayPal an Anna ist immer Dining.")

    output = outputs_of(chunks)[0]
    assert output["error"] is None
    assert output["category"] == "Dining"
    assert output["subcategory"] == "Restaurant"
    assert output["matched"] == 6
    assert output["updated"] == 6
    assert output["rule"] == "created"
    assert answer(chunks) == "Done: set_rule 6 matched, 6 updated"

    anna = await rows_of(client, profile_id, "ANNA WEBER")
    assert len(anna) == 6
    assert {(row["category"], row["subcategory"]) for row in anna} == {("Dining", "Restaurant")}
    # Only that merchant moved.
    assert {row["category"] for row in await rows_of(client, profile_id, "MAX SCHULZ")} == {None}


async def test_a_rule_for_a_category_the_profile_does_not_have_is_refused(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast = call_tools(("set_rule", {"pattern": "Anna Weber", "category": "Bribes"}))
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Anna ist immer Bribes.")

    output = outputs_of(chunks)[0]
    assert "'Bribes' is not a category of this profile" in output["error"]
    assert "Groceries" in output["error"]
    assert {row["category"] for row in await rows_of(client, profile_id, "ANNA WEBER")} == {None}


async def test_the_import_hands_the_uncertain_rows_to_a_question_card(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    import_id = await last_import(client, profile_id)
    report = await categorize(client, profile_id, import_id)
    assert [question["pattern"] for question in report["uncertain"]] == [
        "jonas keller",
        "max schulz",
        "anna weber",
        "lea hoffmann",
    ]
    assert report["uncertain"][0]["guess"] == "Transfers > Friends and family"
    assert report["uncertain"][0]["bookings"] == 7

    opened = await client.post(
        f"/api/imports/{import_id}/review-conversation", json={"profile_id": profile_id}
    )
    assert opened.status_code == 201, opened.text
    body = opened.json()
    assert body["questions"] == 4
    assert body["pending_merchants"] == 4
    assert body["title"] == "Review sparkasse-2025.csv"

    detail = (await client.get(f"/api/conversations/{body['conversation_id']}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["parts"][0]["text"] == "Categorize the import I just did."
    assistant = detail["messages"][1]
    assert [part["type"] for part in assistant["parts"]] == ["text", "tool-ask_user"]
    # The summary is counted in code, not written by a model.
    assert "433 of 433 bookings" in assistant["parts"][0]["text"]
    assert "25 are still Needs review" in assistant["parts"][0]["text"]
    card = assistant["parts"][1]
    assert card["state"] in {"input-available", "approval-requested"}
    rows = card["input"]["rows"]
    assert [row["ref"] for row in rows] == ["jonas keller", "max schulz", "anna weber", "lea hoffmann"]
    assert rows[0]["label"] == "Jonas Keller (via PayPal)"
    assert rows[0]["bookings"] == 7
    assert rows[0]["options"][0] == {"label": "Transfers > Friends and family", "value": "Transfers > Friends and family"}
    assert rows[0]["options"][-1] == {"label": "Unknown", "value": "Unknown"}
    assert card["input"]["allow_free_text"] is True


async def test_answering_a_question_card_creates_rules_and_recategorizes(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    import_id = await last_import(client, profile_id)
    await categorize(client, profile_id, import_id)
    opened = (
        await client.post(f"/api/imports/{import_id}/review-conversation", json={"profile_id": profile_id})
    ).json()
    conversation_id = opened["conversation_id"]
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    card = detail["messages"][1]["parts"][1]

    # The browser answers two of the four rows and leaves the rest alone.
    answers = {
        "answers": [
            {"ref": "anna weber", "value": "Dining > Restaurant", "text": None},
            {"ref": "jonas keller", "value": None, "text": "Leisure"},
        ]
    }
    scripts.fast = call_tools(
        ("set_rule", {"pattern": "Anna Weber", "category": "Dining", "subcategory": "Restaurant"}),
        ("set_rule", {"pattern": "Jonas Keller", "category": "Leisure"}),
    )
    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(conversation_id, detail["messages"][1]["id"], card, answers),
    )
    assert response.status_code == 200, response.text
    chunks = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]

    # The run continued from the pending call: the answer became the tool's result, and two
    # rules were stored from it.
    resolved = [c for c in chunks if c["type"] == "tool-output-available"]
    assert resolved[0]["toolCallId"] == card["toolCallId"]
    assert resolved[0]["output"] == answers
    # Two calls in one response, so they resolve in whatever order they finish.
    stored = {rule["pattern"]: rule for rule in (c["output"] for c in resolved[1:])}
    assert set(stored) == {"Anna Weber", "Jonas Keller"}
    assert (stored["Anna Weber"]["matched"], stored["Anna Weber"]["updated"]) == (6, 6)
    assert (stored["Jonas Keller"]["matched"], stored["Jonas Keller"]["updated"]) == (7, 7)

    anna = await rows_of(client, profile_id, "ANNA WEBER")
    assert {(row["category"], row["subcategory"]) for row in anna} == {("Dining", "Restaurant")}
    jonas = await rows_of(client, profile_id, "JONAS KELLER")
    assert {row["category"] for row in jonas} == {"Leisure"}
    # The rows nobody answered are still Needs review.
    assert {row["category"] for row in await rows_of(client, profile_id, "MAX SCHULZ")} == {None}

    # One turn, one assistant message: the card now carries its answer, then the rules, then
    # the text, then the stats of the request that finished the turn. A reload shows what the
    # stream showed.
    reloaded = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in reloaded["messages"]] == ["user", "assistant"]
    parts = reloaded["messages"][1]["parts"]
    assert [part["type"] for part in parts] == [
        "text",
        "tool-ask_user",
        "tool-set_rule",
        "tool-set_rule",
        "text",
        "data-context",
    ]
    assert parts[1]["state"] == "output-available"
    assert parts[1]["output"] == answers
    assert parts[2]["output"]["category"] == "Dining"


async def test_a_card_the_user_skips_leaves_the_rows_alone(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    import_id = await last_import(client, profile_id)
    await categorize(client, profile_id, import_id)
    opened = (
        await client.post(f"/api/imports/{import_id}/review-conversation", json={"profile_id": profile_id})
    ).json()
    conversation_id = opened["conversation_id"]
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    card = detail["messages"][1]["parts"][1]

    scripts.fast = script("Alles klar, ich frage spaeter noch einmal.")
    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(conversation_id, detail["messages"][1]["id"], card, {"answers": []}),
    )

    assert response.status_code == 200, response.text
    assert "Alles klar" in response.text
    # Nothing was decided, so the rows are still Needs review and no rule appeared.
    assert {row["category"] for row in await rows_of(client, profile_id, "ANNA WEBER")} == {None}
    reloaded = (await client.get(f"/api/conversations/{conversation_id}")).json()
    parts = reloaded["messages"][1]["parts"]
    assert [part["type"] for part in parts] == ["text", "tool-ask_user", "text", "data-context"]
    assert parts[1]["output"] == {"answers": []}


async def test_a_categorized_import_changes_what_the_query_sub_agent_is_told(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    respond = scripted_categorizer()
    scripts.fast_call = respond  # type: ignore[assignment]
    scripts.fast = call_tools(("query", {"request": "total spending on groceries in May 2025"}))
    conversation_id = await new_conversation(client, profile_id)

    await chat(conversation_id, "Wie viel habe ich im Mai fuer Lebensmittel ausgegeben?")
    before = respond.queries[-1]  # type: ignore[attr-defined]
    assert "no booking is categorized yet" in before

    await categorize(client, profile_id, await last_import(client, profile_id))
    await chat(conversation_id, "Und im Juni?")
    after = respond.queries[-1]  # type: ignore[attr-defined]

    assert "only 408 of 433 bookings have a category" in after
    assert "Groceries (Supermarket, Bakery, Drugstore)" in after
