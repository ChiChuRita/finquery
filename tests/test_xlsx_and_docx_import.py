"""Excel workbooks and Word documents through the chat, at the same seam as every other file.

An XLSX is the CSV mapping engine one step earlier: the same header detection, the same presets
and the same Question card, with the cells' own types kept so a number is never re-read out of a
string. A DOCX is the statement reader over the document's own text, so every figure is held to
the verbatim guard and the running balance the way a printed page is (ADR 0011).

The chat model and every sub-agent are scripted, so what these tests assert is the pipeline: the
rows that landed with their exact cents and days, the card that was asked, the sheet the picker
switched to, and the review card a figure that is not in the document produces.
"""

import base64
import io
import json
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import openpyxl
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from .conftest import SYNTHETIC, Scripts, new_conversation, parse_sse
from .test_categorization import TOTAL_ROWS, _tool_returns, answer_card, outputs_of
from .test_chat_import import attach, cards_in, pending_card, progress_of, rows_of, sub_agents, transcript
from .test_extraction import importing as importing_statement
from .test_extraction import statement_reader

WORKBOOK = SYNTHETIC / "sparkasse-2025.xlsx"
WORD_STATEMENT = SYNTHETIC / "statement-excerpt.docx"

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

DOCX_BOOKINGS = 15
DOCX_OPENING = 421055
DOCX_CLOSING = 233258

UNKNOWN_HEADER = ("Belegnr", "Empfänger", "Datum", "Vorgangsart", "Buchungsinfo", "Soll", "Haben", "Wg")
UNKNOWN_MAPPING = {
    "date_column": "Datum",
    "debit_column": "Soll",
    "credit_column": "Haben",
    "description_column": "Buchungsinfo",
    "counterparty_column": "Empfänger",
    # What a model proposes for a German export, and what the cells say instead: these two are
    # the fields `with_cell_types` corrects for a typed sheet.
    "date_format": "DD.MM.YYYY",
    "decimal_separator": "comma",
}

JANUARY = (
    (date(2025, 1, 9), "REWE Markt GmbH", "REWE SAGT DANKE", Decimal("-40.90")),
    (date(2025, 1, 28), "Mustermann Systems GmbH", "GEHALT 01/2025", Decimal("2850.00")),
)
FEBRUARY = (
    (date(2025, 2, 3), "ALDI SUED", "ALDI SUED SAGT DANKE", Decimal("-31.45")),
    (date(2025, 2, 14), "Deutsche Bahn AG", "DB FERNVERKEHR TICKET", Decimal("-89.00")),
)


def workbook_bytes(sheets: dict[str, tuple[tuple[object, ...], ...]]) -> bytes:
    """A workbook whose dates and amounts are cells rather than text."""
    book = openpyxl.Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def unknown_sheet(bookings: tuple[tuple[date, str, str, Decimal], ...]) -> tuple[tuple[object, ...], ...]:
    """A sheet no preset knows: a title block, the header, then money in two columns."""
    return (
        ("Kontoumsätze Musterbank",),
        (),
        UNKNOWN_HEADER,
        *(
            (
                f"B{index:05d}",
                counterparty,
                booked_on,
                "Umsatz",
                reference,
                -amount if amount < 0 else None,
                amount if amount > 0 else None,
                "EUR",
            )
            for index, (booked_on, counterparty, reference, amount) in enumerate(bookings, start=1)
        ),
    )


def drop(conversation_id: str, text: str, name: str, data: bytes, media_type: str) -> dict[str, Any]:
    """The request the composer sends for one file dropped into it, from bytes."""
    return {
        "id": conversation_id,
        "trigger": "submit-message",
        "messages": [
            {
                "id": "u1",
                "role": "user",
                "parts": [
                    {"type": "text", "text": text},
                    {
                        "type": "file",
                        "mediaType": media_type,
                        "filename": name,
                        "url": f"data:{media_type};base64,{base64.b64encode(data).decode()}",
                    },
                ],
            }
        ],
    }


