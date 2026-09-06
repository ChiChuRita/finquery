"""One entry point for web knowledge, used by the chat tool, the categorizer and the receipt.

`Lookups` is what a caller holds when the profile has web lookup switched on: it knows where to
write, whom to ask and what may leave. `lookups_for` is the only place the switch is read, so
"off" means the object does not exist and there is nothing to call.

Three ways in, one cache, one journal, one switch:

- `merchant(description, counterparty, taxonomy)`: one booking, for the chat tool.
- `merchants(pairs, taxonomy)`: a batch for one import run. It deduplicates by token, answers a
  refused or cached token without a request, and runs the rest one at a time with a pause
  between them, because five loops at once would be five conversations with the same search
  backend in the same second.
- `store(header, taxonomy)`: the shop behind a receipt header, which is the same call with the
  header as the description and no counterparty. Never the line items: a basket is personal,
  a shop's name is not.

The order inside `merchant` is the whole feature in five lines: scrub, refuse or continue, look
in the cache, run the loop, keep the result. A merchant token therefore leaves at most once per
profile.
"""

import asyncio
from collections.abc import Sequence
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
    pages_of,
    sources_of,
    store_lookup,
    web_lookup_enabled,
)

Taxonomy = tuple[tuple[str, tuple[str, ...]], ...]

PAUSE_SECONDS = 1.0
"""Between two lookups of one batch that both reach the network. The search library's backend
chain is the only other politeness there is, and an import of an unknown bank would otherwise
open five loops back to back."""


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
    evidence: str = ""
    """One sentence out of a snippet or a page, checked in code to occur there word for word."""
    evidence_url: str | None = None
    pages: list[str] = field(default_factory=list)
    """The URLs whose text was really read, so the card can link the page it says it read."""
    capped: bool = False
    """No source named the merchant, so the confidence was held down and the card says unsure."""
    cached: bool = False
    error: str | None = None

    @property
    def placed(self) -> bool:
        """True when it named a category, which is what the pipeline can act on."""
        return bool(self.category)

    @property
    def brief(self) -> str:
        """The one line a sub-agent gets when this lookup is context rather than an answer."""
        if not self.summary:
            return ""
        place = f" ({self.category}{f' > {self.subcategory}' if self.subcategory else ''})" if self.category else ""
        return f"{self.summary}{place}"

    def payload(self) -> dict[str, object]:
        """The `lookup_merchant` tool result. `sources` is what the transcript cites."""
        return {
            "merchant": self.token,
            "summary": self.summary,
            "category": self.category,
            "subcategory": self.subcategory,
            "confidence": round(self.confidence, 2),
            "capped": self.capped,
            "evidence": self.evidence,
            "evidence_url": self.evidence_url,
            "sources": [source.payload() for source in self.sources],
            "pages": self.pages,
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
    pause: float = PAUSE_SECONDS

    async def merchant(self, description: str, counterparty: str | None, taxonomy: Taxonomy) -> Lookup:
        """Find out what a merchant is, from the cache or from the web."""
        token = scrub(description, counterparty)
        if not token:
            return Lookup(token="", error=token.reason)

        cached = self._cached(token.text)
        if cached is not None:
            return cached

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

    async def merchants(
        self, pairs: Sequence[tuple[str, str | None]], taxonomy: Taxonomy, *, limit: int | None = None
    ) -> list[Lookup]:
        """One `Lookup` per input, in order. A token that appears twice leaves once.

        `limit` caps how many of them may reach the network; the rest come back as a lookup
        with no token and no error, which reads as "not looked up this run" to the caller.
        Refused and cached tokens cost nothing and are not counted against it.
        """
        answered: dict[str, Lookup] = {}
        results: list[Lookup] = []
        ran = 0
        for description, counterparty in pairs:
            token = scrub(description, counterparty)
            if not token:
                results.append(Lookup(token="", error=token.reason))
                continue
            if token.text in answered:
                results.append(answered[token.text])
                continue
            cached = self._cached(token.text)
            if cached is not None:
                answered[token.text] = cached
                results.append(cached)
                continue
            if limit is not None and ran >= limit:
                results.append(Lookup(token=""))
                continue
            if ran:
                await asyncio.sleep(self.pause)
            ran += 1
            found = await self.merchant(description, counterparty, taxonomy)
            answered[token.text] = found
            results.append(found)
        return results

    async def store(self, header: str, taxonomy: Taxonomy) -> Lookup:
        """The shop or chain behind a receipt header, through the same path and the same rules.

        A header is a printed shop name, so it goes in as the description with no counterparty.
        A header that is really an address ("Kreiller Str. 81673 Muenchen") or a person is
        refused by `scrub` the way a booking is, and the line items never come near this.
        """
        return await self.merchant(header, None, taxonomy)

    def _cached(self, token: str) -> Lookup | None:
        """What this profile already learned about this token, if anything."""
        row = cached_lookup(self.session_factory, self.profile_id, token)
        if row is None:
            return None
        return Lookup(
            token=row.merchant_token,
            summary=row.summary,
            category=row.category,
            subcategory=row.subcategory,
            confidence=row.confidence,
            capped=row.capped,
            sources=sources_of(row),
            searches=row.searches,
            fetches=row.fetches,
            evidence=row.evidence,
            evidence_url=row.evidence_url,
            pages=pages_of(row),
            cached=True,
        )

    def _kept(self, outcome: Outcome) -> Lookup:
        """Store what the loop concluded. A lookup with no conclusion is not cached: the next
        run may do better, and nothing was learned to hand out."""
        lookup = Lookup(
            token=outcome.token,
            summary=outcome.summary,
            category=outcome.category,
            subcategory=outcome.subcategory,
            confidence=outcome.confidence,
            capped=outcome.capped,
            sources=outcome.sources,
            searches=outcome.searches,
            fetches=outcome.fetches,
            evidence=outcome.evidence,
            evidence_url=outcome.evidence_url,
            pages=outcome.pages,
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
                evidence=lookup.evidence,
                evidence_url=lookup.evidence_url,
                pages=lookup.pages,
                capped=lookup.capped,
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
