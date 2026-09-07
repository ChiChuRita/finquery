"""The local provider over the same HTTP seam, with no real model loaded.

Two stubs are what `create_app(local=...)` exists for: a fetch function instead of a download,
and a `Slot` returning canned llama.cpp chat chunks instead of a loaded GGUF. What is asserted
is what a client sees: the models endpoint, the SSE stream of a turn, and the turn a later GET
returns.
"""

import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent

from finquery.agent import chat_agent
from finquery.app import create_app
from finquery.local.adapters import AdapterRegistry
from finquery.local.catalog import FileSpec, ModelSpec, adapter_path
from finquery.local.check import solid_png
from finquery.local.downloads import DownloadManager, Report
from finquery.local.runtime import LocalStack
from finquery.providers import with_adapter

from .conftest import NoWeb, chat_body, default_profile_id, make_settings, new_conversation, parse_sse


def spec(key: str, seat: str, name: str, weights_size: int, wire: str) -> ModelSpec:
    return ModelSpec(
        key=key,
        seat=seat,  # type: ignore[arg-type]
        name=name,
        label=name,
        wire=wire,  # type: ignore[arg-type]
        weights=FileSpec(kind="weights", repo_id="acme/tiny", filename=f"{name}.gguf", size=weights_size, sha256="0" * 64),
        projector=FileSpec(kind="projector", repo_id="acme/tiny", filename="mmproj.gguf", size=4, sha256="1" * 64),
    )


FAST, GEMMA = "local:gemma-4-e4b", "local:gemma-4-26b"

#: Stand-ins for the two real local models, under the keys the catalog offers them under:
#: E4B (the fast slot and the smaller chat entry) and the 26B A4B in the chat seat, which is
#: what a new conversation starts on since ticket 75. One of the two is loaded at a time.
TINY_MODELS = {
    FAST: spec(FAST, "fast", "tiny-fast", 8, "gemma"),
    GEMMA: spec(GEMMA, "chat", "tiny-gemma", 24, "gemma"),
}


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
        self.closed = 0

    def stream(self, **kwargs: Any) -> Iterator[dict[str, Any]]:
        self.requests.append(kwargs)
        return chunks(*(self._turns.pop(0) if self._turns else ("nothing scripted",)))

    def context_tokens(self) -> int:
        return 12

    def reset(self) -> None:
        self.resets += 1

    def close(self) -> None:
        self.closed += 1


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


NAMED = {"fast": FAST, "gemma": GEMMA}


def _slots(**named: FakeSlot) -> dict[str, FakeSlot]:
    """A stand-in slot per local model, overridden by keyword: `fast`, `gemma`."""
    default = {FAST: FakeSlot("tiny-fast"), GEMMA: FakeSlot("tiny-gemma")}
    return {**default, **{NAMED[name]: slot for name, slot in named.items()}}


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
        models=TINY_MODELS,
        adapters=AdapterRegistry(settings.models_dir, api=FakeAdapterApi()),
        load=lambda model, *_: slots[model.key],
    )


@asynccontextmanager
async def local_client(stack: LocalStack) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings(provider="local"), local=stack, web_client=NoWeb(), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def turn(client: httpx.AsyncClient, conversation_id: str, text: str) -> list[dict[str, Any]]:
    response = await client.post(f"/api/conversations/{conversation_id}/chat", json=chat_body(text, conversation_id))
    assert response.status_code == 200
    return parse_sse(response.text)


def _entries(response: httpx.Response) -> list[dict[str, Any]]:
    """The local chat entries of a `GET /api/models` body, in catalog order."""
    return [entry for entry in response.json()["entries"] if entry["provider"] == "local"]


