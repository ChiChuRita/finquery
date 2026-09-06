"""Which model a run is scored on.

Four ways to name one, and the runner needs no code change to move between them:

- `local:qwen3.5-9b` or any other catalog key (`finquery.catalog`), which is what the app itself
  stores on a conversation;
- `fast` or `quality`: the pre-catalog names, kept because every recorded run uses them.
  `quality` is the Qwen entry of the configured provider and `fast` its sub-agent slot;
- `google/gemini-3.8-flash`: any OpenRouter id, resolved directly;
- `local:fast` with an optional `--adapter query`: the local sub-agent slot, with a LoRA adapter
  attached for the run through the `finquery_adapter` model setting.

Whatever the target, every role the sub-agents ask for resolves to the same model: a benchmark
compares weights, so a run must not quietly answer half its datapoints on something else.
"""

from dataclasses import dataclass

from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.catalog import Catalog
from finquery.providers import (
    SUBAGENT_MAX_TOKENS,
    HostedModel,
    ModelResolver,
    ModelRole,
    build_local_stack,
    subagent_settings,
)
from finquery.settings import Settings

LOCAL_PREFIX = "local:"
LEGACY_SLOTS = {"fast": "fast", "quality": "chat"}
"""The pre-catalog `--model` values, as the role they name on the configured provider."""


@dataclass(frozen=True)
class Target:
    """The model under test: a resolver every slot maps to, and the settings a sub-agent runs with."""

    name: str
    resolve: ModelResolver
    settings: ModelSettings

    @property
    def slug(self) -> str:
        """The name as a file name: `google/gemini-3.8-flash` becomes `google-gemini-3.8-flash`."""
        return self.name.replace("/", "-").replace(":", "-")


def _everywhere(model: Model) -> ModelResolver:
    """One model for every role, so nothing in the path can reach for a second one."""

    def resolve(_role: ModelRole) -> Model:
        return model

    return resolve


def openrouter_target(model_id: str, settings: Settings) -> Target:
    """An OpenRouter id, with reasoning off the way `providers.subagent_settings` asks for it."""
    from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set, so an OpenRouter model cannot be benchmarked")
    provider = OpenRouterProvider(api_key=settings.openrouter_api_key)
    model = HostedModel(OpenRouterModel(model_id, provider=provider))
    return Target(
        name=model_id,
        resolve=_everywhere(model),
        settings=OpenRouterModelSettings(
            openrouter_reasoning={"enabled": False}, max_tokens=SUBAGENT_MAX_TOKENS
        ),
    )


def local_target(name_part: str, adapter: str | None, settings: Settings) -> Target:
    """One local model, with the named LoRA adapter attached for every call of the run."""
    from finquery.local.catalog import LOCAL_MODELS
    from finquery.local.model import LocalModelSettings

    stack = build_local_stack(settings, download=False)
    key = "local:fast" if name_part in ("fast", "quality") else f"{LOCAL_PREFIX}{name_part}"
    spec = LOCAL_MODELS.get("local:qwen3.5-9b" if name_part == "quality" else key)
    if spec is None:
        raise RuntimeError(f"{LOCAL_PREFIX}{name_part} is not a local model; try {sorted(LOCAL_MODELS)}")
    model = stack.resolve(spec)
    slot = name_part
    name = f"{LOCAL_PREFIX}{slot}" + (f"+{adapter}" if adapter else "")
    model_settings: ModelSettings = LocalModelSettings(max_tokens=SUBAGENT_MAX_TOKENS)
    if adapter:
        model_settings = LocalModelSettings(max_tokens=SUBAGENT_MAX_TOKENS, finquery_adapter=adapter)
    return Target(name=name, resolve=_everywhere(model), settings=model_settings)


def resolve_target(spec: str, adapter: str | None, settings: Settings) -> Target:
    """Turn `--model` (and `--adapter`) into the one model this run uses."""
    if spec.startswith(LOCAL_PREFIX):
        return local_target(spec[len(LOCAL_PREFIX) :], adapter, settings)
    if spec.startswith("openrouter:"):
        return openrouter_target(spec[len("openrouter:") :], settings)
    if "/" in spec:
        if adapter:
            raise RuntimeError("an adapter only attaches to a local slot, not to a hosted model")
        return openrouter_target(spec, settings)
    if spec not in LEGACY_SLOTS:
        raise RuntimeError(f"{spec} is neither a role (fast, quality), an OpenRouter id, nor a catalog key")
    if adapter and settings.provider != "local":
        raise RuntimeError("an adapter only attaches on the local provider")
    catalog = Catalog(settings, local=build_local_stack(settings, download=False))
    model = catalog.model(catalog.default_key, LEGACY_SLOTS[spec])  # type: ignore[arg-type]
    model_settings = subagent_settings(settings)
    if adapter:
        from finquery.local.model import LocalModelSettings

        model_settings = LocalModelSettings(**{**model_settings, "finquery_adapter": adapter})  # type: ignore[typeddict-item]
    name = f"{settings.provider}:{spec}" + (f"+{adapter}" if adapter else "")
    return Target(name=name, resolve=_everywhere(model), settings=model_settings)
