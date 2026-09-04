"""One test seam: the FastAPI app over HTTP, both model slots scripted per test."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic_ai.messages import ModelMessage, ModelResponse
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy.orm import Session, sessionmaker

from finquery.app import create_app
from finquery.settings import Settings

StreamFn = Callable[[list[ModelMessage], AgentInfo], AsyncIterator[object]]
CallFn = Callable[[list[ModelMessage], AgentInfo], ModelResponse]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SYNTHETIC = FIXTURES / "synthetic"
# The user's own bank export. Gitignored, so tests that need it skip when it is not there.
PRIVATE = FIXTURES / "private"


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
        return FunctionModel(call, stream_function=stream, model_name=f"scripted-{slot}")


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, db_path=":memory:", **overrides)  # type: ignore[call-arg]


@pytest.fixture
def scripts() -> Scripts:
    return Scripts()


@pytest.fixture
def app(scripts: Scripts) -> FastAPI:
    return create_app(make_settings(), resolve_model=scripts.resolve, serve_frontend=False)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
            yield c


@pytest.fixture
def session_factory(app: FastAPI, client: httpx.AsyncClient) -> sessionmaker[Session]:
    """The app's own database, for tests that arrange rows the API cannot create yet."""
    return app.state.session_factory


@pytest.fixture
def profile_id(app: FastAPI, client: httpx.AsyncClient) -> str:
    return app.state.profile_id


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
