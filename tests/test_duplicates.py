"""Duplicate detection: nothing an import already has is inserted or dropped without a decision.

Both paths are driven over HTTP. The REST path commits through `/api/imports` and then
reads and answers the candidates through `/api/imports/{id}/duplicates`; the chat path drops the
same file on the composer and answers the `ask_user` card the server applies in code. The chat
model and every sub-agent a turn starts are scripted, so what is asserted is what landed in the
profile, what was asked about, and what the import record remembers afterwards.
"""

import base64
import csv
import io
import json
from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from finquery.db import DuplicateCandidate

from .conftest import PRIVATE, SYNTHETIC, Scripts, new_conversation, parse_sse, script
from .test_categorization import TOTAL_ROWS, answer, answer_card, outputs_of, scripted_categorizer
from .test_chat_import import _call, _returns, cards_in, sub_agents, transcript
from .test_import import upload

SPARKASSE = SYNTHETIC / "sparkasse-2025.csv"
OVERLAP_A = PRIVATE / "frames" / "tr-overlap-A-2025-01-to-04.csv"
OVERLAP_B = PRIVATE / "frames" / "tr-overlap-B-2025-03-to-06.csv"

SHIFTED = 3
"""Bookings whose date the near-match fixture moves by one day."""

BATCH = 5
"""Candidates one duplicate card asks about, the cap `ask_user` sets for its rows."""

OVERLAP_ROWS = 105
"""Bookings the two Trade Republic frames share: all of March and April 2025."""


def shifted_copy(path: Path, count: int = SHIFTED) -> bytes:
    """The same export with the first `count` booking dates one day later.

    A booking that moved by a day is the realistic near duplicate: the same payment, booked on
    another day by the bank, so the fingerprint misses it and the amount plus the text catch it.
    """
    lines = path.read_bytes().decode("cp1252").splitlines()
    out = [lines[0]]
    for index, line in enumerate(lines[1:], start=1):
        fields = line.split(";")
        if index <= count:
            day, month, year = (int(part) for part in fields[1].strip('"').split("."))
            fields[1] = f'"{(date(year, month, day) + timedelta(days=1)).strftime("%d.%m.%Y")}"'
        out.append(";".join(fields))
    return "\r\n".join(out).encode("cp1252")


