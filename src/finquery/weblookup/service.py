"""One entry point for a merchant lookup, used by the chat tool and by the categorizer.

`Lookups` is what a caller holds when the profile has web lookup switched on: it knows where to
write, whom to ask and what may leave. `lookups_for` is the only place the switch is read, so
"off" means the object does not exist and there is nothing to call.

The order inside `merchant` is the whole feature in five lines: scrub, refuse or continue, look
in the cache, run the loop, keep the result. A merchant token therefore leaves at most once per
profile.
"""

from dataclasses import dataclass, field

from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session, sessionmaker

from finquery.providers import ModelResolver, ProviderNotAvailable
from finquery.weblookup.client import WebClient
from finquery.weblookup.loop import Outcome, run_loop
from finquery.weblookup.scrub import scrub
from finquery.weblookup.store import (
    OutboundJournal,
    Source,
    cached_lookup,
    sources_of,
    store_lookup,
    web_lookup_enabled,
)

Taxonomy = tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True)
class Lookup:
    """What the app knows about one merchant from the web, fresh or from the cache."""

    token: str
    summary: str = ""
    category: str | None = None
    subcategory: str | None = None
    confidence: float = 0.0
    sources: list[Source] = field(default_factory=list)
    searches: int = 0
    fetches: int = 0
    cached: bool = False
    error: str | None = None

    @property
    def placed(self) -> bool:
        """True when it named a category, which is what the pipeline can act on."""
        return bool(self.category)

    def payload(self) -> dict[str, object]:
        """The `lookup_merchant` tool result. `sources` is what the transcript cites."""
        return {
            "merchant": self.token,
            "summary": self.summary,
            "category": self.category,
            "subcategory": self.subcategory,
            "confidence": round(self.confidence, 2),
            "sources": [source.payload() for source in self.sources],
            "searches": self.searches,
            "fetches": self.fetches,
            "cached": self.cached,
            "error": self.error,
        }


@dataclass(frozen=True)
class Lookups:
    """Web lookup for one profile that has it switched on."""

    session_factory: sessionmaker[Session]
    profile_id: str
    client: WebClient
    resolve_model: ModelResolver
    model_settings: ModelSettings | None = None

    async def merchant(self, description: str, counterparty: str | None, taxonomy: Taxonomy) -> Lookup:
        """Find out what a merchant is, from the cache or from the web."""
        token = scrub(description, counterparty)
        if not token:
            return Lookup(token="", error=token.reason)

        row = cached_lookup(self.session_factory, self.profile_id, token.text)
        if row is not None:
            return Lookup(
                token=row.merchant_token,
                summary=row.summary,
                category=row.category,
                subcategory=row.subcategory,
                confidence=row.confidence,
                sources=sources_of(row),
                searches=row.searches,
                fetches=row.fetches,
                cached=True,
            )

        try:
            # Sub-agents are pinned to the fast slot whatever the conversation runs on.
            model = self.resolve_model("fast")
        except ProviderNotAvailable as exc:
            return Lookup(token=token.text, error=f"The web lookup is unavailable: {exc}")

        outcome = await run_loop(
            model,
            token,
            taxonomy,
            client=self.client,
            journal=OutboundJournal(self.session_factory, self.profile_id, token.text),
            model_settings=self.model_settings,
        )
        return self._kept(outcome)

    def _kept(self, outcome: Outcome) -> Lookup:
        """Store what the loop concluded. A lookup with no conclusion is not cached: the next
        run may do better, and nothing was learned to hand out."""
        lookup = Lookup(
            token=outcome.token,
            summary=outcome.summary,
            category=outcome.category,
            subcategory=outcome.subcategory,
            confidence=outcome.confidence,
            sources=outcome.sources,
            searches=outcome.searches,
            fetches=outcome.fetches,
            error=outcome.error,
        )
        if lookup.summary:
            store_lookup(
                self.session_factory,
                self.profile_id,
                lookup.token,
                summary=lookup.summary,
                sources=lookup.sources,
                category=lookup.category,
                subcategory=lookup.subcategory,
                confidence=lookup.confidence,
                searches=lookup.searches,
                fetches=lookup.fetches,
            )
        return lookup


def lookups_for(
    session_factory: sessionmaker[Session],
    profile_id: str,
    *,
    client: WebClient,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> Lookups | None:
    """Web lookup for this profile, or `None` when the profile has it switched off.

    The one place the switch is read. Read per turn and per import, so switching it off in
    Settings takes effect on the next one.
    """
    with session_factory() as session:
        if not web_lookup_enabled(session, profile_id):
            return None
    return Lookups(
        session_factory=session_factory,
        profile_id=profile_id,
        client=client,
        resolve_model=resolve_model,
        model_settings=model_settings,
    )
