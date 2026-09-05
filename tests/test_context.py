"""Context compression at the HTTP seam, with a budget small enough to cross in a few turns."""

from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

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
# and the prompt must be over 60 percent of the budget. The system prompt alone is 3109 tokens
# now, so the token half is already true on the first turn and the turn count is what decides.
# What the budget has to clear is the floor a compressed prompt cannot go below (the system
# prompt, the summary and the last six turns), measured at 4027 tokens here. The real default is
# 32768, far above any floor. Every ticket that adds a prompt block has had to move this: this
# time for ticket 30's three minors (a message that is not a question, memories as the only
# source of a name, the duplicate summary in the model's own words), which cost 225 tokens on
# top of the 2884 main carried. Measured rather than guessed, the way this paragraph describes:
# drive twelve turns with the budget in the settings and take the largest `used` of the turns
# that compressed. 4800 leaves about 19 percent of headroom over the floor, the same margin
# ticket 27 left.
BUDGET = 4800
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
    assert first["slot"] == "fast"
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
    # Requests per turn: the chat model on the conversation's slot, then the follow-up and the
    # distillation step on fast, plus one more fast request for the summary on a turn that
    # compresses. Ten turns, three of them compressing.
    assert scripts.resolved == ["fast"] * (10 * 3 + 3)

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