def mini_csv(rows: list[tuple[str, str, str, str]]) -> bytes:
    """A tiny Sparkasse-layout export, so a duplicate card can be read row by row."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(
        ["Auftragskonto", "Buchungstag", "Verwendungszweck", "Beguenstigter/Zahlungspflichtiger", "Betrag"]
    )
    for booked_on, description, counterparty, amount in rows:
        writer.writerow(["DE02120300000000202051", booked_on, description, counterparty, amount])
    return buffer.getvalue().encode("cp1252")


SIX = [
    ("02.01.2025", "REWE SAGT DANKE", "REWE Markt GmbH", "-24,90"),
    ("03.01.2025", "LIDL FILIALE 4711", "Lidl Dienstleistung", "-18,40"),
    ("04.01.2025", "NETFLIX MONATSABO", "Netflix International", "-12,99"),
    ("05.01.2025", "BVG MONATSKARTE", "BVG", "-86,00"),
    ("06.01.2025", "PAYPAL ANNA WEBER", "PayPal Europe", "-32,00"),
    ("07.01.2025", "GEHALT 01/2025", "Mustermann Systems GmbH", "2.400,00"),
]
SIX_FILE = "six-bookings.csv"

EIGHT = [
    *SIX,
    ("08.01.2025", "DM DROGERIEMARKT", "dm-drogerie markt", "-14,75"),
    ("09.01.2025", "SPOTIFY ABO", "Spotify AB", "-10,99"),
]
EIGHT_FILE = "eight-bookings.csv"


def shift_first(rows: list[tuple[str, str, str, str]], count: int) -> list[tuple[str, str, str, str]]:
    """The same bookings with the first `count` dates one day later: three near matches."""
    moved = []
    for index, (booked_on, description, counterparty, amount) in enumerate(rows):
        if index < count:
            day, month, year = (int(part) for part in booked_on.split("."))
            booked_on = (date(year, month, day) + timedelta(days=1)).strftime("%d.%m.%Y")
        moved.append((booked_on, description, counterparty, amount))
    return moved


def upload_bytes(name: str, data: bytes) -> dict[str, tuple[str, bytes, str]]:
    return {"file": (name, data, "text/csv")}


def attach_bytes(conversation_id: str, text: str, name: str, data: bytes) -> dict[str, Any]:
    """The request the browser sends for a file dropped into the composer."""
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
                        "mediaType": "text/csv",
                        "filename": name,
                        "url": f"data:text/csv;base64,{base64.b64encode(data).decode()}",
                    },
                ],
            }
        ],
    }


async def commit(
    client: httpx.AsyncClient, profile_id: str, files: dict[str, tuple[str, bytes, str]]
) -> dict[str, Any]:
    """Preview and commit one upload over REST, the way the tests and `scripts/` drive it."""
    preview = (await client.post("/api/imports/preview", files=files)).json()
    response = await client.post(
        "/api/imports",
        files=files,
        data={
            "profile_id": profile_id,
            "mapping": json.dumps(preview["mapping"]),
            "account_name": preview["account_name"],
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def duplicates_of(client: httpx.AsyncClient, profile_id: str, import_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/imports/{import_id}/duplicates", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return dict(response.json())


async def decide(
    client: httpx.AsyncClient,
    profile_id: str,
    import_id: str,
    decisions: list[dict[str, str]] | None = None,
    *,
    remove_all_exact: bool = False,
) -> dict[str, Any]:
    response = await client.post(
        f"/api/imports/{import_id}/duplicates",
        json={
            "profile_id": profile_id,
            "decisions": decisions or [],
            "remove_all_exact": remove_all_exact,
        },
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def rows_of(client: httpx.AsyncClient, profile_id: str) -> list[dict[str, Any]]:
    page = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()
    return list(page["rows"])


async def import_record(client: httpx.AsyncClient, profile_id: str, import_id: str) -> dict[str, Any]:
    imports = (await client.get("/api/imports", params={"profile_id": profile_id})).json()
    return next(record for record in imports if record["id"] == import_id)


async def test_reimporting_the_same_file_holds_every_row_aside_and_the_shortcut_removes_them(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    first = await commit(client, profile_id, upload(SPARKASSE))
    second = await commit(client, profile_id, upload(SPARKASSE))

    assert (first["imported_count"], first["duplicate_count"]) == (TOTAL_ROWS, 0)
    # Nothing was inserted and nothing was dropped: every row waits for an answer.
    assert (second["imported_count"], second["duplicate_count"]) == (0, TOTAL_ROWS)
    assert len(await rows_of(client, profile_id)) == TOTAL_ROWS

    found = await duplicates_of(client, profile_id, second["id"])
    assert (found["found"], found["pending"], found["exact"], found["near"]) == (
        TOTAL_ROWS,
        TOTAL_ROWS,
        TOTAL_ROWS,
        0,
    )
    assert found["shortcut"] is True, "an identical re-import offers to remove them all at once"
    assert len(found["candidates"]) < TOTAL_ROWS, "the page asks a page at a time"
    candidate = found["candidates"][0]
    assert candidate["kind"] == "exact"
    assert candidate["existing_booked_on"] == candidate["booked_on"]
    assert candidate["existing_description"] == candidate["description"]

    result = await decide(client, profile_id, second["id"], remove_all_exact=True)
    assert (result["kept"], result["removed"], result["remaining"]) == (0, TOTAL_ROWS, 0)
    # Removing a duplicate leaves the data exactly as it was.
    assert len(await rows_of(client, profile_id)) == TOTAL_ROWS

    record = await import_record(client, profile_id, second["id"])
    assert (record["duplicate_count"], record["duplicates_kept"], record["duplicates_removed"]) == (
        TOTAL_ROWS,
        0,
        TOTAL_ROWS,
    )
    assert f"0 were kept and {TOTAL_ROWS} removed" in result["summary"]
    assert (await duplicates_of(client, profile_id, second["id"]))["pending"] == 0


async def test_a_one_day_shift_is_a_near_candidate_and_keep_both_inserts_and_categorizes_it(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    await commit(client, profile_id, upload(SPARKASSE))
    second = await commit(client, profile_id, upload_bytes("sparkasse-again.csv", shifted_copy(SPARKASSE)))

    assert (second["imported_count"], second["duplicate_count"]) == (0, TOTAL_ROWS)
    found = await duplicates_of(client, profile_id, second["id"])
    assert (found["exact"], found["near"]) == (TOTAL_ROWS - SHIFTED, SHIFTED)

    near = [row for row in found["candidates"] if row["kind"] == "near"]
    assert len(near) == SHIFTED
    for row in near:
        # The same amount and the same text, one day apart: what the fingerprint cannot see.
        assert row["existing_booked_on"] < row["booked_on"]
        assert row["existing_description"] == row["description"]

    kept = await decide(
        client, profile_id, second["id"], [{"ref": row["ref"], "decision": "keep"} for row in near]
    )
    assert (kept["kept"], kept["removed"]) == (SHIFTED, 0)
    rows = await rows_of(client, profile_id)
    assert len(rows) == TOTAL_ROWS + SHIFTED
    # A kept row is a real booking of that import, categorized like any other.
    inserted = [row for row in rows if row["booked_on"] == near[0]["booked_on"]]
    assert [row for row in inserted if row["description"] == near[0]["description"] and row["title"]]

    left = await duplicates_of(client, profile_id, second["id"])
    assert (left["pending"], left["kept"], left["removed"]) == (TOTAL_ROWS - SHIFTED, SHIFTED, 0)
    rest = await decide(client, profile_id, second["id"], remove_all_exact=True)
    assert (rest["kept"], rest["removed"], rest["remaining"]) == (0, TOTAL_ROWS - SHIFTED, 0)
    assert len(await rows_of(client, profile_id)) == TOTAL_ROWS + SHIFTED

    record = await import_record(client, profile_id, second["id"])
    assert (record["imported_count"], record["duplicates_kept"], record["duplicates_removed"]) == (
        SHIFTED,
        SHIFTED,
        TOTAL_ROWS - SHIFTED,
    )
    assert f"{SHIFTED} were kept and {TOTAL_ROWS - SHIFTED} removed" in rest["summary"]


async def test_removing_one_candidate_leaves_the_others_pending_and_the_data_untouched(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(SIX[:3])))
    second = await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(SIX[:3])))

    found = await duplicates_of(client, profile_id, second["id"])
    assert (found["found"], found["pending"], found["exact"]) == (3, 3, 3)
    # Three candidates fit on one card, so there is nothing to shortcut.
    assert found["shortcut"] is False

    result = await decide(
        client, profile_id, second["id"], [{"ref": found["candidates"][0]["ref"], "decision": "remove"}]
    )
    assert (result["kept"], result["removed"], result["remaining"]) == (0, 1, 2)
    assert len(await rows_of(client, profile_id)) == 3
    assert (await duplicates_of(client, profile_id, second["id"]))["pending"] == 2


def importing_with_duplicates(file_name: str):
    """A chat model that imports the file, shows each duplicate card, then asks for the next.

    It states no figure of its own: the summary is the tool's, every card is the one the server
    built, and after each answered card it asks `review_duplicates` for the next batch.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        imports = _returns(messages, "import_file")
        reviews = _returns(messages, "review_duplicates")
        cards = _returns(messages, "ask_user")
        if not imports:
            yield _call(0, "import_file", file_name=file_name)
            return
        latest = imports[-1]
        if latest["status"] != "imported":
            yield latest.get("message") or latest.get("error") or "Nothing happened."
            return
        if len(cards) < len(reviews) + 1:
            # One card per batch: the first came with the import, every later one from a review.
            card = reviews[-1]["card"] if reviews else latest["duplicate_card"]
            if card:
                yield _call(0, "ask_user", **card)
                return
        if reviews and reviews[-1]["pending"] == 0:
            yield f"{latest['summary']} Every duplicate candidate is decided."
            return
        yield _call(0, "review_duplicates")

    return fn


