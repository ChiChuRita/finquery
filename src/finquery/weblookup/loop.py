"""The self-directed lookup loop: the model decides the next step, our code takes it.

One step is one request to the fast slot with a forced single tool, `decide`, which says
`search` with a query, `fetch` with one of the URLs it has been shown, or `finish` with what
the merchant is, where it belongs and the sources it relied on. Our code executes that step,
appends the observation to the transcript and asks again. So the search strategy is the
model's and the actions are ours: nothing leaves except a query built from the merchant token,
and every request is written to the outbound log before it is made.

The budget (four searches, three fetches) is a ceiling, not a plan. The model is told what is
left and stops when it has enough. Four things hold the loop to the web rather than to what the
model remembers, and all four are code rather than prompt lines, because a stronger model
recalls instead of searching and then the elective's claim would depend on which model runs
(the review of 2026-09-06: 34 of 82 lookups finished without a single search, and not one ever
read a page):

- **the one-search floor**: a finish before any search is handed back once,
- **the forced fetch**: when a hit is the merchant's own site or a Wikipedia article about it
  and no page has been read, the loop fetches it and asks again before it accepts a finish,
- **the evidence quote**: a finish carries one sentence that has to occur verbatim in what the
  steps returned, checked here the way an extracted figure is checked against its page,
- **the confidence cap**: no source whose title or host carries the token means at most 0.6,
  because "hausverwaltung bergmann" matches a real company that is probably not this one.

A failed search backend is retried once in the same step, and that retry costs neither a model
call nor a search from the budget.

`lookup_prompt` is a pure function of the token, the taxonomy and the steps so far, so a
training row is the text the model saw plus the decision it made.
"""

import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.categorize.subagent import taxonomy_block
from finquery.weblookup.client import Hit, SearchUnavailable, WebClient
from finquery.weblookup.scrub import MerchantToken, safe_query
from finquery.weblookup.store import OK, Source, WebLookupOff

logger = logging.getLogger(__name__)

MAX_SEARCHES = 4
MAX_FETCHES = 3
MAX_STEPS = MAX_SEARCHES + MAX_FETCHES + 4
"""Loop guard: the budget plus a few rounds for a decision we could not use."""

PAGE_CHARS = 2000
"""How much of a fetched page the next prompt carries."""
MAX_SOURCES = 4

MIN_EVIDENCE_CHARS = 12
"""Shorter than this is not a sentence from a page, it is a word that happens to occur."""
NAME_CHARS = 4
"""How long a word of the token has to be before a host or a title is read as carrying it."""
CAPPED_CONFIDENCE = 0.6
"""What a finish is worth when no source names the merchant: enough to say, not enough to file
without asking (the pipeline's threshold is 0.75)."""

GENERIC_TOKENS = frozenset(
    {"zeit", "action", "shop", "markt", "online", "telecom", "energie", "cafe", "apotheke", "center"}
)
"""One-word tokens that are also ordinary words, so the first search comes back about anything.
The prompt suggests a second, narrower query for these; the model still decides."""

DECIDE_TOOL = "decide"
SEARCH, FETCH, FINISH = "search", "fetch", "finish"

INSTRUCTIONS = """\
You find out what an unknown merchant is, by searching the web yourself, so a German
household's bank transaction can be categorized.

You are given a merchant token, the household's category list, and what your own earlier steps
returned. The token is the only thing about this household that ever leaves the machine: there
are no amounts, no dates, no account numbers and no names in it, and you must never put
anything into a search query that you were not given.

Call `decide` exactly once. You never answer in words: the decision is the answer.
"""

