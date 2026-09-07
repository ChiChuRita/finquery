"""The model catalog: every chat model the app offers, across both providers.

A **catalog entry** is what a conversation runs on. It names its provider, so choosing an entry
chooses a provider for that conversation and nothing else: the local entries and the cloud
entry are live at the same time, and `FINQUERY_PROVIDER` only decides which entry a new
conversation starts on. Three entries since ticket 75: Gemma 4 E4B and Gemma 4 26B A4B locally,
and the same 26B A4B through OpenRouter.

Each sub-agent **role** has a setting saying which model it runs on: `chat` (the conversation's
own entry, the default), `fast` (the sub-agent slot of that entry's provider: the Gemma 4 E4B
entry for a local one, where the adapters attach, and `FINQUERY_OPENROUTER_FAST_MODEL`
for a cloud one) or a catalog key that pins the role to one model. That is the whole resolution
rule, and `Catalog.for_role` is where it lives; `Catalog.resolver` binds it to one entry and
hands a turn a role to model callable. The query and chart sub-agents ask for their LoRA
adapter on every run and get it exactly when they land on E4B (`finquery.local.model`), so a
chat on E4B runs the fine-tuned sub-agents and a chat on a bigger model runs its base weights.

One local model is loaded at a time (ADR 0013, ticket 68 amendment), so a role set to `fast`
on a chat on the 26B swaps to E4B and back around every sub-agent call. The default `chat`
never swaps.

See docs/adr/0013-model-catalog-across-providers.md, which amends 0002 and 0006, and its
ticket 75 amendment for why the shipped chat model is Gemma 4 26B A4B.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai.models import Model

from finquery.local.catalog import LOCAL_CHAT_MODELS, LOCAL_FAST, ModelSpec
from finquery.providers import (
    MODEL_ROLES,
    NO_API_KEY,
    SUBAGENT_ROLES,
    ModelResolver,
    ProviderNotAvailable,
    Role,
    hosted_model,
    openrouter_label,
)
from finquery.settings import Provider, Settings

if TYPE_CHECKING:
    from finquery.local.runtime import LocalStack

#: The test seam: one entry key and one role to a model. `create_app(resolve_model=...)` passes
#: a scripted one, which is how a test asserts which model each role was asked for.
Resolver = Callable[[str, Role], Model]

LEGACY_KEYS = ("fast", "quality")
"""What a conversation stored before the catalog. Both read as the default entry of the
configured provider: `fast` was the sub-agent slot, never a chat choice the user meant to
keep, and `quality` was a position rather than a model."""

HOSTED_CHAT_MODELS: tuple[str, ...] = ("google/gemma-4-26b-a4b-it",)
"""The OpenRouter ids the catalog offers as chat entries. Gemma 4 26B A4B is the model the demo
ships locally and the same weights as `local:gemma-4-26b`, so a question can be compared on the
two. A constant rather than a setting so the entry is always offered, including while
`FINQUERY_OPENROUTER_FAST_MODEL` points at it."""

DEFAULT_KEYS: dict[Provider, str] = {
    "local": "local:gemma-4-26b",
    "openrouter": f"openrouter:{HOSTED_CHAT_MODELS[0]}",
}
"""The entry a new conversation starts on per provider. The 26B A4B on both since ticket 75, so
the local default and the hosted one are the same weights, not the smallest entry the picker
lists first."""


@dataclass(frozen=True)
class Entry:
    """One chat model the picker offers, on one provider."""

    key: str
    """Stable id, stored on conversations and turns: `local:gemma-4-26b`, `openrouter:<id>`."""
    label: str
    provider: Provider
    local: ModelSpec | None = None
    """The GGUF behind a local entry, else None."""
    hosted_id: str | None = None
    """The OpenRouter id behind a cloud entry, else None."""


@dataclass(frozen=True)
class Availability:
    """Whether an entry can answer right now, and in one sentence why not."""

    available: bool
    reason: str | None = None


def hosted_entry(model_id: str) -> Entry:
    return Entry(
        key=f"openrouter:{model_id}",
        label=f"{openrouter_label(model_id)} (cloud)",
        provider="openrouter",
        hosted_id=model_id,
    )


def local_entry(spec: ModelSpec) -> Entry:
    return Entry(key=spec.key, label=spec.label, provider="local", local=spec)


def build_entries() -> list[Entry]:
    """The three entries, in the order the picker lists them: the two local Gemma 4 sizes small
    to large, then the cloud one. E4B is both the smaller chat entry and the local fast slot, so
    it appears here and in `Catalog.fast_slots` under one key."""
    return [local_entry(LOCAL_FAST), *(local_entry(spec) for spec in LOCAL_CHAT_MODELS), *map(hosted_entry, HOSTED_CHAT_MODELS)]


class Catalog:
    """The catalog and the rule that resolves a turn: the chat on its entry, every sub-agent
    role on what its setting says (`chat` by default, `fast`, or a catalog key)."""

    def __init__(
        self,
        settings: Settings,
        *,
        local: "LocalStack | None" = None,
        resolve: Resolver | None = None,
    ) -> None:
        self.settings = settings
        self.local = local
        self._resolve = resolve
        self.entries = build_entries()
        self.fast_slots: dict[Provider, Entry] = {
            "local": local_entry(LOCAL_FAST),
            "openrouter": Entry(
                key="openrouter:fast",
                label=openrouter_label(settings.openrouter_fast_model),
                provider="openrouter",
                hosted_id=settings.openrouter_fast_model,
            ),
        }
        self._hosted: dict[str, Model] = {}

    @property
    def default_key(self) -> str:
        """The entry a new conversation starts on: Gemma 4 26B A4B on either provider
        (`DEFAULT_KEYS`)."""
        return DEFAULT_KEYS[self.settings.provider]

    def key_of(self, stored: str | None) -> str:
        """Read a stored value as a catalog key, mapping the pre-catalog `fast` and `quality`.

        Anything the catalog no longer offers (a hosted id that was taken out of the settings)
        reads as the default entry too, so a conversation from an older run still opens.
        """
        if stored is not None and any(entry.key == stored for entry in self.entries):
            return stored
        return self.default_key

    def entry(self, key: str) -> Entry:
        for entry in self.entries:
            if entry.key == key:
                return entry
        raise ProviderNotAvailable(f"{key} is not a model this app offers")

    def for_role(self, key: str, role: Role) -> Entry:
        """The entry a role resolves to, for a conversation on `key`.

        `chat` is that entry itself and `fast` its provider's sub-agent slot (the Gemma 4 E4B
        entry locally). A sub-agent role is one setting (`FINQUERY_SUBAGENT_MODEL_<ROLE>`)
        holding one of those two words, which it then follows, or a catalog key pinning that
        role to one model whatever the conversation runs on. The default is `chat`, so a
        sub-agent runs on the model the user picked: the fine-tuned E4B sub-agents on a chat on
        E4B, the base weights of the 26B on a chat there, where the benchmark says the sub-agent
        path is 79 percent right on the 459 question SQL set against E4B's 62 before its adapter
        (`bench/results/20260907T141018Z-local-gemma-4-26b-sql.md` and `20260907-adapters-compare.md`).
        """
        if role not in MODEL_ROLES:
            wanted = self.settings.subagent_model(role)
            if wanted not in MODEL_ROLES:
                return self.entry(wanted)
            role = wanted  # type: ignore[assignment]
        entry = self.entry(key)
        return entry if role == "chat" else self.fast_slots[entry.provider]

    def role_targets(self, key: str) -> dict[str, Entry]:
        """What every sub-agent role resolves to right now, for a conversation on `key`.

        The models card shows this, because a setting saying `chat` is only half an answer.
        """
        return {role: self.for_role(key, role) for role in SUBAGENT_ROLES}

    def set_openrouter_key(self, key: str | None) -> None:
        """Take a key from the Settings page: the cloud entry answers with it from the next
        request on. The hosted models built with the old key are dropped, so nothing keeps
        sending a key the user just replaced. Persisting it is `finquery.settings.save_openrouter_key`."""
        self.settings.openrouter_api_key = key
        self._hosted.clear()

    def availability(self, entry: Entry) -> Availability:
        """Can this entry answer, and if not, what the user can do about it."""
        if entry.provider == "openrouter":
            if not self.settings.openrouter_api_key:
                return Availability(False, NO_API_KEY)
            return Availability(True)
        if self.local is None:
            return Availability(False, "The local provider is switched off in this process.")
        spec = entry.local
        assert spec is not None
        if self.local.downloads.ready(spec.key):
            return Availability(True)
        return Availability(False, f"{spec.label} is not downloaded yet: {self.local.download_summary(spec.key)}")

    def model(self, key: str, role: Role) -> Model:
        """The model for one role of one conversation. Loads nothing and touches no network."""
        entry = self.for_role(key, role)
        if self._resolve is not None:
            return self._resolve(entry.key, role)
        if not (state := self.availability(entry)).available:
            raise ProviderNotAvailable(state.reason or f"{entry.label} is not available")
        if entry.provider == "local":
            assert self.local is not None and entry.local is not None
            return self.local.resolve(entry.local)
        assert entry.hosted_id is not None
        if entry.hosted_id not in self._hosted:
            self._hosted[entry.hosted_id] = hosted_model(self.settings, entry.hosted_id)
        return self._hosted[entry.hosted_id]

    def resolver(self, key: str) -> ModelResolver:
        """What a turn hands to its tools and sub-agents: a role to a model, bound to one entry."""
        resolved = self.key_of(key)

        def resolve(role: Role) -> Model:
            return self.model(resolved, role)

        return resolve