async def answers_for(
    client: httpx.AsyncClient, conversation_id: str, output: dict[str, Any]
) -> httpx.Response:
    """Answer the card the pending turn is parked on, the way `addToolOutput` does.

    A turn that asked several cards holds all of them, so the open one is the card with no
    output yet, not the first one in the message.
    """
    message = (await transcript(client, conversation_id))["messages"][-1]
    card = next(
        part
        for part in reversed(message["parts"])
        if part["type"] == "tool-ask_user" and not part.get("output")
    )
    return await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=answer_card(conversation_id, message["id"], card, output),
    )


async def test_a_chat_import_asks_about_duplicates_per_batch_and_the_server_applies_the_answers(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast_call = sub_agents()  # type: ignore[assignment]
    scripts.fast = importing_with_duplicates(EIGHT_FILE)
    # The same eight bookings, three of them a day later: three near matches and five exact.
    await commit(client, profile_id, upload_bytes(EIGHT_FILE, mini_csv(EIGHT)))
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach_bytes(conversation_id, "import this", EIGHT_FILE, mini_csv(shift_first(EIGHT, 3))),
    )
    assert first.status_code == 200, first.text
    chunks = parse_sse(first.text)

    output = outputs_of(chunks)[0]
    assert (output["status"], output["imported"], output["duplicates"]) == ("imported", 0, 8)
    assert (output["exact_duplicates"], output["near_duplicates"]) == (5, 3)
    # The merchants wait: one card at a time, and the duplicates come first.
    assert output["questions"] == []
    card = cards_in(chunks)[0]["input"]
    assert card["apply"] == {"kind": "duplicate_decision"}
    assert len(card["rows"]) == BATCH
    assert [option["value"] for option in card["rows"][0]["options"]] == ["keep", "remove"]
    # Five exact is one card's worth, so every candidate is asked about on its own, and the
    # first three are the ones the bank booked a day later.
    assert "1 day apart" in card["rows"][0]["description"]
    assert "same amount and text" in card["rows"][4]["description"]

    # Two kept, three removed, three candidates left over for the next card.
    refs = [row["ref"] for row in card["rows"]]
    decisions = {
        "answers": [
            {"ref": ref, "value": "keep" if index < 2 else "remove", "text": None}
            for index, ref in enumerate(refs)
        ]
    }
    second = await answers_for(client, conversation_id, decisions)
    assert second.status_code == 200, second.text
    resumed = parse_sse(second.text)

    # The server applied the answers before the model was asked to continue.
    answered = [part for part in (await transcript(client, conversation_id))["messages"][-1]["parts"]
                if part["type"] == "tool-ask_user"][0]
    assert answered["output"]["applied"] is not None
    assert "kept 2" in answered["output"]["applied"]
    assert "removed 3" in answered["output"]["applied"]
    # The sentence the model is asked to write is not the line the card already shows, because
    # a model handed a finished sentence writes it back word for word (e2e of 2026-09-05, m4).
    assert answered["output"]["say"] == (
        "Of 5 bookings that looked like duplicates, 2 were kept and 3 removed."
    )
    assert answered["output"]["say"] != answered["output"]["applied"]
    rows = await rows_of(client, profile_id)
    assert len(rows) == 10, "the two kept bookings landed, the three removed ones did not"
    # The eight the REST import brought in were never categorized here, so an enrichment marks
    # exactly the two the applier inserted: a kept booking goes through categorization.
    assert len([row for row in rows if row["title"]]) == 2

    review = [out for out in outputs_of(resumed) if "pending" in out][0]
    assert review["pending"] == 3
    assert len(review["card"]["rows"]) == 3

    third = await answers_for(
        client,
        conversation_id,
        {"answers": [{"ref": row["ref"], "value": "remove", "text": None} for row in review["card"]["rows"]]},
    )
    assert third.status_code == 200, third.text
    finished = parse_sse(third.text)
    assert len(await rows_of(client, profile_id)) == 10
    assert "Every duplicate candidate is decided." in answer(finished)
    assert [out for out in outputs_of(finished) if out.get("pending") == 0]

    record = await import_record(client, profile_id, (await client.get(
        "/api/imports", params={"profile_id": profile_id}
    )).json()[0]["id"])
    assert (record["duplicate_count"], record["duplicates_kept"], record["duplicates_removed"]) == (8, 2, 6)