RULES = """\
The three decisions:
- `search`: `query` is a short web query, at most eight words, about the merchant. Add at most
  a couple of plain words to the token ("what is", "shop", "was ist", "Unternehmen"). Never
  add a number or a date.
- `fetch`: `url` is one of the result URLs you were shown, copied exactly. Read a page when the
  snippets do not tell you what the merchant sells, and read the merchant's own site or its
  Wikipedia article when one of your results is that.
- `finish`: `summary` says in at most 200 characters what the merchant is and what it sells.
  `category` is one of the household's categories, spelled as listed, `subcategory` one of its
  subcategories or null. `sources` are the URLs you relied on, from what you were shown.
  `evidence` is one sentence copied **word for word** out of a snippet or a page above, the one
  that says what this merchant is. Copy it exactly, do not tidy it up and do not translate it:
  a quote that is not in your steps is handed back to you.

`confidence` goes with every decision: 0 for a search or a fetch, and for a finish your honest
number between 0.0 and 1.0. 0.9 or more when the sources name the trade plainly, 0.7 when they
are convincing but indirect, 0.5 or less when you are guessing between two categories. A finish
with a confidence of 0 counts as no answer, and then the household is asked instead of the
booking being filed.

Rules:
- Search first. Answering from what you already know about the merchant is not an answer here,
  and a finish before your first search is handed back to you.
- Then stop as soon as you know. One search and the one page it points at are usually enough,
  and finishing early is better than spending the budget.
- If the token is one word, or a word that means something else as well, a second query with
  "Unternehmen", "Firma" or the trade you suspect is worth more than a page read.
- Never answer `Unknown`: it is a category only a human assigns. If the sources do not say what
  this merchant is, finish with the closest category and a low confidence.
- Money in (a refund, a salary) is never a spending category.
- If the search says nothing about the merchant, finish and say so in the summary.

Fill `reasoning` first, in two to four very short lines: what the token looks like, what your
steps have already told you, which of the three actions follows from that, and, on a finish,
which source says so.

A worked lookup, both of its steps:

  The merchant token: dean david
  You have taken no step yet, so start with a search.
  reasoning:
  the token reads like a chain, not a person
  nothing known yet, so one search first
  a plain query, the token and two words, no number and no date
  -> action search, query "what is dean david restaurant", confidence 0

  Step 1: search "what is dean david restaurant"
    3 result(s)
    - dean&david: Salate, Bowls, Sandwiches | https://www.deandavid.de
      Frische Salate, Bowls und Sandwiches, in ueber 130 Filialen.
  reasoning:
  the first result is the chain's own page and names the trade plainly
  salads and bowls sold over a counter is takeaway, not a restaurant visit
  the sources say it outright, so a high confidence and no second search
  -> action finish, summary "German fast casual chain selling salads, bowls and sandwiches",
     category Dining, subcategory Takeaway, confidence 0.9,
     evidence "Frische Salate, Bowls und Sandwiches, in ueber 130 Filialen.",
     sources ["https://www.deandavid.de"]
"""


class Decision(BaseModel):
    """One step of the loop, as the model returns it.

    `reasoning` is first so the step is decided before it is written down: the observed failure
    is a second search for what the first one already answered (ticket 42).
    """

    reasoning: str = Field(
        description=(
            "Two to four very short lines, one each, written before the action: what the token "
            "looks like, what your steps have told you so far, which action follows, and on a "
            "finish which source says so."
        )
    )
    action: Literal["search", "fetch", "finish"] = Field(description="What to do next.")
    query: str | None = Field(default=None, description="The web query, for a search.")
    url: str | None = Field(default=None, description="One of the result URLs, for a fetch.")
    summary: str | None = Field(default=None, description="What the merchant is, for a finish.")
    category: str | None = Field(default=None, description="One of the household's categories, for a finish.")
    subcategory: str | None = Field(default=None, description="One of that category's subcategories, or null.")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="How sure you are that the category is right, 0.0 to 1.0. Send 0 for a search or a fetch.",
    )
    """Required, unlike every other field here, because the observed fast model leaves an
    optional float out and then nothing can be filed from what it found. A search decision has
    no confidence to give, so it sends 0, and a finish that sends 0 is asked once for a real
    one (see `run_loop`)."""
    evidence: str | None = Field(
        default=None,
        description=(
            "For a finish: one sentence copied word for word out of a snippet or a page above, "
            "the one that says what this merchant is. It is checked against your steps."
        ),
    )
    sources: list[str] = Field(default_factory=list, description="The URLs you relied on, for a finish.")


