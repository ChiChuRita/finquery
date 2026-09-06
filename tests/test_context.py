"""Context compression at the HTTP seam, with a budget small enough to cross in a few turns."""

import json
from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from finquery.context import MAX_SUMMARY_CHARS

from .conftest import (
    Chat,
    Scripts,
    default_profile_id,
    distilled,
    is_distillation_request,
    is_followup_request,
    is_summary_request,
    new_conversation,
)

# Two conditions have to hold for compression to fire, and only the second is what this budget
# is for: there must be something older than the last six turns (so never before the eighth),
# and the prompt must be over 60 percent of the budget. The system prompt alone is 3920 tokens
# now, so the token half is already true on the first turn and the turn count is what decides.
# What the budget has to clear is the floor a compressed prompt cannot go below (the system
# prompt, the summary and the last six turns), measured at 4838 tokens here. The real default is
# 32768, far above any floor. Every ticket that adds a prompt block has had to move this;
# ticket 42 added one paragraph on reading a tool result, 328 tokens on top of the 3592 that
# stood after ticket 37, and the floor went from 4500 to 4838, so the constant moves with it.
# Measured rather than guessed, the way this paragraph describes: drive twelve turns with the
# budget in the settings and take the largest `used` of the turns that compressed. 5700 leaves
# about 18 percent of headroom over the floor, the margin ticket 27 left. Tenth ticket to move it.
BUDGET = 5700
SUMMARY = "The user asked about groceries and rent in the spring and cares about subscriptions."

# Long enough that a turn is worth about a hundred tokens on either side.
QUESTION = "Tell me about my spending in {month}, and please be thorough about the details. " * 3
ANSWER = "Here is what I would look at for {month} once your statements are imported. " * 3
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


@pytest.fixture
def settings_overrides() -> dict[str, object]:
    return {"context_budget": BUDGET}


