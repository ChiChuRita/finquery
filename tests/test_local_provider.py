"""The local provider over the same HTTP seam, with no real model loaded.

Two stubs are what `create_app(local=...)` exists for: a fetch function instead of a download,
and a `Slot` returning canned llama.cpp chat chunks instead of a loaded GGUF. What is asserted
is what a client sees: the models endpoint, the SSE stream of a turn, and the turn a later GET
returns.
"""

import asyncio
import base64
import hashlib
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel
from pydantic_ai import Agent

from finquery.agent import chat_agent
from finquery.app import create_app
from finquery.local.adapters import AdapterRegistry
from finquery.local.catalog import FileSpec, ModelSpec, adapter_path
from finquery.local.check import solid_png
from finquery.local.downloads import DownloadManager, Report
from finquery.local.runtime import LocalStack

from .conftest import chat_body, default_profile_id, make_settings, new_conversation, parse_sse


def spec(slot: str, name: str, weights_size: int) -> ModelSpec:
    return ModelSpec(
        slot=slot,  # type: ignore[arg-type]
        name=name,
        weights=FileSpec(kind="weights", repo_id="acme/tiny", filename=f"{name}.gguf", size=weights_size, sha256="0" * 64),
        projector=FileSpec(kind="projector", repo_id="acme/tiny", filename="mmproj.gguf", size=4, sha256="1" * 64),
    )


TINY_MODELS = {"fast": spec("fast", "tiny-fast", 8), "quality": spec("quality", "tiny-quality", 16)}


