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

from finquery.api.chat import ALREADY_ANSWERED

from .conftest import (
    Chat,
    Scripts,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
    parse_sse,
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

# What the categorizer fills its `reasoning` field with before it files a merchant.
READING = "read each merchant off its text"


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
            return ModelResponse(
                parts=[ToolCallPart("run_sql", json.dumps({"reasoning": "one row", "sql": "SELECT 1 AS one"}))]
            )
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
            for key in keys_in(prompt)
            if key in guesses
        ]
        return ModelResponse(
            parts=[ToolCallPart("categorize", json.dumps({"reasoning": READING, "merchants": merchants}))]
        )

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
    """The merchant keys of the batch, which is everything after the last heading.

    The worked example of the prompt is written in the same shape, keys included, so a search
    over the whole text would find its merchants too."""
    return set(_KEY.findall(prompt.rsplit("Categorize these", 1)[-1]))


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


def echo_applied(followups: Sequence[str] = ()):
    """A chat turn that only summarizes an answered card, quoting what the server applied.

    It calls no tool, so anything that moves in the database was moved by code. `settings`
    records what the resumed half was run with, and `followups` is what the post-turn step
    offers, so a test can check that a card turn ends with a way forward.
    """
    settings: list[object] = []

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "\n".join(followups) if followups else "No follow-ups."
            return
        settings.append(info.model_settings)
        card = next((result for name, result in _tool_returns(messages) if name == "ask_user"), None)
        yield f"Summarized: {card['applied']}" if card else "Nothing to summarize."

    fn.settings = settings  # type: ignore[attr-defined]
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


async def test_a_batch_naming_a_category_the_household_does_not_have_is_resubmitted(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """A refused answer is handed back with what is wrong with it, not thrown away (ticket 42).

    A category this profile does not carry costs the merchant its category silently, and the
    model that wrote it usually has the right one: it just has to be told which line is wrong.
    """
    await import_synthetic(client, profile_id)
    prompts: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="No follow-ups.")])
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        prompt = _last_user_prompt(messages)
        prompts.append(prompt)
        first = len(prompts) == 1
        merchants = [
            {
                "key": key,
                # The first answer files the landlord under a category nobody has, and leaves
                # the employer out altogether.
                "category": "Wohnkosten" if first and key == "hausverwaltung bergmann" else GUESSES[key][0],
                "subcategory": GUESSES[key][1],
                "confidence": GUESSES[key][2],
                "title": key.title(),
                "description": "guessed by the model",
            }
            for key in keys_in(prompt)
            if key in GUESSES and not (first and key == "mustermann systems")
        ]
        return ModelResponse(
            parts=[ToolCallPart("categorize", json.dumps({"reasoning": "rent and salary", "merchants": merchants}))]
        )

    scripts.fast_call = respond  # type: ignore[assignment]

    report = await categorize(client, profile_id, await last_import(client, profile_id))

    assert len(prompts) == 2, "the refused batch was handed back exactly once"
    resubmit = prompts[1]
    assert "Your last answer could not be filed." in resubmit
    assert "Your reasoning was:\nrent and salary" in resubmit
    assert "hausverwaltung bergmann -> Wohnkosten > Rent" in resubmit
    assert "this household has no category `Wohnkosten`" in resubmit
    assert "`mustermann systems` has no entry" in resubmit
    assert "The first line of the reasoning says what you changed." in resubmit
    # The corrected answer is the one that was filed.
    assert report["by_model"] == 24
    rent = await rows_of(client, profile_id, "MIETE WOHNUNG")
    assert {(row["category"], row["subcategory"]) for row in rent} == {("Housing", "Rent")}


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


