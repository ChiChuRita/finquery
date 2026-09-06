"""The model catalog: every chat model the app offers, across both providers.

A **catalog entry** is what a conversation runs on. It names its provider, so choosing an entry
chooses a provider for that conversation and nothing else: the local entries and the cloud
entries are live at the same time, and `FINQUERY_PROVIDER` only decides which entry a new
conversation starts on.

Sub-agents never appear in the catalog. Each sub-agent **role** has a setting saying which model
it runs on: `chat` (the conversation's own entry, the default), `fast` (the sub-agent slot of
that entry's provider: Gemma 4 E4B for a local entry, resident, where the adapters attach, and
`FINQUERY_OPENROUTER_FAST_MODEL` for a cloud one) or a catalog key that pins the role to one
model. That is the whole resolution rule, and `Catalog.for_role` is where it lives;
`Catalog.resolver` binds it to one entry and hands a turn a role to model callable.

See docs/adr/0013-model-catalog-across-providers.md, which amends 0002 and 0006, and the 0006
amendment of ticket 61 for why the shipped pair is Gemma 4 12B with E4B.
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

HOSTED_CHAT_MODELS: tuple[str, str] = ("google/gemma-4-26b-a4b-it", "qwen/qwen3.5-9b")
"""The two OpenRouter ids the catalog offers as chat entries, in the order the picker lists
them. Gemma 4 26B A4B is first because it is the family the demo ships locally (Gemma 4 12B,
which OpenRouter does not serve) and so the closest hosted stand-in for it; Qwen3.5 9B is the
alternative. They are constants rather than settings so that both entries are always offered,
including while `FINQUERY_OPENROUTER_FAST_MODEL` points at one of them."""


@dataclass(frozen=True)
class Entry:
    """One chat model the picker offers, on one provider."""

    key: str
    """Stable id, stored on conversations and turns: `local:qwen3.5-9b`, `openrouter:<id>`."""
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
    """The four entries, in the order the picker lists them: local, cloud, local, cloud.

    The shipped pair comes first, so the entry a new conversation starts on is the first of its
    provider: Gemma 4 12B locally (the cluster benchmark of 2026-09-06 decided it) and Gemma 4
    26B A4B in the cloud. Qwen3.5 9B stays as the alternative on both.
    """
    return [
        local_entry(LOCAL_CHAT_MODELS[0]),
        hosted_entry(HOSTED_CHAT_MODELS[0]),
        local_entry(LOCAL_CHAT_MODELS[1]),
        hosted_entry(HOSTED_CHAT_MODELS[1]),
    ]


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
        """The entry a new conversation starts on: the first entry of the configured provider,
        which is Gemma 4 12B locally and Gemma 4 26B A4B in the cloud."""
        wanted = "local" if self.settings.provider == "local" else "openrouter"
        return next(entry.key for entry in self.entries if entry.provider == wanted)

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

        `chat` is that entry itself and `fast` its provider's sub-agent slot. A sub-agent role
        is one setting (`FINQUERY_SUBAGENT_MODEL_<ROLE>`) holding one of those two words, which
        it then follows, or a catalog key pinning that role to one model whatever the
        conversation runs on. The default is `chat`, so a sub-agent runs on the model the user
        picked: Gemma 4 12B on the demo machine, where the benchmark says the sub-agent path is
        87 percent right against E4B's 66 (`bench/results/20260906-cluster-compare.md`).
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
