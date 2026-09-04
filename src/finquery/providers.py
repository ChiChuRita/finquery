"""Resolve the two logical model slots (fast, quality) to Pydantic AI models.

This is the only module that knows provider specifics. Everything else asks for a slot.
See docs/adr/0002-provider-switch-with-two-slots.md.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, get_args

from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.settings import Settings

if TYPE_CHECKING:
    from finquery.local.runtime import LocalStack

ModelSlot = Literal["fast", "quality"]
MODEL_SLOTS: tuple[ModelSlot, ...] = get_args(ModelSlot)

OPENROUTER_MODELS: dict[ModelSlot, str] = {
    "fast": "google/gemma-4-26b-a4b-it",
    "quality": "qwen/qwen3.5-9b",
}
"""The hosted half of each slot: the same two models the local provider runs, so a turn does
not change character with the provider. See docs/adr/0006 for why the quality slot is Qwen."""

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


def build_local_stack(settings: Settings) -> "LocalStack":
    """The local provider's state: the model files, the resident slots and the adapters.

    Anything missing starts downloading right away, so a fresh checkout only needs
    `uv run finquery` and the Settings page to watch.
    """
    from finquery.local.runtime import LocalStack

    stack = LocalStack(settings)
    stack.downloads.start()
    return stack


def build_resolver(settings: Settings, *, local: "LocalStack | None" = None) -> ModelResolver:
    """Return a callable mapping a slot to a model. Construction never touches the network.

    On the local provider nothing is downloaded or loaded here either: the first chat on a slot
    does that, so the app starts (and can show download progress) with no weights on disk.
    """
    if settings.provider == "openrouter":
        return _openrouter_resolver(settings)
    return (local or build_local_stack(settings)).resolve


def subagent_settings(settings: Settings) -> ModelSettings:
    """Overrides for a sub-agent run on the fast slot.

    A sub-agent answers one question behind a tool call and its thinking is never shown, so
    reasoning is turned off: on OpenRouter that is the difference between three and eleven
    seconds for a suggestion nobody asked to wait for. Locally the model itself turns thinking
    off for a forced single tool, so there is nothing to override.
    """
    if settings.provider == "openrouter":
        from pydantic_ai.models.openrouter import OpenRouterModelSettings

        return OpenRouterModelSettings(openrouter_reasoning={"enabled": False})
    return ModelSettings()