async def test_answering_a_question_card_applies_the_answers_in_code(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The rules are stored before the model runs again, and it is told what was applied.

    The fast model is never asked to sequence one `set_rule` call per answer: it looped for
    minutes on that and stored nothing (review of 2026-09-04). Here the script makes no tool
    call at all and the rows still move.
    """
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
    answers = [
        {"ref": "anna weber", "value": "Dining > Restaurant", "text": None},
        {"ref": "jonas keller", "value": None, "text": "Leisure"},
    ]
    summarize = echo_applied(followups=["Show me what changed?", "Which merchants are left?"])
    scripts.fast = summarize
    # Categorization is behind us and applying the answers is code, so nothing on this half of
    # the turn calls a sub-agent with a schema. Clearing it lets the post-turn steps reach the
    # script above, which is what has the follow-ups.
    scripts.fast_call = None
    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(conversation_id, detail["messages"][1]["id"], card, {"answers": answers}),
    )
    assert response.status_code == 200, response.text
    chunks = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]

    # The run continued from the pending call. The tool result is the user's answers plus the
    # line stating what the server already did with them.
    resolved = [c for c in chunks if c["type"] == "tool-output-available"]
    assert len(resolved) == 1, "the model called no tool of its own"
    assert resolved[0]["toolCallId"] == card["toolCallId"]
    assert resolved[0]["output"]["answers"] == answers
    applied = resolved[0]["output"]["applied"]
    assert "Anna Weber" in applied and "Dining > Restaurant" in applied and "6 bookings" in applied
    assert "Jonas Keller" in applied and "Leisure" in applied and "7 bookings" in applied
    assert "Max Schulz" in applied, "the rows nobody answered are named as skipped"
    # And the one sentence the model is asked to write instead of the line above, counted in
    # code: the resumed half used to list every merchant the card below already named.
    assert resolved[0]["output"]["say"] == "2 merchants now have rules and 2 are still to decide."
    # The model's own answer quotes the line, which is how we know it was told rather than asked.
    assert answer(chunks) == f"Summarized: {applied}"
    # Nothing is left to reason about on this half of the turn, so it runs with reasoning off:
    # the fast model collapsed into a repetition loop when it was left to think here.
    # It also carries the sub-agent output ceiling, because it runs with the sub-agent settings.
    assert summarize.settings[0] == {"openrouter_reasoning": {"enabled": False}, "max_tokens": 3072}  # type: ignore[attr-defined]

    anna = await rows_of(client, profile_id, "ANNA WEBER")
    assert {(row["category"], row["subcategory"]) for row in anna} == {("Dining", "Restaurant")}
    jonas = await rows_of(client, profile_id, "JONAS KELLER")
    assert {row["category"] for row in jonas} == {"Leisure"}
    # The rows nobody answered are still Needs review.
    assert {row["category"] for row in await rows_of(client, profile_id, "MAX SCHULZ")} == {None}

    # One turn, one assistant message: the card now carries its answer, then the text, then the
    # stats of the request that finished the turn. A reload shows what the stream showed.
    reloaded = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in reloaded["messages"]] == ["user", "assistant"]
    parts = reloaded["messages"][1]["parts"]
    assert [part["type"] for part in parts] == [
        "text",
        "tool-ask_user",
        "text",
        "data-context",
        # A resumed card turn has no user prompt of its own, and used to be the one turn in the
        # app that ended with no way forward.
        "data-followups",
    ]
    assert parts[1]["state"] == "output-available"
    assert parts[1]["output"]["applied"] == applied
    assert parts[4]["data"]["suggestions"] == ["Show me what changed?", "Which merchants are left?"]


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
    # Nothing was applied, so the output is the answers as they came in.
    assert parts[1]["output"] == {"answers": []}


async def test_a_bulk_edit_phrase_is_not_a_rule_pattern(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """`set_rule` is for teaching a merchant, not for changing rows in bulk.

    A bulk change belongs in a changeset with a preview the user applies, so a pattern that
    reads like the request itself is refused with the tool to use instead.
    """
    await import_synthetic(client, profile_id)
    scripts.fast = call_tools(("set_rule", {"pattern": "all Netflix rows", "category": "Subscriptions"}))
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Recategorize all Netflix rows as Subscriptions.")

    output = outputs_of(chunks)[0]
    assert "propose_changeset" in output["error"]
    assert output.get("matched") is None, "nothing was touched"
    # The bookings are untouched: this import was never categorized, so they are Needs review.
    assert {row["category"] for row in await rows_of(client, profile_id, "NETFLIX")} == {None}


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
    assert "category Groceries / subcategories: Supermarket, Bakery, Drugstore" in after



def narrates_the_queue():
    """A chat turn that asks `review_batch` for the queue and then writes about it in prose.

    Exactly what the fast model did on 2026-09-05: "There is one merchant left to categorize",
    with no card below it and nothing for the user to press.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        queues = [result for name, result in _tool_returns(messages) if name == "review_batch"]
        if not queues:
            yield {0: DeltaToolCall(name="review_batch", json_args="{}")}
            return
        yield f"There are {queues[-1]['pending_merchants']} merchants left to categorize."

    return fn


async def test_a_review_queue_the_model_only_narrates_still_reaches_the_user_as_a_card(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """`review_batch` returning a queue is always followed by a card (e2e of 2026-09-05, M1).

    The card is already built, by the same `categorize.review_card` the seeded review
    conversation uses, so when the model writes about the queue instead of showing it the server
    shows it. The run then parks on that call exactly as if the model had made it, which is what
    answering it below proves.
    """
    await import_synthetic(client, profile_id)
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    await categorize(client, profile_id, await last_import(client, profile_id))

    scripts.fast = narrates_the_queue()
    conversation_id = await new_conversation(client, profile_id)
    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={
            "id": conversation_id,
            "trigger": "submit-message",
            "messages": [
                {"id": "u1", "role": "user", "parts": [{"type": "text", "text": "Which merchants are left?"}]}
            ],
        },
    )
    assert response.status_code == 200, response.text
    chunks = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: {")]

    cards = [c for c in chunks if c["type"] == "tool-input-available" and c["toolName"] == "ask_user"]
    assert len(cards) == 1, "the queue reached the user as prose and nothing else"
    card = cards[0]["input"]
    assert {row["ref"] for row in card["rows"]} <= MODEL_MERCHANTS
    assert card["rows"], "an empty card is no card"
    assert card["apply"] == {"kind": "category_rule"}
    # The prose the model did write is still the answer above the card.
    assert "merchants left to categorize" in answer(chunks)
    # A turn waiting on a card offers no follow-ups.
    assert [c for c in chunks if c["type"] == "data-followups"] == []

    # It is a real pending call: answering it resumes the run and the answers are applied.
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    pending = next(part for part in detail["messages"][1]["parts"] if part["type"] == "tool-ask_user")
    assert pending["state"] == "approval-requested"
    scripts.fast = echo_applied()
    scripts.fast_call = None
    resumed = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(
            conversation_id,
            detail["messages"][1]["id"],
            pending,
            {"answers": [{"ref": "anna weber", "value": "Dining > Restaurant", "text": None}]},
        ),
    )
    assert resumed.status_code == 200, resumed.text
    rows = await rows_of(client, profile_id, "ANNA WEBER")
    assert {(row["category"], row["subcategory"]) for row in rows} == {("Dining", "Restaurant")}


async def _review_conversation(
    client: httpx.AsyncClient, profile_id: str, scripts: Scripts
) -> tuple[str, dict[str, Any]]:
    """A conversation whose first turn is parked on a four-merchant Question card."""
    await import_synthetic(client, profile_id)
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    import_id = await last_import(client, profile_id)
    await categorize(client, profile_id, import_id)
    opened = (
        await client.post(f"/api/imports/{import_id}/review-conversation", json={"profile_id": profile_id})
    ).json()
    detail = (await client.get(f"/api/conversations/{opened['conversation_id']}")).json()
    return str(opened["conversation_id"]), detail


async def test_a_card_answered_after_a_newer_message_still_resumes_its_own_turn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Ticket 29: the run a card parked is the run that resumes, whatever came after it.

    The user typed something else before coming back to the card, so the card's call is a turn
    back. The turn it belongs to is looked up rather than assumed to be the last one, the
    prompt for the resumed run ends where that turn ended (which is where the framework looks
    for a pending call), and the rewritten turn keeps its place in the transcript.
    """
    conversation_id, detail = await _review_conversation(client, profile_id, scripts)
    card = detail["messages"][1]["parts"][1]

    # A whole turn in between: a typed question, asked and answered.
    scripts.fast = script("You spent 403,60 EUR on groceries in May 2025.")
    scripts.fast_call = None
    _, chunks = await chat(conversation_id, "How much did I spend on groceries in May?")
    assert "403,60" in answer(chunks)

    prompts: list[list[ModelMessage]] = []
    summarize = echo_applied(followups=["Which merchants are left?"])

    async def record(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        if not is_followup_request(messages) and not is_distillation_request(messages):
            prompts.append(messages)
        async for item in summarize(messages, info):
            yield item

    scripts.fast = record
    answers = [{"ref": "anna weber", "value": "Dining > Restaurant", "text": None}]
    resumed = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(conversation_id, detail["messages"][1]["id"], card, {"answers": answers}),
    )
    assert resumed.status_code == 200, resumed.text
    # The browser streams a resumed answer into its newest message, and this card is not on it,
    # so the output chunk for the call is left out rather than sent somewhere it cannot land.
    assert outputs_of(parse_sse(resumed.text)) == []
    assert "Summarized: Applied: Anna Weber" in resumed.text

    # The answers were applied in code, exactly as they are for a card nothing came after.
    rows = await rows_of(client, profile_id, "ANNA WEBER")
    assert {(row["category"], row["subcategory"]) for row in rows} == {("Dining", "Restaurant")}

    # The resumed run was given the card's own turn as the end of its history, because that is
    # where the pending call is. The question asked in between is in the transcript, not here.
    text = " ".join(
        str(part.content)
        for message in prompts[0]
        for part in message.parts
        if part.part_kind in {"user-prompt", "text"}
    )
    assert "Categorize the import I just did." in text
    assert "groceries" not in text

    # The rewritten turn kept its place: the card and what it applied are still the first turn,
    # the question asked in between is still the second.
    reloaded = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in reloaded["messages"]] == ["user", "assistant", "user", "assistant"]
    first = reloaded["messages"][1]["parts"]
    assert [part["type"] for part in first] == ["text", "tool-ask_user", "text", "data-context", "data-followups"]
    assert first[1]["state"] == "output-available"
    # The `applied` line reaches the card with the stored turn, which is what the browser reads
    # back once the resumed turn is over.
    assert "Anna Weber" in first[1]["output"]["applied"]
    assert reloaded["messages"][2]["parts"][0]["text"] == "How much did I spend on groceries in May?"


async def test_a_card_whose_merchant_moved_meanwhile_still_applies_and_counts_honestly(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The user categorized the merchant themselves while the card sat there unanswered.

    The card is not a claim about the rows: `set_rule` runs against the data as it is when the
    answer arrives, so the answer wins and the count is what actually moved. Nothing is refused
    for having been overtaken.
    """
    conversation_id, detail = await _review_conversation(client, profile_id, scripts)
    card = detail["messages"][1]["parts"][1]

    # A rule taught in plain language in the meantime, in another conversation.
    scripts.fast = call_tools(("set_rule", {"pattern": "anna weber", "category": "Groceries"}))
    _, taught = await chat(await new_conversation(client, profile_id), "Anna Weber is always Groceries.")
    assert "6 matched, 6 updated" in answer(taught)
    assert {row["category"] for row in await rows_of(client, profile_id, "ANNA WEBER")} == {"Groceries"}

    scripts.fast = echo_applied()
    resumed = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(
            conversation_id,
            detail["messages"][1]["id"],
            card,
            {"answers": [{"ref": "anna weber", "value": "Dining > Restaurant", "text": None}]},
        ),
    )

    assert resumed.status_code == 200, resumed.text
    applied = outputs_of(parse_sse(resumed.text))[0]["applied"]
    # Six bookings moved again, from Groceries to what the card was answered with.
    assert "Anna Weber" in applied and "Dining > Restaurant" in applied and "6 bookings" in applied
    assert {(r["category"], r["subcategory"]) for r in await rows_of(client, profile_id, "ANNA WEBER")} == {
        ("Dining", "Restaurant")
    }


async def test_a_card_answered_twice_is_refused_rather_than_applied_again(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The second answer is another browser tab, and replaying it would apply everything twice."""
    conversation_id, detail = await _review_conversation(client, profile_id, scripts)
    card = detail["messages"][1]["parts"][1]
    body = answer_card(
        conversation_id,
        detail["messages"][1]["id"],
        card,
        {"answers": [{"ref": "anna weber", "value": "Dining > Restaurant", "text": None}]},
    )

    scripts.fast = echo_applied()
    scripts.fast_call = None
    assert (await client.post(f"/api/conversations/{conversation_id}/chat", json=body)).status_code == 200

    again = await client.post(f"/api/conversations/{conversation_id}/chat", json=body)
    assert again.status_code == 409
    assert again.json()["detail"] == ALREADY_ANSWERED
    # One turn, not two, and one rule: nothing was applied a second time.
    reloaded = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in reloaded["messages"]] == ["user", "assistant"]
