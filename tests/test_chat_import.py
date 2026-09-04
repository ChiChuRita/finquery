"""Import through the chat: an attached file, a mapping to confirm, a typed transaction.

Every test posts what the browser posts. An attachment is a file part with a data URL, which is
what `useChat` sends for a file dropped into the composer, and a Question card answer is the
tool output on the assistant message, the same shape ticket 07 tests. The chat model and every
sub-agent one of these turns starts are scripted, so what is asserted is the pipeline: the rows
that landed, the progress the transcript saw, the card that was asked and the booking a
confirmation created.
"""

import base64
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from .conftest import SYNTHETIC, Scripts, new_conversation, parse_sse, script
from .test_categorization import (
    TOTAL_ROWS,
    _tool_returns,
    answer,
    answer_card,
    outputs_of,
    scripted_categorizer,
)
from .test_import import UNKNOWN_BANK_MAPPING

SPARKASSE = SYNTHETIC / "sparkasse-2025.csv"
UNKNOWN_BANK = SYNTHETIC / "unknown-bank-2025.csv"
STATEMENT_PDF = SYNTHETIC / "sparkasse-kontoauszug-2025.pdf"

# The four PayPal payments to friends: what the categorizer is honestly unsure about.
UNCERTAIN = ["jonas keller", "max schulz", "anna weber", "lea hoffmann"]


def data_url(path: Path, media_type: str) -> str:
    return f"data:{media_type};base64,{base64.b64encode(path.read_bytes()).decode()}"


def attach(
    conversation_id: str, text: str, path: Path, media_type: str = "text/csv", message_id: str = "u1"
) -> dict[str, Any]:
    """The request a browser sends for a file dropped into the composer."""
    return {
        "id": conversation_id,
        "trigger": "submit-message",
        "messages": [
            {
                "id": message_id,
                "role": "user",
                "parts": [
                    {"type": "text", "text": text},
                    {
                        "type": "file",
                        "mediaType": media_type,
                        "filename": path.name,
                        "url": data_url(path, media_type),
                    },
                ],
            }
        ],
    }


def sub_agents(
    *,
    mapping: dict[str, Any] | None = None,
    account_name: str = "Volksbank Giro",
    transactions: list[dict[str, Any]] | None = None,
):
    """The fast slot answering every sub-agent these turns start.

    The categorizer, the follow-up step and the distillation pass come from ticket 07's script;
    the two forced tools this ticket adds are answered here. `calls` records which sub-agent ran,
    which is how a test sees that a preset never asked the model for a mapping.
    """
    categorizer = scripted_categorizer()
    calls: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tools = [tool.name for tool in info.output_tools]
        if tools == ["propose_mapping"]:
            calls.append("propose_mapping")
            assert info.allow_text_output is False
            payload = {"mapping": mapping, "account_name": account_name, "note": "Soll is out, Haben in."}
            return ModelResponse(parts=[ToolCallPart("propose_mapping", json.dumps(payload))])
        if tools == ["propose_transactions"]:
            calls.append("propose_transactions")
            assert info.allow_text_output is False
            return ModelResponse(
                parts=[ToolCallPart("propose_transactions", json.dumps({"transactions": transactions or []}))]
            )
        if tools == ["categorize"]:
            calls.append("categorize")
        return categorizer(messages, info)

    respond.calls = calls  # type: ignore[attr-defined]
    return respond


def _call(index: int, name: str, **args: Any) -> dict[int, DeltaToolCall]:
    return {index: DeltaToolCall(name=name, json_args=json.dumps(args))}


def _returns(messages: list[ModelMessage], name: str) -> list[dict[str, Any]]:
    """What one tool returned during the turn being answered, oldest first."""
    return [result for tool, result in _tool_returns(messages) if tool == name]


