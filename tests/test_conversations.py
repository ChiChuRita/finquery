import asyncio
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart

from finquery.api.conversations import TITLE_LENGTH
from finquery.app import create_app

from .conftest import (
    Chat,
    NoWeb,
    Scripts,
    chat_body,
    default_profile_id,
    is_followup_request,
    make_settings,
    new_conversation,
    parse_sse,
    script,
)


def data_parts(chunks: list[dict[str, object]], kind: str) -> list[dict[str, object]]:
    return [c for c in chunks if c["type"] == kind]


def assistant_metadata(chunks: list[dict[str, object]]) -> dict[str, object]:
    """What the client ends up with: every message-metadata chunk of the turn, merged in order."""
    merged: dict[str, object] = {}
    for chunk in chunks:
        if chunk["type"] == "message-metadata":
            merged.update(chunk["messageMetadata"])  # type: ignore[arg-type]
    assert merged, "the turn sent no message metadata"
    return merged


async def test_conversation_can_be_renamed_and_deleted(client: httpx.AsyncClient) -> None:
    profile_id = await default_profile_id(client)
    conversation_id = await new_conversation(client, profile_id)

    renamed = await client.patch(f"/api/conversations/{conversation_id}", json={"title": "  Grocery spending  "})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "Grocery spending"
    assert (await client.patch(f"/api/conversations/{conversation_id}", json={"title": " "})).status_code == 422
    # A pasted paragraph is a title too long for the sidebar and for the column, so it is cut
    # rather than refused: nothing about it is a mistake the user has to correct.
    long = await client.patch(f"/api/conversations/{conversation_id}", json={"title": "Groceries " * 50})
    assert long.status_code == 200, long.text
    assert len(long.json()["title"]) == TITLE_LENGTH

    assert (await client.delete(f"/api/conversations/{conversation_id}")).status_code == 204
    assert (await client.get(f"/api/conversations/{conversation_id}")).status_code == 404
    assert (await client.delete(f"/api/conversations/{conversation_id}")).status_code == 404
    assert (await client.get("/api/conversations", params={"profile_id": profile_id})).json() == []


async def test_conversations_are_listed_by_last_activity(client: httpx.AsyncClient, scripts: Scripts, chat: Chat) -> None:
    scripts.fast = script("answer")
    profile_id = await default_profile_id(client)
    first = await new_conversation(client, profile_id)
    second = await new_conversation(client, profile_id)

    await chat(second, "second question")
    await chat(first, "first question")

    listing = (await client.get("/api/conversations", params={"profile_id": profile_id})).json()
    assert [c["id"] for c in listing] == [first, second]
    assert [c["title"] for c in listing] == ["first question", "second question"]


async def test_model_slot_switches_mid_conversation_and_every_turn_carries_its_slot(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    scripts.fast = script("fast answer", thought="f")
    scripts.quality = script("quality answer", thought="q")
    profile_id = await default_profile_id(client)
    conversation_id = await new_conversation(client, profile_id)

    _, first = await chat(conversation_id, "first question")
    assert assistant_metadata(first)["model_slot"] == "fast"

    assert (await client.patch(f"/api/conversations/{conversation_id}", json={"model_slot": "quality"})).status_code == 200
    assert (await client.patch(f"/api/conversations/{conversation_id}", json={"model_slot": "turbo"})).status_code == 422
    _, second = await chat(conversation_id, "second question")
    assert assistant_metadata(second)["model_slot"] == "quality"
    assert "".join(str(c["delta"]) for c in second if c["type"] == "text-delta").strip() == "quality answer"

    # Three resolutions per turn: the chat model on the conversation's slot, then the two
    # post-turn steps (follow-up suggestions, memory distillation), both pinned to fast.
    assert scripts.resolved == ["fast", "fast", "fast", "quality", "fast", "fast"]
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["metadata"]["model_slot"] for m in detail["messages"] if m["role"] == "assistant"] == ["fast", "quality"]
    assert detail["model_slot"] == "quality"