async def test_the_two_local_entries_share_one_loaded_model(tmp_path: Path) -> None:
    """A turn on the other local entry swaps it in, and nothing else stays loaded."""
    slots = _slots(
        fast=FakeSlot("tiny-fast", ("Hello from E4B.",)),
        gemma=FakeSlot("tiny-gemma", ("Hello from the 26B.",)),
    )
    stack = local_stack(tmp_path, slots)
    async with local_client(stack) as client:
        body = (await client.get("/api/models")).json()
        assert body["provider"] == "local"
        assert body["default_key"] == GEMMA
        local_entries = [entry for entry in body["entries"] if entry["provider"] == "local"]
        assert [entry["key"] for entry in local_entries] == [FAST, GEMMA]
        assert all(entry["ready"] and entry["available"] and not entry["loaded"] for entry in local_entries)
        assert all(f["state"] == "ready" for entry in local_entries for f in entry["files"])
        assert [entry["key"] for entry in body["fast_slots"]] == [FAST, "openrouter:fast"]
        assert [(a["name"], a["present"]) for a in body["adapters"]] == [("query", False), ("chart", False)]

        profile_id = await default_profile_id(client)
        await turn(client, await new_conversation(client, profile_id, FAST), "hi")
        assert [entry["loaded"] for entry in _entries(await client.get("/api/models"))] == [True, False]
        e4b_requests = len(slots[FAST].requests)

        await turn(client, await new_conversation(client, profile_id, GEMMA), "hi")
        after = _entries(await client.get("/api/models"))
        # One model in memory: the entry that answered last is the one that is loaded.
        assert [entry["loaded"] for entry in after] == [False, True]
        assert [entry["n_ctx"] for entry in after] == [32768, 32768]
        # The one that gave way was unloaded, and the second turn never asked for the fast
        # slot: with every sub-agent role on `chat`, its sub-agents ran on the 26B too.
        assert (slots[FAST].closed, slots[GEMMA].closed) == (1, 0)
        assert stack.loaded_spec("fast") is None
        assert len(slots[FAST].requests) == e4b_requests

        # Each turn is its answer plus the two post-turn steps (follow-up suggestions and
        # memory distillation), all of them on the entry the conversation runs on rather than
        # on the fast slot, which is what the default `chat` on every sub-agent role means.
        assert e4b_requests >= 3
        assert len(slots[GEMMA].requests) >= 3


async def test_a_chat_on_e4b_holds_the_fast_seat_and_nothing_is_loaded_twice(tmp_path: Path) -> None:
    """E4B is a chat entry and the fast slot at once (ticket 67): one seat, one load."""
    slots = _slots(fast=FakeSlot("tiny-fast", ("Hello from E4B.",)))
    stack = local_stack(tmp_path, slots)
    async with local_client(stack) as client:
        profile_id = await default_profile_id(client)
        await turn(client, await new_conversation(client, profile_id, FAST), "hi")

        assert stack.loaded_spec("fast") is TINY_MODELS[FAST]
        assert stack.loaded_spec("chat") is None
        assert [entry["loaded"] for entry in _entries(await client.get("/api/models"))] == [True, False]
        assert len(slots[FAST].requests) >= 3