async def test_a_chat_import_of_a_file_the_profile_has_asks_once_for_all_of_it(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast_call = sub_agents()  # type: ignore[assignment]
    scripts.fast = importing_with_duplicates(SIX_FILE)
    six = mini_csv(SIX)
    await commit(client, profile_id, upload_bytes(SIX_FILE, six))
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach_bytes(conversation_id, "import this", SIX_FILE, six),
    )
    assert first.status_code == 200, first.text
    card = cards_in(parse_sse(first.text))[0]["input"]

    # Six exact matches is more than one card holds, so one row stands for all of them. It is a
    # row and not a button on the question because a row is what survives being copied by the
    # model, and `bookings` is how a card says what a row stands for.
    assert len(card["rows"]) == 1
    row = card["rows"][0]
    assert (row["ref"], row["bookings"]) == ("all-exact", 6)
    assert row["label"] == "All 6 exact duplicates"
    assert [option["value"] for option in row["options"]] == ["remove"]
    assert row["options"][0]["label"] == "Remove all 6"

    answered = await answers_for(
        client, conversation_id, {"answers": [{"ref": "all-exact", "value": "remove", "text": None}]}
    )
    assert answered.status_code == 200, answered.text
    resumed = parse_sse(answered.text)

    applied = [part for part in (await transcript(client, conversation_id))["messages"][-1]["parts"]
               if part["type"] == "tool-ask_user"][0]["output"]["applied"]
    assert "removed 6 duplicates" in applied
    assert "No duplicate candidate is left." in applied
    # One answer, and the data is exactly as it was.
    assert len(await rows_of(client, profile_id)) == 6
    assert [out for out in outputs_of(resumed) if out.get("pending") == 0]
    record = (await client.get("/api/imports", params={"profile_id": profile_id})).json()[0]
    assert (record["duplicate_count"], record["duplicates_removed"]) == (6, 6)