async def test_switching_the_slot_while_a_turn_runs_lands_on_the_next_turn(
    client: httpx.AsyncClient, scripts: Scripts
) -> None:
    """The model of a running turn was resolved when it started, and it keeps it.

    The picker in the composer writes the conversation's slot, which is read at the top of the
    next request. Switching it mid-answer must not relabel the turn that is on screen, and must
    not be refused either: it is a setting, not part of the turn.
    """
    started = asyncio.Event()
    release = asyncio.Event()

    async def waits(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        started.set()
        await release.wait()
        yield "answered on the fast slot"

    scripts.fast = waits
    scripts.quality = script("answered on the quality slot")
    conversation_id = await new_conversation(client, await default_profile_id(client))

    turn = asyncio.create_task(
        client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body("first", conversation_id))
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    switched = await client.patch(f"/api/conversations/{conversation_id}", json={"model_slot": "quality"})
    assert switched.status_code == 200
    release.set()
    running = await asyncio.wait_for(turn, timeout=5)

    assert assistant_metadata(parse_sse(running.text))["model_slot"] == "fast"
    response = await client.post(
        f"/api/conversations/{conversation_id}/chat", json=chat_body("second", conversation_id)
    )
    assert assistant_metadata(parse_sse(response.text))["model_slot"] == "quality"
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["metadata"]["model_slot"] for m in detail["messages"] if m["role"] == "assistant"] == [
        "fast",
        "quality",
    ]


async def test_followup_suggestions_travel_as_a_data_part_and_are_persisted(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    # Only questions are kept, so a chatty preamble from the model never becomes a suggestion.
    scripts.fast = script(
        "You have no data yet.",
        followups=["Here are some ideas:", "How do I import a statement?", "What can you do?"],
    )
    profile_id = await default_profile_id(client)
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "what can you do")

    parts = data_parts(chunks, "data-followups")
    assert len(parts) == 1
    assert parts[0]["data"] == {"suggestions": ["How do I import a statement?", "What can you do?"]}

    assistant = (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"][-1]
    followups = [p for p in assistant["parts"] if p["type"] == "data-followups"]
    assert followups and followups[0]["data"]["suggestions"][0] == "How do I import a statement?"


async def test_a_turn_without_usable_followups_emits_no_data_part(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    scripts.fast = script("You have no data yet.")
    profile_id = await default_profile_id(client)
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "what can you do")

    assert data_parts(chunks, "data-followups") == []


async def test_the_conversation_continues_after_an_interruption(client: httpx.AsyncClient, scripts: Scripts) -> None:
    started = asyncio.Event()
    seen: list[list[ModelMessage]] = []

    async def stalling(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "Anything else?"
            return
        seen.append(messages)
        if len(seen) == 1:
            yield {0: DeltaThinkingPart(content="deep thought")}
            yield "half an ans"
            started.set()
            await asyncio.sleep(60)
            yield "never sent"
        else:
            yield "the full answer"

    scripts.fast = stalling
    profile_id = await default_profile_id(client)
    conversation_id = await new_conversation(client, profile_id)

    interrupted_turn = asyncio.create_task(
        client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body("go", conversation_id))
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    assert (await client.post(f"/api/conversations/{conversation_id}/stop")).json() == {"stopped": True}
    stopped = parse_sse((await asyncio.wait_for(interrupted_turn, timeout=5)).text)
    # An interrupted turn gets no follow-up suggestions, it was cut off mid-thought.
    assert data_parts(stopped, "data-followups") == []

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat", json=chat_body("and now?", conversation_id)
    )
    chunks = parse_sse(response.text)

    assert response.status_code == 200
    assert "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta").strip() == "the full answer"
    # The next run sees the interrupted turn: its user message, the partial answer, then the new question.
    continued = [
        (part.part_kind, part.content)
        for message in seen[1]
        for part in message.parts
        if part.part_kind in {"user-prompt", "text"}
    ]
    assert continued == [("user-prompt", "go"), ("text", "half an ans"), ("user-prompt", "and now?")]

    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail["messages"][1]["metadata"]["interrupted"] is True
    assert detail["messages"][3]["metadata"].get("interrupted") is None
    assert detail["interrupted"] is False


async def test_a_database_from_before_the_rolling_summary_keeps_its_conversations(tmp_path: Path) -> None:
    """Columns added to a shipped table are migrated in, so nobody's chats are lost on upgrade."""
    db = tmp_path / "finquery.db"

    async def conversations(title: str | None = None) -> list[dict[str, object]]:
        app = create_app(
            make_settings(db_path=db),
            resolve_model=lambda _slot: None,  # type: ignore[arg-type,return-value]
            web_client=NoWeb(),
            serve_frontend=False,
        )
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                profile_id = await default_profile_id(client)
                if title is not None:
                    conversation_id = await new_conversation(client, profile_id)
                    await client.patch(f"/api/conversations/{conversation_id}", json={"title": title})
                return list((await client.get(f"/api/conversations?profile_id={profile_id}")).json())

    await conversations("Groceries in May")
    # Make the file look like one written before ticket 12 added the rolling summary.
    with sqlite3.connect(db) as connection:
        connection.execute("ALTER TABLE conversation DROP COLUMN summary")
        connection.execute("ALTER TABLE conversation DROP COLUMN summary_through")

    rows = await conversations()

    assert [row["title"] for row in rows] == ["Groceries in May"]
