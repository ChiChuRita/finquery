"""A turn outlives the request that started it (ticket 33).

The run is a task the app owns; the HTTP response is one subscriber of the chunks it produces.
So a browser that reloads, switches conversation or closes the tab leaves the run alone, and
whoever comes back asks for the same stream from its first chunk (`GET .../stream`, which is
the URL `useChat`'s own resume calls).

Every case here is driven at the HTTP seam with a scripted model that parks in the middle of
its answer, which is what a two minute import looks like from the outside.
"""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from finquery.api import chat as chat_api
from finquery.api.running import RunningTurn

from .conftest import (
    Scripts,
    chat_body,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
    parse_sse,
)


def _parked(started: asyncio.Event, release: asyncio.Event):
    """A model that says half of its answer, then waits to be let go.

    The half ends with a newline because the text filter judges a line at a time (a bare channel
    name is a whole line, ticket 27), so an unfinished line is held back until the part ends.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        yield "half an\n"
        started.set()
        await release.wait()
        yield "answer"

    return fn


def _parked_after_a_tool(started: asyncio.Event, release: asyncio.Event):
    """A model that stores a memory and then waits, so the turn parks past a tool boundary."""

    def has_result(messages: list[ModelMessage]) -> bool:
        return any(
            part.part_kind == "tool-return" for message in messages if message.kind == "request" for part in message.parts
        )

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        if has_result(messages):
            started.set()
            await release.wait()
            yield "Noted."
            return
        yield {0: DeltaToolCall(name="remember", json_args='{"text": "I cycle to work."}')}

    return fn


def turns_of(app: FastAPI) -> dict[str, RunningTurn]:
    return app.state.running_turns  # type: ignore[no-any-return]


def app_of(client: httpx.AsyncClient) -> FastAPI:
    return client._transport.app  # type: ignore[attr-defined,no-any-return]


def text_of(chunks: list[dict[str, object]]) -> str:
    return "".join(str(chunk["delta"]) for chunk in chunks if chunk["type"] == "text-delta")


async def start_turn(
    client: httpx.AsyncClient, conversation_id: str, text: str = "go"
) -> "asyncio.Task[httpx.Response]":
    return asyncio.create_task(
        client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body(text, conversation_id))
    )


async def test_the_question_is_stored_and_the_chat_says_it_is_running_before_the_answer(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """A dropped connection can never lose the question, because the question is written first.

    The turn is open from before the model is asked, and while it is open the conversation says
    it is running: that is the flag the spinner on the tab and the sidebar row is drawn from,
    and what tells a chat opened elsewhere to reattach rather than to look finished.
    """
    started, release = asyncio.Event(), asyncio.Event()
    scripts.fast = _parked(started, release)
    conversation_id = await new_conversation(client, profile_id)

    turn = await start_turn(client, conversation_id, "What did I spend on groceries?")
    await asyncio.wait_for(started.wait(), timeout=5)

    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["messages"][0]["role"] == "user"
    assert detail["messages"][0]["parts"][0]["text"] == "What did I spend on groceries?"
    assert detail["title"] == "What did I spend on groceries?"
    assert detail["running"] is True
    assert detail["interrupted"] is False, "an answer is still on its way"
    listed = (await client.get("/api/conversations", params={"profile_id": profile_id})).json()
    assert [c["running"] for c in listed] == [True]

    release.set()
    await asyncio.wait_for(turn, timeout=5)
    assert (await client.get(f"/api/conversations/{conversation_id}")).json()["running"] is False


async def test_a_dropped_stream_leaves_the_run_to_finish_and_the_whole_turn_lands(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """Reload, switch conversation, close the tab: the response goes, the turn does not.

    Before ticket 33 the run was the request, so a browser that hung up mid-answer left the
    question with an interrupted marker and nothing else, four seconds of work thrown away. Now
    only Stop ends a run: the reader leaves and the turn finishes into the transcript.
    """
    started, release = asyncio.Event(), asyncio.Event()
    scripts.fast = _parked(started, release)
    conversation_id = await new_conversation(client, profile_id)

    turn = await start_turn(client, conversation_id)
    await asyncio.wait_for(started.wait(), timeout=5)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn

    running = turns_of(app_of(client))[conversation_id]
    assert not running.finished.is_set(), "hanging up is one subscriber leaving, not a cancel"

    release.set()
    await asyncio.wait_for(running.finished.wait(), timeout=5)

    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["parts"][0]["text"] == "half an\nanswer"
    assert detail["interrupted"] is False
    assert detail["running"] is False
    assert turns_of(app_of(client)) == {}


async def test_reattaching_replays_what_was_missed_and_then_follows_the_turn(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """`GET .../stream` is the whole turn from its first chunk, however late it is asked for.

    The buffer is what makes that possible: a reattaching client is not given the rest of the
    stream, it is given the stream. So the browser rebuilds the message it missed and carries on
    into the live part with no seam.
    """
    started, release = asyncio.Event(), asyncio.Event()
    scripts.fast = _parked(started, release)
    conversation_id = await new_conversation(client, profile_id)

    turn = await start_turn(client, conversation_id)
    await asyncio.wait_for(started.wait(), timeout=5)

    # The reattach is asked for while the turn is parked, and read once it ends: httpx's ASGI
    # transport hands the response back whole, so there is nothing to watch arrive in a test.
    # What it proves is the same thing: the second reader was given the half it never saw.
    reattached = asyncio.create_task(client.get(f"/api/conversations/{conversation_id}/stream"))
    await asyncio.sleep(0.05)
    release.set()

    response = await asyncio.wait_for(reattached, timeout=5)
    assert response.status_code == 200, "the turn was still running when this was asked for"
    assert response.headers["content-type"].startswith("text/event-stream")
    replayed = parse_sse(response.text)
    assert replayed[0]["type"] == "start", "the reattached stream starts where the turn started"
    assert text_of(replayed) == "half an\nanswer", "what was missed and what came after it"

    # The client that asked for the turn in the first place read exactly the same stream.
    original = parse_sse((await asyncio.wait_for(turn, timeout=5)).text)
    assert [c["type"] for c in original] == [c["type"] for c in replayed]


async def test_reattaching_a_conversation_with_nothing_running_says_so(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """204 is what the SDK reads as "carry on with the transcript you have"."""
    conversation_id = await new_conversation(client, profile_id)
    response = await client.get(f"/api/conversations/{conversation_id}/stream")
    assert response.status_code == 204
    assert response.content == b""


async def test_a_second_message_while_the_turn_runs_is_refused_rather_than_interleaved(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """One turn per conversation. The composer is disabled for it; this is the guarantee."""
    started, release = asyncio.Event(), asyncio.Event()
    scripts.fast = _parked(started, release)
    conversation_id = await new_conversation(client, profile_id)

    turn = await start_turn(client, conversation_id)
    await asyncio.wait_for(started.wait(), timeout=5)

    second = await client.post(
        f"/api/conversations/{conversation_id}/chat", json=chat_body("and again", conversation_id)
    )
    assert second.status_code == 409
    assert second.json()["detail"] == chat_api.ALREADY_RUNNING

    release.set()
    await asyncio.wait_for(turn, timeout=5)
    # Once it is over the same message is taken.
    assert (
        await client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body("and again", conversation_id))
    ).status_code == 200


async def test_the_text_so_far_is_stored_while_the_turn_runs(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A long answer is written down as it is written, not only when it ends.

    The cadence is a few seconds of text, so the clock is turned off here rather than waited
    out. What it buys is a process that stops in the middle of a paragraph leaving the paragraph
    behind (`close_open_turns` then marks it interrupted) instead of the question alone.
    """
    monkeypatch.setattr(chat_api, "PARTIAL_SECONDS", 0.0)
    started, release = asyncio.Event(), asyncio.Event()
    scripts.fast = _parked(started, release)
    conversation_id = await new_conversation(client, profile_id)

    turn = await start_turn(client, conversation_id)
    await asyncio.wait_for(started.wait(), timeout=5)

    assistant = (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["parts"][0] == {"type": "text", "text": "half an\n", "state": "streaming"}

    release.set()
    await asyncio.wait_for(turn, timeout=5)
    messages = (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"]
    # The finished turn replaces the partial one rather than being written next to it.
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[1]["parts"][0]["text"] == "half an\nanswer"


async def test_a_tool_step_is_stored_as_soon_as_it_returns(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The tool step is in the transcript before the turn ends, not only after it.

    A reload finds it there whether or not the process that was producing it is still alive,
    which is the difference between "the answer is still coming" and a question with nothing
    under it.
    """
    started, release = asyncio.Event(), asyncio.Event()
    scripts.fast = _parked_after_a_tool(started, release)
    conversation_id = await new_conversation(client, profile_id)

    turn = await start_turn(client, conversation_id, "I cycle to work.")
    await asyncio.wait_for(started.wait(), timeout=5)

    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assistant = detail["messages"][-1]
    assert assistant["role"] == "assistant"
    step = next(part for part in assistant["parts"] if part["type"] == "tool-remember")
    assert step["state"] == "output-available"
    assert detail["running"] is True

    release.set()
    await asyncio.wait_for(turn, timeout=5)
    messages = (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert [p["type"] for p in messages[1]["parts"]][:2] == ["tool-remember", "text"]


async def test_stop_ends_a_turn_nobody_is_streaming_and_keeps_what_it_had(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """Stop is the only thing that cancels a run, and it works with no reader attached.

    The browser that pressed it may not be the one that started the turn (another tab, or this
    one after a reload), so Stop goes through the cancellation token of the running turn rather
    than through the response.
    """
    started, release = asyncio.Event(), asyncio.Event()
    scripts.fast = _parked(started, release)
    conversation_id = await new_conversation(client, profile_id)

    turn = await start_turn(client, conversation_id)
    await asyncio.wait_for(started.wait(), timeout=5)
    turn.cancel()
    with pytest.raises(asyncio.CancelledError):
        await turn

    stop = await client.post(f"/api/conversations/{conversation_id}/stop")
    assert stop.json() == {"stopped": True}

    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["interrupted"] is True
    assert detail["running"] is False
    assert detail["messages"][1]["parts"][0]["text"].strip() == "half an"
    release.set()
