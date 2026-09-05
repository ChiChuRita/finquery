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

KNOWN_LABELS: dict[str, str] = {
    "google/gemma-4-26b-a4b-it": "Gemma 4 26B",
    "qwen/qwen3.5-9b": "Qwen3.5 9B",
}
"""What the UI calls the hosted models it ships with. The local labels live on the catalog
entries; both reach the browser through `GET /api/models`, so a selector never names a model
that is not running. See docs/adr/0006 for why the quality slot is Qwen."""


def openrouter_models(settings: Settings) -> dict[ModelSlot, str]:
    """The hosted model id behind each slot, from the settings (defaults match the local pair)."""
    return {"fast": settings.openrouter_fast_model, "quality": settings.openrouter_quality_model}


def openrouter_label(model_id: str) -> str:
    """A short display name for any OpenRouter id: the known table, else derived from the id.

    `google/gemini-3.8-flash` reads as `Gemini 3.8 Flash`; a `:free` or `:batch` variant tag is
    kept in lower case so the user sees which one is running.
    """
    base, _, variant = model_id.partition(":")
    if base in KNOWN_LABELS:
        return f"{KNOWN_LABELS[base]} ({variant})" if variant else KNOWN_LABELS[base]
    name = base.rsplit("/", 1)[-1]
    words = [w.upper() if w.isupper() or (len(w) <= 3 and w.isalpha()) else w.capitalize() for w in name.split("-")]
    label = " ".join(words)
    return f"{label} ({variant})" if variant else label

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
        slot: OpenRouterModel(name, provider=provider, settings=reasoning)
        for slot, name in openrouter_models(settings).items()
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


SUBAGENT_MAX_TOKENS = 3072
"""The most a sub-agent may generate for one call.

The largest honest answer any sub-agent gives is about 2500 tokens: a 30 booking statement
page from the extraction sub-agent, or a 25 merchant batch from the categorizer. A forced
tool call is a grammar, and a grammar over a list lets a small model repeat rows until the
context is full (ticket 11 measured six minutes and a prompt past n_ctx for three pages on the
local fast slot). This is the ceiling that stops it: a call that hits it fails its validation
and is retried once, instead of running away.
"""


def subagent_settings(settings: Settings) -> ModelSettings:
    """Overrides for a sub-agent run on the fast slot.

    A sub-agent answers one question behind a tool call and its thinking is never shown, so
    reasoning is turned off: on OpenRouter that is the difference between three and eleven
    seconds for a suggestion nobody asked to wait for. Locally the model itself turns thinking
    off for a forced single tool, so there is nothing to override. Both providers get the
    same output ceiling, `SUBAGENT_MAX_TOKENS`.
    """
    if settings.provider == "openrouter":
        from pydantic_ai.models.openrouter import OpenRouterModelSettings

        return OpenRouterModelSettings(openrouter_reasoning={"enabled": False}, max_tokens=SUBAGENT_MAX_TOKENS)
    return ModelSettings(max_tokens=SUBAGENT_MAX_TOKENS)
