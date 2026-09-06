"""Shared plumbing for the web lookup prototypes: the hosted fast model with a token meter, an
in-memory outbound journal, a recording web client, and the default taxonomy.

Nothing here is production code. It reuses `finquery.weblookup` as it is and only adds the
instruments a measurement needs (time, tokens, what left, what came back).

Run every script from the repo root so `Settings` finds the copied `.env`:

    uv run python .scratch/finquery/prototypes/weblookup/run_lookups.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai.models import Model
from pydantic_ai.models.wrapper import WrapperModel

from finquery.providers import build_resolver, subagent_settings
from finquery.settings import Settings
from finquery.taxonomy import DEFAULT_TAXONOMY
from finquery.weblookup.client import Hit, HttpWebClient, Page

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
ROOT = HERE.parents[3]
MODEL_ID = "google/gemini-3.8-flash"
PRICE_IN, PRICE_OUT = 0.75 / 1_000_000, 3.75 / 1_000_000
"""OpenRouter list price of the model on 2026-09-06, USD per token, for the cost column."""

TAXONOMY = tuple((name, subs) for name, subs in DEFAULT_TAXONOMY.items())


def chdir_root() -> None:
    os.chdir(ROOT)


class Metered(WrapperModel):
    """Counts requests and tokens across everything that runs on this model."""

    def __init__(self, wrapped: Model) -> None:
        super().__init__(wrapped)
        self.requests = 0
        self.input_tokens = 0
        self.output_tokens = 0

    async def request(self, messages, model_settings, model_request_parameters):  # type: ignore[override]
        response = await super().request(messages, model_settings, model_request_parameters)
        self.requests += 1
        self.input_tokens += response.usage.input_tokens or 0
        self.output_tokens += response.usage.output_tokens or 0
        return response

    def snapshot(self) -> tuple[int, int, int]:
        return self.requests, self.input_tokens, self.output_tokens

    @property
    def cost_usd(self) -> float:
        return self.input_tokens * PRICE_IN + self.output_tokens * PRICE_OUT


def fast_model() -> tuple[Metered, Any]:
    """The hosted fast slot pinned to Gemini 3.8 Flash, plus the sub-agent settings."""
    chdir_root()
    settings = Settings(provider="openrouter", openrouter_fast_model=MODEL_ID, openrouter_quality_model=MODEL_ID)
    resolver = build_resolver(settings)
    return Metered(resolver("fast")), subagent_settings(settings)


@dataclass
class Sent:
    """One request that left, as the journal saw it: kind, target and how it ended."""

    token: str
    kind: str
    target: str
    status: str = "sent"
    seconds: float = 0.0
    note: str = ""


@dataclass
class MemoryJournal:
    """`weblookup.loop.Journal` in memory: the same before/after contract, no database."""

    token: str
    entries: list[Sent]

    def before(self, kind: str, target: str) -> str:
        self.entries.append(Sent(token=self.token, kind=kind, target=target))
        return str(len(self.entries) - 1)

    def after(self, handle: str, status: str) -> None:
        self.entries[int(handle)].status = status


@dataclass
class RecordingClient:
    """The real `HttpWebClient` with a stopwatch and a note of what came back."""

    journal_entries: list[Sent]
    inner: HttpWebClient = field(default_factory=HttpWebClient)

    def _last(self, kind: str, target: str) -> Sent | None:
        for entry in reversed(self.journal_entries):
            if entry.kind == kind and entry.target == target:
                return entry
        return None

    async def search(self, query: str) -> list[Hit]:
        started = time.perf_counter()
        try:
            hits = await self.inner.search(query)
        finally:
            entry = self._last("search", query)
            if entry is not None:
                entry.seconds = time.perf_counter() - started
        if entry is not None:
            entry.note = f"{len(hits)} hits: " + "; ".join(h.url for h in hits)
        return hits

    async def fetch(self, url: str) -> Page:
        started = time.perf_counter()
        entry = self._last("fetch", url)
        try:
            page = await self.inner.fetch(url)
        except Exception as exc:
            if entry is not None:
                entry.seconds = time.perf_counter() - started
                entry.note = f"failed: {type(exc).__name__}: {str(exc)[:80]}"
            raise
        if entry is not None:
            entry.seconds = time.perf_counter() - started
            entry.note = f"{len(page.text)} chars, title {page.title[:60]!r}"
        return page


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=_plain), encoding="utf-8")


def _plain(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


def run(coro: Any) -> Any:
    return asyncio.run(coro)