def newest_card(message: dict[str, Any]) -> dict[str, Any]:
    """The card a turn parked on, when the same turn has already asked one before it."""
    return [part for part in message["parts"] if part["type"] == "tool-ask_user"][-1]


def _call(index: int, name: str, **args: Any) -> dict[int, DeltaToolCall]:
    return {index: DeltaToolCall(name=name, json_args=json.dumps(args))}


def _returns(messages: list[ModelMessage], name: str) -> list[dict[str, Any]]:
    return [result for tool, result in _tool_returns(messages) if tool == name]


def importing_workbook(file_name: str):
    """A chat model that imports a workbook and does what the mapping card was answered with.

    The whole contract the system prompt describes, scripted: show the card the tool built, and
    on `confirm` call again with `confirmed=true`, on `sheet:NAME` call again with that sheet.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        imports = _returns(messages, "import_file")
        answers = [answer for card in _returns(messages, "ask_user") for answer in card.get("answers", [])]
        if not imports:
            yield _call(0, "import_file", file_name=file_name)
            return
        latest = imports[-1]
        if latest["status"] == "confirm_mapping":
            value = answers[-1]["value"] if answers else None
            if value == "confirm":
                yield _call(0, "import_file", file_name=file_name, confirmed=True)
            elif value and value.startswith("sheet:") and latest["sheet"] != value.removeprefix("sheet:"):
                yield _call(0, "import_file", file_name=file_name, sheet=value.removeprefix("sheet:"))
            else:
                yield _call(0, "ask_user", **latest["card"])
            return
        if latest["status"] == "imported":
            yield latest["say"]
            return
        yield latest.get("message") or latest.get("error") or "Nothing happened."

    return fn


async def test_a_workbook_dropped_into_the_chat_is_imported_by_its_preset(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The shipped workbook: the Sparkasse header is recognized, so no model writes a mapping.

    The figures are the point. A cell holds -1150.0 and 2025-01-01, not `-1.150,00` and
    `01.01.2025`, and the preset says German comma and DD.MM.YYYY: reading the cells with the
    preset's description of a text file is what would turn 39,90 EUR into 3.990,00 EUR.
    """
    responder = sub_agents()
    scripts.fast = importing_workbook(WORKBOOK.name)
    scripts.fast_call = responder  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "import this", WORKBOOK, media_type=XLSX_MEDIA_TYPE),
    )
    assert response.status_code == 200, response.text
    chunks = parse_sse(response.text)

    assert "propose_mapping" not in responder.calls  # type: ignore[attr-defined]
    read = progress_of(chunks)[0]
    assert read["data"]["counts"]["rows_read"] == TOTAL_ROWS
    # One sheet, so the progress line says nothing about sheets at all.
    assert "sheet" not in read["data"]["message"]

    output = outputs_of(chunks)[0]
    assert output["status"] == "imported"
    assert (output["rows_read"], output["imported"], output["duplicates"]) == (TOTAL_ROWS, TOTAL_ROWS, 0)
    assert output["account"] == "Sparkasse Girokonto"
    assert output["ignored"] == "Charts, pictures and macros in a workbook are not read, only its cells."

    rows = await rows_of(client, profile_id)
    assert len(rows) == TOTAL_ROWS
    rent = next(row for row in rows if row["description"] == "MIETE WOHNUNG 12 01/2025")
    assert (rent["booked_on"], rent["amount_cents"]) == ("2025-01-01", -115000)
    salary = next(row for row in rows if row["description"] == "GEHALT 01/2025 PERS.NR 4711")
    assert (salary["booked_on"], salary["amount_cents"]) == ("2025-01-28", 285000)
    # The whole year adds up to the same closing balance the CSV and the PDF of it do.
    assert sum(row["amount_cents"] for row in rows) == 569901

    record = (await client.get("/api/imports", params={"profile_id": profile_id})).json()[0]
    assert (record["kind"], record["preset"], record["file_name"]) == ("xlsx", "sparkasse", WORKBOOK.name)


