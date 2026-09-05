"""PDF and photo extraction over HTTP: the two guards, the review card, the bill flow.

The scripted fast slot here is not a canned answer: it reads the numbered lines out of the
prompt the extraction sub-agent was given and answers with the bookings it finds. So these
tests run the real shipped statement through the real pipeline, and a test that wants a guard
to fire asks the script to misread one specific booking (an amount that is not printed, a row
left out). What is asserted is what the outside sees: the rows the extract endpoint returns
with their flags, the card the chat parks on, the changeset a receipt proposes, and what ends
up in the profile.
"""

import json
import re
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic_ai.messages import BinaryContent, ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from .conftest import PRIVATE, SYNTHETIC, Scripts, new_conversation, parse_sse
from .test_categorization import (
    _tool_returns,
    answer_card,
    distilled,
    is_distillation_request,
    is_followup_request,
    outputs_of,
    scripted_categorizer,
)
from .test_chat_import import attach, cards_in, pending_card, progress_of, rows_of, transcript
from .test_query import import_synthetic

STATEMENT = SYNTHETIC / "sparkasse-kontoauszug-2025.pdf"
EDEKA_BILL = SYNTHETIC / "bill-edeka-2025-03-14.png"
OBI_BILL = SYNTHETIC / "bill-obi-2025-07-19.png"
TRADE_REPUBLIC = PRIVATE / "frames" / "tr-2025-02-to-2025-05.pdf"

TOTAL_BOOKINGS = 433
OPENING = 421055
CLOSING = 990956

# The Edeka receipt of 14.03.2025 and the booking of the same amount that is in the CSV.
EDEKA_ITEMS = (
    ("Vollmilch 3,5% 1L", "1,29"),
    ("Vollkornbrot 750g", "2,49"),
    ("Bio-Eier 10 Stk", "3,49"),
    ("Rispentomaten 500g", "2,19"),
    ("Spuelmittel Zitrone", "1,99"),
    ("Kuechenrolle 4x", "2,29"),
    ("Waschmittel 20WL", "6,99"),
)
EDEKA_TOTAL = "20,73"

NUMBERED = re.compile(r"^\s*(\d+)\|\s(.*)$", re.MULTILINE)
BOOKING = re.compile(
    r"^(\d{2}\.\d{2}\.\d{2})\s+(?:\d{2}\.\d{2}\.\d{2})\s+(.+?)\s\s+(-?[\d.]+,\d{2})\s\s+(-?[\d.]+,\d{2})$"
)


def _prompt_of(messages: Sequence[ModelMessage]) -> str:
    for message in reversed(messages):
        for part in message.parts:
            if part.part_kind == "user-prompt":
                if isinstance(part.content, str):
                    return part.content
                return "".join(item for item in part.content if isinstance(item, str))
    return ""


def _images_of(messages: Sequence[ModelMessage]) -> list[BinaryContent]:
    return [
        item
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt" and not isinstance(part.content, str)
        for item in part.content
        if isinstance(item, BinaryContent)
    ]


def read_page(prompt: str, *, retype: int | None = None, drop: int | None = None) -> dict[str, Any]:
    """The bookings printed on the page the sub-agent was handed, read with a regex.

    This is the stand-in for the model: it points at the spans it read, exactly as the contract
    asks. `retype` rewrites one booking's amount into a rendering that is nowhere on the page
    (same value, so only the verbatim guard can catch it) and `drop` leaves one booking out
    (so only the reconciliation guard can catch it), both counted from 1 within this page.
    """
    rows = []
    found = 0
    for number, line in NUMBERED.findall(prompt):
        match = BOOKING.match(line)
        if match is None:
            continue
        found += 1
        if drop == found:
            continue
        booked_on, description, amount, balance = match.groups()
        if retype == found:
            # What a model does when it "helpfully" normalizes: the same money, a rendering the
            # page does not contain.
            amount = amount.replace(".", "").replace(",", ".")
        rows.append(
            {
                "line": int(number),
                "date_text": booked_on,
                "amount_text": amount,
                "direction": "out" if amount.strip().startswith("-") else "in",
                "description": description,
                "counterparty": description.split("  ")[-1],
                "balance_text": balance,
            }
        )
    return {"rows": rows}


