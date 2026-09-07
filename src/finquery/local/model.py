"""A Pydantic AI model over llama-cpp-python, for any local model.

The chat template inside the GGUF does the prompt building, so this module's job is the two
translations around it: Pydantic AI messages to the OpenAI-shaped dicts the template expects,
and the model's single text stream back to thinking parts, text parts and tool calls. Which
template that is decides the details, and those live in `finquery.local.gemma` (the three Gemma 4
sizes the catalog offers) and `finquery.local.qwen` (Qwen3.5 and Qwen3.8, benchmark candidates
only since ticket 67), picked per model through `WIRE_FORMATS`.

Two rules from the spec hold for both. Thinking is switched on through the chat template
rather than a request flag, and schema-constrained output is never combined with free tool
calling: a request that needs a schema forces a single tool, which makes llama.cpp build a
GBNF grammar from that tool's parameters.
"""

import json
import os
from collections.abc import AsyncGenerator, AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic_ai import RunContext
# The same helper `FunctionModel` uses to resolve instructions plus instruction parts.
from pydantic_ai._instrumentation import get_instructions
from pydantic_ai.exceptions import UserError
from pydantic_ai.messages import (
    BinaryContent,
    FileUrl,
    ImageUrl,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponseStreamEvent,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters, StreamedResponse
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.profiles.google import GoogleOpenAPISchemaTransformer
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import RequestUsage

from finquery.local import gemma, qwen
from finquery.local.catalog import ModelSpec
from finquery.local.runtime import LocalStack, Slot, adapter_note
from finquery.local.wire import Event, Sampling, WireFormat, WireName
from finquery.providers import ModelRole

SYSTEM = "llama-cpp"

MAX_TOKENS = 4096

WIRE_FORMATS: dict[WireName, WireFormat] = {
    "gemma": WireFormat(
        splitter=gemma.StreamSplitter,
        stop=gemma.STOP,
        # The Gemma 4 model card's sampling settings; min_p and the two penalties are what
        # llama-cpp-python's chat handler defaults to, spelled out so both formats say it.
        sampling=Sampling(temperature=1.0, top_p=0.95, top_k=64, min_p=0.05, presence_penalty=0.0, repeat_penalty=1.1),
        reasoning_key="reasoning",
        # This template opens the thought channel only after a tool response.
        thought_open_at_start=False,
        # Keep the thinking that led to a tool call, drop the rest of the history's.
        template_kwargs={"preserve_thinking": True},
    ),
    "qwen": WireFormat(
        splitter=qwen.StreamSplitter,
        stop=qwen.STOP,
        # The Qwen3.5 model card's thinking-mode settings for general tasks; Qwen3.8 shares
        # the template and the architecture (`model_type` qwen3_5).
        sampling=Sampling(temperature=1.0, top_p=0.95, top_k=20, min_p=0.0, presence_penalty=1.5, repeat_penalty=1.0),
        reasoning_key="reasoning_content",
        # With thinking on, the generation prompt itself ends on `<think>`.
        thought_open_at_start=True,
        # This template drops stale thinking by message index, so it needs no flag for it.
    ),
}

LOCAL_PROFILE = ModelProfile(
    supports_tools=True,
    supports_thinking=True,
    # Everything schema-shaped goes through a forced single tool, never a response format.
    supports_json_schema_output=False,
    supports_json_object_output=False,
    default_structured_output_mode="tool",
    json_schema_transformer=GoogleOpenAPISchemaTransformer,
)


class LocalModelSettings(ModelSettings, total=False):
    """Extra settings the local provider understands."""

    finquery_adapter: str
    """Set by a sub-agent to name the LoRA adapter its run should use (see `LocalStack`)."""


@dataclass(init=False)
class LlamaCppModel(Model):
    """One local model, speaking that model's wire format.

    `_hold` asks for this model by spec, and `LocalStack.holding` drains, unloads and loads
    under the one lock before the run starts, so a request on a model that is not the loaded
    one pays for the swap and nothing runs mid-swap.
    """

    _spec: ModelSpec
    _stack: LocalStack
    _wire: WireFormat

    def __init__(self, spec: ModelSpec, stack: LocalStack) -> None:
        super().__init__(profile=LOCAL_PROFILE)
        self._spec = spec
        self._stack = stack
        self._wire = WIRE_FORMATS[spec.wire]

    @property
    def model_name(self) -> str:
        return self._spec.name

    @property
    def system(self) -> str:
        return SYSTEM

    @property
    def provider(self) -> None:
        return None

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        async with self.request_stream(messages, model_settings, model_request_parameters) as stream:
            async for _ in stream:
                pass
            return stream.get()

    @asynccontextmanager
    async def request_stream(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
        run_context: RunContext[Any] | None = None,
    ) -> AsyncGenerator[StreamedResponse]:
        model_settings, model_request_parameters = self.prepare_request(model_settings, model_request_parameters)
        adapter = (model_settings or {}).get("finquery_adapter")
        async with self._hold(adapter) as loaded:
            tools, forced = _render_tools(model_request_parameters)
            # A grammar-constrained answer has no room for a thought channel, so thinking is on
            # for every free-form request and off exactly when a single tool is forced.
            thinking = forced is None
            sampling = self._wire.sampling
            request: dict[str, Any] = {
                "messages": _render_messages(messages, model_request_parameters, self._wire.reasoning_key),
                "temperature": (model_settings or {}).get("temperature", sampling.temperature),
                "top_p": (model_settings or {}).get("top_p", sampling.top_p),
                "top_k": sampling.top_k,
                "min_p": sampling.min_p,
                "presence_penalty": sampling.presence_penalty,
                "repeat_penalty": sampling.repeat_penalty,
                "max_tokens": (model_settings or {}).get("max_tokens", MAX_TOKENS),
                "stop": self._wire.stop,
                "enable_thinking": thinking,
                **self._wire.template_kwargs,
            }
            if tools:
                request["tools"] = tools
                request["tool_choice"] = forced if forced is not None else "auto"
            response = LlamaCppStreamedResponse(
                model_request_parameters=model_request_parameters,
                _model_name=self.model_name,
                _stack=self._stack,
                _seat=self._spec.seat,
                _slot=loaded,
                _wire=self._wire,
                _request=request,
                _forced_tool=forced is not None,
                _in_thought=thinking and (self._wire.thought_open_at_start or _prompt_opens_thought(messages)),
                _run_context=run_context,
            )
            if (note := adapter_note()) is not None:
                response.metadata = {"audit_notes": [{"kind": "adapter-fallback", "text": note}]}
            try:
                yield response
            finally:
                # Still inside `_hold`, so the slot stays locked until nothing is in llama.cpp.
                response.stop()
                self._stack.drain(self._spec.seat)

    @asynccontextmanager
    async def _hold(self, adapter: str | None) -> AsyncIterator[Slot]:
        """Hold this model for the request, with the sub-agent's adapter attached if asked.

        An adapter is trained against the fast seat's base weights (Gemma 4 E4B, ADR 0006), so
        it is only ever attached there. The query and chart sub-agents ask for theirs on every
        run (`finquery.providers.with_adapter`); on E4B they get it, and on the 12B or the 26B
        they run on that model's own weights, which is the rule of ticket 67 and not a fallback,
        so no audit note is written for it. The one fallback that is noted is an adapter file
        missing on E4B (`AdapterRegistry.attached_to`).
        """
        # The benchmark scores adapters trained for the chat seat's base too; it says so with
        # FINQUERY_ADAPTERS_ANY_SEAT=1 and points FINQUERY_MODELS_DIR at that base's own adapters
        # directory (training/cluster/bench.sbatch). The app never sets it: its adapters directory
        # holds E4B adapters, which cannot load onto the 12B.
        any_seat = os.environ.get("FINQUERY_ADAPTERS_ANY_SEAT") == "1"
        if adapter is not None and (self._spec.seat == "fast" or any_seat):
            async with self._stack.with_adapter(adapter, self._spec) as loaded:  # type: ignore[arg-type]
                yield loaded
            return
        async with self._stack.holding(self._spec.seat, self._spec) as loaded:
            yield loaded



def normalize_json_arguments(text: str) -> str:
    """Tool-call arguments as strict JSON, whatever the model put inside the strings.

    llama.cpp turns Gemma 4's tool-call DSL into JSON without escaping control characters, so a
    statement written over several lines arrives with raw line breaks inside the `sql` string,
    which strict JSON rejects and the output validation then counts as a failed attempt. The
    fine-tuned 12B writes its SQL that way on almost every call (probe of 2026-09-07). Python's
    lenient parser reads it; the re-dump is what Pydantic AI validates.
    """
    try:
        return json.dumps(json.loads(text, strict=False), ensure_ascii=False)
    except ValueError:
        return text

def _prompt_opens_thought(messages: Sequence[ModelMessage]) -> bool:
    """Whether a Gemma 4 prompt leaves the thought channel already open.

    With thinking on it does exactly when the prompt ends on a tool response, so the model
    starts writing reasoning with no opening marker for the splitter to see. The Qwen3.5
    template opens it on every turn instead, which is `thought_open_at_start`.
    """
    last = messages[-1] if messages else None
    if not isinstance(last, ModelRequest):
        return False
    return any(isinstance(part, ToolReturnPart | RetryPromptPart) for part in last.parts)


def _tool_dict(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.parameters_json_schema,
        },
    }