def wrapping_the_card(file_name: str):
    """A chat model that hands the card back the way the fast model really did.

    Seen on OpenRouter on 2026-09-04: the card arrives nested under its own `card` key, twice,
    with every scalar stringified (`"amount_cents": "null"`). Read literally that is a card with
    no title and no rows, and it would not validate, so the answers would apply nothing. The
    server unwraps it and reads `"null"` as null instead.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        imports = _returns(messages, "import_file")
        cards = _returns(messages, "ask_user")
        if not imports:
            yield _call(0, "import_file", file_name=file_name)
            return
        if not cards:
            inner = imports[-1]["duplicate_card"]
            stringified = {
                **inner,
                "allow_free_text": "false",
                "rows": [
                    {key: ("null" if value is None else value) for key, value in row.items()}
                    for row in inner["rows"]
                ],
            }
            yield _call(0, "ask_user", card={"card": stringified, "apply": inner["apply"]})
            return
        yield f"Done. {cards[-1].get('applied')}"

    return fn


async def test_a_card_the_model_wrapped_and_stringified_is_still_applied(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast_call = sub_agents()  # type: ignore[assignment]
    scripts.fast = wrapping_the_card(SIX_FILE)
    six = mini_csv(SIX)
    await commit(client, profile_id, upload_bytes(SIX_FILE, six))
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach_bytes(conversation_id, "import this", SIX_FILE, six),
    )
    assert first.status_code == 200, first.text

    answered = await answers_for(
        client, conversation_id, {"answers": [{"ref": "all-exact", "value": "remove", "text": None}]}
    )
    assert answered.status_code == 200, answered.text
    applied = [part for part in (await transcript(client, conversation_id))["messages"][-1]["parts"]
               if part["type"] == "tool-ask_user"][0]["output"]["applied"]
    assert applied is not None, "a wrapped card must still reach its applier"
    assert "removed 6 duplicates" in applied
    assert len(await rows_of(client, profile_id)) == 6


def typing_a_possible_duplicate(text: str):
    """A chat model that types a booking, confirms the preview, then answers the duplicate card."""

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        previews = _returns(messages, "extract_transaction")
        adds = _returns(messages, "add_transaction")
        cards = _returns(messages, "ask_user")
        if not previews:
            yield _call(0, "extract_transaction", text=text)
            return
        if not cards:
            yield _call(0, "ask_user", **previews[-1]["card"])
            return
        if not adds:
            confirmed = [a["ref"] for card in cards for a in card.get("answers", []) if a.get("value") == "add"]
            for index, ref in enumerate(confirmed):
                yield _call(index, "add_transaction", ref=ref)
            return
        if adds[-1]["status"] == "duplicate_candidate" and len(cards) < 2:
            yield _call(0, "ask_user", **adds[-1]["card"])
            return
        yield f"Done: {cards[-1].get('applied') or adds[-1].get('message')}"

    return fn


async def test_a_typed_booking_the_profile_may_already_have_is_held_aside_too(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    typed = "I paid 12 EUR for lunch on 2 January"
    scripts.fast_call = sub_agents(  # type: ignore[assignment]
        transactions=[
            {
                "booked_on": "2025-01-02",
                "amount": "12.00",
                "direction": "out",
                "description": "Lunch",
                "counterparty": "Kantine",
                "account_name": "Sparkasse Girokonto",
            }
        ]
    )
    scripts.fast = typing_a_possible_duplicate(typed)
    await commit(client, profile_id, upload_bytes("one.csv", mini_csv([("02.01.2025", "Lunch", "Kantine", "-12,00")])))
    conversation_id = await new_conversation(client, profile_id)

    first = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={"id": conversation_id, "trigger": "submit-message",
              "messages": [{"id": "u1", "role": "user", "parts": [{"type": "text", "text": typed}]}]},
    )
    assert first.status_code == 200, first.text

    # Confirming the preview does not write it: the booking looks like the one already there.
    confirmed = await answers_for(client, conversation_id, {"answers": [{"ref": "t1", "value": "add", "text": None}]})
    assert confirmed.status_code == 200, confirmed.text
    resumed = parse_sse(confirmed.text)
    held = [out for out in outputs_of(resumed) if out.get("status") == "duplicate_candidate"][0]
    assert "looks like a booking this profile already has in Sparkasse Girokonto" in held["message"]
    assert len(await rows_of(client, profile_id)) == 1

    card = cards_in(resumed)[-1]["input"]
    assert card["apply"] == {"kind": "duplicate_decision"}
    assert [option["value"] for option in card["rows"][0]["options"]] == ["keep", "remove"]

    kept = await answers_for(
        client, conversation_id, {"answers": [{"ref": card["rows"][0]["ref"], "value": "keep", "text": None}]}
    )
    assert kept.status_code == 200, kept.text
    rows = await rows_of(client, profile_id)
    assert len(rows) == 2
    manual = [row for row in rows if row["source"] == "manual"]
    assert len(manual) == 1
    assert (manual[0]["amount_cents"], manual[0]["description"], manual[0]["account"]) == (
        -1200,
        "Lunch",
        "Sparkasse Girokonto",
    )
    assert "kept 1 booking" in answer(parse_sse(kept.text))


@pytest.mark.skipif(not OVERLAP_A.exists(), reason="the private Trade Republic frames are not here")
async def test_two_overlapping_trade_republic_frames_find_exactly_the_shared_months(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    first = await commit(client, profile_id, upload(OVERLAP_A))
    second = await commit(client, profile_id, upload(OVERLAP_B))

    assert first["preset"] == "traderepublic"
    assert first["account_name"] == "Trade Republic"
    found = await duplicates_of(client, profile_id, second["id"])
    # March and April are in both frames; nothing outside them is a candidate.
    assert (found["found"], found["exact"], found["near"]) == (OVERLAP_ROWS, OVERLAP_ROWS, 0)
    assert second["imported_count"] == second["row_count"] - OVERLAP_ROWS
    assert {row["booked_on"][:7] for row in found["candidates"]} <= {"2025-03", "2025-04"}

    total = len(await rows_of(client, profile_id))
    result = await decide(client, profile_id, second["id"], remove_all_exact=True)
    assert (result["kept"], result["removed"], result["remaining"]) == (0, OVERLAP_ROWS, 0)
    assert len(await rows_of(client, profile_id)) == total


# The candidates of an import that is no longer the latest one, and undoing an import.


async def delete_import(client: httpx.AsyncClient, profile_id: str, import_id: str) -> dict[str, Any]:
    response = await client.delete(f"/api/imports/{import_id}", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_the_candidates_of_an_older_import_are_still_listed_and_still_decidable(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The page reads them back whenever it opens, not only right after the commit that held them.

    An undecided import stays undecided while other imports happen, and the endpoint answers for
    that import alone: its counts, its pending candidates and the file they came from.
    """
    await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(SIX[:3])))
    waiting = await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(SIX[:3])))
    later = await commit(client, profile_id, upload_bytes(EIGHT_FILE, mini_csv(SIX[3:])))

    assert (waiting["imported_count"], waiting["duplicate_count"]) == (0, 3)
    assert (later["imported_count"], later["duplicate_count"]) == (3, 0)
    assert (await duplicates_of(client, profile_id, later["id"]))["pending"] == 0

    found = await duplicates_of(client, profile_id, waiting["id"])
    assert (found["found"], found["pending"], found["exact"]) == (3, 3, 3)
    assert found["file_name"] == SIX_FILE
    assert len(found["candidates"]) == 3

    # Deciding from that list works the same as deciding right after the commit.
    result = await decide(
        client,
        profile_id,
        waiting["id"],
        [{"ref": candidate["ref"], "decision": "remove"} for candidate in found["candidates"]],
    )
    assert (result["kept"], result["removed"], result["remaining"]) == (0, 3, 0)
    record = await import_record(client, profile_id, waiting["id"])
    assert (record["duplicates_kept"], record["duplicates_removed"]) == (0, 3)