lookup_agent = Agent(
    instructions=INSTRUCTIONS,
    output_type=ToolOutput(Decision, name=DECIDE_TOOL),
    name="finquery-web-lookup",
)


class Journal(Protocol):
    """Where a request is written before it is made. `finquery.weblookup.store` implements it.

    `before` raises `WebLookupOff` when the profile has switched web lookup off since this loop
    started, which is how a running loop stops sending mid-way.
    """

    def before(self, kind: str, target: str) -> str: ...

    def after(self, handle: str, status: str) -> None: ...


@dataclass
class Step:
    """One executed step, as the next prompt reads it back."""

    kind: str
    target: str
    observation: str

    def as_prompt(self, index: int) -> str:
        return f'Step {index}: {self.kind} "{self.target}"\n{self.observation}'


def refused(decision: "Decision", finding: str, correction: str) -> Step:
    """A decision our code could not execute, written back as the step it was (ticket 42).

    The model's own reasoning is in front of the finding, because the next prompt is the same
    prompt again: without it the model reads the refusal as a new question and starts over,
    which is how a whole budget went on the same malformed decision.
    """
    return Step(
        decision.action,
        decision.query or decision.url or decision.category or "",
        f"  refused: {finding}\n"
        f"  you reasoned: {' '.join(line.strip() for line in decision.reasoning.splitlines() if line.strip())}\n"
        f"  {correction}",
    )


@dataclass
class Outcome:
    """What the loop came to. `category` is None when it reached no conclusion."""

    token: str
    summary: str = ""
    category: str | None = None
    subcategory: str | None = None
    confidence: float = 0.0
    sources: list[Source] = field(default_factory=list)
    searches: int = 0
    fetches: int = 0
    evidence: str = ""
    """The sentence the finish quoted, checked to occur in what the steps returned."""
    evidence_url: str | None = None
    """Which page or result that sentence was quoted from, when it could be told."""
    pages: list[str] = field(default_factory=list)
    """The URLs whose text was really read, in the order they were read."""
    capped: bool = False
    """True when no source's title or host carried the token, so the confidence was held down."""
    error: str | None = None


def _words_of(token: str) -> list[str]:
    """The parts of a token long enough to recognize in a host or a title."""
    return [word for word in token.split() if len(word) >= NAME_CHARS]


def _flat(text: str) -> str:
    return " ".join(text.split()).casefold()


def quoted_verbatim(quote: str, steps: list[Step]) -> bool:
    """Does this sentence really occur in what the steps returned?

    The same discipline as the extraction verbatim guard (ADR 0011): whitespace is normalized
    and case ignored, nothing else. A quote nobody was shown is a sentence the model wrote, and
    the whole point of the evidence is that it did not.
    """
    if len(quote.strip()) < MIN_EVIDENCE_CHARS:
        return False
    seen = _flat("\n".join(step.observation for step in steps))
    return _flat(quote) in seen


def own_page(token: str, seen: dict[str, Source]) -> str | None:
    """The first result that is the merchant's own site or a Wikipedia article about it.

    This is what the loop fetches before it lets a finish through, so "it visits pages and uses
    what is on them" is a property of the code and not of the model's mood. A token with no
    word of its own (`dm`, `o2`) has nothing to recognize a host by, so it forces nothing.
    """
    words = _words_of(token)
    if not words:
        return None
    for url in seen:
        host = urlparse(url).netloc.casefold().removeprefix("www.")
        name = host.split(".")[0].replace("-", "") if host else ""
        path = urlparse(url).path.casefold().replace("_", " ")
        if any(word in name for word in words):
            return url
        if "wikipedia.org" in host and any(word in path for word in words):
            return url
    return None


def names_the_token(token: str, sources: list[Source]) -> bool:
    """Does any source's title or host carry the merchant's name?

    A local token matches many real businesses ("hausverwaltung bergmann" found a property
    manager of that name, in another city, at 0.95). When nothing that came back names the
    merchant, the answer is about something else as easily as about this one.
    """
    words = _words_of(token) or token.split()
    for source in sources:
        haystack = _flat(f"{source.title} {urlparse(source.url).netloc}").replace("-", "")
        if any(word in haystack for word in words):
            return True
    return False