async def test_thinking_is_split_out_of_the_text_stream(tmp_path: Path) -> None:
    reply = ("<|channel>", "thought\n", "They asked ", "for a number. ", "<channel|>", "I cannot ", "compute that yet.")
    slots = _slots(gemma=FakeSlot("tiny-gemma", reply))
    async with local_client(local_stack(tmp_path, slots)) as client:
        conversation_id = await new_conversation(client, await default_profile_id(client), GEMMA)
        seen = await turn(client, conversation_id, "How much in May?")

        kinds = [c["type"] for c in seen]
        assert kinds.index("reasoning-end") < kinds.index("text-start")
        assert "".join(str(c["delta"]) for c in seen if c["type"] == "reasoning-delta") == "They asked for a number. "
        assert "".join(str(c["delta"]) for c in seen if c["type"] == "text-delta") == "I cannot compute that yet."

        # Thinking is switched on through the chat template, not through a request flag.
        assert slots[GEMMA].requests[0]["enable_thinking"] is True
        assert slots[GEMMA].requests[0]["top_k"] == 64

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
    slots = _slots(gemma=FakeSlot("tiny-gemma", calling, answering))
    with chat_agent.override(tools=[query]):
        async with local_client(local_stack(tmp_path, slots)) as client:
            profile_id = await default_profile_id(client)
            seen = await turn(client, await new_conversation(client, profile_id, GEMMA), "groceries in May?")

            available = [c for c in seen if c["type"] == "tool-input-available"]
            assert [c["toolName"] for c in available] == ["query"]
            assert available[0]["input"] == {"question": "groceries in May", "limit": 20}
            output = [c for c in seen if c["type"] == "tool-output-available"]
            assert output[0]["output"] == "groceries in May -> 120.00 EUR (limit 20)"
            assert "".join(str(c["delta"]) for c in seen if c["type"] == "text-delta") == "You spent 120 EUR."

            # Free tool calling: the tools are declared, nothing is forced, no response format.
            # `ask_user` rides along because the chat agent always carries the deferred toolset.
            first = slots[GEMMA].requests[0]
            assert [t["function"]["name"] for t in first["tools"]] == ["query", "ask_user"]
            assert first["tool_choice"] == "auto"
            assert "response_format" not in first
            # The tool result goes back as a tool message the chat template renders as a response.
            assert slots[GEMMA].requests[1]["messages"][-1]["role"] == "tool"


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

    slots = _slots(gemma=SlowSlot("tiny-gemma"))
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

    models = {GEMMA: TINY_MODELS[GEMMA]}
    settings = make_settings(provider="local", models_dir=tmp_path / "models")
    stack = LocalStack(
        settings,
        models=models,
        downloads=DownloadManager(settings.models_dir, models=models, fetch=fetch),
        load=lambda *_: FakeSlot("tiny-gemma"),
    )
    async with local_client(stack) as client:
        before = next(e for e in _entries(await client.get("/api/models")) if e["key"] == GEMMA)
        assert before["ready"] is False
        # A model whose files are missing is listed, unavailable, with what to do about it.
        assert before["available"] is False
        assert "not downloaded yet" in before["reason"]
        assert [f["state"] for f in before["files"]] == ["missing", "missing"]

        assert (await client.post("/api/models/download")).json()["downloading"] is True
        await asyncio.wait_for(halfway.wait(), timeout=5)

        during = next(e for e in _entries(await client.get("/api/models")) if e["key"] == GEMMA)["files"][0]
        assert during["state"] == "downloading"
        assert during["downloaded"] == during["size"] // 2

        release.set()
        body = await _wait_for_downloads(client)
        entry = next(e for e in body["entries"] if e["key"] == GEMMA)
        assert entry["ready"] is True and entry["available"] is True
        assert [f["state"] for f in entry["files"]] == ["ready", "ready"]


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
        key=FAST,
        seat="fast",
        name="tiny",
        label="Tiny",
        wire="gemma",
        weights=parked_spec(weights_payload, "wanted.gguf", "weights"),
        projector=parked_spec(projector_payload, "mmproj.gguf", "projector"),
    )

    def never(*_args: Any) -> None:
        raise AssertionError("a parked copy whose hash matches must not be downloaded again")

    manager = DownloadManager(tmp_path / "models", models={FAST: model}, parked_dirs=[parked], fetch=never)
    manager.ensure(FAST, timeout=10)
    assert manager.path(model, model.weights).read_bytes() == weights_payload
    assert manager.path(model, model.projector).read_bytes() == projector_payload
    assert [(row.state, row.source) for row in manager.progress()] == [
        ("ready", f"a parked copy at {parked / 'someone-elses-name.gguf'}"),
        ("ready", f"a parked copy at {parked / 'mm.gguf'}"),
    ]


async def test_adapter_falls_back_to_base_weights_with_a_note(tmp_path: Path) -> None:
    slots = _slots()
    stack = local_stack(tmp_path, slots)
    calls: list[str] = stack.adapters._api.calls  # type: ignore[attr-defined] # noqa: SLF001

    # No file for the query adapter: the run goes ahead on the base weights, loudly.
    with stack.adapters.attached_to("query", slots[FAST]) as note:  # type: ignore[arg-type]
        assert note is not None
        assert "base weights" in note.text
    assert calls == []

    # With a file there, the low-level attach and detach both happen and the slot is reset.
    path = adapter_path(stack.downloads.models_dir, "chart")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"lora")
    with stack.adapters.attached_to("chart", slots[FAST]) as note:  # type: ignore[arg-type]
        assert note is None
        assert stack.adapters.attached == "chart"
    assert calls == ["init:chart.gguf", "attach", "detach", "free"]
    assert stack.adapters.attached is None
    assert slots[FAST].resets == 1

    async with local_client(stack) as client:
        assert [a["present"] for a in (await client.get("/api/models")).json()["adapters"]] == [False, True]