async def test_an_unknown_workbook_asks_for_the_mapping_and_the_cells_correct_it(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """A layout no preset knows: proposed once, confirmed on a card, then committed.

    The proposal says German comma and DD.MM.YYYY, because that is what a model reading a
    German export answers. The sheet's cells say otherwise, and the card already shows the
    amounts the cells really hold.
    """
    responder = sub_agents(mapping=UNKNOWN_MAPPING, account_name="Musterbank Giro")
    scripts.fast = importing_workbook("musterbank.xlsx")
    scripts.fast_call = responder  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    data = workbook_bytes({"Umsaetze": unknown_sheet(JANUARY)})

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=drop(conversation_id, "import this", "musterbank.xlsx", data, XLSX_MEDIA_TYPE),
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)

    assert responder.calls == ["propose_mapping"]  # type: ignore[attr-defined]
    output = outputs_of(chunks)[0]
    assert output["status"] == "confirm_mapping"
    # The title block above the header was skipped, so the header is the header.
    assert output["mapping"]["debit_column"] == "Soll"
    # What the cells corrected about the proposal.
    assert output["mapping"]["date_format"] == "YYYY-MM-DD"
    assert output["mapping"]["decimal_separator"] == "dot"
    assert await rows_of(client, profile_id) == []

    card = cards_in(chunks)[0]["input"]
    assert card["title"] == "Import musterbank.xlsx with this mapping?"
    # One sheet with bookings on it, so no sheet buttons.
    assert [option["value"] for option in card["options"]] == ["confirm", "reject"]
    assert "Read from the sheet" not in card["note"]
    # The card shows the bookings the cells really hold, written the German way.
    assert "09.01.2025" in card["note"]
    assert "-40,90 EUR" in card["note"]
    assert "2.850,00 EUR" in card["note"]

    pending = (await transcript(client, conversation_id))["messages"][1]
    second = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(
            conversation_id,
            pending["id"],
            pending_card(pending),
            {"answers": [{"ref": "", "value": "confirm", "text": None}]},
        ),
    )
    assert second.status_code == 200, second.text

    rows = await rows_of(client, profile_id)
    assert [(row["booked_on"], row["amount_cents"]) for row in rows] == [
        ("2025-01-28", 285000),
        ("2025-01-09", -4090),
    ]
    record = (await client.get("/api/imports", params={"profile_id": profile_id})).json()[0]
    assert (record["kind"], record["preset"], record["account_name"]) == ("xlsx", None, "Musterbank Giro")