def lookup_prompt(
    token: str,
    taxonomy: tuple[tuple[str, tuple[str, ...]], ...],
    steps: list[Step],
    *,
    searches_left: int,
    fetches_left: int,
) -> str:
    """The whole prompt one step sees. Pure function, reused by training."""
    blocks = [taxonomy_block(taxonomy), RULES, f"The merchant token: {token}"]
    words = token.split()
    if len(words) == 1 or any(word in GENERIC_TOKENS for word in words):
        blocks.append(
            "That token is one word, or a word with an everyday meaning of its own, so a first "
            "search about it comes back about anything. If it does, search once more with "
            '"Unternehmen" or the trade you suspect added to it.'
        )
    if steps:
        taken = "\n\n".join(step.as_prompt(index + 1) for index, step in enumerate(steps))
        blocks.append(f"What your steps returned so far:\n\n{taken}")
    else:
        blocks.append("You have taken no step yet, so start with a search.")
    if searches_left <= 0 and fetches_left <= 0:
        blocks.append("You have no searches and no fetches left. Finish now with what you know.")
    else:
        blocks.append(
            f"Budget left: {searches_left} search(es) and {fetches_left} page fetch(es). "
            "Finish as soon as you know, whatever is left."
        )
    return "\n\n".join(blocks)


def _hit_lines(hits: list[Hit]) -> str:
    if not hits:
        return "  no results"
    return "\n".join(f"  - {hit.title} | {hit.url}\n    {hit.snippet}" for hit in hits)


def _sources_for(decision: Decision, seen: dict[str, Source], fetched: list[str]) -> list[Source]:
    """The URLs a finish may cite: only pages this loop really saw.

    A model that cites nothing gets the pages it read, or failing that the results it was
    shown, so the transcript can always show where the answer came from.
    """
    named = [seen[url] for url in decision.sources if url in seen]
    if named:
        return named[:MAX_SOURCES]
    if fetched:
        return [seen[url] for url in fetched if url in seen][:MAX_SOURCES]
    return list(seen.values())[:MAX_SOURCES]


def _quoted_from(quote: str, steps: list[Step]) -> str | None:
    """Which step's observation the evidence came out of, as a URL when the step has one."""
    flat = _flat(quote)
    for step in steps:
        if flat not in _flat(step.observation):
            continue
        if step.kind == FETCH:
            return step.target
        for line in step.observation.splitlines():
            if " | http" in line:
                return line.rsplit(" | ", 1)[-1].strip()
    return None