async def test_the_fallback_note_reaches_the_client_and_the_stored_turn(tmp_path: Path) -> None:
    # An adapter attaches on the fast seat, so the chat runs on E4B here and asks for the query
    # adapter by naming it in the model settings; there is no file, so the note is written.
    slots = _slots(fast=FakeSlot("tiny-fast", ("120 EUR.",)))
    stack = local_stack(tmp_path, slots)
    with chat_agent.override(model_settings={"finquery_adapter": "query"}):
        async with local_client(stack) as client:
            conversation_id = await new_conversation(client, await default_profile_id(client), FAST)
            seen = await turn(client, conversation_id, "groceries?")

            metadata = [c for c in seen if c["type"] == "message-metadata"]
            notes = metadata[-1]["messageMetadata"]["audit_notes"]
            assert [n["kind"] for n in notes] == ["adapter-fallback"]
            assert "base weights" in notes[0]["text"]

            detail = (await client.get(f"/api/conversations/{conversation_id}")).json()
            assert detail["messages"][-1]["metadata"]["audit_notes"] == notes


async def test_an_adapter_attaches_on_e4b_and_a_bigger_model_runs_its_own_weights_without_a_note(
    tmp_path: Path,
) -> None:
    """The rule of ticket 67, at the model: the sub-agent asks every time, the seat decides.

    On E4B the query adapter file is attached and detached around the run. On the 26B the same
    request runs on the base weights with no adapter call and no audit note, because that is
    what choosing a bigger model means, not a fallback to report.
    """
    slots = _slots(fast=FakeSlot("tiny-fast", ("42",)), gemma=FakeSlot("tiny-gemma", ("42",)))
    stack = local_stack(tmp_path, slots)
    calls: list[str] = stack.adapters._api.calls  # type: ignore[attr-defined] # noqa: SLF001
    path = adapter_path(stack.downloads.models_dir, "query")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"lora")
    settings = with_adapter(None, "query")

    on_e4b = await Agent(stack.resolve(TINY_MODELS[FAST])).run("How much?", model_settings=settings)
    assert on_e4b.output == "42"
    assert calls == ["init:query.gguf", "attach", "detach", "free"]
    assert on_e4b.all_messages()[-1].metadata is None  # type: ignore[union-attr]

    calls.clear()
    on_26b = await Agent(stack.resolve(TINY_MODELS[GEMMA])).run("How much?", model_settings=settings)
    assert on_26b.output == "42"
    assert calls == []
    assert on_26b.all_messages()[-1].metadata is None  # type: ignore[union-attr]
    assert len(slots[GEMMA].requests) == 1


async def test_models_endpoint_lists_the_whole_catalog_on_openrouter(tmp_path: Path) -> None:
    """Both providers are live at once, so an OpenRouter run still lists the local entries.

    Nothing local is downloaded here, so they come back unavailable with the reason, which is
    what the picker disables them with.
    """
    settings = make_settings(openrouter_api_key="test-key", models_dir=tmp_path / "empty")
    app = create_app(settings, web_client=NoWeb(), serve_frontend=False)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = (await client.get("/api/models")).json()
            assert body["provider"] == "openrouter"
            assert body["default_key"] == "openrouter:google/gemma-4-26b-a4b-it"
            assert [(entry["key"], entry["label"]) for entry in body["entries"]] == [
                (FAST, "Gemma 4 E4B (local)"),
                (GEMMA, "Gemma 4 26B (local)"),
                ("openrouter:google/gemma-4-26b-a4b-it", "Gemma 4 26B (cloud)"),
            ]
            assert [entry["available"] for entry in body["entries"]] == [False, False, True]
            assert all("not downloaded" in entry["reason"] for entry in body["entries"] if not entry["available"])
            # The local download endpoint answers on either provider now.
            assert (await client.post("/api/models/download")).status_code == 200


QWEN = "local:qwen3.8-27b"
TINY_QWEN = spec(QWEN, "chat", "tiny-qwen", 16, "qwen")


def qwen_stack(tmp_path: Path, slot: FakeSlot) -> LocalStack:
    """A stack over the catalog stand-ins plus the Qwen benchmark candidate, which the app never
    lists: the benchmark builds one like it (`finquery_bench.models.local_target`)."""
    settings = make_settings(provider="local", models_dir=tmp_path / "models")
    models = {**TINY_MODELS, QWEN: TINY_QWEN}
    for candidate in models.values():
        for file in candidate.files:
            path = candidate.path(settings.models_dir, file)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x" * file.size)
    slots = {**_slots(), QWEN: slot}
    return LocalStack(settings, models=models, load=lambda spec, *_: slots[spec.key])  # type: ignore[arg-type]