async def test_an_import_with_candidates_opens_a_conversation_that_asks_about_them(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """"Continue in chat" on the Imports overview, for an import with no conversation of its own.

    Nothing is stranded: the seeded turn holds the duplicate card, not the categorization one,
    because a booking nobody has decided about is not in the data yet.
    """
    scripts.fast = script("Removed those three.")
    await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(SIX[:3])))
    waiting = await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(SIX[:3])))

    opened = await client.post(
        f"/api/imports/{waiting['id']}/review-conversation", json={"profile_id": profile_id}
    )
    assert opened.status_code == 201, opened.text
    body = opened.json()
    assert (body["questions"], body["pending_merchants"]) == (3, 0)

    detail = (await client.get(f"/api/conversations/{body['conversation_id']}")).json()
    assistant = detail["messages"][1]
    assert [part["type"] for part in assistant["parts"]] == ["text", "tool-ask_user"]
    assert "3 look like bookings you already have" in assistant["parts"][0]["text"]
    card = assistant["parts"][1]["input"]
    assert card["apply"] == {"kind": "duplicate_decision"}
    assert [option["value"] for option in card["rows"][0]["options"]] == ["keep", "remove"]

    # Answering it decides the candidates, the same as any other duplicate card.
    answered = await answers_for(
        client,
        body["conversation_id"],
        {"answers": [{"ref": row["ref"], "value": "remove", "text": None} for row in card["rows"]]},
    )
    assert answered.status_code == 200, answered.text
    assert (await duplicates_of(client, profile_id, waiting["id"]))["pending"] == 0