def statement_reader(*, retype: tuple[int, int] | None = None, drop: tuple[int, int] | None = None):
    """The fast slot for a statement extraction plus every other sub-agent of the turn.

    `retype` and `drop` are (page, booking on that page).
    """
    categorizer = scripted_categorizer()
    pages: list[int] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="No follow-ups.")])
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        tools = [tool.name for tool in info.output_tools]
        if tools == ["read_statement"]:
            assert info.allow_text_output is False
            prompt = _prompt_of(messages)
            page = int(re.search(r"This is page (\d+) of", prompt).group(1))
            pages.append(page)
            answer = read_page(
                prompt,
                retype=retype[1] if retype and retype[0] == page else None,
                drop=drop[1] if drop and drop[0] == page else None,
            )
            return ModelResponse(parts=[ToolCallPart("read_statement", json.dumps(answer))])
        return categorizer(messages, info)

    respond.pages = pages  # type: ignore[attr-defined]
    return respond


def bill_reader(
    *,
    items: Sequence[tuple[str, str]],
    total: str | None,
    date_text: str,
    merchant: str,
    currency_text: str = "EUR",
    tax_text: str | None = None,
    direction: str = "out",
    note: str | None = None,
    several_receipts: bool = False,
):
    """The fast slot for a receipt: the line items it was asked for, and the images it was sent."""
    categorizer = scripted_categorizer({description: ("Groceries", None, 0.8) for description, _ in items})
    images: list[BinaryContent] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="No follow-ups.")])
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        tools = [tool.name for tool in info.output_tools]
        if tools == ["read_bill"]:
            assert info.allow_text_output is False
            images.extend(_images_of(messages))
            payload = {
                "merchant": merchant,
                "date_text": date_text,
                "total_text": total,
                "currency_text": currency_text,
                "tax_text": tax_text,
                "direction": direction,
                "note": note,
                "several_receipts": several_receipts,
                "items": [{"description": description, "amount_text": amount} for description, amount in items],
            }
            return ModelResponse(parts=[ToolCallPart("read_bill", json.dumps(payload))])
        if tools == ["categorize"]:
            # Each line item is one entry, so the legs of a split are grouped by a real guess.
            prompt = _prompt_of(messages)
            merchants = [
                {
                    "key": f"i{index}",
                    "category": "Shopping" if "Waschmittel" in description or "Spuelmittel" in description else "Groceries",
                    "subcategory": "Household" if "Waschmittel" in description or "Spuelmittel" in description else None,
                    "confidence": 0.8,
                    "title": description[:40],
                    "description": "read off a receipt",
                }
                for index, (description, _) in enumerate(items)
                if f"i{index}" in prompt
            ]
            if merchants:
                return ModelResponse(parts=[ToolCallPart("categorize", json.dumps({"merchants": merchants}))])
        return categorizer(messages, info)

    respond.images = images  # type: ignore[attr-defined]
    return respond


def _call(index: int, name: str, **args: Any) -> dict[int, DeltaToolCall]:
    return {index: DeltaToolCall(name=name, json_args=json.dumps(args))}


def _returns(messages: list[ModelMessage], name: str) -> list[dict[str, Any]]:
    return [result for tool, result in _tool_returns(messages) if tool == name]


