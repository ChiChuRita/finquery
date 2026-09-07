"""Which model a run is scored on.

Four ways to name one, and the runner needs no code change to move between them:

- `local:gemma-4-e4b`, `local:gemma-4-12b`, `local:gemma-4-26b` or any other catalog key
  (`finquery.catalog`), which is what the app itself stores on a conversation. E4B is also the
  sub-agent slot, which the recorded runs name `local:fast`. A benchmark candidate the app does
  not offer (`finquery_bench.candidates`, `local:qwen3.8-27b`) is named the same way;
- `fast` or `quality`: the pre-catalog names, kept because every recorded run uses them.
  `quality` is the default entry of the configured provider (Gemma 4 12B locally since ticket
  61) and `fast` its sub-agent slot;
- `google/gemini-3.8-flash`: any OpenRouter id, resolved directly;
- `local:fast` with an optional `--adapter query`: the local sub-agent slot, with a LoRA adapter
  attached for the run through the `finquery_adapter` model setting.

Whatever the target, every role the sub-agents ask for resolves to the same model: a benchmark
compares weights, so a run must not quietly answer half its datapoints on something else. That
also makes `--model local:gemma-4-12b` the "chat and sub-agents on the same model" shape the
demo runs, with no second flag to pass.
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
"""The pre-catalog `--model` values, as the model role they name on the configured provider.
Neither is a sub-agent role: a benchmark pins one model to every role of the run."""

LOCAL_ALIASES = {"local:fast": "local:gemma-4-e4b"}
"""Names for a local model that are not its catalog key, and what they resolve to.

`local:fast` is what every recorded run on the sub-agent slot is named after; since ticket 67
that model, Gemma 4 E4B, is a catalog entry under its own name. `local:quality` named Qwen3.5
9B, which left the catalog in the same ticket: its recorded runs stay, and the name resolves to
nothing. The run keeps the name it was asked for, so two files never claim to be the same run."""


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
    """One local model, with the named LoRA adapter attached for every call of the run.

    The catalog's models and the benchmark candidates are one map here, and the stack is built
    over that map so a candidate's files are found and verified the same way; nothing about the
    app's own stack changes, this one lives for the run.
    """
    from finquery.local.catalog import LOCAL_MODELS
    from finquery.local.model import LocalModelSettings
    from finquery.local.runtime import LocalStack

    from finquery_bench.candidates import CANDIDATES

    models = {**LOCAL_MODELS, **CANDIDATES}
    stack = LocalStack(settings, models=models)
    requested = f"{LOCAL_PREFIX}{name_part}"
    spec = models.get(LOCAL_ALIASES.get(requested, requested))
    if spec is None:
        raise RuntimeError(f"{requested} is not a local model; try {sorted(models)} or {sorted(LOCAL_ALIASES)}")
    model = stack.resolve(spec)
    name = requested + (f"+{adapter}" if adapter else "")
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
    model_settings = subagent_settings()
    if adapter:
        from finquery.local.model import LocalModelSettings

        model_settings = LocalModelSettings(**{**model_settings, "finquery_adapter": adapter})  # type: ignore[typeddict-item]
    name = f"{settings.provider}:{spec}" + (f"+{adapter}" if adapter else "")
    return Target(name=name, resolve=_everywhere(model), settings=model_settings)
