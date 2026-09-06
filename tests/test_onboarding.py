"""Onboarding at the HTTP seam: the state, the three steps and the two seeded conversations.

Everything a step does is an endpoint that already existed or one this ticket adds. Step 1
edits the taxonomy through the changeset path the Settings editor uses, step 2 writes the three
preferences through `PATCH /api/settings`, and step 3 imports the shipped year through the same
`chat_import` the composer's attachment path uses. What is asserted is what the user would see
afterwards: the categories the profile has, the language rule in the prompt of the next turn,
the bookings in the profile and the parts of the seeded transcript.
"""

from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo

from .conftest import (
    Chat,
    Scripts,
    default_profile_id,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
)
from .test_categorization import scripted_categorizer
from .test_memory import Recorder

TOTAL_ROWS = 433

CLOUD_GEMMA = "openrouter:google/gemma-4-26b-a4b-it"
"""A catalog entry that is not the default, so a stored choice is visibly a choice."""


async def settings_of(client: httpx.AsyncClient, profile_id: str) -> dict[str, Any]:
    response = await client.get("/api/settings", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return dict(response.json())


async def patch_settings(client: httpx.AsyncClient, profile_id: str, **patch: Any) -> httpx.Response:
    return await client.patch("/api/settings", json={"profile_id": profile_id, **patch})


async def category_names(client: httpx.AsyncClient, profile_id: str) -> list[str]:
    response = await client.get("/api/categories", params={"profile_id": profile_id})
    return [row["name"] for row in response.json()]


async def taxonomy_change(client: httpx.AsyncClient, profile_id: str, title: str, **taxonomy: Any) -> httpx.Response:
    """Propose and apply one taxonomy change, which is what a toggle, an add and a rename do."""
    proposed = await client.post(
        "/api/changesets",
        json={"profile_id": profile_id, "intent": {"kind": "taxonomy", "title": title, "taxonomy": taxonomy}},
    )
    assert proposed.status_code == 201, proposed.text
    return await client.post(
        f"/api/changesets/{proposed.json()['id']}/apply", json={"profile_id": profile_id}
    )


def parts_of(messages: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
    return [part for message in messages if message["role"] == role for part in message["parts"]]


async def test_a_profile_starts_in_not_started_and_the_state_moves_once(client: httpx.AsyncClient) -> None:
    """The state is a profile setting, so it is read and written where the switch already is."""
    seeded = await default_profile_id(client)
    assert (await settings_of(client, seeded))["onboarding_state"] == "not_started"

    created = (await client.post("/api/profiles", json={"name": "Household"})).json()["id"]
    assert (await settings_of(client, created))["onboarding_state"] == "not_started"

    assert (await patch_settings(client, created, onboarding_state="skipped")).status_code == 200
    assert (await settings_of(client, created))["onboarding_state"] == "skipped"
    # Reopened from Settings and finished: the state is the last thing the user did with it.
    assert (await patch_settings(client, created, onboarding_state="done")).status_code == 200
    assert (await settings_of(client, created))["onboarding_state"] == "done"

    assert (await patch_settings(client, created, onboarding_state="halfway")).status_code == 422
    assert (await client.get("/api/settings", params={"profile_id": "nope"})).status_code == 404


async def test_step_one_removes_adds_and_renames_categories(client: httpx.AsyncClient, profile_id: str) -> None:
    """A toggle turned off is a delete, and the taxonomy really loses it. One code path."""
    before = await category_names(client, profile_id)
    assert "Health" in before and "Education" in before

    assert (await taxonomy_change(client, profile_id, "Remove Health", operation="delete", category="Health")).status_code == 200
    assert (await taxonomy_change(client, profile_id, "Remove Education", operation="delete", category="Education")).status_code == 200
    assert (await taxonomy_change(client, profile_id, "Add Pets", operation="add", category="Pets")).status_code == 200
    assert (
        await taxonomy_change(client, profile_id, "Add Vet", operation="add", category="Pets", subcategory="Vet")
    ).status_code == 200
    assert (
        await taxonomy_change(client, profile_id, "Rename Leisure", operation="rename", category="Leisure", new_name="Fun")
    ).status_code == 200

    after = (await client.get("/api/categories", params={"profile_id": profile_id})).json()
    names = [row["name"] for row in after]
    assert "Health" not in names and "Education" not in names
    assert "Pets" in names and "Fun" in names and "Leisure" not in names
    pets = next(row for row in after if row["name"] == "Pets")
    assert [sub["name"] for sub in pets["subcategories"]] == ["Vet"]
    assert len(names) == len(before) - 1


async def test_step_two_stores_the_preferences_and_the_prompt_follows_the_language(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The three preferences of step 2, and the one of them the model has to obey."""
    recorder = Recorder("Bitte sehr.")
    scripts.fast = recorder

    stored = (
        await patch_settings(
            client, profile_id, answer_language="de", default_model_key=CLOUD_GEMMA, web_lookup_enabled=False
        )
    ).json()
    assert stored["answer_language"] == "de"
    assert stored["default_model_key"] == CLOUD_GEMMA
    assert stored["web_lookup_enabled"] is False

    conversation = await new_conversation(client, profile_id)
    await chat(conversation, "How much did I spend?")
    assert "Write every answer in German" in recorder.prompt

    await patch_settings(client, profile_id, answer_language="follow")
    await chat(conversation, "And how much was it in May?")
    assert "Write every answer in German" not in recorder.prompt
    assert "Write every answer in English" not in recorder.prompt
    # On `follow` the language of the newest message is detected in code and named outright,
    # because the local fast model left to detect it answers German data in German.
    assert "The user's newest message is written in English" in recorder.prompt
    await chat(conversation, "Und wie viel war es im April?")
    assert "The user's newest message is written in German" in recorder.prompt
    await chat(conversation, "Netflix 2025?")
    assert "newest message is written in" not in recorder.prompt, "a message with no function words names no language"

    assert (await patch_settings(client, profile_id, answer_language="fr")).status_code == 422
    assert (await patch_settings(client, profile_id, default_model_key="huge")).status_code == 422


async def test_step_three_imports_the_sample_year_as_a_dropped_file_would(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    """The shipped year, imported through the chat path, seeded as the turn it would have been."""
    scripts.fast_call = scripted_categorizer()

    response = await client.post("/api/onboarding/sample", json={"profile_id": profile_id})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported"] == TOTAL_ROWS
    assert body["needs_review"] > 0

    assert (await client.get("/api/transactions", params={"profile_id": profile_id})).json()["total"] == TOTAL_ROWS
    records = (await client.get("/api/imports", params={"profile_id": profile_id})).json()
    assert [record["file_name"] for record in records] == ["sparkasse-2025.csv"]
    # The import knows the conversation it happened in, the way a dropped file's import does.
    assert records[0]["conversation_id"] == body["conversation_id"]

    detail = (await client.get(f"/api/conversations/{body['conversation_id']}")).json()
    assert detail["title"] == "The sample year"
    user_parts = parts_of(detail["messages"], "user")
    chips = [part for part in user_parts if part["type"] == "file"]
    assert [chip["filename"] for chip in chips] == ["sparkasse-2025.csv"]
    # The chip is a link, so the id in it has to be a stored attachment: the seeded turn read it
    # off a record that had not been flushed yet and linked to `/api/attachments/None`.
    stored = await client.get(chips[0]["url"])
    assert stored.status_code == 200, chips[0]["url"]
    assert stored.content.startswith(b'"Auftragskonto"'), "the chip serves the CSV that was imported"
    assistant_parts = parts_of(detail["messages"], "assistant")
    imports = [part for part in assistant_parts if part["type"] == "tool-import_file"]
    assert len(imports) == 1
    assert imports[0]["output"]["imported"] == TOTAL_ROWS
    cards = [part for part in assistant_parts if part["type"] == "tool-ask_user"]
    assert len(cards) == 1, "the merchants the import could not place are asked about on a card"
    # The state a reload of a pending deferred call dumps as, which is what the card treats as open.
    assert cards[0]["state"] == "approval-requested", "the card is pending, so answering it resumes the run"


async def test_finish_seeds_a_welcome_turn_with_three_suggestions(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """No model runs for it: an empty profile is told so, and offered three things to ask."""
    response = await client.post("/api/onboarding/welcome", json={"profile_id": profile_id})
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["suggestions"]) == 3

    detail = (await client.get(f"/api/conversations/{body['conversation_id']}")).json()
    assert detail["title"] == "Welcome"
    parts = parts_of(detail["messages"], "assistant")
    text = next(part["text"] for part in parts if part["type"] == "text")
    assert "Nothing is imported in this profile yet" in text
    followups = [part for part in parts if part["type"] == "data-followups"]
    assert len(followups) == 1
    assert followups[0]["data"]["suggestions"] == body["suggestions"]
    assert not parts_of(detail["messages"], "user"), "nobody asked for the welcome, so nobody said anything"


async def test_the_welcome_names_the_data_and_speaks_the_chosen_language(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    scripts.fast_call = scripted_categorizer()
    await client.post("/api/onboarding/sample", json={"profile_id": profile_id})
    await patch_settings(client, profile_id, answer_language="de")

    body = (await client.post("/api/onboarding/welcome", json={"profile_id": profile_id})).json()
    detail = (await client.get(f"/api/conversations/{body['conversation_id']}")).json()
    text = next(part["text"] for part in parts_of(detail["messages"], "assistant") if part["type"] == "text")
    assert f"{TOTAL_ROWS} Buchungen" in text and "Sparkasse Girokonto" in text
    assert "von 01.01.2025 bis 28.12.2025" in text, "the real range of the shipped year, in German"
    assert detail["title"] == "Willkommen"
    assert all("?" in suggestion for suggestion in body["suggestions"])
    assert any("2025" in suggestion for suggestion in body["suggestions"])


async def test_the_seeded_conversations_belong_to_the_profile_that_asked(client: httpx.AsyncClient) -> None:
    for path in ("/api/onboarding/sample", "/api/onboarding/welcome"):
        assert (await client.post(path, json={"profile_id": "nope"})).status_code == 404


async def test_the_follow_up_chips_are_written_in_the_language_the_profile_fixed(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Chips are read next to the answer, so they follow the same rule the answer does.

    A profile fixed to English got German suggestions under an English answer (e2e of
    2026-09-05, m3), because the follow-up step was only ever told "the language of the
    exchange" and the exchange it saw had been German.
    """
    asked: list[str] = []

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            asked.append(_prompt_of(messages))
            yield "What did I spend on groceries in May?"
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        yield "You spent 440,72 EUR on groceries in May 2025."

    scripts.fast = fn
    conversation = await new_conversation(client, profile_id)

    await patch_settings(client, profile_id, answer_language="en")
    await chat(conversation, "Wie viel habe ich im Mai fuer Lebensmittel ausgegeben?")
    assert "write the questions in English" in asked[-1]

    await patch_settings(client, profile_id, answer_language="de")
    await chat(conversation, "And in June?")
    assert "write the questions in German" in asked[-1]

    # On `follow` nothing is named and the exchange decides, as it always did.
    await patch_settings(client, profile_id, answer_language="follow")
    await chat(conversation, "And in July?")
    assert "write the questions in" not in asked[-1]


def _prompt_of(messages: list[ModelMessage]) -> str:
    return "\n".join(
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt" and isinstance(part.content, str)
    )
