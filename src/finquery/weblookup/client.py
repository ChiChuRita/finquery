"""The two things that touch the internet: a keyless search, and one page fetch.

Search goes through `ddgs`, which needs no key and takes a comma-separated chain of backends,
so a backend that rate-limits us is skipped rather than fatal. It is a synchronous library, so
it runs in a thread. Its `RatelimitException` is not raised by version 9.16, which reports a
rate limit as a `DDGSException` whose message carries the HTTP status, so both are handled.

A fetch is deliberately boring: one GET, ten seconds, a size cap, HTML to text with the
standard library, and at most one redirect, to the same host. Redirects are limited that way
rather than followed off-site because the loop writes the outbound log entry before it calls
this: a same-host hop keeps the log honest (same host, same token, one entry), while an
off-site hop would be a request to somewhere the log never named.

Both are behind `WebClient` so tests inject a stub through the app state and no test ever
reaches the network (ADR 0003).
"""

import asyncio
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import urlparse

import httpx

REGION = "de-de"
BACKENDS = "duckduckgo,bing,brave"
"""Tried in order; the first that answers wins."""
MAX_RESULTS = 5
SEARCH_TIMEOUT = 5
FETCH_TIMEOUT = 10.0
MAX_PAGE_BYTES = 300_000
MAX_SNIPPET_CHARS = 240
USER_AGENT = "FinQuery/0.1 (personal finance assistant; merchant lookup)"

SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head"}


class SearchUnavailable(RuntimeError):
    """The search backends refused (rate limit) or failed. The loop reports it and moves on."""


@dataclass(frozen=True)
class Hit:
    """One search result, as the loop shows it to the model."""

    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class Page:
    """One fetched page, already reduced to text."""

    url: str
    title: str
    text: str


class WebClient(Protocol):
    """What the lookup loop is allowed to do to the outside world, and nothing more."""

    async def search(self, query: str) -> list[Hit]: ...

    async def fetch(self, url: str) -> Page: ...


class _TextExtractor(HTMLParser):
    """HTML to text, enough for a merchant's own page or a Wikipedia article."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._chunks: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"p", "div", "li", "br", "h1", "h2", "h3", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data.strip()
        if not self._skip and data.strip():
            self._chunks.append(data.strip())

    @property
    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self._chunks).splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> tuple[str, str]:
    """The page's title and its readable text. Pure, so it is testable without a network."""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.title, parser.text


def _rate_limited(exc: Exception) -> bool:
    message = str(exc)
    return "HTTP 429" in message or "HTTP 403" in message or "atelimit" in message


@dataclass(frozen=True)
class HttpWebClient:
    """The real client: `ddgs` in a thread for a search, one `httpx` GET for a page."""

    backends: str = BACKENDS
    region: str = REGION
    max_results: int = MAX_RESULTS

    async def search(self, query: str) -> list[Hit]:
        try:
            rows = await asyncio.to_thread(self._search, query)
        except Exception as exc:  # noqa: BLE001 - every backend failure is one message to the loop
            if _rate_limited(exc):
                raise SearchUnavailable("the search backends are rate limiting us right now") from exc
            raise SearchUnavailable(f"the search failed: {exc}") from exc
        return [
            Hit(
                title=str(row.get("title") or "").strip(),
                url=str(row.get("href") or "").strip(),
                snippet=" ".join(str(row.get("body") or "").split())[:MAX_SNIPPET_CHARS],
            )
            for row in rows
            if row.get("href")
        ]

    def _search(self, query: str) -> list[dict[str, object]]:
        from ddgs import DDGS

        return DDGS(timeout=SEARCH_TIMEOUT).text(
            query, region=self.region, max_results=self.max_results, backend=self.backends
        )

    async def fetch(self, url: str) -> Page:
        """One page as text. A client per call: three fetches at most, so pooling buys nothing
        and there is no client to own or close."""
        async with httpx.AsyncClient(
            timeout=FETCH_TIMEOUT,
            follow_redirects=False,
            headers={"user-agent": USER_AGENT, "accept": "text/html,text/plain"},
        ) as client:
            response = await client.get(url)
            if response.is_redirect:
                target = str(response.next_request.url) if response.next_request else ""
                if not target or urlparse(target).netloc != urlparse(url).netloc:
                    raise httpx.HTTPError("the page redirects to another site, which is not followed")
                response = await client.get(target)
            response.raise_for_status()
            body = response.content[:MAX_PAGE_BYTES].decode(response.encoding or "utf-8", errors="replace")
        title, text = html_to_text(body)
        return Page(url=str(response.url), title=title or url, text=text)