def importing(file_name: str):
    """A chat model that imports the attached file and does what the tool asked of it.

    It states no figure of its own: it says the tool's own sentence and shows the tool's own
    card, which is the contract the system prompt describes, scripted.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        imports = _returns(messages, "import_file")
        cards = _returns(messages, "ask_user")
        added = _returns(messages, "add_transaction")
        if not imports:
            yield _call(0, "import_file", file_name=file_name)
            return
        latest = imports[-1]
        if added:
            yield f"Added {added[-1].get('description')} for {added[-1].get('amount_cents')} cents."
            return
        if latest["status"] in {"extraction_review", "bill_draft"}:
            answered = [answer for card in cards for answer in card.get("answers", [])]
            if not answered:
                yield _call(0, "ask_user", **latest["card"])
                return
            applied = cards[-1].get("applied")
            if applied:
                yield f"Summarized: {applied}"
                return
            confirmed = [answer["ref"] for answer in answered if answer.get("value") == "add"]
            for index, ref in enumerate(confirmed):
                yield _call(index, "add_transaction", ref=ref)
            return
        if latest["status"] == "bill_split":
            changeset = latest["changeset"]
            yield f"Proposed: {changeset['summary']}"
            return
        if latest["status"] == "imported":
            yield latest["summary"]
            return
        yield latest.get("message") or latest.get("error") or "Nothing happened."

    return fn


async def extract(client: httpx.AsyncClient, path: Path, media_type: str = "application/pdf") -> dict[str, Any]:
    response = await client.post(
        "/api/imports/extract", files={"file": (path.name, path.read_bytes(), media_type)}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def commit_body(profile_id: str, extraction: dict[str, Any], rows: list[dict[str, Any]], dropped: int = 0) -> dict[str, Any]:
    """What a caller posts after the review: the rows as they stood when they were accepted."""
    return {
        "profile_id": profile_id,
        "file_name": extraction["file_name"],
        "kind": extraction["kind"],
        "layout": extraction["layout"],
        "account_name": extraction["account_name"],
        "dropped": dropped,
        "rows": [
            {
                "booked_on": row["booked_on"],
                "amount_cents": row["amount_cents"],
                "description": row["description"],
                "counterparty": row["counterparty"],
                "balance_cents": row["balance_cents"],
                "page": row["page"],
                "line": row["line"],
            }
            for row in rows
        ],
    }


async def test_the_synthetic_pdf_extracts_reconciles_and_imports(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    reader = statement_reader()
    scripts.fast_call = reader  # type: ignore[assignment]

    extraction = await extract(client, STATEMENT)

    # Every page was read once, and the layout was recognized from the page header.
    assert sorted(reader.pages) == list(range(1, 16))  # type: ignore[attr-defined]
    assert (extraction["layout"], extraction["pages"]) == ("sparkasse", 15)
    assert extraction["account_name"] == "Sparkasse Girokonto"
    assert extraction["scanned_pages"] == []
    assert len(extraction["rows"]) == TOTAL_BOOKINGS
    assert extraction["flagged"] == 0

    # The printed balances of the statement, and the arithmetic between them.
    check = extraction["reconciliation"]
    assert check["status"] == "ok"
    assert (check["opening_cents"], check["closing_cents"]) == (OPENING, CLOSING)
    assert check["booked_cents"] == CLOSING - OPENING
    assert check["pages_failed"] == []
    assert "Reconciled" in check["line"]

    first = extraction["rows"][0]
    assert (first["booked_on"], first["amount_cents"], first["balance_cents"]) == ("2025-01-01", -3990, 417065)
    assert first["amount_text"] == "-39,90"
    assert first["page"] == 1 and first["line"] == 6
    assert "Fitness First" in first["description"]

    committed = await client.post("/api/imports/extracted", json=commit_body(profile_id, extraction, extraction["rows"]))
    assert committed.status_code == 201, committed.text
    record = committed.json()
    assert (record["kind"], record["preset"]) == ("pdf", "sparkasse")
    assert (record["row_count"], record["imported_count"]) == (TOTAL_BOOKINGS, TOTAL_BOOKINGS)
    assert "Reconciled" in record["reconciliation"]
    assert len(await rows_of(client, profile_id)) == TOTAL_BOOKINGS

    # The Import record keeps the verdict, which is what the past imports list shows.
    listed = (await client.get("/api/imports", params={"profile_id": profile_id})).json()
    assert listed[0]["reconciliation"] == record["reconciliation"]


async def test_an_amount_that_is_not_printed_is_flagged_by_the_verbatim_guard(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    # The second booking of page 1 comes back as `-1150.00`: the right money, a rendering that
    # is nowhere on the page. The arithmetic cannot see it, so only the verbatim guard can.
    scripts.fast_call = statement_reader(retype=(1, 2))  # type: ignore[assignment]

    extraction = await extract(client, STATEMENT)

    assert extraction["flagged"] == 1
    flagged = [row for row in extraction["rows"] if row["flags"]][0]
    assert flagged["flags"] == ["verbatim"]
    assert flagged["amount_text"] == "-1150.00"
    assert "not printed" in flagged["reason"]
    assert "Hausverwaltung" in flagged["description"]
    # The value was still read from the span, and the running balance still adds up.
    assert flagged["amount_cents"] == -115000
    assert extraction["reconciliation"]["status"] == "ok"


async def test_a_missed_booking_is_caught_by_the_reconciliation_guard(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast_call = statement_reader(drop=(1, 3))  # type: ignore[assignment]

    extraction = await extract(client, STATEMENT)

    assert len(extraction["rows"]) == TOTAL_BOOKINGS - 1
    check = extraction["reconciliation"]
    assert check["status"] == "failed"
    # The Allianz booking of -42,50 is the one that was left out.
    assert "42,50" in check["line"]
    assert check["pages_failed"] == [1]
    flagged = [row for row in extraction["rows"] if row["flags"]]
    assert len(flagged) == 1
    assert flagged[0]["flags"] == ["reconciliation"]
    assert "a booking is missing or misread" in flagged[0]["reason"]
    # The row the chain breaks on is the one after the hole.
    assert "LIDL" in flagged[0]["description"]


async def test_a_flagged_statement_in_chat_asks_before_it_imports_anything(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast = importing(STATEMENT.name)
    scripts.fast_call = statement_reader(drop=(1, 3))  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "import this statement", STATEMENT, media_type="application/pdf"),
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)

    output = outputs_of(chunks)[0]
    assert output["status"] == "extraction_review"
    assert (output["rows_read"], output["flagged"]) == (TOTAL_BOOKINGS - 1, 1)
    assert output["reconciled"] == "failed"
    assert output["layout"] == "Sparkasse Kontoauszug"
    # Reading the file streamed its progress, and nothing was written.
    assert [line["data"]["stage"] for line in progress_of(chunks)][:2] == ["read", "extracting"]
    assert await rows_of(client, profile_id) == []

    card = cards_in(chunks)[0]["input"]
    assert card["apply"] == {"kind": "extraction_review"}
    assert [option["value"] for option in card["rows"][0]["options"]] == ["accept", "drop"]
    assert "Did not reconcile" in card["note"]
    assert "LIDL" in card["rows"][0]["label"]

    pending = (await transcript(client, conversation_id))["messages"][1]
    answers = {"answers": [{"ref": card["rows"][0]["ref"], "value": "accept", "text": None}]}
    second = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(conversation_id, pending["id"], pending_card(pending), answers),
    )
    assert second.status_code == 200, second.text

    # The server committed the accepted row together with the ones the guards passed, through
    # the same commit a CSV import uses, and said so on the card.
    rows = await rows_of(client, profile_id)
    assert len(rows) == TOTAL_BOOKINGS - 1
    answered = [
        part
        for part in (await transcript(client, conversation_id))["messages"][1]["parts"]
        if part["type"] == "tool-ask_user"
    ][0]
    applied = answered["output"]["applied"]
    assert f"{TOTAL_BOOKINGS - 1} of {TOTAL_BOOKINGS - 1} bookings" in applied
    assert "1 of them you accepted" in applied
    assert f"Summarized: {applied}" in second.text

    record = (await client.get("/api/imports", params={"profile_id": profile_id})).json()[0]
    assert record["kind"] == "pdf"
    assert "Did not reconcile" in record["reconciliation"]
    # Every imported row went through categorization, the same as a CSV import's rows.
    assert all(row["title"] for row in rows)


async def test_a_bill_matching_a_booking_proposes_a_split_changeset(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    reader = bill_reader(items=EDEKA_ITEMS, total=EDEKA_TOTAL, date_text="14.03.2025", merchant="EDEKA Sander")
    scripts.fast = importing(EDEKA_BILL.name)
    scripts.fast_call = reader  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "this is the receipt for it", EDEKA_BILL, media_type="image/png"),
    )
    assert response.status_code == 200, response.text
    output = outputs_of(parse_sse(response.text))[0]

    # The photo reached the model as an image content part, not as text.
    images = reader.images  # type: ignore[attr-defined]
    assert len(images) == 1
    assert images[0].media_type == "image/png"
    assert images[0].data[:8] == EDEKA_BILL.read_bytes()[:8]

    assert output["status"] == "bill_split"
    assert output["bill"]["total_cents"] == 2073
    assert output["bill"]["verified"] is True
    assert output["matched"]["amount_cents"] == -2073
    assert output["matched"]["booked_on"] == "2025-03-14"

    changeset = output["changeset"]
    assert changeset["kind"] == "split"
    legs = [row for row in changeset["rows"] if row["before"] is None]
    assert len(legs) == 2, "the seven line items grouped into groceries and household"
    assert sum(round(float(leg["after"]["amount"]) * 100) for leg in legs) == -2073
    assert {leg["after"]["category"] for leg in legs} == {"Groceries", "Shopping"}

    # Nothing was written: the card applies it.
    before = await rows_of(client, profile_id)
    applied = await client.post(f"/api/changesets/{changeset['id']}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text
    after = await rows_of(client, profile_id)
    # The split parent leaves the query view and its two legs take its place.
    assert len(after) == len(before) + 1
    assert sum(row["amount_cents"] for row in after) == sum(row["amount_cents"] for row in before)


async def test_a_bill_that_matches_nothing_previews_a_new_transaction(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    # A total no booking of the profile has, so there is nothing to split.
    reader = bill_reader(
        items=(("Blumenerde 40L", "7,99"), ("Giesskanne", "4,50")),
        total="12,49",
        date_text="19.07.2025",
        merchant="OBI Markt",
    )
    scripts.fast = importing(OBI_BILL.name)
    scripts.fast_call = reader  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "book this receipt", OBI_BILL, media_type="image/png"),
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)
    output = outputs_of(chunks)[0]

    assert output["status"] == "bill_draft"
    assert output["drafts"] == [
        {
            "ref": "t1",
            "booked_on": "2025-07-19",
            "amount_cents": -1249,
            "description": "OBI Markt",
            "counterparty": "OBI Markt",
            "account": "Cash",
        }
    ]
    card = cards_in(chunks)[0]["input"]
    assert card["apply"] == {"kind": "transaction_draft"}
    assert [option["value"] for option in card["rows"][0]["options"]] == ["add", "discard"]
    before = len(await rows_of(client, profile_id))

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
    added = [out for out in outputs_of(parse_sse(second.text)) if out.get("status") == "added"][0]
    assert (added["amount_cents"], added["description"]) == (-1249, "OBI Markt")

    rows = await rows_of(client, profile_id)
    assert len(rows) == before + 1
    written = next(row for row in rows if row["description"] == "OBI Markt")
    assert (written["amount_cents"], written["booked_on"], written["source"]) == (-1249, "2025-07-19", "manual")


async def test_a_receipt_date_printed_with_its_time_is_the_date_that_is_booked(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """A German till prints `04.09.26 20:00`, and that is a date, not an unreadable span.

    The real Edeka receipt of the end-to-end test printed exactly that, the span came back
    with the time on it, and the booking fell back to today (2026-09-05).
    """
    await import_synthetic(client, profile_id)
    reader = bill_reader(
        items=(("Uludag Gazoz 0,33l", "0,99"), ("Hi-Chew Original", "3,49")),
        total="4,48",
        date_text="04.09.26 20:00",
        merchant="EDEKA Mueller",
    )
    scripts.fast = importing(OBI_BILL.name)
    scripts.fast_call = reader  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "here is a receipt", OBI_BILL, media_type="image/png"),
    )
    assert response.status_code == 200, response.text
    output = outputs_of(parse_sse(response.text))[0]

    assert output["status"] == "bill_draft"
    assert output["bill"]["booked_on"] == "2026-09-04"
    assert output["bill"]["date_read"] is True
    assert output["drafts"][0]["booked_on"] == "2026-09-04"
    # Nothing was flagged, so the card is the plain preview with no question about the date.
    assert output["bill"]["verified"] is True
    assert output["card"]["allow_free_text"] is False


async def test_a_receipt_date_printed_after_its_time_is_read_too(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """An ALDI till prints the clock first: `14:12 04.05.2019`."""
    output = await read_receipt(
        client,
        profile_id,
        bill_reader(
            items=(("GESCHIRRSPULTABS", "2,65"),),
            total="2,65",
            date_text="14:12 04.05.2019",
            merchant="ALDI",
        ),
        scripts,
    )

    assert output["bill"]["booked_on"] == "2019-05-04"
    assert output["bill"]["date_read"] is True


async def read_receipt(client: httpx.AsyncClient, profile_id: str, reader, scripts: Scripts) -> dict[str, Any]:
    """One receipt through the chat, as a photo on the composer: the tool's own output."""
    scripts.fast = importing(OBI_BILL.name)
    scripts.fast_call = reader  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "here is a receipt", OBI_BILL, media_type="image/png"),
    )
    assert response.status_code == 200, response.text
    return outputs_of(parse_sse(response.text))[0]