def importing(file_name: str, **extra: Any):
    """A chat model that imports the attached file and then does what the tool asked for.

    It never states a figure of its own: the summary it answers with is the one the tool
    counted, and the card it asks with is the one the tool built. That is the contract the
    system prompt describes, scripted.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        imports = _returns(messages, "import_file")
        cards = _returns(messages, "ask_user")
        if not imports:
            yield _call(0, "import_file", file_name=file_name, **extra)
            return
        latest = imports[-1]
        if latest["status"] == "confirm_mapping":
            confirmed = any(
                a.get("value") == "confirm" for card in cards for a in card.get("answers", [])
            )
            if confirmed:
                yield _call(0, "import_file", file_name=file_name, confirmed=True, **extra)
            else:
                yield _call(0, "ask_user", **latest["card"])
            return
        if latest["status"] == "imported":
            # A card about the merchants follows unless one was already answered about a row:
            # the mapping card is answered with an empty ref, a Question card with a merchant.
            asked = any(a.get("ref") for card in cards for a in card.get("answers", []))
            yield latest["summary"]
            if latest["questions"] and not asked:
                yield _call(1, "ask_user", **_card_from(latest["questions"]))
            return
        yield latest.get("message") or latest.get("error") or "Nothing happened."

    return fn


def _card_from(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """The Question card the assistant builds from what the tool returned, as ticket 07's does."""
    return {
        "title": "Which category do these belong to?",
        "rows": [
            {
                "ref": question["pattern"],
                "label": question["label"],
                "description": question["description"],
                "amount_cents": question["amount_cents"],
                "date": question["date"],
                "bookings": question["bookings"],
                "options": [{"label": option, "value": option} for option in question["options"]],
            }
            for question in questions
        ],
        "allow_free_text": True,
    }


def typing_a_transaction(text: str):
    """A chat model that extracts what the user typed, asks the preview card, then adds it."""

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        previews = _returns(messages, "extract_transaction")
        cards = _returns(messages, "ask_user")
        added = _returns(messages, "add_transaction")
        if added:
            row = added[-1]
            yield f"Added {row['description']} for {row['amount_cents'] / 100:.2f} EUR to {row['account']}."
            return
        if not previews:
            yield _call(0, "extract_transaction", text=text)
            return
        if not cards:
            yield _call(0, "ask_user", **previews[-1]["card"])
            return
        confirmed = [a["ref"] for card in cards for a in card.get("answers", []) if a.get("value") == "add"]
        for index, ref in enumerate(confirmed):
            yield _call(index, "add_transaction", ref=ref)

    return fn


def progress_of(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if chunk["type"] == "data-import_progress"]


