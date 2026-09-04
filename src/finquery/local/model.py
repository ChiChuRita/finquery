"""A Pydantic AI model over llama-cpp-python and Gemma 4.

The Gemma 4 chat template does the prompt building, so this module's job is the two
translations around it: Pydantic AI messages to the OpenAI-shaped dicts the template expects,
and the model's single text stream back to thinking parts, text parts and tool calls.

Two rules from the spec hold here. Thinking is switched on through the chat template rather
than a request flag, and schema-constrained output is never combined with free tool calling:
a request that needs a schema forces a single tool, which makes llama.cpp build a GBNF grammar
from that tool's parameters.
"""

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

from finquery.local import gemma
from finquery.local.catalog import ModelSpec
from finquery.local.runtime import LocalStack, Slot, adapter_note
from finquery.providers import ModelSlot

SYSTEM = "llama-cpp"

#: The Gemma 4 model card's sampling settings.
TEMPERATURE = 1.0
TOP_P = 0.95
TOP_K = 64

MAX_TOKENS = 4096

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
    """One logical slot backed by a resident Gemma 4 GGUF."""

    _spec: ModelSpec
    _stack: LocalStack

    def __init__(self, spec: ModelSpec, stack: LocalStack) -> None:
        super().__init__(profile=LOCAL_PROFILE)
        self._spec = spec
        self._stack = stack

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
            request: dict[str, Any] = {
                "messages": _render_messages(messages, model_request_parameters),
                "temperature": (model_settings or {}).get("temperature", TEMPERATURE),
                "top_p": (model_settings or {}).get("top_p", TOP_P),
                "top_k": TOP_K,
                "max_tokens": (model_settings or {}).get("max_tokens", MAX_TOKENS),
                "stop": gemma.STOP,
                "enable_thinking": thinking,
                # Keep the thinking that led to a tool call, drop the rest of the history's.
                "preserve_thinking": True,
            }
            if tools:
                request["tools"] = tools
                request["tool_choice"] = forced if forced is not None else "auto"
            response = LlamaCppStreamedResponse(
                model_request_parameters=model_request_parameters,
                _model_name=self.model_name,
                _stack=self._stack,
                _slot_name=self._spec.slot,
                _slot=loaded,
                _request=request,
                _forced_tool=forced is not None,
                _in_thought=thinking and _prompt_opens_thought(messages),
                _run_context=run_context,
            )
            if (note := adapter_note()) is not None:
                response.metadata = {"audit_notes": [{"kind": "adapter-fallback", "text": note}]}
            try:
                yield response
            finally:
                # Still inside `_hold`, so the slot stays locked until nothing is in llama.cpp.
                response.stop()
                self._stack.drain(self._spec.slot)

    @asynccontextmanager
    async def _hold(self, adapter: str | None) -> AsyncIterator[Slot]:
        """Take the slot for this request, with the sub-agent's adapter attached if asked."""
        if adapter is None:
            async with self._stack.holding(self._spec.slot) as loaded:
                yield loaded
        else:
            async with self._stack.with_adapter(adapter) as loaded:  # type: ignore[arg-type]
                yield loaded


def _prompt_opens_thought(messages: Sequence[ModelMessage]) -> bool:
    """Whether the chat template leaves the thought channel already open.

    With thinking on it does exactly when the prompt ends on a tool response, so the model
    starts writing reasoning with no opening marker for the splitter to see.
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


def _render_messages(messages: Sequence[ModelMessage], params: ModelRequestParameters) -> list[dict[str, Any]]:
    """Pydantic AI messages as the OpenAI-shaped dicts the Gemma 4 chat template expects.

    The template only treats `messages[0]` as the system turn, so instructions and every system
    prompt are folded into one leading message.
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
            rendered.append(_assistant_message(message))
    if system:
        rendered.insert(0, {"role": "system", "content": "\n\n".join(system)})
    return rendered


def _assistant_message(message: ModelResponse) -> dict[str, Any]:
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
        out["reasoning"] = thinking
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
    _slot_name: ModelSlot
    _slot: Slot
    _request: dict[str, Any]
    _forced_tool: bool
    _in_thought: bool
    _run_context: RunContext[Any] | None
    _timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    _stopped: bool = False
    _chunks: Iterator[dict[str, Any]] | None = None

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
        self._chunks = await run(self._slot_name, lambda: self._slot.stream(**self._request))
        splitter = gemma.StreamSplitter(in_thought=self._in_thought)
        generated = 0
        prompt_tokens = 0
        cancelled = False
        while (chunks := self._chunks) is not None:
            # Checked between tokens: this is what the Stop endpoint's cancellation token reaches.
            if self._stopped or self._cancel_requested():
                cancelled = True
                break
            chunk = await run(self._slot_name, lambda: next(chunks, None))
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
                for event in self._tool_call_deltas(calls or []):
                    yield event
            else:
                for event in self._events(splitter.feed(content or "")):
                    yield event
        for event in self._events(splitter.finish()):
            yield event
        self._usage = RequestUsage(input_tokens=prompt_tokens, output_tokens=generated)
        if not cancelled:
            # A cancelled turn is left without a reason; the response state already says
            # interrupted, and none of the normalized reasons means "the user pressed Stop".
            called = any(part.part_kind == "tool-call" for part in self._parts_manager.get_parts())
            self.finish_reason = "tool_call" if called else "stop"

    def _events(self, parsed: Sequence[gemma.Event]) -> Iterator[ModelResponseStreamEvent]:
        for kind, payload in parsed:
            if kind == "thinking":
                yield from self._parts_manager.handle_thinking_delta(vendor_part_id=None, content=payload)
            elif kind == "text":
                yield from self._parts_manager.handle_text_delta(vendor_part_id=None, content=payload)
            else:
                yield self._parts_manager.handle_tool_call_part(
                    vendor_part_id=None, tool_name=payload.name, args=payload.args
                )

    def _tool_call_deltas(self, calls: Sequence[dict[str, Any]]) -> Iterator[ModelResponseStreamEvent]:
        """The forced-tool path: llama.cpp already emits OpenAI tool-call deltas."""
        for call in calls:
            event = self._parts_manager.handle_tool_call_delta(
                vendor_part_id=call.get("index", 0),
                tool_name=call["function"].get("name"),
                args=call["function"].get("arguments"),
                tool_call_id=call.get("id"),
            )
            if event is not None:
                yield event