def _render_tools(params: ModelRequestParameters) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """The tools for one request, plus a forced choice when the answer must match a schema.

    A single tool and no free-text answer is the sub-agent shape: forcing it makes llama.cpp
    build a GBNF grammar from the tool's parameters, which is the only schema constraint this
    provider uses. Anything else is free tool calling.
    """
    tools = [_tool_dict(tool) for tool in [*params.declared_function_tools, *params.output_tools]]
    if len(tools) == 1 and not params.allow_text_output:
        return tools, {"type": "function", "function": {"name": tools[0]["function"]["name"]}}
    return tools, None


def _render_messages(
    messages: Sequence[ModelMessage], params: ModelRequestParameters, reasoning_key: str
) -> list[dict[str, Any]]:
    """Pydantic AI messages as the OpenAI-shaped dicts a chat template expects.

    Both templates only treat `messages[0]` as the system turn, so instructions and every
    system prompt are folded into one leading message. They differ over what the assistant's
    past thinking is called, which is `reasoning_key`.
    """
    system = [text for text in [get_instructions(messages, params)] if text]
    rendered: list[dict[str, Any]] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, SystemPromptPart):
                    system.append(part.content)
                elif isinstance(part, UserPromptPart):
                    rendered.append({"role": "user", "content": _user_content(part)})
                elif isinstance(part, ToolReturnPart):
                    rendered.append(
                        {
                            "role": "tool",
                            "tool_call_id": part.tool_call_id,
                            "name": part.tool_name,
                            "content": part.model_response_str(),
                        }
                    )
                elif isinstance(part, RetryPromptPart):
                    if part.tool_name is None:
                        rendered.append({"role": "user", "content": part.model_response()})
                    else:
                        rendered.append(
                            {
                                "role": "tool",
                                "tool_call_id": part.tool_call_id,
                                "name": part.tool_name,
                                "content": part.model_response(),
                            }
                        )
        else:
            rendered.append(_assistant_message(message, reasoning_key))
    if system:
        rendered.insert(0, {"role": "system", "content": "\n\n".join(system)})
    return rendered


