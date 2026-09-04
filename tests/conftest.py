"""One test seam: the FastAPI app over HTTP, both model slots scripted per test."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, FunctionModel
from sqlalchemy.orm import Session, sessionmaker

from finquery.app import create_app
from finquery.context import SUMMARY_MARKER
from finquery.followups import FOLLOWUP_MARKER
from finquery.memory import DISTILL_MARKER, DISTILL_TOOL, MemoryKind
from finquery.settings import Settings
from finquery.weblookup import Hit, Page

StreamFn = Callable[[list[ModelMessage], AgentInfo], AsyncIterator[object]]
CallFn = Callable[[list[ModelMessage], AgentInfo], ModelResponse]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SYNTHETIC = FIXTURES / "synthetic"
# The user's own bank export. Gitignored, so tests that need it skip when it is not there.
PRIVATE = FIXTURES / "private"


def _collected(fn: StreamFn) -> Callable[[list[ModelMessage], AgentInfo], Awaitable[ModelResponse]]:
    """The same script as one response, for the steps that do not stream (the sub-agents).

    A script that yields a `ToolCallPart` answers a sub-agent with a schema; anything else is
    collected into text. The distillation pass needs its tool either way, so a script that says
    nothing about it remembers nothing.
    """

    async def function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        items = [item async for item in fn(messages, info)]
        if tool_calls := [item for item in items if isinstance(item, ToolCallPart)]:
            return ModelResponse(parts=tool_calls)
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        return ModelResponse(parts=[TextPart(content="".join(item for item in items if isinstance(item, str)))])

    return function


class Scripts:
    """Per-slot scripted models.

    Tests assign `scripts.fast = ...` for a streamed chat turn and `scripts.fast_call = ...`
    for a sub-agent that runs to completion (the CSV mapping proposal, for instance).
    """

    def __init__(self) -> None:
        self.fast: StreamFn | None = None
        self.quality: StreamFn | None = None
        self.fast_call: CallFn | None = None
        self.quality_call: CallFn | None = None
        self.resolved: list[str] = []

    def resolve(self, slot: str) -> FunctionModel:
        self.resolved.append(slot)
        stream = getattr(self, slot)
        call = getattr(self, f"{slot}_call")
        assert stream is not None or call is not None, f"test did not script the {slot} slot"
        # A streamed script also answers the non-streamed requests sub-agents make, unless the
        # test scripted that side itself.
        return FunctionModel(call or _collected(stream), stream_function=stream, model_name=f"scripted-{slot}")


def _asks_for(messages: Sequence[ModelMessage], marker: str) -> bool:
    last = messages[-1]
    return last.kind == "request" and any(
        part.part_kind == "user-prompt" and isinstance(part.content, str) and marker in part.content
        for part in last.parts
    )


def is_followup_request(messages: Sequence[ModelMessage]) -> bool:
    """True for the post-turn step that asks the fast slot for follow-up questions."""
    return _asks_for(messages, FOLLOWUP_MARKER)


def is_distillation_request(messages: Sequence[ModelMessage]) -> bool:
    """True for the post-turn step that asks the fast slot what is worth remembering."""
    return _asks_for(messages, DISTILL_MARKER)


def is_summary_request(messages: Sequence[ModelMessage]) -> bool:
    """True for the compression step that asks the fast slot for the rolling summary."""
    return _asks_for(messages, SUMMARY_MARKER)


def distilled(*facts: str, kind: MemoryKind = "fact") -> ToolCallPart:
    """The distillation pass's forced tool call: these facts are durable, none by default."""
    return ToolCallPart(tool_name=DISTILL_TOOL, args={"facts": [{"text": text, "kind": kind} for text in facts]})


def script(
    answer: str, *, thought: str | None = None, followups: Sequence[str] = (), memories: Sequence[str] = ()
) -> StreamFn:
    """A model that thinks, answers, and serves every fast-slot step of the turn.

    `followups` are the suggestions it offers, `memories` what its distillation pass finds
    worth remembering. It says nothing about compression: a test whose conversation crosses the
    budget scripts `is_summary_request` itself (see `test_context.py`).
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "\n".join(followups) if followups else "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled(*memories)
            return
        if thought is not None:
            yield {0: DeltaThinkingPart(content=thought)}
        yield answer

    return fn


class NoWeb:
    """The web client every test gets unless it scripts its own: calling it is the failure.

    Web lookup is the only feature that would leave this machine, and it is off by default, so
    a test that reaches here has either flipped the switch without scripting a stub or leaked a
    request from somewhere it should not be. See `tests/test_web_lookup.py` for the stub.
    """

    async def search(self, query: str) -> list[Hit]:
        raise AssertionError(f"a test tried to search the web for {query!r}")

    async def fetch(self, url: str) -> Page:
        raise AssertionError(f"a test tried to fetch {url!r}")


def make_settings(**overrides: object) -> Settings:
    """The app's settings for a test. In-memory database unless the test asks for a file."""
    return Settings(_env_file=None, **{"db_path": ":memory:", **overrides})  # type: ignore[call-arg]


@pytest.fixture
def scripts() -> Scripts:
    return Scripts()


@pytest.fixture
def settings_overrides() -> dict[str, object]:
    """Settings a test module changes for its whole app, such as a small context budget."""
    return {}


@pytest.fixture
def web_client() -> object:
    """The search and page fetch of the web lookup. Overridden by the module that scripts it."""
    return NoWeb()


@pytest.fixture
def app(scripts: Scripts, settings_overrides: dict[str, object], web_client: object) -> FastAPI:
    return create_app(
        make_settings(**settings_overrides),
        resolve_model=scripts.resolve,
        web_client=web_client,  # type: ignore[arg-type]
        serve_frontend=False,
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c


@pytest.fixture
def session_factory(app: FastAPI, client: httpx.AsyncClient) -> sessionmaker[Session]:
    """The app's own database, for tests that arrange rows the API cannot create yet."""
    return app.state.session_factory


async def default_profile_id(client: httpx.AsyncClient) -> str:
    """The profile the app seeds at startup."""
    profiles = (await client.get("/api/profiles")).json()
    return str(profiles[0]["id"])


@pytest.fixture
async def profile_id(client: httpx.AsyncClient) -> str:
    """The seeded profile's id. Every profile-scoped endpoint takes it explicitly."""
    return await default_profile_id(client)


async def new_conversation(client: httpx.AsyncClient, profile_id: str, slot: str = "fast") -> str:
    response = await client.post("/api/conversations", json={"profile_id": profile_id, "model_slot": slot})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def ui_message(text: str, message_id: str = "u1") -> dict[str, object]:
    return {"id": message_id, "role": "user", "parts": [{"type": "text", "text": text}]}


def chat_body(text: str, conversation_id: str, extra_messages: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "id": conversation_id,
        "trigger": "submit-message",
        "messages": [*(extra_messages or []), ui_message(text)],
    }


def parse_sse(body: str) -> list[dict[str, object]]:
    chunks: list[dict[str, object]] = []
    for line in body.splitlines():
        if line.startswith("data: ") and line != "data: [DONE]":
            chunks.append(json.loads(line[len("data: ") :]))
    return chunks


Chat = Callable[[str, str], Awaitable[tuple[httpx.Response, list[dict[str, object]]]]]


@pytest.fixture
def chat(client: httpx.AsyncClient) -> Chat:
    async def _chat(conversation_id: str, text: str) -> tuple[httpx.Response, list[dict[str, object]]]:
        response = await client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body(text, conversation_id))
        return response, parse_sse(response.text)

    return _chat
