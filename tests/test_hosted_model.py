"""The hosted model falls back to low reasoning effort where switching it off is refused."""

from datetime import datetime, timezone

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.settings import ModelSettings

from finquery.providers import REASONING_MANDATORY, HostedModel


class Picky(Model):
    """Answers only when reasoning is not switched off, like Gemini 3.x Flash on OpenRouter."""

    def __init__(self) -> None:
        self.seen: list[ModelSettings | None] = []

    async def request(self, messages, model_settings, model_request_parameters):  # type: ignore[override]
        self.seen.append(model_settings)
        reasoning = (model_settings or {}).get("openrouter_reasoning") or {}
        if reasoning.get("enabled") is False:
            raise ModelHTTPError(
                status_code=400, model_name="picky", body={"message": f"{REASONING_MANDATORY} for this endpoint."}
            )
        return ModelResponse(parts=[TextPart("ok")], model_name="picky", timestamp=datetime.now(timezone.utc))

    @property
    def model_name(self) -> str:
        return "picky"

    @property
    def system(self) -> str:
        return "test"


def _messages() -> list[ModelMessage]:
    return [ModelRequest(parts=[UserPromptPart(content="hi")])]


async def test_a_refused_off_becomes_low_effort_and_is_remembered() -> None:
    inner = Picky()
    model = HostedModel(inner)
    off: ModelSettings = {"openrouter_reasoning": {"enabled": False}}  # type: ignore[typeddict-item]

    first = await model.request(_messages(), off, ModelRequestParameters())
    second = await model.request(_messages(), off, ModelRequestParameters())

    assert first.parts[0].content == "ok" and second.parts[0].content == "ok"  # type: ignore[union-attr]
    # One refusal, then the fallback; the second call skips the refused attempt.
    assert [s["openrouter_reasoning"] for s in inner.seen] == [  # type: ignore[index]
        {"enabled": False},
        {"effort": "low"},
        {"effort": "low"},
    ]


async def test_other_errors_and_other_settings_pass_through() -> None:
    inner = Picky()
    model = HostedModel(inner)
    on: ModelSettings = {"openrouter_reasoning": {"enabled": True}}  # type: ignore[typeddict-item]
    await model.request(_messages(), on, ModelRequestParameters())
    assert inner.seen == [on]

    class Broken(Picky):
        async def request(self, messages, model_settings, model_request_parameters):  # type: ignore[override]
            raise ModelHTTPError(status_code=500, model_name="picky", body={"message": "down"})

    with pytest.raises(ModelHTTPError):
        await HostedModel(Broken()).request(_messages(), on, ModelRequestParameters())
