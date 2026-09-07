"""The model catalog at the HTTP seam, the sub-agent role settings, and the local seat.

The rule this file holds the app to: a conversation's chat model is its catalog entry, and
every sub-agent role runs on what its own setting names, which is that same entry by default
(`chat`), the fast slot of the entry's provider (`fast`), or a catalog key. The scripted
resolver is asked for `(entry key, role)`, so every half is assertable without a model anywhere
near it. See docs/adr/0013-model-catalog-across-providers.md and the ticket 61 amendment of
docs/adr/0006-local-gemma-4-through-llama-cpp.md.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from finquery.app import create_app
from finquery.db import Conversation, Profile, Turn
from finquery.local.catalog import LOCAL_FAST, LOCAL_GEMMA_12B, LOCAL_GEMMA_26B, ModelSpec
from finquery.local.runtime import LocalStack
from finquery.providers import SUBAGENT_ROLES
from finquery.settings import Settings

from .conftest import (
    Chat,
    NoWeb,
    Scripts,
    chat_body,
    default_profile_id,
    make_settings,
    model_keys,
    new_conversation,
    parse_sse,
    script,
)


@pytest.fixture
def settings_overrides(tmp_path: Path) -> dict[str, object]:
    """A key, so the cloud entry is live, and an empty models folder for the local three.

    The fast slot points at the Gemma id the development `.env` uses, which is the case that
    used to collapse the cloud entries into the slot.
    """
    return {
        "openrouter_api_key": "test-key",
        "models_dir": tmp_path / "no-models",
        "openrouter_fast_model": "google/gemma-4-26b-a4b-it",
    }


LOCAL_E4B_KEY = "local:gemma-4-e4b"
LOCAL_GEMMA_KEY = "local:gemma-4-12b"
LOCAL_26B_KEY = "local:gemma-4-26b"
CLOUD_GEMMA_KEY = "openrouter:google/gemma-4-26b-a4b-it"


@asynccontextmanager
async def app_on(scripts: Scripts, tmp_path: Path, **overrides: object) -> AsyncIterator[httpx.AsyncClient]:
    """One app with settings of its own, for the tests that change a role setting."""
    settings = make_settings(openrouter_api_key="test-key", models_dir=tmp_path / "no-models", **overrides)
    app = create_app(settings, resolve_model=scripts.resolve, web_client=NoWeb(), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def one_turn_on(client: httpx.AsyncClient, key: str) -> None:
    """One chat turn on one entry, which resolves the chat model and both post-turn roles."""
    conversation_id = await new_conversation(client, await default_profile_id(client), key)
    response = await client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body("go", conversation_id))
    assert response.status_code == 200, response.text
    assert parse_sse(response.text), "the turn produced nothing"


async def test_the_catalog_lists_four_entries_with_their_availability(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/models")).json()

    # The three local Gemma 4 sizes small to large, then the same 26B in the cloud. The cloud
    # entry is listed although the fast slot points at it, because it is the catalog's own id
    # and not a setting. Qwen3.5 9B left in ticket 67.
    assert [(e["key"], e["label"], e["provider"]) for e in body["entries"]] == [
        (LOCAL_E4B_KEY, "Gemma 4 E4B (local)", "local"),
        (LOCAL_GEMMA_KEY, "Gemma 4 12B (local)", "local"),
        (LOCAL_26B_KEY, "Gemma 4 26B (local)", "local"),
        (CLOUD_GEMMA_KEY, "Gemma 4 26B (cloud)", "openrouter"),
    ]
    # No weights in this test's models folder, so the local entries say so rather than
    # disappearing: the picker disables them with the reason.
    assert [e["available"] for e in body["entries"]] == [False, False, False, True]
    assert all(e["reason"] is None for e in body["entries"] if e["available"])
    assert body["default_key"] == CLOUD_GEMMA_KEY
    # The sub-agent slot of each provider comes with the catalog. Locally it is the E4B entry
    # itself, so that key is in both lists and the models card shows it once.
    assert [e["key"] for e in body["fast_slots"]] == [LOCAL_E4B_KEY, "openrouter:fast"]
    assert body["openrouter_key_hint"] == "...-key"


@pytest.mark.parametrize("key", [LOCAL_26B_KEY, CLOUD_GEMMA_KEY])
async def test_a_conversation_on_each_entry_records_it_and_its_turns_carry_it(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, key: str
) -> None:
    scripts.entries[key] = script(f"answered by {key}")
    conversation_id = await new_conversation(client, profile_id, key)

    _, chunks = await chat(conversation_id, "How much in May?")

    metadata = [c["messageMetadata"] for c in chunks if c["type"] == "message-metadata"]
    assert [m for m in metadata if m.get("model_key") == key], metadata
    detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
    assert detail["model_key"] == key
    assistants = [m for m in detail["messages"] if m["role"] == "assistant"]
    assert [m["metadata"]["model_key"] for m in assistants] == [key]
    assert f"answered by {key}" in str(detail["messages"])


async def test_a_sub_agent_role_runs_on_the_conversations_own_entry_by_default(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, session_factory: sessionmaker[Session]
) -> None:
    """The default of every role is `chat`, so a sub-agent runs on the model the user picked.

    The local entries have no weights in this test, so the local turn is driven by putting the
    conversation on that entry directly: the scripted resolver stands in for every model, and
    what is asserted is which entry key the app asked for, which is where a real run would have
    gone.
    """
    scripts.fast = script("the answer")
    cloud = await new_conversation(client, profile_id, CLOUD_GEMMA_KEY)
    await chat(cloud, "cloud question")

    assert scripts.resolved[0] == (CLOUD_GEMMA_KEY, "chat")
    assert scripts.resolved[1:], "the post-turn sub-agents never ran"
    assert set(scripts.resolved[1:]) == {(CLOUD_GEMMA_KEY, "summary"), (CLOUD_GEMMA_KEY, "memory")}

    scripts.resolved.clear()
    local = await new_conversation(client, profile_id, LOCAL_GEMMA_KEY)
    await chat(local, "local question")

    assert scripts.resolved[0] == (LOCAL_GEMMA_KEY, "chat")
    assert set(scripts.resolved[1:]) == {
        (LOCAL_GEMMA_KEY, "summary"),
        (LOCAL_GEMMA_KEY, "memory"),
    }, "a local entry keeps its sub-agents local"
    with session_factory() as session:
        turns = session.query(Turn).join(Conversation).filter(Conversation.id == local).all()
        assert [turn.model_key for turn in turns] == [LOCAL_GEMMA_KEY]


async def test_a_role_set_to_fast_runs_on_the_fast_slot_of_the_entrys_provider(
    scripts: Scripts, tmp_path: Path
) -> None:
    """`fast` is what every role meant before this setting existed, and still means."""
    scripts.fast = script("the answer")
    every_role_fast = {f"subagent_model_{role}": "fast" for role in SUBAGENT_ROLES}

    async with app_on(scripts, tmp_path, **every_role_fast) as client:
        await one_turn_on(client, CLOUD_GEMMA_KEY)
        assert scripts.resolved[0] == (CLOUD_GEMMA_KEY, "chat")
        assert set(scripts.resolved[1:]) == {("openrouter:fast", "summary"), ("openrouter:fast", "memory")}

        scripts.resolved.clear()
        await one_turn_on(client, LOCAL_GEMMA_KEY)
        assert set(scripts.resolved[1:]) == {(LOCAL_E4B_KEY, "summary"), (LOCAL_E4B_KEY, "memory")}

        roles = {r["role"]: (r["setting"], r["key"]) for r in (await client.get("/api/models")).json()["roles"]}
        assert roles["query"] == ("fast", "openrouter:fast")


async def test_a_role_pinned_to_a_catalog_key_runs_there_whatever_the_chat_runs_on(
    scripts: Scripts, tmp_path: Path
) -> None:
    """A catalog key in the setting pins that one role, and moves nothing else."""
    scripts.fast = script("the answer")

    async with app_on(scripts, tmp_path, subagent_model_memory=LOCAL_GEMMA_KEY) as client:
        await one_turn_on(client, CLOUD_GEMMA_KEY)

        assert set(scripts.resolved) == {
            (CLOUD_GEMMA_KEY, "chat"),
            (CLOUD_GEMMA_KEY, "summary"),
            (LOCAL_GEMMA_KEY, "memory"),
        }


async def test_the_models_endpoint_says_what_every_role_resolves_to(client: httpx.AsyncClient) -> None:
    """The models card lists the roles, because a setting saying `chat` is only half an answer."""
    body = (await client.get("/api/models")).json()

    assert [r["role"] for r in body["roles"]] == list(SUBAGENT_ROLES)
    assert {r["setting"] for r in body["roles"]} == {"chat"}
    assert {(r["key"], r["label"]) for r in body["roles"]} == {(CLOUD_GEMMA_KEY, "Gemma 4 26B (cloud)")}


async def test_a_hosted_entry_without_an_api_key_is_a_sentence_not_a_stack_trace(tmp_path: Path) -> None:
    """No key, so the cloud entry is listed unavailable and a turn on it says why."""
    settings = make_settings(openrouter_api_key=None, models_dir=tmp_path / "empty")
    app = create_app(settings, web_client=NoWeb(), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = (await client.get("/api/models")).json()
            cloud = [e for e in body["entries"] if e["provider"] == "openrouter"]
            assert [e["available"] for e in cloud] == [False]
            assert all("OPENROUTER_API_KEY" in e["reason"] and "Settings" in e["reason"] for e in cloud)
            assert body["openrouter_key_hint"] is None

            profile_id = await default_profile_id(client)
            conversation_id = await new_conversation(client, profile_id, CLOUD_GEMMA_KEY)
            response = await client.post(
                f"/api/conversations/{conversation_id}/chat", json=chat_body("go", conversation_id)
            )

            assert response.status_code == 503
            assert "OPENROUTER_API_KEY" in response.json()["detail"]
            # Nothing half-written was left behind for the next load to explain away.
            assert (await client.get(f"/api/conversations/{conversation_id}")).json()["messages"] == []


async def test_a_key_entered_in_settings_makes_the_cloud_entry_answer_and_survives_a_restart(tmp_path: Path) -> None:
    """The Settings card takes the key: live at once, written to the key file, cleared again.

    The file keeps every other line as it was, so a hand-edited `.env` loses nothing, and the
    browser only ever sees the last four characters.
    """
    key_file = tmp_path / ".env"
    key_file.write_text("FINQUERY_PROVIDER=openrouter\n# a comment\nOPENROUTER_API_KEY=\n")
    settings = make_settings(openrouter_api_key=None, models_dir=tmp_path / "empty", key_file=key_file)
    app = create_app(settings, web_client=NoWeb(), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            saved = await client.put("/api/models/openrouter-key", json={"key": "  sk-or-v1-abcd1234  "})
            assert saved.status_code == 200, saved.text
            body = saved.json()
            cloud = next(e for e in body["entries"] if e["provider"] == "openrouter")
            assert cloud["available"] is True
            assert body["openrouter_key_hint"] == "...1234"
            assert "sk-or-v1-abcd1234" not in saved.text
            assert key_file.read_text() == "FINQUERY_PROVIDER=openrouter\n# a comment\nOPENROUTER_API_KEY=sk-or-v1-abcd1234\n"
            # The next process reads it from the same file.
            assert Settings(_env_file=key_file).openrouter_api_key == "sk-or-v1-abcd1234"  # type: ignore[call-arg]

            assert (await client.put("/api/models/openrouter-key", json={"key": "   "})).status_code == 422

            cleared = (await client.delete("/api/models/openrouter-key")).json()
            assert next(e for e in cleared["entries"] if e["provider"] == "openrouter")["available"] is False
            assert cleared["openrouter_key_hint"] is None
            assert key_file.read_text() == "FINQUERY_PROVIDER=openrouter\n# a comment\nOPENROUTER_API_KEY=\n"


async def test_a_row_from_before_the_catalog_reads_as_the_default_entry_of_the_provider(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, session_factory: sessionmaker[Session]
) -> None:
    """`fast` and `quality` were the two values a conversation could hold before ticket 54.

    Both read as the default entry of the configured provider: `fast` was the sub-agent slot,
    never a chat choice a user meant to keep, and `quality` was a position rather than a model,
    which is exactly why the model in it moved again in ticket 61. A profile default from before
    the catalog reads the same way, so nobody's next conversation starts somewhere they never
    chose.
    """
    scripts.fast = script("still answering")
    with session_factory() as session:
        for legacy in ("fast", "quality"):
            session.add(Conversation(profile_id=profile_id, model_slot=legacy, title=f"a {legacy} chat"))
        profile = session.get(Profile, profile_id)
        assert profile is not None
        profile.default_model_slot = "quality"
        session.commit()

    listing = (await client.get("/api/conversations", params={"profile_id": profile_id})).json()
    assert [c["model_key"] for c in listing] == [CLOUD_GEMMA_KEY, CLOUD_GEMMA_KEY]
    assert (await client.get("/api/settings", params={"profile_id": profile_id})).json()[
        "default_model_key"
    ] == CLOUD_GEMMA_KEY

    # And a legacy row still answers, on that entry.
    conversation_id = str(listing[0]["id"])
    _, chunks = await chat(conversation_id, "still there?")
    assert scripts.resolved[0] == (CLOUD_GEMMA_KEY, "chat")
    assert [c for c in chunks if c["type"] == "text-delta"], "a legacy row still answers"


async def test_the_default_entry_follows_the_provider_setting_and_nothing_else(tmp_path: Path) -> None:
    """`FINQUERY_PROVIDER=local` moves the default entry; the cloud entries stay listed."""
    settings = make_settings(provider="local", openrouter_api_key="test-key", models_dir=tmp_path / "empty")
    app = create_app(settings, web_client=NoWeb(), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = (await client.get("/api/models")).json()
            assert body["default_key"] == LOCAL_GEMMA_KEY
            assert [e["key"] for e in body["entries"]] == await model_keys(client)
            assert [e["available"] for e in body["entries"]] == [False, False, False, True]


# The seat under the two local chat models, without a llama.cpp anywhere near it.


class SeatSlot:
    """A `Slot` that only remembers what was done to it."""

    load_seconds = 0.1
    model = object()
    ctx = object()

    def __init__(self, name: str, log: list[str]) -> None:
        self.name = name
        self._log = log

    def stream(self, **_kwargs: Any) -> Any:
        raise AssertionError("the seat test never generates")

    def context_tokens(self) -> int:
        return 0

    def reset(self) -> None: ...

    def close(self) -> None:
        self._log.append(f"unload:{self.name}")


def seat_stack(tmp_path: Path, log: list[str]) -> LocalStack:
    """A stack over the three real specs whose files exist and whose loader is a stub."""
    settings = make_settings(provider="local", models_dir=tmp_path / "models")
    models: dict[str, ModelSpec] = {spec.key: spec for spec in (LOCAL_FAST, LOCAL_GEMMA_12B, LOCAL_GEMMA_26B)}
    for spec in models.values():
        for file in spec.files:
            path = spec.path(settings.models_dir, file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    def load(spec: ModelSpec, *_args: object) -> SeatSlot:
        log.append(f"load:{spec.key}")
        return SeatSlot(spec.key, log)

    stack = LocalStack(settings, models=models, load=load)  # type: ignore[arg-type]
    stack.drain = lambda seat, timeout=60: log.append(f"drain:{seat}")  # type: ignore[assignment,method-assign]
    return stack


async def test_the_chat_seat_drains_unloads_and_loads_and_never_holds_three(tmp_path: Path) -> None:
    """Choosing the other chat model swaps the seat, in that order, and E4B stays put.

    Gemma 12B plus E4B is about 12.9 GB and the 26B is 12.9 GB of weights on its own. The three
    together do not fit on a 24 GB Mac, which is what this order and this seat exist for. A
    chat on E4B itself holds the fast seat, so it never takes the chat seat from either.
    """
    log: list[str] = []
    stack = seat_stack(tmp_path, log)

    async with stack.holding("fast", LOCAL_FAST):
        pass
    async with stack.holding("chat", LOCAL_GEMMA_26B):
        pass
    assert log == ["load:local:gemma-4-e4b", "load:local:gemma-4-26b"], "nothing is drained into an empty seat"
    assert stack.loaded_spec("chat") is LOCAL_GEMMA_26B

    log.clear()
    async with stack.holding("chat", LOCAL_GEMMA_12B):
        pass

    assert log == ["drain:chat", "unload:local:gemma-4-26b", "load:local:gemma-4-12b"]
    assert stack.loaded_spec("chat") is LOCAL_GEMMA_12B
    # Two seats, so two models, whatever order they were asked for in.
    assert stack.loaded_spec("fast") is LOCAL_FAST
    assert len(stack._seats) == 2  # noqa: SLF001 - the seat count is the point

    # Asking for the model that is already in the seat swaps nothing.
    log.clear()
    async with stack.holding("chat", LOCAL_GEMMA_12B):
        pass
    assert log == []
