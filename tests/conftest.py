"""One test seam: the FastAPI app over HTTP, both model slots scripted per test."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import ModelMessage

from finquery.app import create_app
from finquery.settings import Settings

StreamFn = Callable[[list[ModelMessage], AgentInfo], AsyncIterator[object]]


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
        return FunctionModel(stream_function=fn, model_name=f"scripted-{slot}")


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
