import asyncio
from collections.abc import AsyncIterator

import httpx
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart

from finquery.app import create_app

from .conftest import (
    Chat,
    Scripts,
    chat_body,
    default_profile_id,
    is_followup_request,
    make_settings,
    new_conversation,
    parse_sse,
    script,
)


def kinds(chunks: list[dict[str, object]]) -> list[str]:
    # message-metadata is bookkeeping (model slot, interrupted flag), not part of the visible order.
    return [str(c["type"]) for c in chunks if c["type"] != "message-metadata"]


def collapse(types: list[str]) -> list[str]:
    out: list[str] = []
    for t in types:
        if not out or out[-1] != t:
            out.append(t)
    return out


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.json() == {"provider": "openrouter", "slots": ["fast", "quality"]}


async def test_stream_order_reasoning_text_finish(client: httpx.AsyncClient, scripts: Scripts, chat: Chat) -> None:
    scripts.fast = script("I cannot compute numbers yet.", thought="Let me think about that.")
    conversation_id = await new_conversation(client, await default_profile_id(client))

    response, chunks = await chat(conversation_id, "How much did I spend in May?")

    assert response.status_code == 200
    assert response.headers["x-vercel-ai-ui-message-stream"] == "v1"
    assert response.text.rstrip().endswith("data: [DONE]")
    assert collapse(kinds(chunks)) == [
        "start",
        "start-step",
        "reasoning-start",
        "reasoning-delta",
        "reasoning-end",
        "text-start",
        "text-delta",
        "text-end",
        "finish-step",
        "finish",
    ]
    assert "".join(str(c["delta"]) for c in chunks if c["type"] == "reasoning-delta") == "Let me think about that."
    assert "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta").strip() == "I cannot compute numbers yet."


async def test_turn_is_persisted_and_history_is_server_owned(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    seen: list[list[ModelMessage]] = []

    async def recording(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        seen.append(messages)
        yield {0: DeltaThinkingPart(content="thinking")}
        yield f"answer {len(seen)}"

    scripts.fast = recording
    conversation_id = await new_conversation(client, await default_profile_id(client))

    await chat(conversation_id, "first question")
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["title"] == "first question"
    assert detail["interrupted"] is False
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert [p["type"] for p in detail["messages"][1]["parts"]] == ["reasoning", "text"]
    assert detail["messages"][1]["metadata"]["thinking_seconds"] >= 0
    assert detail["messages"][1]["parts"][1]["text"] == "answer 1"

    # The client resends its whole transcript; the server keeps its own history and appends only the newest message.
    body = chat_body("second question", conversation_id, extra_messages=detail["messages"])
    await client.post(f"/api/conversations/{conversation_id}/chat", json=body)
    assert len(seen) == 2
    user_prompts = [
        part.content for msg in seen[1] if msg.kind == "request" for part in msg.parts if part.part_kind == "user-prompt"
    ]
    assert user_prompts == ["first question", "second question"]
    assert len((await client.get(f"/api/conversations/{conversation_id}")).json()["messages"]) == 4


async def test_stop_persists_partial_turn_as_interrupted(client: httpx.AsyncClient, scripts: Scripts) -> None:
    started = asyncio.Event()

    async def slow(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        yield {0: DeltaThinkingPart(content="deep thought")}
        yield "partial "
        started.set()
        await asyncio.sleep(60)
        yield "never sent"

    scripts.fast = slow
    conversation_id = await new_conversation(client, await default_profile_id(client))

    turn = asyncio.create_task(
        client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body("go", conversation_id))
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    stop = await client.post(f"/api/conversations/{conversation_id}/stop")
    assert stop.json() == {"stopped": True}

    response = await asyncio.wait_for(turn, timeout=5)
    chunks = parse_sse(response.text)
    assert "abort" in kinds(chunks)
    assert "finish" not in kinds(chunks)
    metadata = [c for c in chunks if c["type"] == "message-metadata"]
    assert metadata and metadata[-1]["messageMetadata"]["interrupted"] is True
    assert isinstance(metadata[-1]["messageMetadata"]["thinking_seconds"], float)

    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["interrupted"] is True
    assistant = detail["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["metadata"]["interrupted"] is True
    assert assistant["parts"][0]["type"] == "reasoning"
    assert assistant["parts"][1]["text"].strip() == "partial"

    # Nothing is running any more, so a second stop is a no-op.
    assert (await client.post(f"/api/conversations/{conversation_id}/stop")).json() == {"stopped": False}


async def test_local_provider_starts_but_refuses_to_chat() -> None:
    app = create_app(make_settings(provider="local"), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/health")).json()["provider"] == "local"
            conversation_id = await new_conversation(client, await default_profile_id(client))
            response = await client.post(
                f"/api/conversations/{conversation_id}/chat", json=chat_body("hi", conversation_id)
            )
            assert response.status_code == 503
            assert "ticket 16" in response.json()["detail"]


async def test_unknown_conversation_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/conversations/nope")).status_code == 404
    assert (await client.post("/api/conversations/nope/chat", json=chat_body("hi", "nope"))).status_code == 404