def cards_in(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [chunk for chunk in chunks if chunk["type"] == "tool-input-available" and chunk["toolName"] == "ask_user"]


async def transcript(client: httpx.AsyncClient, conversation_id: str) -> dict[str, Any]:
    return dict((await client.get(f"/api/conversations/{conversation_id}")).json())


def pending_card(message: dict[str, Any]) -> dict[str, Any]:
    """The card of a turn that parked on it, as the browser finds it after a reload."""
    return next(part for part in message["parts"] if part["type"] == "tool-ask_user")


async def rows_of(client: httpx.AsyncClient, profile_id: str) -> list[dict[str, Any]]:
    page = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()
    return list(page["rows"])


async def test_a_csv_dropped_into_the_chat_is_imported_and_categorized(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    responder = sub_agents()
    scripts.fast = importing(SPARKASSE.name)
    scripts.fast_call = responder  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat", json=attach(conversation_id, "import this", SPARKASSE)
    )
    assert response.status_code == 200, response.text
    chunks = parse_sse(response.text)

    # The tool reported its way through the file while it worked, and none of it was persisted.
    stages = [chunk["data"]["stage"] for chunk in progress_of(chunks)]
    assert stages == ["read", "mapping", "imported", "categorizing", "categorized"]
    assert all(chunk["transient"] is True for chunk in progress_of(chunks))
    read, _, imported, _, categorized = progress_of(chunks)
    assert read["data"]["counts"]["rows_read"] == TOTAL_ROWS
    assert imported["data"]["counts"]["imported"] == TOTAL_ROWS
    assert categorized["data"]["counts"]["needs_review"] == 25

    # The preset recognized the file, so no model wrote a mapping.
    assert "propose_mapping" not in responder.calls  # type: ignore[attr-defined]

    output = outputs_of(chunks)[0]
    assert output["status"] == "imported"
    assert (output["rows_read"], output["imported"], output["duplicates"]) == (TOTAL_ROWS, TOTAL_ROWS, 0)
    assert output["account"] == "Sparkasse Girokonto"
    assert output["categorized"]["needs_review"] == 25
    assert f"{TOTAL_ROWS} of {TOTAL_ROWS} bookings" in output["summary"]
    assert [question["pattern"] for question in output["questions"]] == UNCERTAIN

    # The assistant said the summary the tool counted and asked about the rest in one card.
    assert f"{TOTAL_ROWS} of {TOTAL_ROWS} bookings" in answer(chunks)
    assert [row["ref"] for row in cards_in(chunks)[0]["input"]["rows"]] == UNCERTAIN

    assert len(await rows_of(client, profile_id)) == TOTAL_ROWS
    imports = (await client.get("/api/imports", params={"profile_id": profile_id})).json()
    assert (imports[0]["file_name"], imports[0]["imported_count"]) == (SPARKASSE.name, TOTAL_ROWS)

    # A reload shows the attachment chip on the user's message and the same steps after it.
    reloaded = await transcript(client, conversation_id)
    user = reloaded["messages"][0]
    assert [part["type"] for part in user["parts"]] == ["text", "file"]
    assert user["parts"][1]["filename"] == SPARKASSE.name
    assert [part["type"] for part in reloaded["messages"][1]["parts"]] == [
        "tool-import_file",
        "text",
        "tool-ask_user",
        "data-context",
    ]
    # The chip links to the stored file, which is still there.
    stored = await client.get(user["parts"][1]["url"])
    assert stored.status_code == 200
    assert len(stored.content) == SPARKASSE.stat().st_size


async def test_the_same_attachment_is_never_imported_twice(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast = importing(SPARKASSE.name)
    scripts.fast_call = sub_agents()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    await client.post(
        f"/api/conversations/{conversation_id}/chat", json=attach(conversation_id, "import this", SPARKASSE)
    )
    assert len(await rows_of(client, profile_id)) == TOTAL_ROWS

    # The user asks again in the next turn. The file is still attached to the conversation, so
    # the tool finds it, sees the import it already produced, and writes nothing.
    again = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"id": conversation_id, "trigger": "submit-message",
              "messages": [{"id": "u2", "role": "user", "parts": [{"type": "text", "text": "import it again"}]}]},
    )
    assert again.status_code == 200, again.text
    output = outputs_of(parse_sse(again.text))[0]
    assert output["status"] == "already_imported"
    assert "already imported" in answer(parse_sse(again.text))
    assert len(await rows_of(client, profile_id)) == TOTAL_ROWS
    imports = (await client.get("/api/imports", params={"profile_id": profile_id})).json()
    assert len(imports) == 1