async def test_the_qwen_wire_format_splits_thinking_and_keeps_its_own_sampling(tmp_path: Path) -> None:
    """The Qwen format stays for the benchmark candidates (Qwen3.8 27B), driven directly.

    Qwen's generation prompt already contains `<think>`, so the model starts inside the thought
    channel and writes the closing tag itself, split over as many tokens as it likes.
    """
    slot = FakeSlot("tiny-qwen", ("Adding it ", "up. ", "</th", "ink>", "\n\nYou spent ", "120 EUR."))
    stack = qwen_stack(tmp_path, slot)

    result = await Agent(stack.resolve(TINY_QWEN)).run("How much in May?")

    assert result.output == "You spent 120 EUR."
    parts = result.all_messages()[-1].parts
    assert [p.part_kind for p in parts] == ["thinking", "text"]
    assert parts[0].content == "Adding it up. "  # type: ignore[union-attr]
    request = slot.requests[0]
    assert request["enable_thinking"] is True
    assert request["stop"] == ["<|im_end|>"]
    # Qwen's model card, not Gemma's, and no Gemma-only template argument rides along.
    assert (request["top_k"], request["min_p"]) == (20, 0.0)
    assert "preserve_thinking" not in request


async def test_the_qwen_tool_call_syntax_becomes_a_tool_call_and_its_result_goes_back(tmp_path: Path) -> None:
    def query(question: str, limit: int) -> str:
        """Answer a question from the transactions."""
        return f"{question} -> 120.00 EUR (limit {limit})"

    calling = (
        "I need the data.</think>\n\n",
        "<tool_call>\n<function=query>\n<parameter=question>\ngroceries",
        " in May\n</parameter>\n<parameter=limit>\n20\n</parameter>\n</function>\n</tool_call>",
    )
    answering = ("That is the total.</think>\n\nYou spent ", "120 EUR.")
    slot = FakeSlot("tiny-qwen", calling, answering)
    stack = qwen_stack(tmp_path, slot)

    result = await Agent(stack.resolve(TINY_QWEN), tools=[query]).run("groceries in May?")

    assert result.output == "You spent 120 EUR."
    calls = [p for m in result.all_messages() for p in m.parts if p.part_kind == "tool-call"]
    # A parameter arrives as text; the tool's own schema is what turns "20" into 20.
    assert [(c.tool_name, c.args_as_dict()) for c in calls] == [("query", {"question": "groceries in May", "limit": "20"})]
    returns = [p for m in result.all_messages() for p in m.parts if p.part_kind == "tool-return"]
    assert returns[0].content == "groceries in May -> 120.00 EUR (limit 20)"
    first = slot.requests[0]
    assert [t["function"]["name"] for t in first["tools"]] == ["query"]
    assert first["tool_choice"] == "auto"
    # The tool result goes back as a tool message the Qwen template renders as a
    # `<tool_response>` block, under an assistant message that keeps its reasoning.
    second = slot.requests[1]["messages"]
    assert second[-1]["role"] == "tool"
    assert second[-2]["reasoning_content"] == "I need the data."
    assert second[-2]["tool_calls"][0]["function"]["arguments"]["question"] == "groceries in May"