class Recorder:
    """The fast slot for a whole conversation: every kind of request it gets, told apart.

    One turn asks it for the answer, a follow-up list and a distillation, plus a summary on the
    turns that compress. Only the chat requests are recorded, because those are the prompts
    these tests are about.
    """

    def __init__(self, summary: str = SUMMARY) -> None:
        self.summary = summary
        self.prompts: list[list[ModelMessage]] = []
        self.summaries: list[str] = []

    async def __call__(self, messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
        elif is_distillation_request(messages):
            # These turns establish nothing durable, so no memory joins the prompt and the
            # token counts below stay about the transcript.
            yield distilled()
        elif is_summary_request(messages):
            prompt = last_prompt(messages)
            self.summaries.append(prompt)
            # A summarizer is told to merge the previous summary in rather than to replace it,
            # which is what keeps an edited summary alive through the next compression.
            previous = previous_summary(prompt)
            yield previous if self.summary in previous else "\n".join(filter(None, [previous, self.summary]))
        else:
            self.prompts.append(messages)
            yield ANSWER.format(month=MONTHS[len(self.prompts) - 1])

    def user_prompts(self, index: int = -1) -> list[str]:
        """The user messages the model was given for one turn."""
        return [
            part.content
            for message in self.prompts[index]
            if message.kind == "request"
            for part in message.parts
            if part.part_kind == "user-prompt" and isinstance(part.content, str)
        ]

    def instructions(self, index: int = -1) -> str:
        """The system-level text of one turn: the agent's prompt plus any note added to it."""
        return "\n".join(
            message.instructions for message in self.prompts[index] if message.kind == "request" and message.instructions
        )


def last_prompt(messages: list[ModelMessage]) -> str:
    return "\n".join(
        part.content
        for part in messages[-1].parts
        if part.part_kind == "user-prompt" and isinstance(part.content, str)
    )


def previous_summary(prompt: str) -> str:
    """The summary the compression step was handed to merge into, empty on the first one."""
    if "Previous summary:\n" not in prompt:
        return ""
    return prompt.split("Previous summary:\n", 1)[1].split("\n\nTurns to fold in:", 1)[0]


def context_stats(chunks: list[dict[str, object]]) -> dict[str, object]:
    parts = [c["data"] for c in chunks if c["type"] == "data-context"]
    assert len(parts) == 1, f"expected exactly one context data part, got {len(parts)}"
    assert isinstance(parts[0], dict)
    return parts[0]


async def drive(chat: Chat, conversation_id: str, turns: int) -> list[dict[str, object]]:
    """Send `turns` questions and return the context stats of each turn."""
    stats = []
    for month in MONTHS[:turns]:
        _, chunks = await chat(conversation_id, QUESTION.format(month=month))
        stats.append(context_stats(chunks))
    return stats


async def test_every_turn_reports_token_stats_for_the_badge(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    scripts.fast = Recorder()
    conversation_id = await new_conversation(client, await default_profile_id(client))

    first, second = await drive(chat, conversation_id, 2)

    assert first["budget"] == BUDGET
    assert first["model_key"] == "openrouter:qwen/qwen3.5-9b"
    # Nothing was distilled from these turns, so the prompt carries no memories (test_memory
    # covers the other side: a memory in the prompt is counted here).
    assert first["memories"] == 0
    assert first["summarized_turns"] == 0
    assert isinstance(first["used"], int) and first["used"] > 0
    # The context grows with the conversation, which is what makes the badge climb.
    assert isinstance(second["used"], int) and second["used"] > first["used"]

    # The same part is stored on the assistant message, so a reload shows the same badge.
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    stored = [p for p in detail["messages"][-1]["parts"] if p["type"] == "data-context"]
    assert stored and stored[0]["data"] == second
    assert detail["summary"] is None
    assert detail["summarized_turns"] == 0
    assert detail["summarized_messages"] == 0


async def test_at_the_threshold_older_turns_are_summarized_and_no_longer_sent(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    recorder = Recorder()
    scripts.fast = recorder
    conversation_id = await new_conversation(client, await default_profile_id(client))

    stats = await drive(chat, conversation_id, 10)

    # The last six turns always survive, so the eighth is the first with anything to fold in,
    # and every turn after it folds in one more.
    assert [s["summarized_turns"] for s in stats] == [0, 0, 0, 0, 0, 0, 0, 1, 2, 3]
    assert len(recorder.summaries) == 3, "one compression per turn once the threshold is behind us"
    # Requests per turn: the chat model on the conversation's entry, then the follow-up and the
    # distillation step on the fast slot, plus one more fast request for the summary on a turn
    # that compresses. Ten turns, three of them compressing.
    assert scripts.roles.count("chat") == 10
    assert len(scripts.roles) == 10 * 3 + 3

    used = [s["used"] for s in stats]
    assert used[:7] == sorted(set(used[:7])), "the badge climbs while the whole history is sent"
    # And then it holds: the prompt is six turns plus a summary, however long the chat gets.
    assert max(used[7:]) < BUDGET
    assert max(used[7:]) - min(used[7:]) < 30

    # The turns before the marker are gone from the prompt, the summary stands in for them.
    assert SUMMARY in recorder.instructions()
    prompts = recorder.user_prompts()
    assert len(prompts) == 7, "six recent turns plus the new question"
    assert QUESTION.format(month="January") not in prompts
    assert QUESTION.format(month="August") in prompts

    # The transcript keeps every turn and says where the summary took over.
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert len(detail["messages"]) == 20
    assert detail["summary"] == SUMMARY
    assert detail["summarized_turns"] == stats[-1]["summarized_turns"]
    assert detail["summarized_messages"] == detail["summarized_turns"] * 2


async def test_an_edited_summary_reaches_the_model_on_the_next_turn(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    recorder = Recorder()
    scripts.fast = recorder
    conversation_id = await new_conversation(client, await default_profile_id(client))
    await drive(chat, conversation_id, 8)
    assert recorder.summaries

    edited = "  The user rents in Berlin and wants subscriptions watched.  \n\n"
    patched = await client.patch(f"/api/conversations/{conversation_id}", json={"summary": edited})
    assert patched.status_code == 200
    assert (await client.get(f"/api/conversations/{conversation_id}")).json()["summary"] == edited.strip()

    await drive(chat, conversation_id, 1)
    assert edited.strip() in recorder.summaries[-1], "the edit was not what the next summary built on"
    assert edited.strip() in recorder.instructions(), "the edit did not reach the chat model"


async def test_an_empty_summary_is_rejected(client: httpx.AsyncClient) -> None:
    conversation_id = await new_conversation(client, await default_profile_id(client))
    response = await client.patch(f"/api/conversations/{conversation_id}", json={"summary": "   \n "})
    assert response.status_code == 422


async def test_a_summary_edited_past_its_ceiling_is_cut_rather_than_refused(
    client: httpx.AsyncClient,
) -> None:
    """The summary exists to save context, so it has a ceiling. Pasting past it is not an error."""
    conversation_id = await new_conversation(client, await default_profile_id(client))

    response = await client.patch(f"/api/conversations/{conversation_id}", json={"summary": "a" * 5000})

    assert response.status_code == 200, response.text
    stored = (await client.get(f"/api/conversations/{conversation_id}")).json()["summary"]
    assert len(stored) == MAX_SUMMARY_CHARS


async def test_a_card_the_summary_has_reached_is_still_answerable(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    """A Question card left open while the conversation grows past the threshold.

    The rolling summary stands in for the turns older than the last six, and the turn the card
    is on is one of them by the time the user comes back to it. A prompt with the pending call
    summarized away is a prompt the run cannot be resumed from at all, so the marker is read
    one turn short of the card for that one run. The card is answerable however long the user
    took (ticket 29 with ticket 12 in the way).
    """
    recorder = Recorder()
    card = {"title": "Which category do these belong to?", "options": [{"label": "Dining", "value": "Dining"}]}

    async def asks_then_answers(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        if not recorder.prompts and not is_followup_request(messages) and not is_distillation_request(messages):
            recorder.prompts.append(messages)
            yield {0: DeltaToolCall(name="ask_user", json_args=json.dumps(card))}
            return
        async for item in recorder(messages, info):
            yield item

    scripts.fast = asks_then_answers
    conversation_id = await new_conversation(client, await default_profile_id(client))
    await chat(conversation_id, "Categorize what I just imported.")
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    pending = next(part for part in detail["messages"][1]["parts"] if part["type"] == "tool-ask_user")

    # Nine more turns, which takes the summary marker past the turn the card is on.
    await drive(chat, conversation_id, 9)
    reloaded = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert reloaded["summarized_turns"] >= 2, "the card's own turn is behind the divider now"

    resumed = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json={
            "id": conversation_id,
            "trigger": "submit-message",
            "messages": [
                {
                    "id": detail["messages"][1]["id"],
                    "role": "assistant",
                    "parts": [
                        {
                            "type": "tool-ask_user",
                            "toolCallId": pending["toolCallId"],
                            "state": "output-available",
                            "input": pending["input"],
                            "output": {"answers": [{"ref": "", "value": "Dining", "text": None}]},
                        }
                    ],
                }
            ],
        },
    )

    assert resumed.status_code == 200, resumed.text
    # The card's own turn was in the prompt the resumed run was given, whatever the marker says.
    assert "Categorize what I just imported." in recorder.user_prompts()
    # And the marker itself was left alone: the rest of the conversation is assembled from it.
    after = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert after["summarized_turns"] == reloaded["summarized_turns"]
    assert [m["role"] for m in after["messages"]] == ["user", "assistant"] * 10
