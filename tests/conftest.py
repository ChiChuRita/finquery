"""One test seam: the FastAPI app over HTTP, both model slots scripted per test."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, DeltaThinkingPart, FunctionModel

from finquery.app import create_app
from finquery.followups import FOLLOWUP_MARKER
from finquery.settings import Settings

StreamFn = Callable[[list[ModelMessage], AgentInfo], AsyncIterator[object]]


def _collected(fn: StreamFn) -> Callable[[list[ModelMessage], AgentInfo], Awaitable[ModelResponse]]:
    """The same script as one response, for the steps that do not stream (follow-up suggestions)."""

    async def function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        text = "".join([item async for item in fn(messages, info) if isinstance(item, str)])
        return ModelResponse(parts=[TextPart(content=text)])

    return function


class Scripts:
    """Per-slot scripted stream functions. Tests assign `scripts.fast = ...` before chatting."""

    def __init__(self) -> None:
        self.fast: StreamFn | None = None
        self.quality: StreamFn | None = None
        self.resolved: list[str] = []

    def resolve(self, slot: str) -> FunctionModel:
        self.resolved.append(slot)
        fn = getattr(self, slot)
        assert fn is not None, f"test did not script the {slot} slot"
        return FunctionModel(_collected(fn), stream_function=fn, model_name=f"scripted-{slot}")


def is_followup_request(messages: Sequence[ModelMessage]) -> bool:
    """True for the post-turn step that asks the fast slot for follow-up questions."""
    last = messages[-1]
    return last.kind == "request" and any(
        part.part_kind == "user-prompt" and isinstance(part.content, str) and FOLLOWUP_MARKER in part.content
        for part in last.parts
    )


def script(answer: str, *, thought: str | None = None, followups: Sequence[str] = ()) -> StreamFn:
    """A model that thinks, answers, and offers these follow-ups when the post-turn step asks."""

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "\n".join(followups) if followups else "No follow-ups."
            return
        if thought is not None:
            yield {0: DeltaThinkingPart(content=thought)}
        yield answer

    return fn


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, db_path=":memory:", **overrides)  # type: ignore[call-arg]


@pytest.fixture
def scripts() -> Scripts:
    return Scripts()


@pytest.fixture
async def client(scripts: Scripts) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(), resolve_model=scripts.resolve, serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c


async def default_profile_id(client: httpx.AsyncClient) -> str:
    """The profile the app seeds at startup."""
    profiles = (await client.get("/api/profiles")).json()
    return str(profiles[0]["id"])


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