async def test_an_unknown_layout_asks_for_the_mapping_and_the_answer_finishes_the_import(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    responder = sub_agents(mapping=UNKNOWN_BANK_MAPPING)
    scripts.fast = importing(UNKNOWN_BANK.name)
    scripts.fast_call = responder  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat", json=attach(conversation_id, "import this", UNKNOWN_BANK)
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)

    # No preset knows this header, so the mapping was proposed and nothing was committed.
    assert responder.calls == ["propose_mapping"]  # type: ignore[attr-defined]
    output = outputs_of(chunks)[0]
    assert output["status"] == "confirm_mapping"
    assert output["mapping"]["debit_column"] == "Soll"
    assert await rows_of(client, profile_id) == []

    card = cards_in(chunks)[0]["input"]
    assert card["title"] == f"Import {UNKNOWN_BANK.name} with this mapping?"
    assert [option["value"] for option in card["options"]] == ["confirm", "reject"]
    # The card shows what the mapping says and the first bookings it produces.
    assert "money out: Soll" in card["note"]
    assert "2025-01-01" in card["note"]

    pending = (await transcript(client, conversation_id))["messages"][1]
    answers = {"answers": [{"ref": "", "value": "confirm", "text": None}]}
    second = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(conversation_id, pending["id"], pending_card(pending), answers),
    )
    assert second.status_code == 200, second.text
    resumed = parse_sse(second.text)

    # The confirmed mapping was the stored one: the model was not asked for it a second time.
    assert responder.calls == ["propose_mapping", "categorize", "categorize"]  # type: ignore[attr-defined]
    committed = [out for out in outputs_of(resumed) if out.get("status") == "imported"][0]
    assert committed["imported"] == TOTAL_ROWS
    assert committed["account"] == "Volksbank Giro"
    assert len(await rows_of(client, profile_id)) == TOTAL_ROWS

    # One turn, rewritten: the answered card, the second import step and the answer, with the
    # chip still on the user's message.
    reloaded = await transcript(client, conversation_id)
    assert [message["role"] for message in reloaded["messages"]] == ["user", "assistant"]
    assert [part["type"] for part in reloaded["messages"][0]["parts"]] == ["text", "file"]
    assert [part["type"] for part in reloaded["messages"][1]["parts"]] == [
        "tool-import_file",
        "tool-ask_user",
        "tool-import_file",
        "text",
        "tool-ask_user",
        "data-context",
    ]
    assert reloaded["messages"][1]["parts"][1]["output"] == answers


async def test_a_typed_transaction_is_previewed_and_confirming_it_creates_the_row(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    typed = "I paid 12 EUR cash for lunch today"
    responder = sub_agents(
        transactions=[
            {
                "booked_on": "2025-06-02",
                "amount": "12.00",
                "direction": "out",
                "description": "Lunch",
                "counterparty": None,
                "account_name": "Cash",
            }
        ]
    )
    scripts.fast = typing_a_transaction(typed)
    scripts.fast_call = responder  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"id": conversation_id, "trigger": "submit-message",
              "messages": [{"id": "u1", "role": "user", "parts": [{"type": "text", "text": typed}]}]},
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)

    preview = outputs_of(chunks)[0]
    assert preview["status"] == "preview"
    assert preview["drafts"] == [
        {
            "ref": "t1",
            "booked_on": "2025-06-02",
            "amount_cents": -1200,
            "description": "Lunch",
            "counterparty": None,
            "account": "Cash",
        }
    ]
    card = cards_in(chunks)[0]["input"]
    row = card["rows"][0]
    assert (row["ref"], row["label"], row["amount_cents"]) == ("t1", "Lunch", -1200)
    assert [option["value"] for option in row["options"]] == ["add", "discard"]
    # The card says which kind of decision it collects, and this one is not categorization:
    # `add_transaction` acts on it, so `finquery.answers` must pass the answers through
    # untouched instead of offering "add" to `set_rule` as a category name.
    assert card["apply"] == {"kind": "transaction_draft"}
    # A preview writes nothing.
    assert await rows_of(client, profile_id) == []

    pending = (await transcript(client, conversation_id))["messages"][1]
    answers = {"answers": [{"ref": "t1", "value": "add", "text": None}]}
    second = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(conversation_id, pending["id"], pending_card(pending), answers),
    )
    assert second.status_code == 200, second.text
    resumed = parse_sse(second.text)

    answered = [part for part in (await transcript(client, conversation_id))["messages"][1]["parts"]
                if part["type"] == "tool-ask_user"][0]
    assert answered["output"].get("applied") is None, "nothing was applied in code for a draft card"

    added = [out for out in outputs_of(resumed) if out.get("status") == "added"][0]
    assert (added["amount_cents"], added["description"], added["account"]) == (-1200, "Lunch", "Cash")
    assert "12.00 EUR" in answer(resumed)

    rows = await rows_of(client, profile_id)
    assert len(rows) == 1
    assert (rows[0]["amount_cents"], rows[0]["description"], rows[0]["source"]) == (-1200, "Lunch", "manual")
    assert rows[0]["booked_on"] == "2025-06-02"
    assert rows[0]["account"] == "Cash"
    # It went through categorization, so it carries an enrichment whatever its category came to.
    assert rows[0]["title"]


