import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, DeltaToolCall

from finquery import agent
from finquery.api import chat as chat_api
from finquery.app import create_app
from finquery.local.runtime import LocalStack
from finquery.providers import ProviderNotAvailable

from .conftest import (
    Chat,
    NoWeb,
    Scripts,
    chat_body,
    default_profile_id,
    distilled,
    is_distillation_request,
    is_followup_request,
    make_settings,
    new_conversation,
    parse_sse,
    script,
)


def kinds(chunks: list[dict[str, object]]) -> list[str]:
    # message-metadata is bookkeeping (model slot, interrupted flag), not part of the visible order.
    return [str(c["type"]) for c in chunks if c["type"] != "message-metadata"]


def turn_metadata(chunks: list[dict[str, object]]) -> dict[str, object]:
    """The turn's own metadata, told apart from the one pydantic AI adds for its timestamp."""
    ours = [
        c["messageMetadata"]
        for c in chunks
        if c["type"] == "message-metadata" and "model_slot" in c["messageMetadata"]  # type: ignore[operator]
    ]
    assert ours, chunks
    return dict(ours[-1])  # type: ignore[call-overload]


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
        # The context badge's stats: tokens, budget and the memories the turn was given.
        "data-context",
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
        if is_distillation_request(messages):
            yield distilled()
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
    assert [p["type"] for p in detail["messages"][1]["parts"]] == ["reasoning", "text", "data-context"]
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