async def test_a_workbook_with_several_sheets_offers_the_others_on_the_card(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The first sheet with bookings is read, and the card is where another one is chosen.

    A cover sheet with a line of text on it is not a sheet with bookings, so it is not offered.
    """
    responder = sub_agents(mapping=UNKNOWN_MAPPING, account_name="Musterbank Giro")
    scripts.fast = importing_workbook("zwei-monate.xlsx")
    scripts.fast_call = responder  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    data = workbook_bytes(
        {
            "Deckblatt": (("Kontoumsätze Musterbank",),),
            "Januar": unknown_sheet(JANUARY),
            "Februar": unknown_sheet(FEBRUARY),
        }
    )

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=drop(conversation_id, "import this", "zwei-monate.xlsx", data, XLSX_MEDIA_TYPE),
    )
    assert first.status_code == 200, first.text
    card = cards_in(parse_sse(first.text))[0]["input"]
    assert [option["value"] for option in card["options"]] == ["confirm", "sheet:Februar", "reject"]
    assert "Read from the sheet Januar, of 2 sheets with bookings on them." in card["note"]
    assert "09.01.2025" in card["note"]

    pending = (await transcript(client, conversation_id))["messages"][1]
    second = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(
            conversation_id,
            pending["id"],
            pending_card(pending),
            {"answers": [{"ref": "", "value": "sheet:Februar", "text": None}]},
        ),
    )
    assert second.status_code == 200, second.text
    chunks = parse_sse(second.text)

    # The other sheet was read and asked about, and still nothing has been written.
    assert "(sheet Februar)" in progress_of(chunks)[0]["data"]["message"]
    again = cards_in(chunks)[0]["input"]
    assert [option["value"] for option in again["options"]] == ["confirm", "sheet:Januar", "reject"]
    assert "Read from the sheet Februar" in again["note"]
    assert "03.02.2025" in again["note"]
    assert await rows_of(client, profile_id) == []

    parked = (await transcript(client, conversation_id))["messages"][1]
    third = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(
            conversation_id,
            parked["id"],
            newest_card(parked),
            {"answers": [{"ref": "", "value": "confirm", "text": None}]},
        ),
    )
    assert third.status_code == 200, third.text

    # The sheet the user picked is the sheet that landed, not the one the workbook opens on.
    rows = await rows_of(client, profile_id)
    assert [(row["booked_on"], row["amount_cents"]) for row in rows] == [
        ("2025-02-14", -8900),
        ("2025-02-03", -3145),
    ]


async def test_a_word_statement_is_read_from_its_text_and_reconciles(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The DOCX excerpt through the statement reader: one page, both guards, then the commit."""
    scripts.fast = importing_statement(WORD_STATEMENT.name)
    scripts.fast_call = statement_reader()  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "import this statement", WORD_STATEMENT, media_type=DOCX_MEDIA_TYPE),
    )
    assert response.status_code == 200, response.text
    chunks = parse_sse(response.text)

    output = outputs_of(chunks)[0]
    assert output["status"] == "imported"
    # A Word document is one page of text, so nothing was rendered and nothing was looked at.
    assert (output["pages"], output["scanned_pages"]) == (1, 0)
    assert (output["rows_read"], output["flagged"]) == (DOCX_BOOKINGS, 0)
    assert output["layout"] == "Sparkasse Kontoauszug"
    assert output["reconciled"] == "ok"
    assert output["ignored"] == "Pictures, headers and footers in a Word document are not read, only its text."

    rows = await rows_of(client, profile_id)
    assert len(rows) == DOCX_BOOKINGS
    assert DOCX_OPENING + sum(row["amount_cents"] for row in rows) == DOCX_CLOSING
    rent = next(row for row in rows if "Bergmann" in (row["counterparty"] or ""))
    assert (rent["booked_on"], rent["amount_cents"]) == ("2025-01-01", -115000)

    record = (await client.get("/api/imports", params={"profile_id": profile_id})).json()[0]
    assert (record["kind"], record["file_name"]) == ("docx", WORD_STATEMENT.name)
    assert "Reconciled" in record["reconciliation"]


async def test_a_figure_not_printed_in_the_word_document_is_flagged_before_anything_is_written(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The verbatim guard on a DOCX, exactly as on a PDF page.

    The scripted reader rewrites one amount into a rendering the document does not contain, the
    same money and another spelling. Nothing distinguishes that from an invention, so the row
    goes to the review card and nothing is imported until it is answered.
    """
    scripts.fast = importing_statement(WORD_STATEMENT.name)
    scripts.fast_call = statement_reader(retype=(1, 2))  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "import this statement", WORD_STATEMENT, media_type=DOCX_MEDIA_TYPE),
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)

    output = outputs_of(chunks)[0]
    assert output["status"] == "extraction_review"
    assert (output["rows_read"], output["flagged"]) == (DOCX_BOOKINGS, 1)
    assert await rows_of(client, profile_id) == []

    card = cards_in(chunks)[0]["input"]
    assert card["apply"] == {"kind": "extraction_review"}
    assert "Bergmann" in card["rows"][0]["label"]
    assert "is not printed on this page" in card["rows"][0]["description"]

    pending = (await transcript(client, conversation_id))["messages"][1]
    second = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(
            conversation_id,
            pending["id"],
            pending_card(pending),
            {"answers": [{"ref": card["rows"][0]["ref"], "value": "accept", "text": None}]},
        ),
    )
    assert second.status_code == 200, second.text

    # Accepting commits it together with the rows both guards passed, through the same commit a
    # CSV import uses.
    rows = await rows_of(client, profile_id)
    assert len(rows) == DOCX_BOOKINGS
    assert DOCX_OPENING + sum(row["amount_cents"] for row in rows) == DOCX_CLOSING