def _assistant_message(message: ModelResponse, reasoning_key: str) -> dict[str, Any]:
    text = "".join(part.content for part in message.parts if isinstance(part, TextPart))
    thinking = "\n".join(part.content for part in message.parts if isinstance(part, ThinkingPart) and part.content)
    calls = [
        {
            "id": part.tool_call_id,
            "type": "function",
            # A mapping is what the template wants; a JSON string would be re-serialized by hand.
            "function": {"name": part.tool_name, "arguments": part.args_as_dict()},
        }
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    out: dict[str, Any] = {"role": "assistant", "content": text}
    if thinking:
        # The template's own gate decides whether this is rendered or dropped as stale.
        out[reasoning_key] = thinking
    if calls:
        out["tool_calls"] = calls
    return out


def _user_content(part: UserPromptPart) -> str | list[dict[str, Any]]:
    if isinstance(part.content, str):
        return part.content
    items: list[dict[str, Any]] = []
    for item in part.content:
        if isinstance(item, str):
            items.append({"type": "text", "text": item})
        elif isinstance(item, BinaryContent) and item.is_image:
            items.append({"type": "image_url", "image_url": {"url": item.data_uri}})
        elif isinstance(item, ImageUrl):
            items.append({"type": "image_url", "image_url": {"url": item.url}})
        elif isinstance(item, FileUrl | BinaryContent):
            raise UserError(f"The local provider supports text and images only, not {item.media_type}.")
        else:
            raise UserError(f"The local provider cannot send {type(item).__name__} content.")
    return items


@dataclass
class LlamaCppStreamedResponse(StreamedResponse):
    """One generation: pulled a token at a time so Stop can land between tokens."""

    _model_name: str
    _stack: LocalStack
    _seat: ModelRole
    _slot: Slot
    _wire: WireFormat
    _request: dict[str, Any]
    _forced_tool: bool
    _in_thought: bool
    _run_context: RunContext[Any] | None
    _timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    _stopped: bool = False
    _chunks: Iterator[dict[str, Any]] | None = None
    _calls: dict[int, dict[str, Any]] = field(default_factory=dict)

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str | None:
        return SYSTEM

    @property
    def provider_url(self) -> str | None:
        return None

    @property
    def timestamp(self) -> datetime:
        return self._timestamp

    def stop(self) -> None:
        """Ask the token loop to end at the next token.

        The llama.cpp generator is dropped rather than closed: closing it from another thread
        while its `next()` is still running raises `generator already executing`. Whatever
        `next()` is in flight finishes on the slot's thread, which is what `drain` waits for.
        """
        self._stopped = True
        self._chunks = None

    async def close_stream(self) -> None:
        """`StreamedResponse.cancel()` calls this; the teardown in `request_stream` drains."""
        self.stop()

    def _cancel_requested(self) -> bool:
        """Whether the run's cancellation token has been cancelled (the Stop endpoint's)."""
        cancellation = getattr(self._run_context, "_cancellation", None) if self._run_context else None
        return bool(cancellation is not None and cancellation.cancel_requested)

    async def _get_event_iterator(self) -> AsyncIterator[ModelResponseStreamEvent]:
        run = self._stack.run
        self._chunks = await run(self._seat, lambda: self._slot.stream(**self._request))
        splitter = self._wire.splitter(in_thought=self._in_thought)
        generated = 0
        prompt_tokens = 0
        cancelled = False
        while (chunks := self._chunks) is not None:
            # Checked between tokens: this is what the Stop endpoint's cancellation token reaches.
            if self._stopped or self._cancel_requested():
                cancelled = True
                break
            chunk = await run(self._seat, lambda: next(chunks, None))
            if chunk is None:
                break
            delta = chunk["choices"][0].get("delta") or {}
            content = delta.get("content")
            calls = delta.get("tool_calls")
            if content is None and not calls:
                continue
            if generated == 0:
                # After the first sampled token the context holds the prompt plus that token.
                prompt_tokens = max(self._slot.context_tokens() - 1, 0)
            generated += 1
            self._usage = RequestUsage(input_tokens=prompt_tokens, output_tokens=generated)
            if self._forced_tool:
                self._buffer_tool_calls(calls or [])
            else:
                for event in self._events(splitter.feed(content or "")):
                    yield event
        for event in self._events(splitter.finish()):
            yield event
        if self._forced_tool:
            for event in self._flush_tool_calls():
                yield event
        self._usage = RequestUsage(input_tokens=prompt_tokens, output_tokens=generated)
        if not cancelled:
            # A cancelled turn is left without a reason; the response state already says
            # interrupted, and none of the normalized reasons means "the user pressed Stop".
            called = any(part.part_kind == "tool-call" for part in self._parts_manager.get_parts())
            self.finish_reason = "tool_call" if called else "stop"

    def _events(self, parsed: Sequence[Event]) -> Iterator[ModelResponseStreamEvent]:
        for kind, payload in parsed:
            if kind == "thinking":
                yield from self._parts_manager.handle_thinking_delta(vendor_part_id=None, content=payload)
            elif kind == "text":
                yield from self._parts_manager.handle_text_delta(vendor_part_id=None, content=payload)
            else:
                yield self._parts_manager.handle_tool_call_part(
                    vendor_part_id=None, tool_name=payload.name, args=payload.args
                )

    def _buffer_tool_calls(self, calls: Sequence[dict[str, Any]]) -> None:
        """The forced-tool path: llama.cpp emits OpenAI tool-call deltas, gathered here.

        It repeats the whole tool name on every chunk rather than sending it once
        (`_convert_completion_to_chat_function`), and it leaves raw control characters inside
        the JSON strings. So the fragments are collected per call and handed over once, at the
        end of the stream, with the name from the first chunk and the arguments normalized
        (`normalize_json_arguments`). Nobody watches a sub-agent's arguments stream live.
        """
        for call in calls:
            index = call.get("index", 0)
            entry = self._calls.setdefault(index, {"name": None, "id": None, "args": []})
            function = call.get("function") or {}
            if entry["name"] is None and function.get("name"):
                entry["name"] = function["name"]
            if entry["id"] is None and call.get("id"):
                entry["id"] = call["id"]
            if function.get("arguments"):
                entry["args"].append(function["arguments"])

    def _flush_tool_calls(self) -> Iterator[ModelResponseStreamEvent]:
        for index, entry in sorted(self._calls.items()):
            event = self._parts_manager.handle_tool_call_delta(
                vendor_part_id=index,
                tool_name=entry["name"],
                args=normalize_json_arguments("".join(entry["args"])),
                tool_call_id=entry["id"],
            )
            if event is not None:
                yield event
        self._calls.clear()