async def test_a_pdf_attachment_is_stored_and_goes_to_the_extraction_path(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The PDF is stored and read, not turned away.

    Until ticket 11 this asserted the sentence that said a PDF could not be read yet. What the
    tool does with one now is `tests/test_extraction.py`; what this pins is the half that is
    this ticket's: the bytes are stored per conversation, the chip links to them, and the file
    reaches the reader rather than a refusal.
    """
    scripts.fast = importing(STATEMENT_PDF.name)
    # The extraction sub-agent answers with nothing at all, so no booking is invented here.
    scripts.fast_call = _reads_nothing()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "import this statement", STATEMENT_PDF, media_type="application/pdf"),
    )
    assert response.status_code == 200, response.text
    chunks = parse_sse(response.text)

    output = outputs_of(chunks)[0]
    assert output["status"] == "nothing_found"
    assert await rows_of(client, profile_id) == []

    # The file is stored all the same, which is what the extraction reads.
    reloaded = await transcript(client, conversation_id)
    chip = reloaded["messages"][0]["parts"][1]
    assert (chip["type"], chip["filename"], chip["mediaType"]) == ("file", STATEMENT_PDF.name, "application/pdf")
    stored = await client.get(chip["url"])
    assert stored.status_code == 200
    assert stored.headers["content-type"] == "application/pdf"


def _reads_nothing():
    """A fast slot whose extraction finds no booking on any page."""
    categorizer = scripted_categorizer()

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if [tool.name for tool in info.output_tools] == ["read_statement"]:
            return ModelResponse(parts=[ToolCallPart("read_statement", json.dumps({"rows": []}))])
        return categorizer(messages, info)

    return respond


async def test_a_file_of_a_kind_we_cannot_read_is_refused_before_the_turn_starts(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast = script("this model is never asked anything")
    conversation_id = await new_conversation(client, profile_id)
    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={
            "id": conversation_id,
            "trigger": "submit-message",
            "messages": [
                {
                    "id": "u1",
                    "role": "user",
                    "parts": [
                        {"type": "text", "text": "import this"},
                        {
                            "type": "file",
                            "mediaType": "application/zip",
                            "filename": "statements.zip",
                            "url": "data:application/zip;base64,UEsDBAoAAAAAAA==",
                        },
                    ],
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "not a kind FinQuery can read" in response.json()["detail"]
    # The turn never ran: nothing was stored and nothing was said.
    assert (await transcript(client, conversation_id))["messages"] == []


async def test_a_typed_transaction_never_stores_the_word_null_as_its_counterparty(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The extraction sub-agent answers an optional field with the word, not with nothing.

    "I paid 12 EUR cash for lunch today" created a booking whose counterparty was the string
    "null" (review of 2026-09-04), while the same booking added by hand stores a real null.
    """
    typed = "I paid 12 EUR cash for lunch today"
    responder = sub_agents(
        transactions=[
            {
                "booked_on": "2025-06-02",
                "amount": "12.00",
                "direction": "out",
                "description": "Lunch",
                "counterparty": "null",
                "account_name": "Cash",
            }
        ]
    )
    scripts.fast = typing_a_transaction(typed)
    scripts.fast_call = responder  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"id": conversation_id, "trigger": "submit-message",
              "messages": [{"id": "u1", "role": "user", "parts": [{"type": "text", "text": typed}]}]},
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)
    assert outputs_of(chunks)[0]["drafts"][0]["counterparty"] is None
    # The preview row names the account only, never "null · Cash".
    assert cards_in(chunks)[0]["input"]["rows"][0]["description"] == "Cash"

    pending = (await transcript(client, conversation_id))["messages"][1]
    second = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(
            conversation_id,
            pending["id"],
            pending_card(pending),
            {"answers": [{"ref": "t1", "value": "add", "text": None}]},
        ),
    )
    assert second.status_code == 200, second.text

    rows = await rows_of(client, profile_id)
    assert len(rows) == 1
    assert rows[0]["counterparty"] is None