async def run_loop(
    model: Model,
    token: MerchantToken,
    taxonomy: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    client: WebClient,
    journal: Journal,
    model_settings: ModelSettings | None = None,
) -> Outcome:
    """Search until the model says it knows, or until the budget is spent."""
    steps: list[Step] = []
    seen: dict[str, Source] = {}
    fetched: list[str] = []
    outcome = Outcome(token=token.text)
    # A finish with a confidence of zero is handed back once. The field is required, but a
    # search decision is told to send zero, and the observed fast model then answers zero on
    # its finish too, where it means nothing can be filed. Handing it back twice would risk
    # losing a good summary, so a second zero is taken as it is: the household is asked.
    nudged = False
    # Each of the three rules below is enforced once per lookup, for the same reason: a model
    # that cannot satisfy one of them would otherwise spend the whole budget being corrected,
    # and half an answer is worth more than none.
    floored = quoted = forced = False
    # The last thing a search backend said, so a lookup that never got a single search through
    # reports that instead of "spent its budget", which names the wrong cause.
    search_failure: str | None = None
    failed_searches = 0
    retried = False

    async def search_once(query: str) -> tuple[list[Hit] | None, str | None]:
        """One search, journaled before it is sent. `None` hits plus a sentence when it failed."""
        handle = journal.before(SEARCH, query)
        try:
            hits = await client.search(query)
        except SearchUnavailable as exc:
            journal.after(handle, str(exc)[:120])
            return None, str(exc)
        journal.after(handle, OK)
        return hits, None

    for _ in range(MAX_STEPS):
        prompt = lookup_prompt(
            token.text,
            taxonomy,
            steps,
            searches_left=MAX_SEARCHES - outcome.searches,
            fetches_left=MAX_FETCHES - outcome.fetches,
        )
        try:
            result = await lookup_agent.run(prompt, model=model, model_settings=model_settings)
        except Exception as exc:  # noqa: BLE001 - a step that cannot be read ends the lookup
            logger.warning("the web lookup loop could not read a decision", exc_info=True)
            outcome.error = f"The lookup could not be run: {exc}"
            return outcome
        decision = result.output

        # A finish with a category and no summary is still a conclusion: the category is what
        # gets filed, the summary is what the card shows, and the local fast model writes the
        # first without the second. The summary then names the page it relied on.
        if decision.action == FINISH and not decision.summary and decision.category:
            relied = _sources_for(decision, seen, fetched)
            decision.summary = f"Filed under {decision.category}" + (f", from {relied[0].title}" if relied else "")
        if decision.action == FINISH and decision.summary:
            if not decision.confidence and not nudged:
                nudged = True
                steps.append(
                    refused(
                        decision,
                        "a finish needs `confidence` between 0.0 and 1.0, and a finish with 0 "
                        "files nothing.",
                        "Send this same summary and category again with your honest confidence "
                        "on it, and say in the first line of the reasoning what you changed.",
                    )
                )
                continue
            if not outcome.searches and not floored:
                floored = True
                steps.append(
                    refused(
                        decision,
                        "you have not searched even once, so this answer is what you remember "
                        "rather than what the web says, and it carries no source.",
                        "Send a `search` for this merchant first. Finish after you have seen "
                        "what came back, and quote it.",
                    )
                )
                continue
            # The forced fetch. The merchant's own page or its Wikipedia article is in front of
            # it and unread, so the loop reads it and asks again: one more model call and one
            # GET, and the difference between "it searched" and "it visited a page".
            page = own_page(token.text, seen) if not fetched else None
            if page is not None and not forced and outcome.fetches < MAX_FETCHES:
                forced = True
                try:
                    handle = journal.before(FETCH, page)
                except WebLookupOff as exc:
                    outcome.error = str(exc)
                    return outcome
                outcome.fetches += 1
                try:
                    read = await client.fetch(page)
                except Exception as exc:  # noqa: BLE001 - any transport failure is one observation
                    journal.after(handle, f"failed: {type(exc).__name__}")
                    steps.append(Step(FETCH, page, f"  failed: the page could not be read ({exc})"))
                    continue
                journal.after(handle, OK)
                fetched.append(page)
                seen[page] = Source(url=page, title=read.title or seen[page].title)
                steps.append(
                    Step(
                        FETCH,
                        page,
                        f"  read for you, because it is this merchant's own site or its "
                        f"Wikipedia article. Page text ({len(read.text)} characters):\n"
                        f"{read.text[:PAGE_CHARS]}",
                    )
                )
                continue
            quote = (decision.evidence or "").strip()
            if not quoted_verbatim(quote, steps) and not quoted:
                quoted = True
                steps.append(
                    refused(
                        decision,
                        "`evidence` has to be one sentence copied word for word out of a "
                        f"snippet or a page above, and {quote[:80]!r} is not in them."
                        if quote
                        else "a finish needs `evidence`: one sentence copied word for word out "
                        "of a snippet or a page above.",
                        "Send this same finish again with a sentence copied exactly from your "
                        "steps, and say in the first line of the reasoning where you took it "
                        "from.",
                    )
                )
                continue
            outcome.summary = decision.summary.strip()[:500]
            outcome.category = (decision.category or "").strip() or None
            outcome.subcategory = (decision.subcategory or "").strip() or None
            outcome.sources = _sources_for(decision, seen, fetched)
            outcome.pages = list(fetched)
            if quoted_verbatim(quote, steps):
                outcome.evidence = quote[:500]
                outcome.evidence_url = _quoted_from(quote, steps)
            confidence = min(1.0, max(0.0, decision.confidence))
            if not names_the_token(token.text, outcome.sources) and confidence > CAPPED_CONFIDENCE:
                outcome.capped = True
                confidence = CAPPED_CONFIDENCE
            outcome.confidence = confidence
            return outcome

        if decision.action == SEARCH and decision.query:
            if outcome.searches >= MAX_SEARCHES:
                steps.append(
                    refused(
                        decision,
                        "no searches left in the budget, so this one was not made.",
                        "Finish now with what the steps above already told you.",
                    )
                )
                continue
            query = safe_query(decision.query, token)
            try:
                hits, failure = await search_once(query)
            except WebLookupOff as exc:
                outcome.error = str(exc)
                return outcome
            # A backend that dropped the connection is not an answer about this merchant, and
            # before this it cost both a search from the budget and a model call to be told so
            # (F5). The one retry is free of both.
            if failure is not None and not retried:
                retried = True
                try:
                    hits, failure = await search_once(query)
                except WebLookupOff as exc:
                    outcome.error = str(exc)
                    return outcome
            outcome.searches += 1
            if failure is not None or hits is None:
                search_failure, failed_searches = failure, failed_searches + 1
                steps.append(Step(SEARCH, query, f"  failed: {failure}"))
                continue
            for hit in hits:
                seen[hit.url] = Source(url=hit.url, title=hit.title or hit.url)
            steps.append(Step(SEARCH, query, f"  {len(hits)} result(s)\n{_hit_lines(hits)}"))
            continue

        if decision.action == FETCH and decision.url:
            url = decision.url.strip()
            if url not in seen:
                steps.append(
                    refused(
                        decision,
                        "that URL was not in your results, so it was not fetched.",
                        "Send a fetch of one of the URLs above, copied exactly, or finish.",
                    )
                )
                continue
            if outcome.fetches >= MAX_FETCHES:
                steps.append(
                    refused(
                        decision,
                        "no page fetches left in the budget, so this one was not made.",
                        "Finish now with what the steps above already told you.",
                    )
                )
                continue
            try:
                handle = journal.before(FETCH, url)
            except WebLookupOff as exc:
                outcome.error = str(exc)
                return outcome
            outcome.fetches += 1
            try:
                page_read = await client.fetch(url)
            except Exception as exc:  # noqa: BLE001 - any transport or HTML failure is one observation
                journal.after(handle, f"failed: {type(exc).__name__}")
                steps.append(Step(FETCH, url, f"  failed: the page could not be read ({exc})"))
                continue
            journal.after(handle, OK)
            fetched.append(url)
            seen[url] = Source(url=url, title=page_read.title or seen[url].title)
            steps.append(Step(FETCH, url, f"  page text ({len(page_read.text)} characters):\n{page_read.text[:PAGE_CHARS]}"))
            continue

        # A decision without the field its action needs. Logged as it came, because the local
        # fast model has spent a whole budget on these and the transcript only shows the sum.
        logger.warning("web lookup step refused for %s: %s", token.text, decision.model_dump(exclude_none=True))
        needed = (
            "query" if decision.action == SEARCH else "url" if decision.action == FETCH else "summary and category"
        )
        steps.append(
            refused(
                decision,
                f"a {decision.action} needs its {needed}, and yours had none, so nothing was done.",
                f"Send this same decision again with the {needed} filled in, and say in the "
                f"first line of the reasoning what you changed.",
            )
        )

    outcome.error = (
        f"No web search went through: {search_failure}. Nothing was learned about this merchant."
        if failed_searches and failed_searches == outcome.searches
        else "The lookup spent its budget without reaching a conclusion."
    )
    outcome.sources = _sources_for(Decision(reasoning="", action=FINISH, confidence=0.0), seen, fetched)
    outcome.pages = list(fetched)
    return outcome