def chunks(*texts: str) -> Iterator[dict[str, Any]]:
    """The shape llama-cpp-python's chat handler streams: one delta per token."""
    yield {"choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
    for text in texts:
        yield {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
    yield {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}


class FakeSlot:
    """A `Slot` that replays canned llama.cpp output and records the requests it was given."""

    load_seconds = 0.5
    model = object()
    ctx = object()

    def __init__(self, name: str, *turns: tuple[str, ...]) -> None:
        self.name = name
        self._turns = list(turns)
        self.requests: list[dict[str, Any]] = []
        self.resets = 0

    def stream(self, **kwargs: Any) -> Iterator[dict[str, Any]]:
        self.requests.append(kwargs)
        return chunks(*(self._turns.pop(0) if self._turns else ("nothing scripted",)))

    def context_tokens(self) -> int:
        return 12

    def reset(self) -> None:
        self.resets += 1


class FakeAdapterApi:
    """Records the low-level llama.cpp adapter calls the registry makes."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def init(self, model: Any, path: Path) -> Any:
        self.calls.append(f"init:{path.name}")
        return object()

    def set(self, ctx: Any, handle: Any | None) -> None:
        self.calls.append("attach" if handle is not None else "detach")

    def free(self, handle: Any) -> None:
        self.calls.append("free")


def local_stack(tmp_path: Path, slots: dict[str, FakeSlot]) -> LocalStack:
    """A stack whose files are on disk and whose slots and adapter API are stubs."""
    settings = make_settings(provider="local", models_dir=tmp_path / "models")
    for model in TINY_MODELS.values():
        for file in model.files:
            path = model.path(settings.models_dir, file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * file.size)
    return LocalStack(
        settings,
        models=TINY_MODELS,  # type: ignore[arg-type]
        adapters=AdapterRegistry(settings.models_dir, api=FakeAdapterApi()),
        load=lambda model, *_: slots[model.slot],
    )


@asynccontextmanager
async def local_client(stack: LocalStack) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(provider="local"), local=stack, serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def turn(client: httpx.AsyncClient, conversation_id: str, text: str) -> list[dict[str, Any]]:
    response = await client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body(text, conversation_id))
    assert response.status_code == 200
    return parse_sse(response.text)


async def test_local_provider_resolves_both_slots_and_reports_them(tmp_path: Path) -> None:
    slots = {"fast": FakeSlot("tiny-fast"), "quality": FakeSlot("tiny-quality")}
    async with local_client(local_stack(tmp_path, slots)) as client:
        body = (await client.get("/api/models")).json()
        assert body["provider"] == "local"
        assert [m["slot"] for m in body["models"]] == ["fast", "quality"]
        assert all(m["ready"] and not m["loaded"] for m in body["models"])
        assert all(f["state"] == "ready" for m in body["models"] for f in m["files"])
        assert [(a["name"], a["present"]) for a in body["adapters"]] == [("query", False), ("chart", False)]

        profile_id = await default_profile_id(client)
        for slot in ("fast", "quality"):
            await turn(client, await new_conversation(client, profile_id, slot), "hi")

        after = (await client.get("/api/models")).json()["models"]
        assert [m["loaded"] for m in after] == [True, True]
        assert [m["n_ctx"] for m in after] == [16384, 16384]
        # Two turns, plus the two post-turn steps each one runs on the fast slot afterwards
        # (follow-up suggestions and memory distillation).
        assert len(slots["fast"].requests) == 5
        assert len(slots["quality"].requests) == 1


async def test_thinking_is_split_out_of_the_text_stream(tmp_path: Path) -> None:
    reply = ("<|channel>", "thought\n", "They asked ", "for a number. ", "<channel|>", "I cannot ", "compute that yet.")
    slots = {"fast": FakeSlot("tiny-fast", reply), "quality": FakeSlot("tiny-quality")}
    async with local_client(local_stack(tmp_path, slots)) as client:
        conversation_id = await new_conversation(client, await default_profile_id(client))
        seen = await turn(client, conversation_id, "How much in May?")

        kinds = [c["type"] for c in seen]
        assert kinds.index("reasoning-end") < kinds.index("text-start")
        assert "".join(str(c["delta"]) for c in seen if c["type"] == "reasoning-delta") == "They asked for a number. "
        assert "".join(str(c["delta"]) for c in seen if c["type"] == "text-delta") == "I cannot compute that yet."

        # Thinking is switched on through the chat template, not through a request flag.
        assert slots["fast"].requests[0]["enable_thinking"] is True
        assert slots["fast"].requests[0]["top_k"] == 64

        detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
        assert [p["type"] for p in detail["messages"][1]["parts"]] == ["reasoning", "text", "data-context"]


async def test_gemma_tool_call_syntax_becomes_a_tool_part(tmp_path: Path) -> None:
    def query(question: str, limit: int) -> str:
        """Answer a question from the transactions."""
        return f"{question} -> 120.00 EUR (limit {limit})"

    calling = (
        "<|channel>thought\nI need the data.<channel|>",
        '<|tool_call>call:query{question:<|"|>groceries',
        ' in May<|"|>,limit:20}<tool_call|>',
    )
    # After a tool response the chat template leaves the thought channel open, so the model
    # closes it before the answer.
    answering = ("Still thinking.<channel|>You spent ", "120 EUR.")
    slots = {"fast": FakeSlot("tiny-fast", calling, answering), "quality": FakeSlot("tiny-quality")}
    with chat_agent.override(tools=[query]):
        async with local_client(local_stack(tmp_path, slots)) as client:
            seen = await turn(client, await new_conversation(client, await default_profile_id(client)), "groceries in May?")

            available = [c for c in seen if c["type"] == "tool-input-available"]
            assert [c["toolName"] for c in available] == ["query"]
            assert available[0]["input"] == {"question": "groceries in May", "limit": 20}
            output = [c for c in seen if c["type"] == "tool-output-available"]
            assert output[0]["output"] == "groceries in May -> 120.00 EUR (limit 20)"
            assert "".join(str(c["delta"]) for c in seen if c["type"] == "text-delta") == "You spent 120 EUR."

            # Free tool calling: the tool is declared, nothing is forced, no response format.
            first = slots["fast"].requests[0]
            assert [t["function"]["name"] for t in first["tools"]] == ["query"]
            assert first["tool_choice"] == "auto"
            assert "response_format" not in first
            # The tool result goes back as a tool message the chat template renders as a response.
            assert slots["fast"].requests[1]["messages"][-1]["role"] == "tool"


async def test_stop_ends_the_token_loop_and_keeps_the_partial_turn(tmp_path: Path) -> None:
    started = asyncio.Event()
    loop = asyncio.get_running_loop()

    class SlowSlot(FakeSlot):
        def stream(self, **kwargs: Any) -> Iterator[dict[str, Any]]:
            self.requests.append(kwargs)

            def generate() -> Iterator[dict[str, Any]]:
                yield {"choices": [{"index": 0, "delta": {"content": "partial "}, "finish_reason": None}]}
                loop.call_soon_threadsafe(started.set)
                while True:
                    yield {"choices": [{"index": 0, "delta": {"content": "more "}, "finish_reason": None}]}

            return generate()

    slots = {"fast": SlowSlot("tiny-fast"), "quality": FakeSlot("tiny-quality")}
    async with local_client(local_stack(tmp_path, slots)) as client:
        conversation_id = await new_conversation(client, await default_profile_id(client))
        running = asyncio.create_task(
            client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body("go", conversation_id))
        )
        await asyncio.wait_for(started.wait(), timeout=5)
        assert (await client.post(f"/api/conversations/{conversation_id}/stop")).json() == {"stopped": True}

        response = await asyncio.wait_for(running, timeout=10)
        assert "abort" in [c["type"] for c in parse_sse(response.text)]
        detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
        assert detail["interrupted"] is True
        assert detail["messages"][-1]["parts"][0]["text"].startswith("partial")


async def test_download_progress_endpoint_reports_each_file(tmp_path: Path) -> None:
    release = asyncio.Event()
    loop = asyncio.get_running_loop()
    halfway = asyncio.Event()

    def fetch(file: FileSpec, destination: Path, report: Report) -> None:
        report(file.size // 2)
        loop.call_soon_threadsafe(halfway.set)
        asyncio.run_coroutine_threadsafe(release.wait(), loop).result(timeout=10)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"y" * file.size)
        report(file.size)

    models = {"fast": TINY_MODELS["fast"]}
    settings = make_settings(provider="local", models_dir=tmp_path / "models")
    stack = LocalStack(
        settings,
        models=models,  # type: ignore[arg-type]
        downloads=DownloadManager(settings.models_dir, models=models, fetch=fetch),  # type: ignore[arg-type]
        load=lambda *_: FakeSlot("tiny-fast"),
    )
    async with local_client(stack) as client:
        before = (await client.get("/api/models")).json()["models"][0]
        assert before["ready"] is False
        assert [f["state"] for f in before["files"]] == ["missing", "missing"]

        assert (await client.post("/api/models/download")).json()["downloading"] is True
        await asyncio.wait_for(halfway.wait(), timeout=5)

        during = (await client.get("/api/models")).json()["models"][0]["files"][0]
        assert during["state"] == "downloading"
        assert during["downloaded"] == during["size"] // 2

        release.set()
        body = await _wait_for_downloads(client)
        assert body["models"][0]["ready"] is True
        assert [f["state"] for f in body["models"][0]["files"]] == ["ready", "ready"]


async def _wait_for_downloads(client: httpx.AsyncClient) -> dict[str, Any]:
    for _ in range(200):
        body = (await client.get("/api/models")).json()
        if not body["downloading"]:
            return body
        await asyncio.sleep(0.05)
    raise AssertionError("downloads never finished")


def parked_spec(payload: bytes, filename: str, kind: str) -> FileSpec:
    return FileSpec(
        kind=kind,  # type: ignore[arg-type]
        repo_id="acme/tiny",
        filename=filename,
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


async def test_parked_file_is_reused_when_its_hash_matches(tmp_path: Path) -> None:
    weights_payload, projector_payload = b"gguf" * 4, b"proj"
    parked = tmp_path / "parked"
    parked.mkdir()
    (parked / "someone-elses-name.gguf").write_bytes(weights_payload)
    (parked / "same-size-wrong-content.gguf").write_bytes(b"z" * len(weights_payload))
    (parked / "mm.gguf").write_bytes(projector_payload)

    model = ModelSpec(
        slot="fast",
        name="tiny",
        weights=parked_spec(weights_payload, "wanted.gguf", "weights"),
        projector=parked_spec(projector_payload, "mmproj.gguf", "projector"),
    )

    def never(*_args: Any) -> None:
        raise AssertionError("a parked copy whose hash matches must not be downloaded again")

    manager = DownloadManager(tmp_path / "models", models={"fast": model}, parked_dirs=[parked], fetch=never)
    manager.ensure("fast", timeout=10)
    assert manager.path(model, model.weights).read_bytes() == weights_payload
    assert manager.path(model, model.projector).read_bytes() == projector_payload
    assert [(row.state, row.source) for row in manager.progress()] == [
        ("ready", f"a parked copy at {parked / 'someone-elses-name.gguf'}"),
        ("ready", f"a parked copy at {parked / 'mm.gguf'}"),
    ]


async def test_adapter_falls_back_to_base_weights_with_a_note(tmp_path: Path) -> None:
    slots = {"fast": FakeSlot("tiny-fast"), "quality": FakeSlot("tiny-quality")}
    stack = local_stack(tmp_path, slots)
    calls: list[str] = stack.adapters._api.calls  # type: ignore[attr-defined] # noqa: SLF001

    # No file for the query adapter: the run goes ahead on the base weights, loudly.
    with stack.adapters.attached_to("query", slots["fast"]) as note:  # type: ignore[arg-type]
        assert note is not None
        assert "base weights" in note.text
    assert calls == []

    # With a file there, the low-level attach and detach both happen and the slot is reset.
    path = adapter_path(stack.downloads.models_dir, "chart")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"lora")
    with stack.adapters.attached_to("chart", slots["fast"]) as note:  # type: ignore[arg-type]
        assert note is None
        assert stack.adapters.attached == "chart"
    assert calls == ["init:chart.gguf", "attach", "detach", "free"]
    assert stack.adapters.attached is None
    assert slots["fast"].resets == 1

    async with local_client(stack) as client:
        assert [a["present"] for a in (await client.get("/api/models")).json()["adapters"]] == [False, True]


async def test_the_fallback_note_reaches_the_client_and_the_stored_turn(tmp_path: Path) -> None:
    slots = {"fast": FakeSlot("tiny-fast", ("120 EUR.",)), "quality": FakeSlot("tiny-quality")}
    stack = local_stack(tmp_path, slots)
    # A sub-agent asks for its adapter by naming it in the model settings; there is no file.
    with chat_agent.override(model_settings={"finquery_adapter": "query"}):
        async with local_client(stack) as client:
            conversation_id = await new_conversation(client, await default_profile_id(client))
            seen = await turn(client, conversation_id, "groceries?")

            metadata = [c for c in seen if c["type"] == "message-metadata"]
            notes = metadata[-1]["messageMetadata"]["audit_notes"]
            assert [n["kind"] for n in notes] == ["adapter-fallback"]
            assert "base weights" in notes[0]["text"]

            detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
            assert detail["messages"][-1]["metadata"]["audit_notes"] == notes


async def test_models_endpoint_also_answers_on_openrouter() -> None:
    app = create_app(make_settings(openrouter_api_key="test-key"), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = (await client.get("/api/models")).json()
            assert body["provider"] == "openrouter"
            assert [m["name"] for m in body["models"]] == ["google/gemma-4-26b-a4b-it", "google/gemma-4-31b-it"]
            assert body["adapters"] == []
            assert (await client.post("/api/models/download")).status_code == 409


async def test_an_image_reaches_the_model_as_a_content_part(tmp_path: Path) -> None:
    png = base64.b64encode(solid_png((10, 200, 10), size=8)).decode()
    slots = {"fast": FakeSlot("tiny-fast", ("Green.",)), "quality": FakeSlot("tiny-quality")}
    async with local_client(local_stack(tmp_path, slots)) as client:
        conversation_id = await new_conversation(client, await default_profile_id(client))
        response = await client.post(
            f"/api/conversations/{conversation_id}/chat",
            json={
                "id": conversation_id,
                "trigger": "submit-message",
                "messages": [
                    {
                        "id": "u1",
                        "role": "user",
                        "parts": [
                            {"type": "text", "text": "What colour is this?"},
                            {"type": "file", "mediaType": "image/png", "url": f"data:image/png;base64,{png}"},
                        ],
                    }
                ],
            },
        )
        assert response.status_code == 200
        content = slots["fast"].requests[0]["messages"][-1]["content"]
        assert [part["type"] for part in content] == ["text", "image_url"]
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_a_schema_constrained_request_forces_a_single_tool(tmp_path: Path) -> None:
    """The sub-agent shape from tickets 05 and 06, driven directly.

    Sub-agents do not exist yet, so no HTTP route produces this request. What matters is the
    contract they will rely on: one forced tool, thinking off, no response format beside it.
    """

    class Sql(BaseModel):
        sql: str

    slot = FakeSlot("tiny-fast")

    def stream(**kwargs: Any) -> Iterator[dict[str, Any]]:
        slot.requests.append(kwargs)
        name = kwargs["tool_choice"]["function"]["name"]
        call = {
            "index": 0,
            "id": "call_0",
            "function": {"name": name, "arguments": '{"sql": "SELECT sum(amount) FROM tx"}'},
        }
        yield {"choices": [{"index": 0, "delta": {"tool_calls": [call]}, "finish_reason": None}]}

    slot.stream = stream  # type: ignore[method-assign]
    stack = local_stack(tmp_path, {"fast": slot, "quality": FakeSlot("tiny-quality")})

    result = await Agent(stack.resolve("fast"), output_type=Sql).run("How much did I spend?")

    assert result.output == Sql(sql="SELECT sum(amount) FROM tx")
    request = slot.requests[0]
    assert len(request["tools"]) == 1
    assert request["tool_choice"] == {"type": "function", "function": {"name": request["tools"][0]["function"]["name"]}}
    assert request["enable_thinking"] is False
    assert "response_format" not in request
