"""Memory across chats, asserted where it matters: what the model is given, and the REST list.

The recorder keeps the instructions of every chat request, which is literally the prompt the
model received, so "a fact from another conversation is known here" is checked without reaching
into the database.
"""

from collections.abc import AsyncIterator, Sequence

import httpx
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from .conftest import (
    Chat,
    Scripts,
    default_profile_id,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
    script,
)


class Recorder:
    """A scripted fast slot that remembers the instructions each chat turn was given."""

    def __init__(self, answer: str, *, memories: Sequence[str] = ()) -> None:
        self.instructions: list[str] = []
        self._script = script(answer, memories=memories)

    async def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        if not is_followup_request(messages) and not is_distillation_request(messages):
            self.instructions.append(getattr(messages[-1], "instructions", None) or "")
        async for item in self._script(messages, info):
            yield item

    @property
    def prompt(self) -> str:
        """The instructions of the most recent chat turn."""
        assert self.instructions, "the chat model was never called"
        return self.instructions[-1]


def memories_in_prompt(chunks: list[dict[str, object]]) -> object:
    """What the turn's one `data-context` part says it carried, which is what the chip shows."""
    parts = [c["data"] for c in chunks if c["type"] == "data-context"]
    assert len(parts) == 1, f"expected one data-context part, got {len(parts)}"
    assert isinstance(parts[0], dict)
    return parts[0]["memories"]


def answer_of(chunks: list[dict[str, object]]) -> str:
    return "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta").strip()


async def memories_of(client: httpx.AsyncClient, profile_id: str) -> list[dict[str, object]]:
    response = await client.get("/api/memories", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return list(response.json())


async def test_a_distilled_fact_reaches_a_new_conversation_and_stays_in_its_profile(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    fact = "PayPal transfers to Anna cover shared dinners"
    teaching = Recorder("Got it.", memories=[fact])
    scripts.fast = teaching
    profile_id = await default_profile_id(client)
    first = await new_conversation(client, profile_id)

    await chat(first, "PayPal to Anna is always dinner, we split the bill")

    stored = await memories_of(client, profile_id)
    assert [(m["text"], m["kind"], m["source"], m["created_from"]) for m in stored] == [
        (fact, "fact", "distilled", first)
    ]

    # A brand new conversation of the same profile starts out knowing it.
    asking = Recorder("Dinner with Anna.")
    scripts.fast = asking
    _, chunks = await chat(await new_conversation(client, profile_id), "What is that PayPal payment to Anna?")
    assert f"- [fact] {fact}" in asking.prompt
    assert memories_in_prompt(chunks) == 1

    # Another profile does not: memory is inside the isolation boundary.
    other = (await client.post("/api/profiles", json={"name": "Household"})).json()["id"]
    elsewhere = Recorder("I do not know.")
    scripts.fast = elsewhere
    await chat(await new_conversation(client, other), "What is that PayPal payment to Anna?")
    assert fact not in elsewhere.prompt
    assert await memories_of(client, other) == []


async def test_a_deleted_memory_is_not_sent_to_the_model_again(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    scripts.fast = script("Got it.", memories=["Rewe is where the groceries come from"])
    profile_id = await default_profile_id(client)
    await chat(await new_conversation(client, profile_id), "I buy my groceries at Rewe")

    stored = await memories_of(client, profile_id)
    assert len(stored) == 1
    assert (await client.delete(f"/api/memories/{stored[0]['id']}")).status_code == 204
    assert (await client.delete(f"/api/memories/{stored[0]['id']}")).status_code == 404
    assert await memories_of(client, profile_id) == []

    forgetful = Recorder("I have nothing on that.")
    scripts.fast = forgetful
    _, chunks = await chat(await new_conversation(client, profile_id), "Where do I buy groceries?")
    assert "Rewe" not in forgetful.prompt
    assert memories_in_prompt(chunks) == 0


async def test_at_most_five_memories_travel_with_a_turn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    facts = [f"Merchant number {n} is a supermarket" for n in range(7)]
    scripts.fast = script("Got it.", memories=facts)
    profile_id = await default_profile_id(client)
    await chat(await new_conversation(client, profile_id), "here are my supermarkets")
    assert len(await memories_of(client, profile_id)) == 7

    asking = Recorder("Seven of them.")
    scripts.fast = asking
    _, chunks = await chat(await new_conversation(client, profile_id), "Which merchants are supermarkets?")

    assert asking.prompt.count("\n- [") == 5
    assert memories_in_prompt(chunks) == 5


async def test_the_remember_tool_stores_an_explicit_memory_and_the_answer_confirms_it(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    stated = "PayPal to Anna is always Dining"

    async def calling(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            # Nothing to distil: the assistant already stored the fact through the tool.
            yield distilled()
            return
        if any(part.part_kind == "tool-return" for part in messages[-1].parts):
            yield "Noted: PayPal to Anna is Dining from now on."
            return
        yield {0: DeltaToolCall(name="remember", json_args=f'{{"text": "{stated}", "kind": "rule"}}')}

    scripts.fast = calling
    profile_id = await default_profile_id(client)
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, stated)

    assert [(m["text"], m["kind"], m["source"], m["created_from"]) for m in await memories_of(client, profile_id)] == [
        (stated, "rule", "explicit", conversation_id)
    ]
    outputs = [c["output"] for c in chunks if c["type"] == "tool-output-available"]
    assert outputs == [f"Remembered: {stated}"]
    assert answer_of(chunks) == "Noted: PayPal to Anna is Dining from now on."


async def test_distillation_does_not_store_a_fact_the_profile_already_knows(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    fact = "Anna is a friend, PayPal to her is dinner"
    scripts.fast = script("Got it.", memories=[fact])
    profile_id = await default_profile_id(client)
    await chat(await new_conversation(client, profile_id), "PayPal to Anna is dinner")

    # The same fact again, in different case and punctuation, plus one that is new.
    scripts.fast = script("Got it.", memories=[f"{fact.lower()}.", "Rewe is groceries"])
    await chat(await new_conversation(client, profile_id), "Anna and I split dinner over PayPal")

    assert [m["text"] for m in await memories_of(client, profile_id)] == ["Rewe is groceries", fact]


async def test_an_edited_memory_is_what_the_next_turn_receives(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    scripts.fast = script("Got it.", memories=["PayPal to Anna is dinner"])
    profile_id = await default_profile_id(client)
    await chat(await new_conversation(client, profile_id), "PayPal to Anna is dinner")
    memory_id = (await memories_of(client, profile_id))[0]["id"]

    patched = await client.patch(f"/api/memories/{memory_id}", json={"text": "  PayPal to Anna is  rent ", "kind": "rule"})
    assert patched.status_code == 200
    assert (patched.json()["text"], patched.json()["kind"]) == ("PayPal to Anna is rent", "rule")
    assert (await client.patch(f"/api/memories/{memory_id}", json={"text": " "})).status_code == 422
    assert (await client.patch("/api/memories/nope", json={"text": "anything"})).status_code == 404
    assert (await client.get("/api/memories", params={"profile_id": "nope"})).status_code == 404

    asking = Recorder("Rent.")
    scripts.fast = asking
    await chat(await new_conversation(client, profile_id), "What is that PayPal payment to Anna?")
    assert "- [rule] PayPal to Anna is rent" in asking.prompt