async def test_deleting_an_import_takes_its_bookings_candidates_and_decisions_with_it(
    client: httpx.AsyncClient, scripts: Scripts, session_factory: sessionmaker[Session], profile_id: str
) -> None:
    """An import into the wrong profile has to be undoable, and undoing it leaves nothing behind.

    The booking a Keep both decision inserted belongs to the second import and goes with it; the
    booking it was a near match of came in with the first import and stays.
    """
    scripts.fast_call = scripted_categorizer()  # type: ignore[assignment]
    first = await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(SIX)))
    second = await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(shift_first(SIX, 1))))

    found = await duplicates_of(client, profile_id, second["id"])
    near = [candidate for candidate in found["candidates"] if candidate["kind"] == "near"]
    assert len(near) == 1
    kept = await decide(client, profile_id, second["id"], [{"ref": near[0]["ref"], "decision": "keep"}])
    assert (kept["kept"], kept["removed"]) == (1, 0)
    assert len(await rows_of(client, profile_id)) == len(SIX) + 1

    deleted = await delete_import(client, profile_id, second["id"])
    assert deleted == {"transactions": 1, "candidates": len(SIX)}

    # The bookings of the first import are untouched, the kept one is gone with its import.
    assert len(await rows_of(client, profile_id)) == len(SIX)
    imports = (await client.get("/api/imports", params={"profile_id": profile_id})).json()
    assert [record["id"] for record in imports] == [first["id"]]

    gone = await client.get(f"/api/imports/{second['id']}/duplicates", params={"profile_id": profile_id})
    assert gone.status_code == 404
    # A candidate and the decision on it are one row: it goes too, rather than only stops showing.
    with session_factory() as session:
        assert session.scalars(select(DuplicateCandidate)).all() == []


async def test_an_import_of_another_profile_cannot_be_deleted(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    other = (await client.post("/api/profiles", json={"name": "Haushalt"})).json()
    record = await commit(client, profile_id, upload_bytes(SIX_FILE, mini_csv(SIX[:3])))

    refused = await client.delete(f"/api/imports/{record['id']}", params={"profile_id": other["id"]})
    assert refused.status_code == 404

    assert len(await rows_of(client, profile_id)) == 3
    assert (await import_record(client, profile_id, record["id"]))["id"] == record["id"]