async def test_stopping_a_running_tool_answers_its_call_with_a_sentence_not_a_result(
    client: httpx.AsyncClient, scripts: Scripts, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stop while a tool is running, which is what took the app to the error boundary.

    A cancelled run closes the open call with a plain sentence where the tool's own result
    object belongs, so the browser gets a `chart` step in state `output-available` whose output
    is a string. Every field a chart card reads off it is then undefined, and reading `.length`
    on one of them replaced the whole page with "Something went wrong!" (e2e of 2026-09-05, B1).
    The card guards the part; this pins the shape the guard exists for, and that the partial
    turn keeps the step.
    """
    running = asyncio.Event()

    async def never_returns(*_args: object, **_kwargs: object) -> object:
        running.set()
        await asyncio.sleep(60)
        raise AssertionError("the chart tool should have been cancelled")

    monkeypatch.setattr(agent, "run_chart", never_returns)

    async def asks_for_a_chart(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        yield {0: DeltaThinkingPart(content="planning a chart")}
        yield {1: DeltaToolCall(name="chart", json_args='{"request": "spending per month"}')}

    scripts.fast = asks_for_a_chart
    conversation_id = await new_conversation(client, await default_profile_id(client))

    turn = asyncio.create_task(
        client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body("chart it", conversation_id))
    )
    await asyncio.wait_for(running.wait(), timeout=5)
    assert (await client.post(f"/api/conversations/{conversation_id}/stop")).json() == {"stopped": True}
    chunks = parse_sse((await asyncio.wait_for(turn, timeout=5)).text)

    calls = [c for c in chunks if c["type"] == "tool-input-available"]
    assert [c["toolName"] for c in calls] == ["chart"]
    outputs = [c for c in chunks if c["type"] == "tool-output-available"]
    assert len(outputs) == 1, chunks
    # Not the chart tool's result: a sentence, with none of the fields the card reads.
    assert isinstance(outputs[0]["output"], str)
    assert "abort" in kinds(chunks)

    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["interrupted"] is True
    parts = [p["type"] for p in detail["messages"][-1]["parts"]]
    # The partial turn keeps its thinking and the step the tool never finished (m6).
    assert parts == ["reasoning", "tool-chart", "data-context"]


async def test_local_provider_refuses_to_chat_until_the_models_are_downloaded(tmp_path: Path) -> None:
    settings = make_settings(provider="local", models_dir=tmp_path / "empty")
    stack = LocalStack(settings, load=lambda *_: pytest.fail("nothing should be loaded"))
    app = create_app(settings, local=stack, web_client=NoWeb(), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/api/health")).json()["provider"] == "local"
            conversation_id = await new_conversation(client, await default_profile_id(client))
            response = await client.post(
                f"/api/conversations/{conversation_id}/chat", json=chat_body("hi", conversation_id)
            )
            assert response.status_code == 503
            assert "not downloaded yet" in response.json()["detail"]


async def test_a_hanging_post_turn_step_does_not_hold_the_finished_answer(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two post-turn steps run on a clock: a model looping on one of them costs the
    suggestions, never the answer."""
    monkeypatch.setattr(chat_api, "POST_TURN_TIMEOUT", 0.2)

    async def stalling(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            await asyncio.sleep(60)
            yield "never sent"
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        yield "the answer"

    scripts.fast = stalling
    conversation_id = await new_conversation(client, await default_profile_id(client))

    _, chunks = await chat(conversation_id, "anything")

    assert "finish" in kinds(chunks)
    assert [c for c in chunks if c["type"] == "data-followups"] == []
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][-1]["parts"][-1]["type"] == "data-context"


async def test_a_thinking_only_response_is_retried_without_a_user_bubble(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """A model that answers with nothing but thinking gets a retry prompt from the agent.

    That prompt is a request message, so the dump would render it as if the user had typed
    "Validation feedback: ...". The model history keeps it; the transcript must not show it.
    """
    attempts = 0

    async def thinks_then_answers(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        nonlocal attempts
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        attempts += 1
        if attempts == 1:
            yield {0: DeltaThinkingPart(content="Only thinking, no answer.")}
            return
        yield "Groceries are the biggest share."

    scripts.fast = thinks_then_answers
    conversation_id = await new_conversation(client, await default_profile_id(client))

    await chat(conversation_id, "What do I spend most on?")

    assert attempts == 2
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["parts"][0]["text"] == "What do I spend most on?"
    texts = [part.get("text", "") for message in detail["messages"] for part in message["parts"]]
    assert not any("Validation feedback" in text for text in texts)


async def test_chat_template_tokens_never_reach_the_answer(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """Gemma's end-of-turn marker is text on OpenRouter, and it arrives split across deltas.

    It has to be gone from the stream and from what a reload renders, whichever provider
    produced it.
    """

    async def leaks(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        yield "In 2025 your income was 68.469,80 EUR."
        # One marker split over two deltas, one whole: both are template tokens, not text.
        yield "<tur"
        yield "n|>"
        yield " Nothing else.<turn|>"

    scripts.fast = leaks
    conversation_id = await new_conversation(client, await default_profile_id(client))

    response, chunks = await chat(conversation_id, "What was my income in 2025?")

    text = "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta")
    assert text.strip() == "In 2025 your income was 68.469,80 EUR. Nothing else."
    assert "turn|>" not in response.text
    detail = await client.get(f"/api/conversations/{conversation_id}")
    assert "turn|>" not in detail.text


async def test_a_bare_channel_name_never_reaches_the_answer(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """OpenRouter swallows `<|channel>` but hands its channel name back as ordinary text.

    The walkthrough of 2026-09-05 got two answers with a line reading nothing but `thought`.
    A word that happens to contain one of those names is untouched.
    """

    async def leaks(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        yield "I thought about it.\n"
        # A whole line, and one split across two deltas the way a stream really arrives.
        yield "thought\n"
        yield "thou"
        yield "ght\nYour income was 68.469,80 EUR.\n"

    scripts.fast = leaks
    conversation_id = await new_conversation(client, await default_profile_id(client))

    response, chunks = await chat(conversation_id, "What was my income in 2025?")

    text = "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta")
    assert text.strip() == "I thought about it.\nYour income was 68.469,80 EUR."
    assert "\nthought\n" not in response.text
    detail = await client.get(f"/api/conversations/{conversation_id}")
    stored = detail.json()["messages"][-1]["parts"]
    answers = [part["text"] for part in stored if part["type"] == "text"]
    assert [answer.strip() for answer in answers] == ["I thought about it.\nYour income was 68.469,80 EUR."]


async def test_the_thinking_duration_covers_the_whole_turn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """A turn thinks once before its tool call and once after; the badge reports both.

    Only the last block used to be measured, so a turn that visibly thought for eight seconds
    reported one (review of 2026-09-04).
    """
    step = 0

    async def thinks_twice(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        nonlocal step
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        step += 1
        if step == 1:
            yield {0: DeltaThinkingPart(content="Let me remember that.")}
            # The block stays open while this sleeps, which is what has to be measured.
            await asyncio.sleep(0.4)
            yield {1: DeltaToolCall(name="remember", json_args='{"text": "Anna is a friend."}')}
            return
        yield {0: DeltaThinkingPart(content="Done.")}
        yield "Stored."

    scripts.fast = thinks_twice
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Remember that Anna is a friend.")

    seconds = turn_metadata(chunks)["thinking_seconds"]
    assert isinstance(seconds, float) and seconds >= 0.4, "the first block was not counted"
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"][-1]["metadata"]["thinking_seconds"] == seconds


async def test_a_turn_keeps_the_slot_that_produced_it_when_the_conversation_switches(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Story 10: a turn's model label is what produced it and never changes."""
    scripts.fast = script("The fast answer.")
    scripts.quality = script("The careful answer.")
    conversation_id = await new_conversation(client, profile_id, slot="fast")

    await chat(conversation_id, "first question")
    patched = await client.patch(f"/api/conversations/{conversation_id}", json={"model_slot": "quality"})
    assert patched.status_code == 200, patched.text
    await chat(conversation_id, "second question")

    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assistants = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert [m["metadata"]["model_slot"] for m in assistants] == ["fast", "quality"]


async def test_the_prompt_carries_the_language_money_and_bulk_rules(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Three findings of the review are prompt work, so the prompt is what is asserted."""
    seen: list[str] = []

    async def recording(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        seen.append(getattr(messages[-1], "instructions", None) or "")
        yield "Alles klar."

    scripts.fast = recording
    conversation_id = await new_conversation(client, profile_id)

    await chat(conversation_id, "Wie viel habe ich im Mai ausgegeben?")

    prompt = seen[-1]
    # The language follows the newest message, not the conversation so far.
    assert "language of the user's newest message" in prompt
    # Money in prose is German, so the answer and the tool result read the same.
    assert "1.234,56 EUR" in prompt
    # A bulk change is a changeset with a preview, never a rule that writes rows at once.
    assert "never `set_rule`" in prompt
    # A question the data cannot answer gets a reason and an alternative.
    assert "one sentence why" in prompt


async def test_a_question_the_data_cannot_answer_still_gets_follow_ups(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The unanswerable turn was the one turn of the review with no suggestions under it."""
    asked: list[str] = []

    async def recording(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            asked.append(getattr(messages[-1], "instructions", None) or "")
            yield "How much did I spend in 2025?"
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        yield "A credit score is not part of a bank statement, so the data cannot say."

    scripts.fast = recording
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "What is my credit score?")

    # The follow-up step is told to offer what the data can answer instead of giving up.
    assert "cannot be answered from the data" in asked[-1]
    suggestions = [c["data"] for c in chunks if c["type"] == "data-followups"]
    assert suggestions == [{"suggestions": ["How much did I spend in 2025?"]}]


async def test_unknown_conversation_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/conversations/nope")).status_code == 404
    assert (await client.post("/api/conversations/nope/chat", json=chat_body("hi", "nope"))).status_code == 404


async def test_the_reasoning_stream_gets_the_filter_the_answer_gets(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """Thinking is part of the transcript, so the same two things are taken out of it.

    The second review found a raw `<turn|>` inside an expanded reasoning panel and the model
    reasoning out loud about "Validation feedback: Please return text or call a tool", which is
    pydantic AI's retry plumbing and never something the user asked about.
    """

    async def leaks(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        yield {0: DeltaThinkingPart(content="The user asks about groceries.\n")}
        # The framework's retry prompt, reasoned about out loud, and a template token split
        # across two deltas, exactly as they arrived in the review session.
        yield {0: DeltaThinkingPart(content="The previous message 'Validation feedback: Please ")}
        yield {0: DeltaThinkingPart(content="return text or call a tool.' is a system message.\n")}
        yield {0: DeltaThinkingPart(content="I will query the year.<tur")}
        yield {0: DeltaThinkingPart(content="n|>\n")}
        yield "Groceries were 8.907,96 EUR."

    scripts.fast = leaks
    conversation_id = await new_conversation(client, await default_profile_id(client))

    response, chunks = await chat(conversation_id, "What did I spend on groceries?")

    thinking = "".join(
        str(c["delta"]) for c in chunks if c["type"] == "reasoning-delta" and not str(c["id"]).startswith("narration")
    )
    assert "The user asks about groceries." in thinking
    assert "I will query the year." in thinking
    assert "Validation feedback" not in thinking
    assert "turn|>" not in thinking
    assert "Validation feedback" not in response.text
    assert "turn|>" not in response.text

    # And the reload shows the same cleaned panel, not the raw one.
    detail = await client.get(f"/api/conversations/{conversation_id}")
    assert "Validation feedback" not in detail.text
    assert "turn|>" not in detail.text
    reasoning = [
        part["text"]
        for message in detail.json()["messages"]
        for part in message["parts"]
        if part["type"] == "reasoning"
    ]
    assert any("I will query the year." in text for text in reasoning)


def _parked(started: asyncio.Event):
    """A model that answers nothing and never returns, so the turn is running until told."""

    async def fn(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        yield "half an "
        started.set()
        await asyncio.sleep(60)
        yield "answer"

    return fn


async def test_a_turn_still_running_when_the_server_stops_is_interrupted_on_the_next_start(
    scripts: Scripts, tmp_path: Path
) -> None:
    """A process that dies mid-turn leaves the turn open; the next one marks it and moves on.

    Nothing writes the turn out when the process is killed, so before this the question simply
    disappeared: the conversation opened on the transcript it had before the message was typed,
    with no way to tell whether an answer was still coming. The turn is written down when the
    run starts and its end marker goes on when the run ends, so what the second process finds
    open belongs to a process that is not here any more.

    The restart is two apps over one database file: the first one's request is left running,
    exactly as it is when the process it lives in goes away.
    """
    settings = make_settings(db_path=tmp_path / "restart.sqlite")
    started = asyncio.Event()
    scripts.fast = _parked(started)
    first = create_app(settings, resolve_model=scripts.resolve, web_client=NoWeb(), serve_frontend=False)

    async with first.router.lifespan_context(first):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=first), base_url="http://test") as client:
            profile_id = await default_profile_id(client)
            conversation_id = await new_conversation(client, profile_id)
            turn = asyncio.create_task(
                client.post(
                    f"/api/conversations/{conversation_id}/chat",
                    json=chat_body("What did I spend on groceries?", conversation_id),
                )
            )
            await asyncio.wait_for(started.wait(), timeout=5)
            # While it runs the question is already stored, and it is not marked interrupted:
            # an answer is still on its way.
            running = (await client.get(f"/api/conversations/{conversation_id}")).json()
            assert [m["role"] for m in running["messages"]] == ["user"]
            assert running["interrupted"] is False
            assert running["title"] == "What did I spend on groceries?"

    # The second process. The first one's task is still parked, the way a killed process's work
    # simply stops existing.
    second = create_app(settings, resolve_model=scripts.resolve, web_client=NoWeb(), serve_frontend=False)
    async with second.router.lifespan_context(second):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=second), base_url="http://test") as client:
            detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
            assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
            assert detail["messages"][0]["parts"][0]["text"] == "What did I spend on groceries?"
            assert detail["interrupted"] is True
            assert detail["messages"][1]["metadata"]["interrupted"] is True
            # The running-turn registry is a fresh dictionary, so the conversation takes a new
            # message instead of answering 409 for a turn nothing is running.
            assert second.state.running_turns == {}
            scripts.fast = script("You spent 403,60 EUR on groceries in May 2025.")
            again = await client.post(
                f"/api/conversations/{conversation_id}/chat", json=chat_body("Again please", conversation_id)
            )
            assert again.status_code == 200, again.text
            assert "403,60" in again.text

    turn.cancel()


async def test_a_failing_post_turn_step_never_costs_the_answer(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The suggestions and the distillation are extras. A raise in either is one lost extra.

    Both steps resolve the fast slot themselves, and on the local provider that raises while
    the models are still downloading, which would have taken the finished answer down with it.
    """

    async def raises(*_args: object, **_kwargs: object) -> list[str]:
        raise RuntimeError("the fast slot is not available")

    monkeypatch.setattr(chat_api, "suggest_followups", raises)
    scripts.fast = script("You spent 403,60 EUR on groceries in May 2025.")
    conversation_id = await new_conversation(client, await default_profile_id(client))

    response, chunks = await chat(conversation_id, "What did I spend on groceries?")

    assert response.status_code == 200
    assert "403,60" in response.text
    assert [c for c in chunks if c["type"] == "data-followups"] == []
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["parts"][-2]["text"] == "You spent 403,60 EUR on groceries in May 2025."


async def test_a_model_that_says_nothing_at_all_leaves_the_question_and_a_marker(
    client: httpx.AsyncClient, scripts: Scripts
) -> None:
    """A response with no text and no tool call is retried, and then the run gives up.

    Whatever the run does, the user is left with what they typed and the reason it stopped
    there, not with a transcript that never heard the question.
    """

    async def says_nothing(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        return
        yield  # pragma: no cover - never reached, this is what makes the function a generator

    scripts.fast = says_nothing
    conversation_id = await new_conversation(client, await default_profile_id(client))

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat", json=chat_body("go", conversation_id)
    )

    assert response.status_code == 200
    # One sentence the reader can act on, not the framework's own exception text.
    errors = [c["errorText"] for c in parse_sse(response.text) if c["type"] == "error"]
    assert errors == [chat_api.TURN_FAILED]
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"][0]["parts"][0]["text"] == "go"
    assert detail["interrupted"] is True


async def test_a_tool_that_raises_leaves_the_question_and_a_marker(
    client: httpx.AsyncClient, scripts: Scripts, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool blowing up is a turn that cannot finish, not a turn that never happened."""

    async def explodes(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("the query sub-agent fell over")

    monkeypatch.setattr(agent, "run_query", explodes)

    async def asks_a_question(_messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        yield {0: DeltaToolCall(name="query", json_args='{"request": "groceries in May"}')}

    scripts.fast = asks_a_question
    conversation_id = await new_conversation(client, await default_profile_id(client))

    response = await client.post(
        f"/api/conversations/{conversation_id}/chat", json=chat_body("groceries?", conversation_id)
    )

    assert response.status_code == 200
    errors = [c["errorText"] for c in parse_sse(response.text) if c["type"] == "error"]
    assert errors == [chat_api.TURN_FAILED]
    assert "fell over" not in response.text, "the exception belongs in the log, not the transcript"
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"][0]["parts"][0]["text"] == "groceries?"
    assert detail["interrupted"] is True


async def test_a_slot_the_provider_cannot_give_is_one_sentence_not_a_crash(
    client: httpx.AsyncClient, scripts: Scripts
) -> None:
    """The quality slot missing is the local provider mid-download, and it reads as a sentence."""

    def refuses(slot: str):
        if slot == "quality":
            raise ProviderNotAvailable("Qwen3.5 9B is not downloaded yet. Open Settings to fetch it.")
        return scripts.resolve(slot)

    conversation_id = await new_conversation(client, await default_profile_id(client), slot="quality")
    client._transport.app.state.resolve_model = refuses  # type: ignore[attr-defined]

    response = await client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body("go", conversation_id))

    assert response.status_code == 503
    assert response.json()["detail"] == "Qwen3.5 9B is not downloaded yet. Open Settings to fetch it."
    # And nothing was left behind: no half a turn to explain away on the next load.
    assert (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"] == []
