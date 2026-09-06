"""The model catalog: every chat model the app offers, across both providers.

A **catalog entry** is what a conversation runs on. It names its provider, so choosing an entry
chooses a provider for that conversation and nothing else: the local entries and the cloud
entries are live at the same time, and `FINQUERY_PROVIDER` only decides which entry a new
conversation starts on.

Sub-agents never appear in the catalog. They run on the **fast slot of the entry's provider**:
Gemma 4 E4B for a local entry (resident, the adapters attach there) and
`FINQUERY_OPENROUTER_FAST_MODEL` for a cloud one. That is the whole resolution rule, and
`Catalog.resolver` is where it lives: one entry key in, a role to model callable out.

See docs/adr/0013-model-catalog-across-providers.md, which amends 0002 and 0006.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic_ai.models import Model

from finquery.local.catalog import LOCAL_CHAT_MODELS, LOCAL_FAST, ModelSpec
from finquery.providers import (
    NO_API_KEY,
    ModelResolver,
    ModelRole,
    ProviderNotAvailable,
    hosted_model,
    openrouter_chat_models,
    openrouter_label,
)
from finquery.settings import Provider, Settings

if TYPE_CHECKING:
    from finquery.local.runtime import LocalStack

#: The test seam: one entry key and one role to a model. `create_app(resolve_model=...)` passes
#: a scripted one, which is how a test asserts which provider a sub-agent was asked for.
Resolver = Callable[[str, ModelRole], Model]

LEGACY_KEYS = ("fast", "quality")
"""What a conversation stored before the catalog. Both read as the Qwen entry of the configured
provider: `fast` was the sub-agent slot, never a chat choice the user meant to keep."""


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


def build_entries(settings: Settings) -> list[Entry]:
    """The four entries, in the order the picker lists them: local, cloud, local, cloud.

    Two settings pointing at the same OpenRouter id (which `.env` does during development) is
    one entry, not a duplicate the user has to tell apart.
    """
    qwen, second = openrouter_chat_models(settings)
    ordered = [
        local_entry(LOCAL_CHAT_MODELS[0]),
        hosted_entry(qwen),
        local_entry(LOCAL_CHAT_MODELS[1]),
        hosted_entry(second),
    ]
    seen: dict[str, Entry] = {}
    for entry in ordered:
        seen.setdefault(entry.key, entry)
    return list(seen.values())


class Catalog:
    """The catalog and the one rule that resolves a turn: chat on the entry, sub-agents fast."""

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
        self.entries = build_entries(settings)
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
        """The entry a new conversation starts on: the Qwen entry of the configured provider."""
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

    def for_role(self, key: str, role: ModelRole) -> Entry:
        """The entry a role resolves to: the chat entry itself, or its provider's fast slot."""
        entry = self.entry(key)
        return entry if role == "chat" else self.fast_slots[entry.provider]

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

    def model(self, key: str, role: ModelRole) -> Model:
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

        def resolve(role: ModelRole) -> Model:
            return self.model(resolved, role)

        return resolve
