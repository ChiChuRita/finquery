"""Prototype of a shared `WebKnowledge` capability the sub-agents could call.

What it adds over today's `weblookup.service.Lookups.merchant`, which is one merchant at a
time and a per-profile SQL cache:

- a batch entry point (`about_many`) that scrubs every input, deduplicates by merchant token,
  answers refused tokens and cached tokens without a request, and runs the rest sequentially
  with a polite pause between lookups;
- one result shape (`Knowledge`) with the evidence a caller can show: summary, category,
  confidence, sources, the searches and fetches it took, seconds, and whether it came from the
  cache or was refused and why;
- a `resolve_store` entry for a receipt header, which is the same call with the header as the
  description and no counterparty.

It reuses `weblookup.scrub`, `weblookup.loop.run_loop` and `weblookup.client.HttpWebClient`
unchanged. The cache here is a JSON file so the prototypes can share it across runs; in the
app it would be the existing `web_lookup` table (per profile, keyed by token).

Interface sketch for the app (not built here):

    knowledge = web_knowledge_for(session_factory, profile_id, client=..., resolve_model=...)
    if knowledge is not None:                       # None when the switch is off
        facts = await knowledge.about_many([(row.description, row.counterparty), ...])
        store = await knowledge.resolve_store("Combi. Frisch. Nebenan.")

Callers: the categorizer's stage 2b (batch, the busiest unknown merchants first), the receipt
path (one header), the chat agent's `lookup_merchant` (one merchant, as today).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.categorize.merchants import fold, merchant_of
from finquery.weblookup.loop import run_loop
from finquery.weblookup.scrub import MAX_TOKEN_CHARS, MAX_TOKEN_WORDS, MIN_TOKEN_CHARS, MerchantToken, _informative, _LEGAL_FORMS, scrub

from common import MemoryJournal, RecordingClient, Sent

Taxonomy = tuple[tuple[str, tuple[str, ...]], ...]

LEGAL_FORM_WORDS = _LEGAL_FORMS | {"e", "v"}
"""`e.V.` folds to `e v`, which the scrubber's list does not carry."""


def widened_scrub(description: str, counterparty: str | None) -> MerchantToken:
    """Prototype of a person rule that reads the legal form before it counts words.

    Today's `scrub` drops `GmbH`, `AG`, `SE`, `KG`, `e.V.` as uninformative and then counts the
    words left, so "Sixt GmbH & Co Autovermietung KG" is two capitalized words and a person. A
    legal form anywhere in the counterparty is the strongest business signal a booking has, so
    here it short-circuits to business and the token is built exactly as `scrub` builds it.
    Everything without a legal form goes through today's rule unchanged.
    """
    raw = fold(counterparty or description).split()
    if not any(word in LEGAL_FORM_WORDS for word in raw):
        return scrub(description, counterparty)
    key = merchant_of(description, counterparty).key
    words = [word for word in key.split() if _informative(word)][:MAX_TOKEN_WORDS]
    token = " ".join(words)[:MAX_TOKEN_CHARS].strip()
    if len(token) < MIN_TOKEN_CHARS:
        return MerchantToken("", "There is no merchant name in that booking, only numbers and dates.")
    return MerchantToken(token)


PAUSE_SECONDS = 1.0
"""Between two lookups that reach the network. The module itself has no pause; the search
library's backend chain is the only politeness today."""


@dataclass
class Knowledge:
    """What the web knows about one merchant token, with the evidence."""

    token: str
    summary: str = ""
    category: str | None = None
    subcategory: str | None = None
    confidence: float = 0.0
    sources: list[dict[str, str]] = field(default_factory=list)
    searches: int = 0
    fetches: int = 0
    seconds: float = 0.0
    cached: bool = False
    refused: str | None = None
    error: str | None = None
    queries: list[str] = field(default_factory=list)
    fetched: list[str] = field(default_factory=list)

    @property
    def placed(self) -> bool:
        return bool(self.category)

    def as_row(self) -> dict[str, Any]:
        return asdict(self)


class WebKnowledge:
    def __init__(
        self,
        model: Model,
        model_settings: ModelSettings | None,
        taxonomy: Taxonomy,
        *,
        cache_path: Path,
        journal_entries: list[Sent] | None = None,
        pause: float = PAUSE_SECONDS,
    ) -> None:
        self.model = model
        self.model_settings = model_settings
        self.taxonomy = taxonomy
        self.cache_path = cache_path
        self.entries: list[Sent] = journal_entries if journal_entries is not None else []
        self.client = RecordingClient(self.entries)
        self.pause = pause
        self.cache: dict[str, dict[str, Any]] = {}
        if cache_path.exists():
            self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
        self._last_network = 0.0

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self.cache, indent=1, ensure_ascii=False), encoding="utf-8")

    async def about_one(self, description: str, counterparty: str | None = None, *, widened: bool = False) -> Knowledge:
        token = (widened_scrub if widened else scrub)(description, counterparty)
        if not token:
            return Knowledge(token="", refused=token.reason)
        if token.text in self.cache:
            row = dict(self.cache[token.text])
            row.update(cached=True, seconds=0.0, queries=[], fetched=[])
            return Knowledge(**row)

        waited = time.perf_counter() - self._last_network
        if waited < self.pause:
            await asyncio.sleep(self.pause - waited)
        before = len(self.entries)
        started = time.perf_counter()
        outcome = await run_loop(
            self.model,
            token,
            self.taxonomy,
            client=self.client,
            journal=MemoryJournal(token.text, self.entries),
            model_settings=self.model_settings,
        )
        self._last_network = time.perf_counter()
        mine = self.entries[before:]
        knowledge = Knowledge(
            token=outcome.token,
            summary=outcome.summary,
            category=outcome.category,
            subcategory=outcome.subcategory,
            confidence=outcome.confidence,
            sources=[{"url": s.url, "title": s.title} for s in outcome.sources],
            searches=outcome.searches,
            fetches=outcome.fetches,
            seconds=time.perf_counter() - started,
            error=outcome.error,
            queries=[e.target for e in mine if e.kind == "search"],
            fetched=[e.target for e in mine if e.kind == "fetch"],
        )
        # Same rule as the app: a lookup with no conclusion is not cached.
        if knowledge.summary:
            row = knowledge.as_row()
            row.pop("cached")
            self.cache[token.text] = row
            self._save()
        return knowledge

    async def about_many(self, merchants: list[tuple[str, str | None]]) -> list[Knowledge]:
        """One `Knowledge` per input, in order; a token that appears twice leaves once."""
        answers: dict[str, Knowledge] = {}
        results: list[Knowledge] = []
        for description, counterparty in merchants:
            token = scrub(description, counterparty)
            if token and token.text in answers:
                results.append(answers[token.text])
                continue
            knowledge = await self.about_one(description, counterparty)
            if token:
                answers[token.text] = knowledge
            results.append(knowledge)
        return results

    async def resolve_store(self, header: str) -> Knowledge:
        """The store or chain behind a receipt header, same path, no counterparty."""
        return await self.about_one(header, None)
