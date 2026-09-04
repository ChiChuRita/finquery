"""Resolve the two logical model slots (fast, quality) to Pydantic AI models.

This is the only module that knows provider specifics. Everything else asks for a slot.
See docs/adr/0002-provider-switch-with-two-slots.md.
"""

from collections.abc import Callable
from typing import Literal, get_args

from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.settings import Settings

ModelSlot = Literal["fast", "quality"]
MODEL_SLOTS: tuple[ModelSlot, ...] = get_args(ModelSlot)

OPENROUTER_MODELS: dict[ModelSlot, str] = {
    "fast": "google/gemma-4-26b-a4b-it",
    "quality": "google/gemma-4-31b-it",
}

ModelResolver = Callable[[ModelSlot], Model]


class ProviderNotAvailable(RuntimeError):
    """The configured provider cannot serve a chat yet."""


def _openrouter_resolver(settings: Settings) -> ModelResolver:
    from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    if not settings.openrouter_api_key:
        raise ProviderNotAvailable("FINQUERY_PROVIDER=openrouter needs OPENROUTER_API_KEY in the environment or .env")
    provider = OpenRouterProvider(api_key=settings.openrouter_api_key)
    reasoning = OpenRouterModelSettings(openrouter_reasoning={"enabled": True})
    models = {
        slot: OpenRouterModel(name, provider=provider, settings=reasoning) for slot, name in OPENROUTER_MODELS.items()
    }
    return models.__getitem__


def _local_resolver(_settings: Settings) -> ModelResolver:
    def resolve(slot: ModelSlot) -> Model:
        raise ProviderNotAvailable(
            f"The local provider is not available yet (slot {slot!r}), see ticket 16. "
            "Set FINQUERY_PROVIDER=openrouter to chat."
        )

    return resolve


def build_resolver(settings: Settings) -> ModelResolver:
    """Return a callable mapping a slot to a model. Construction never touches the network."""
    if settings.provider == "openrouter":
        return _openrouter_resolver(settings)
    return _local_resolver(settings)


def subagent_settings(settings: Settings) -> ModelSettings:
    """Overrides for a sub-agent run on the fast slot.

    A sub-agent answers one question behind a tool call and its thinking is never shown, so
    reasoning is turned off: on OpenRouter that is the difference between three and eleven
    seconds for a suggestion nobody asked to wait for.
    """
    if settings.provider == "openrouter":
        from pydantic_ai.models.openrouter import OpenRouterModelSettings

        return OpenRouterModelSettings(openrouter_reasoning={"enabled": False})
    return ModelSettings()