async def test_an_image_reaches_the_model_as_a_content_part(tmp_path: Path) -> None:
    """The vision path, driven directly.

    It used to be driven through the chat endpoint. Since ticket 08 an attachment is taken out
    of the message and stored instead, so no route sends bytes to the chat model any more: a
    photo goes to the extraction sub-agent of ticket 11, which is the shape asserted here.
    """
    slot = FakeSlot("tiny-fast", ("Green.",))
    stack = local_stack(tmp_path, _slots(fast=slot))

    result = await Agent(stack.resolve(TINY_MODELS[FAST])).run(
        ["What colour is this?", BinaryContent(data=solid_png((10, 200, 10), size=8), media_type="image/png")]
    )

    assert result.output == "Green."
    content = slot.requests[0]["messages"][-1]["content"]
    assert [part["type"] for part in content] == ["text", "image_url"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.parametrize("key", [FAST, GEMMA])
async def test_a_schema_constrained_request_forces_a_single_tool(tmp_path: Path, key: str) -> None:
    """The sub-agent shape from tickets 05 and 06, driven directly.

    A sub-agent runs on whichever entry its role resolves to, and the rule is the model's, not
    the seat's, so both seats are held to it: one forced tool, thinking off, no response format
    beside it. Forcing is what makes llama.cpp build the grammar and emit OpenAI tool-call
    deltas, which is the one path where the splitter is not involved.
    """

    class Sql(BaseModel):
        sql: str

    slot = FakeSlot(f"tiny-{key}")

    def stream(**kwargs: Any) -> Iterator[dict[str, Any]]:
        """llama.cpp's forced-tool stream: one chunk per token, each repeating the whole name."""
        slot.requests.append(kwargs)
        name = kwargs["tool_choice"]["function"]["name"]
        for piece in ('{"sql": "SELECT ', "sum(amount) ", 'FROM tx"}'):
            call = {"index": 0, "id": "call_0", "function": {"name": name, "arguments": piece}}
            yield {"choices": [{"index": 0, "delta": {"tool_calls": [call]}, "finish_reason": None}]}

    slot.stream = stream  # type: ignore[method-assign]
    stack = local_stack(tmp_path, {**_slots(), key: slot})

    result = await Agent(stack.resolve(TINY_MODELS[key]), output_type=Sql).run("How much did I spend?")

    assert result.output == Sql(sql="SELECT sum(amount) FROM tx")
    # The name is not a delta to concatenate, however many chunks repeat it.
    called = [part.tool_name for message in result.all_messages() for part in getattr(message, "parts", []) if part.part_kind == "tool-call"]
    assert called == ["final_result"]
    request = slot.requests[0]
    assert len(request["tools"]) == 1
    assert request["tool_choice"] == {"type": "function", "function": {"name": request["tools"][0]["function"]["name"]}}
    assert request["enable_thinking"] is False
    assert "response_format" not in request


async def test_every_sub_agent_request_carries_the_output_ceiling(tmp_path: Path) -> None:
    """A forced tool call is a grammar, and a grammar over a list has no end of its own.

    The chat turn keeps the model's default ceiling; every request a sub-agent makes behind
    it (here the follow-up suggestions and the memory distillation after the answer) carries
    `SUBAGENT_MAX_TOKENS`, which is what stops a page of extraction running until n_ctx. The
    roles run on the chat entry here, which is the default since ticket 61, so this is also
    where a sub-agent on a big model gets the same ceiling as one on the fast slot.
    """
    from finquery.local.model import MAX_TOKENS
    from finquery.providers import SUBAGENT_MAX_TOKENS

    slots = _slots(gemma=FakeSlot("tiny-gemma", ("Hello there.",)))
    async with local_client(local_stack(tmp_path, slots)) as client:
        await turn(client, await new_conversation(client, await default_profile_id(client), GEMMA), "Hi")

    chat, *others = slots[GEMMA].requests
    assert slots[FAST].requests == [], "no role asked for the fast slot"
    assert chat["tool_choice"] == "auto"
    assert chat["max_tokens"] == MAX_TOKENS
    assert others, "the post-turn sub-agents never ran"
    assert {request["max_tokens"] for request in others} == {SUBAGENT_MAX_TOKENS}
    # The one that is a forced tool (the distillation) is bounded too, with thinking off.
    forced = [request for request in others if isinstance(request.get("tool_choice"), dict)]
    assert forced and all(request["enable_thinking"] is False for request in forced)


def test_tool_call_arguments_with_raw_line_breaks_become_strict_json() -> None:
    """llama.cpp leaves raw newlines inside the JSON strings of a Gemma tool call (probe of
    2026-09-07); the fine-tuned 12B writes multi-line SQL, so every call failed validation."""
    from finquery.local.model import normalize_json_arguments

    raw = '{"reasoning": "period: 2025", "sql": "SELECT 1\nFROM transaction_view\nWHERE amount < 0"}'
    fixed = normalize_json_arguments(raw)
    import json

    assert json.loads(fixed)["sql"] == "SELECT 1\nFROM transaction_view\nWHERE amount < 0"
    assert normalize_json_arguments("not json at all") == "not json at all"
