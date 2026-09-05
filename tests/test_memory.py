"""Memory across chats, asserted where it matters: what the model is given, and the REST list.

The recorder keeps the instructions of every chat request, which is literally the prompt the
model received, so "a fact from another conversation is known here" is checked without reaching
into the database.
"""

from collections.abc import AsyncIterator, Sequence

import httpx
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall
from sqlalchemy.orm import Session, sessionmaker

from finquery.memory import add_memory

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


def seed_memories(session_factory: "sessionmaker[Session]", profile_id: str, facts: Sequence[str]) -> None:
    """Put memories in the profile without going through a turn.

    A turn leaves at most `memory.MAX_DISTILLED` facts behind (ticket 37), and what these tests
    are about is what a prompt carries once a profile has many, not how they got there.
    """
    with session_factory() as session:
        for text in facts:
            add_memory(session, profile_id, text, source="distilled")
        session.commit()


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
    fact = "Rewe is where the groceries come from"
    scripts.fast = script("Got it.", memories=[fact])
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
    # The whole sentence, because the system prompt names Rewe itself in a rule example.
    assert fact not in forgetful.prompt
    assert "\n- [" not in forgetful.prompt
    assert memories_in_prompt(chunks) == 0


async def test_at_most_five_memories_travel_with_a_turn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, session_factory: "sessionmaker[Session]"
) -> None:
    profile_id = await default_profile_id(client)
    seed_memories(session_factory, profile_id, [f"Merchant number {n} is a supermarket" for n in range(7)])
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


async def test_a_distillation_whose_facts_are_all_refused_is_handed_the_refusals_once(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """A refused fact is a lesson for the same turn, not a silent drop (ticket 42).

    The pass that filled a profile with 27 one-off figures in one afternoon never learned that
    a figure is not a memory, because nothing ever told it. Now the refusal goes back with the
    model's own sentence in front of it, and storing nothing is named as the right answer.
    """
    passes: list[str] = []

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            prompt = next(
                part.content
                for part in reversed(messages[-1].parts)
                if part.part_kind == "user-prompt" and isinstance(part.content, str)
            )
            passes.append(prompt)
            if len(passes) == 1:
                yield distilled("The user spent 75,20 EUR at REWE in August 2026")
            else:
                yield distilled()
            return
        yield "You spent 75,20 EUR at REWE in August 2026."

    scripts.fast = fn
    profile_id = await default_profile_id(client)
    await chat(await new_conversation(client, profile_id), "How much did I spend at REWE last month?")

    assert len(passes) == 2, "the refused distillation was handed back exactly once"
    handed_back = passes[1]
    assert "None of what you just answered can be stored." in handed_back
    assert "Your reasoning was:\ndurable, it is about this household" in handed_back
    assert '"The user spent 75,20 EUR at REWE in August 2026": it carries a figure or a date' in handed_back
    assert "An empty list is the right answer" in handed_back
    # And nothing was stored, because the second answer kept nothing.
    assert await memories_of(client, profile_id) == []


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


class PromptSpy:
    """A fast slot that keeps the prompt of every distillation pass, and remembers nothing."""

    def __init__(self, answer: str) -> None:
        self.distillation: list[str] = []
        self._script = script(answer)

    async def __call__(self, messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        if is_distillation_request(messages):
            self.distillation.append(
                (getattr(messages[-1], "instructions", None) or "")
                + "\n"
                + "\n".join(
                    part.content
                    for part in messages[-1].parts
                    if part.part_kind == "user-prompt" and isinstance(part.content, str)
                )
            )
        async for item in self._script(messages, info):
            yield item


async def test_distillation_is_told_to_write_a_fact_in_the_language_of_the_turn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """German facts distilled from English turns are why a fresh chat answered in German.

    The rule lives in the distillation prompt, so the assertion is on the text the pass really
    receives, not on a copy of it (review of 2026-09-04).
    """
    spy = PromptSpy("Groceries were 8.907,96 EUR.")
    scripts.fast = spy
    profile_id = await default_profile_id(client)

    await chat(await new_conversation(client, profile_id), "What did I spend on groceries in 2025?")

    assert len(spy.distillation) == 1
    prompt = spy.distillation[0]
    assert "Write every fact in the language of the user's own message" in prompt
    assert "Never translate what the user said into another language" in prompt


async def test_memories_in_another_language_do_not_decide_the_answer_language(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """A German memory is still German in an English chat, and says so to the model."""
    german = "Alle Netflix-Buchungen sollen als Leisure kategorisiert werden."
    scripts.fast = script("Verstanden.", memories=[german])
    profile_id = await default_profile_id(client)
    await chat(await new_conversation(client, profile_id), "Netflix ist Leisure.")

    asking = Recorder("Netflix is Leisure.")
    scripts.fast = asking
    await chat(await new_conversation(client, profile_id), "What is my Netflix booking?")

    assert f"- [fact] {german}" in asking.prompt
    assert "answer in the language of the newest user message" in asking.prompt


async def test_a_profile_with_two_hundred_memories_still_sends_five_and_lists_them_all(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, session_factory: "sessionmaker[Session]"
) -> None:
    """The cap is what keeps the prompt small, and the page is what makes the rest reachable.

    Selection scores every memory of the profile in Python, so this is also the check that it
    stays a matter of milliseconds at the size a household actually reaches.
    """
    profile_id = await default_profile_id(client)
    seed_memories(
        session_factory, profile_id, [f"Merchant number {n} is a supermarket in Kreuzberg" for n in range(200)]
    )
    assert len(await memories_of(client, profile_id)) == 200

    asking = Recorder("Kreuzberg.")
    scripts.fast = asking
    _, chunks = await chat(await new_conversation(client, profile_id), "Which supermarkets are in Kreuzberg?")

    assert asking.prompt.count("\n- [") == 5
    assert memories_in_prompt(chunks) == 5


async def test_a_fact_that_contradicts_an_older_one_is_kept_and_offered_first(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """Nothing overwrites a memory, so the newer of two contradicting facts leads the block.

    Deduplication compares the text, so "Anna is my flatmate" and "Anna is my sister" are two
    memories and both go to the model. The order is what says which one is current: selection
    ranks by overlap and breaks ties by recency, and the block tells the model the most relevant
    comes first. The Memory page is where a wrong one is deleted.
    """
    profile_id = await default_profile_id(client)
    older, newer = "Anna Weber is the user's flatmate", "Anna Weber is the user's sister"
    for fact in (older, newer):
        scripts.fast = script("Noted.", memories=[fact])
        await chat(await new_conversation(client, profile_id), f"About Anna: {fact}")

    asking = Recorder("Your sister.")
    scripts.fast = asking
    await chat(await new_conversation(client, profile_id), "Who is Anna Weber?")

    assert asking.prompt.index(newer) < asking.prompt.index(older), "the newer fact leads"
    assert "most relevant first" in asking.prompt
    # Both are on the page, which is the only place either is removed.
    assert {m["text"] for m in await memories_of(client, profile_id)} == {older, newer}
