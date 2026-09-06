"""Provider specifics: what a hosted model is, what the local provider is, and the two roles.

A role says what a model is being asked to do in one turn: `chat` is the conversation's own
catalog entry, `fast` is the sub-agent slot of that entry's provider. Everything outside this
module and `finquery.catalog` asks for a role and gets a model.
See docs/adr/0002-provider-switch-with-two-slots.md and docs/adr/0013-model-catalog-across-providers.md.
"""

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Literal, get_args

from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import Model
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from finquery.settings import Settings

if TYPE_CHECKING:
    from finquery.local.runtime import LocalStack

ModelRole = Literal["chat", "fast"]
MODEL_ROLES: tuple[ModelRole, ...] = get_args(ModelRole)
"""The two things a model is asked to be in one turn. `chat` is the conversation's catalog
entry, `fast` the sub-agent slot of that entry's provider. On the local provider the two are
also the two seats in memory (`finquery.local.runtime`)."""

KNOWN_LABELS: dict[str, str] = {
    "google/gemma-4-26b-a4b-it": "Gemma 4 26B",
    "qwen/qwen3.5-9b": "Qwen3.5 9B",
}
"""What the UI calls the hosted models it ships with. The local labels live on the catalog
entries; both reach the browser through `GET /api/models`, so a selector never names a model
that is not running. See docs/adr/0006 for why the quality slot is Qwen."""


def openrouter_chat_models(settings: Settings) -> tuple[str, str]:
    """The two hosted ids offered as chat entries, from the settings."""
    return settings.openrouter_quality_model, settings.openrouter_second_chat_model


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

ModelResolver = Callable[[ModelRole], Model]
"""What a tool or a sub-agent is given: a role to a model, already bound to one catalog entry.
`finquery.catalog.Catalog.resolver` makes one."""


class ProviderNotAvailable(RuntimeError):
    """The configured provider cannot serve a chat yet."""


REASONING_MANDATORY = "Reasoning is mandatory"
"""The start of OpenRouter's 400 for a model that cannot run with reasoning switched off
(Gemini 3.x Flash, for one). Sub-agents ask for it off; on such a model they get the lowest
effort instead, which is the same intent."""


class HostedModel(WrapperModel):
    """An OpenRouter model that falls back to low reasoning effort where off is refused.

    The first refused request costs one round trip; after that the model remembers and sends
    the fallback straight away, so a 100 page statement does not pay it 100 times.
    """

    def __init__(self, wrapped: Model) -> None:
        super().__init__(wrapped)
        self.reasoning_required = False

    def _adjusted(self, model_settings: ModelSettings | None) -> ModelSettings | None:
        reasoning = (model_settings or {}).get("openrouter_reasoning")
        if not self.reasoning_required or not isinstance(reasoning, dict) or reasoning.get("enabled") is not False:
            return model_settings
        return {**model_settings, "openrouter_reasoning": {"effort": "low"}}  # type: ignore[return-value]

    @staticmethod
    def _refused_off(exc: Exception) -> bool:
        return isinstance(exc, ModelHTTPError) and exc.status_code == 400 and REASONING_MANDATORY in str(exc.body)

    async def request(self, messages, model_settings, model_request_parameters):  # type: ignore[override]
        try:
            return await super().request(messages, self._adjusted(model_settings), model_request_parameters)
        except ModelHTTPError as exc:
            if self.reasoning_required or not self._refused_off(exc):
                raise
            self.reasoning_required = True
            return await super().request(messages, self._adjusted(model_settings), model_request_parameters)

    @asynccontextmanager
    async def request_stream(self, messages, model_settings, model_request_parameters, run_context=None):  # type: ignore[override]
        try:
            async with super().request_stream(
                messages, self._adjusted(model_settings), model_request_parameters, run_context
            ) as stream:
                yield stream
                return
        except ModelHTTPError as exc:
            if self.reasoning_required or not self._refused_off(exc):
                raise
            self.reasoning_required = True
        async with super().request_stream(
            messages, self._adjusted(model_settings), model_request_parameters, run_context
        ) as stream:
            yield stream


NO_API_KEY = "OPENROUTER_API_KEY is not set, so the hosted models cannot answer. Put it in .env."


def hosted_model(settings: Settings, model_id: str) -> Model:
    """One OpenRouter model by id. Construction never touches the network."""
    from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    if not settings.openrouter_api_key:
        raise ProviderNotAvailable(NO_API_KEY)
    provider = OpenRouterProvider(api_key=settings.openrouter_api_key)
    reasoning = OpenRouterModelSettings(openrouter_reasoning={"enabled": True})
    return HostedModel(OpenRouterModel(model_id, provider=provider, settings=reasoning))


def build_local_stack(settings: Settings, *, download: bool = True) -> "LocalStack":
    """The local provider's state: the model files, the seats and the adapters.

    Both providers can be live at once, so this is built whatever `FINQUERY_PROVIDER` says and
    nothing here loads weights or touches the network. `download` is what the provider setting
    decides: on `local` anything missing starts coming down right away, so a fresh checkout only
    needs `uv run finquery` and the Settings page to watch, while an OpenRouter run does not
    start a 13 GB download nobody asked for. The Settings models card starts it either way.
    """
    from finquery.local.runtime import LocalStack

    stack = LocalStack(settings)
    if download:
        stack.downloads.start()
    return stack


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