async def test_a_subtotal_line_is_not_a_line_item(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """`ZWI.SUMME` printed between the articles is the basket again, not an article.

    Counted as one it doubles the receipt, which is what an ALDI receipt did in the run of
    twenty public receipts: 32 items summing to 52,13 against a printed 25,74.
    """
    output = await read_receipt(
        client,
        profile_id,
        bill_reader(
            items=(("Bananen", "1,99"), ("Milch", "1,29"), ("ZWI.SUMME", "3,28"), ("Brot", "2,49")),
            total="5,77",
            date_text="04.05.2019",
            merchant="ALDI Hesel",
        ),
        scripts,
    )

    assert [item["description"] for item in output["bill"]["items"]] == ["Bananen", "Milch", "Brot"]
    assert output["bill"]["verified"] is True
    assert "3 line items add up to the printed total of 5,77 EUR." == output["bill"]["check"]


async def test_a_discount_is_a_negative_line_item_so_the_receipt_adds_up(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """A `Rabatt` line is the difference between the articles and the total, so it is kept."""
    output = await read_receipt(
        client,
        profile_id,
        bill_reader(
            items=(("Katzenfutter", "34,97"), ("MwSt.-Senkung", "-0,88")),
            total="34,09",
            date_text="04.12.2020",
            merchant="Fressnapf Koeln",
        ),
        scripts,
    )

    assert [item["amount_cents"] for item in output["bill"]["items"]] == [3497, -88]
    assert output["bill"]["verified"] is True
    assert output["drafts"][0]["amount_cents"] == -3409


async def test_a_receipt_whose_prices_are_printed_before_tax_adds_up_with_it(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """1.00 + 1.00, tax 0.18, total 2.18: every US receipt reads this way and is not broken."""
    output = await read_receipt(
        client,
        profile_id,
        bill_reader(
            items=(("CANDY BAR", "1.00"), ("SODA", "1.00")),
            total="2.18",
            tax_text="0.18",
            date_text="04.05.2019",
            merchant="FAMILY DOLLAR",
        ),
        scripts,
    )

    assert output["bill"]["verified"] is True
    assert output["bill"]["total_cents"] == 218


async def test_a_receipt_in_another_currency_is_refused_instead_of_booked_as_euros(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """8,27 PLN booked as 8,27 EUR is the one wrong figure nothing later would catch."""
    output = await read_receipt(
        client,
        profile_id,
        bill_reader(
            items=(("Chleb", "3,29"), ("Mleko", "4,98")),
            total="8,27",
            currency_text="PLN",
            date_text="2020-01-09",
            merchant="Biedronka",
        ),
        scripts,
    )

    assert output["status"] == "nothing_found"
    assert "in PLN, not euros" in output["error"]
    assert "drafts" not in output and "card" not in output
    assert len(await rows_of(client, profile_id)) == 0


async def test_a_photo_of_several_receipts_says_only_the_first_was_read(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    output = await read_receipt(
        client,
        profile_id,
        bill_reader(
            items=(("Nudeln", "1,29"), ("Sauce", "9,25")),
            total="10,54",
            date_text="16.02.2018",
            merchant="LIDL",
            note="Three receipts are lying side by side in this photo.",
            several_receipts=True,
        ),
        scripts,
    )

    check = output["bill"]["check"]
    assert "only the first one was read" in check
    assert "Three receipts are lying side by side in this photo." in check
    assert output["bill"]["verified"] is False, "a photo of three receipts is not a checked one"
    assert output["drafts"][0]["amount_cents"] == -1054


async def test_a_deposit_refund_is_booked_as_money_in(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """A Leergutbon pays 0,25 EUR back, and money back is not a purchase."""
    output = await read_receipt(
        client,
        profile_id,
        bill_reader(
            items=(("Pfandrueckgabe 1 x 0,25", "0,25"),),
            total="0,25",
            direction="in",
            date_text="23.03.2019",
            merchant="ALDI Markt",
        ),
        scripts,
    )

    assert output["status"] == "bill_draft"
    assert output["bill"]["direction"] == "in"
    assert output["drafts"][0]["amount_cents"] == 25
    assert "0,25 EUR back" in output["bill"]["check"]


def receipt_as_statement(rows: Sequence[tuple[str, str, str]]):
    """A fast slot that reads a photographed receipt as if its articles were bookings."""

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        payload = {
            "rows": [
                {
                    "date_text": date_text,
                    "amount_text": amount,
                    "direction": "out",
                    "description": description,
                    "balance_text": None,
                }
                for date_text, amount, description in rows
            ]
        }
        return ModelResponse(parts=[ToolCallPart("read_statement", json.dumps(payload))])

    return respond


async def test_a_receipt_posted_to_the_statement_door_is_refused(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The chat routes a photo to the receipt reader; this door has to say when it got one.

    Eighteen of twenty public receipts were refused because the reader itself said "this is a
    receipt"; two came back as bookings (`Rucolasauce -0,99`). A page of a statement carries the
    running balance that makes its figures checkable, and a receipt carries none.
    """
    scripts.fast_call = receipt_as_statement(
        [("28.06.2007", "-0,99", "Rucolasauce"), ("28.06.2007", "-2,99", "VISU PENCIL SET")]
    )

    response = await client.post(
        "/api/imports/extract",
        files={"file": (EDEKA_BILL.name, EDEKA_BILL.read_bytes(), "image/png")},
    )

    assert response.status_code == 422, response.text
    assert "till receipt" in response.json()["detail"]


def confirming_with_a_date(file_name: str, *, ref: str, booked_on: str):
    """A chat model that shows the bill's card and books the row with the date the user typed."""

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        imports = _returns(messages, "import_file")
        cards = _returns(messages, "ask_user")
        added = _returns(messages, "add_transaction")
        if not imports:
            yield _call(0, "import_file", file_name=file_name)
            return
        if added:
            yield f"Added {added[-1].get('description')} on {added[-1].get('booked_on')}."
            return
        if not cards:
            yield _call(0, "ask_user", **imports[-1]["card"])
            return
        yield _call(0, "add_transaction", ref=ref, booked_on=booked_on)

    return fn


async def test_a_receipt_with_no_readable_date_asks_for_it_instead_of_booking_today(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """No date on the paper is a question, not a silent booking of today.

    The card says the date could not be read and offers the free text field for it, and the
    date the user types is parsed in code before the booking is written.
    """
    await import_synthetic(client, profile_id)
    reader = bill_reader(
        items=(("Blumenerde 40L", "7,99"), ("Giesskanne", "4,50")),
        total="12,49",
        date_text="",
        merchant="OBI Markt",
    )
    scripts.fast = confirming_with_a_date(OBI_BILL.name, ref="t1", booked_on="19.07.2025")
    scripts.fast_call = reader  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "book this receipt", OBI_BILL, media_type="image/png"),
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)
    output = outputs_of(chunks)[0]

    assert output["status"] == "bill_draft"
    assert output["bill"]["date_read"] is False
    assert "The date on the receipt could not be read." in output["bill"]["check"]
    card = cards_in(chunks)[0]["input"]
    assert card["allow_free_text"] is True
    assert "Type the printed date" in card["note"]

    before = len(await rows_of(client, profile_id))
    pending = (await transcript(client, conversation_id))["messages"][1]
    second = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(
            conversation_id,
            pending["id"],
            pending_card(pending),
            {
                "answers": [
                    {"ref": "t1", "value": "add", "text": None},
                    {"ref": "", "value": None, "text": "19.07.2025"},
                ]
            },
        ),
    )
    assert second.status_code == 200, second.text
    added = [out for out in outputs_of(parse_sse(second.text)) if out.get("status") == "added"][0]
    assert added["booked_on"] == "2025-07-19"

    rows = await rows_of(client, profile_id)
    assert len(rows) == before + 1
    written = next(row for row in rows if row["description"] == "OBI Markt")
    assert written["booked_on"] == "2025-07-19", "the typed date is the one that was written"


@pytest.mark.skipif(not TRADE_REPUBLIC.exists(), reason="the private Trade Republic export is not in this checkout")
async def test_the_trade_republic_layout_reconciles_per_frame_on_its_running_balance(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The real export, one frame of it, and the trap its first page sets.

    Every frame starts with the `KONTOÜBERSICHT` of the whole export, whose figures belong to
    two years of bookings and not to this frame. The layout therefore declares no balance
    labels, and the opening the guard uses is the first row's own running balance minus its own
    amount. Nothing of the file's content is asserted here, only the arithmetic.
    """
    from finquery.extract.layouts import TRADE_REPUBLIC as LAYOUT
    from finquery.extract.pdf import read_pdf

    document = read_pdf(TRADE_REPUBLIC.read_bytes())
    money = re.compile(r"^(.*?)\s\s+([\d.]+,\d{2}) €\s\s+([\d.]+,\d{2}) €$")
    # The day and the year sit on the lines above and below the amounts, each of them possibly
    # carrying a piece of the description as well, which is the layout the hint describes.
    day = re.compile(r"^(\d{1,2} [A-Za-zÄÖÜäöü]{3,5}\.?)(?:\s\s+.*)?$")
    year = re.compile(r"^((?:19|20)\d{2})(?:\s\s+.*)?$")

    def read_trade_republic(prompt: str) -> dict[str, Any]:
        """One page of the frame, read the way the layout hint describes it."""
        lines = NUMBERED.findall(prompt)
        by_number = {int(number): text for number, text in lines}
        rows = []
        for number, text in lines:
            index = int(number)
            match = money.match(text)
            if match is None:
                continue
            above = by_number.get(index - 1, "")
            below = by_number.get(index + 1, "")
            stamp = day.match(above)
            stamped_year = year.match(below)
            if stamp is None or stamped_year is None:
                continue
            rows.append(
                {
                    "line": index,
                    "date_text": f"{stamp.group(1)} {stamped_year.group(1)}",
                    "amount_text": match.group(2),
                    "direction": "out",
                    "description": match.group(1)[:120],
                    "counterparty": None,
                    "balance_text": match.group(3),
                }
            )
        return {"rows": rows}

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert [tool.name for tool in info.output_tools] == ["read_statement"]
        return ModelResponse(parts=[ToolCallPart("read_statement", json.dumps(read_trade_republic(_prompt_of(messages))))])

    scripts.fast_call = respond  # type: ignore[assignment]
    extraction = await extract(client, TRADE_REPUBLIC)

    # Recognized by its own header text, and its overview is not a balance to reconcile against.
    assert extraction["layout"] == "traderepublic"
    assert extraction["pages"] == len(document.pages)
    assert LAYOUT.opening(document.text) is None and LAYOUT.closing(document.text) is None
    assert len(extraction["rows"]) > 100

    check = extraction["reconciliation"]
    rows = extraction["rows"]
    # The opening is the first row's own running balance minus its own amount, and nothing like
    # the 0,00 the overview page prints for the start of the whole export.
    assert check["opening_cents"] == rows[0]["balance_cents"] - rows[0]["amount_cents"]
    assert check["opening_cents"] != 0
    assert check["closing_cents"] == rows[-1]["balance_cents"]
    # Every page of the frame adds up on its own running balance.
    assert check["pages_failed"] == []
    # The two money columns cannot be told apart in the text of this layout, so the running
    # balance decided the direction in code, which is what makes an incoming booking positive.
    assert check["directions_fixed"] > 0
    assert any(row["amount_cents"] > 0 for row in rows)

    # The regex above is a stand-in for the model and it misses a booking where two pages join,
    # so the frame as a whole does not add up. That is the interesting half: the guard says so
    # and points at the row after each hole rather than letting an incomplete reading through.
    flagged = [row for row in rows if row["flags"]]
    assert check["status"] == "failed"
    assert flagged and all(row["flags"] == ["reconciliation"] for row in flagged)
    assert all("a booking is missing or misread" in row["reason"] for row in flagged)

def blank_pdf() -> bytes:
    """A one page PDF with an image on it and no text layer, which is what a scan is.

    Built here rather than committed: what matters is the absence of a text layer, and Pillow
    (already a dependency, it is what shrinks a photo) writes that in three lines.
    """
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (1240, 1754), "white").save(buffer, format="PDF")
    return buffer.getvalue()


def scanned_reader(rows: Sequence[dict[str, Any]]):
    """The fast slot for a page that has to be looked at: it answers, and records the images."""
    images: list[BinaryContent] = []
    prompts: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        assert [tool.name for tool in info.output_tools] == ["read_statement"]
        images.extend(_images_of(messages))
        prompts.append(_prompt_of(messages))
        return ModelResponse(parts=[ToolCallPart("read_statement", json.dumps({"rows": list(rows)}))])

    respond.images = images  # type: ignore[attr-defined]
    respond.prompts = prompts  # type: ignore[attr-defined]
    return respond


async def test_a_page_with_no_text_layer_is_looked_at_and_its_rows_are_flagged(
    client: httpx.AsyncClient, scripts: Scripts
) -> None:
    """A scan has nothing for the verbatim guard, so its rows are never quietly trusted.

    The page goes to the model as a rendered image instead of as text, and a row that comes back
    with no balance to check it against is flagged rather than imported (ADR 0011).
    """
    reader = scanned_reader(
        [
            {
                "line": 1,
                "date_text": "02.01.2025",
                "amount_text": "-19,90",
                "direction": "out",
                "description": "Eingescannte Buchung",
                "counterparty": "Laden",
                "balance_text": None,
            }
        ]
    )
    scripts.fast_call = reader  # type: ignore[assignment]

    response = await client.post(
        "/api/imports/extract", files={"file": ("scan.pdf", blank_pdf(), "application/pdf")}
    )
    assert response.status_code == 200, response.text
    extraction = response.json()

    assert extraction["scanned_pages"] == [1]
    assert reader.images, "the page was rendered and handed over as an image"  # type: ignore[attr-defined]
    assert reader.images[0].media_type == "image/png"  # type: ignore[attr-defined]
    assert "as an image, because it has no text layer" in reader.prompts[0]  # type: ignore[attr-defined]

    assert len(extraction["rows"]) == 1
    row = extraction["rows"][0]
    assert (row["booked_on"], row["amount_cents"]) == ("2025-01-02", -1990)
    assert row["flags"] == ["unverified"]
    assert row["reason"] == "There is no balance or total on this page to check the figures against."
    assert extraction["flagged"] == 1
    assert extraction["reconciliation"]["status"] == "not_checkable"


async def test_a_photo_that_is_not_a_receipt_says_so_instead_of_previewing_a_booking(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """No total and no line item is not a receipt, and nothing is drafted from it."""
    output = await read_receipt(
        client,
        profile_id,
        bill_reader(items=(), total=None, date_text="", merchant="", note="This is a photo of a cat."),
        scripts,
    )

    assert output["status"] == "nothing_found"
    assert output["error"] == (
        "No total and no line item could be read from that photo. Attach a photo of the receipt "
        "itself, or type the booking and I will add it."
    )
    assert "drafts" not in output and "changeset" not in output
