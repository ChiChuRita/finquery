"""The self-directed lookup loop: the model decides the next step, our code takes it.

One step is one request to the fast slot with a forced single tool, `decide`, which says
`search` with a query, `fetch` with one of the URLs it has been shown, or `finish` with what
the merchant is, where it belongs and the sources it relied on. Our code executes that step,
appends the observation to the transcript and asks again. So the search strategy is the
model's and the actions are ours: nothing leaves except a query built from the merchant token,
and every request is written to the outbound log before it is made.

The budget (four searches, three fetches) is a ceiling, not a plan. The model is told what is
left and stops when it has enough, which for a well-known merchant is after the first search.
Once both budgets are gone it is asked to finish with what it has; a model that still does not
finish yields a lookup with no category, which simply leaves the merchant to the categorizer
and the Question card.

`lookup_prompt` is a pure function of the token, the taxonomy and the steps so far, so a
training row is the text the model saw plus the decision it made.
"""

import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.categorize.subagent import taxonomy_block
from finquery.weblookup.client import Hit, SearchUnavailable, WebClient
from finquery.weblookup.scrub import MerchantToken, safe_query
from finquery.weblookup.store import OK, Source

logger = logging.getLogger(__name__)

MAX_SEARCHES = 4
MAX_FETCHES = 3
MAX_STEPS = MAX_SEARCHES + MAX_FETCHES + 3
"""Loop guard: the budget plus a few rounds for a decision we could not use."""

PAGE_CHARS = 2000
"""How much of a fetched page the next prompt carries."""
MAX_SOURCES = 4

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
  snippets do not tell you what the merchant sells.
- `finish`: `summary` says in at most 200 characters what the merchant is and what it sells.
  `category` is one of the household's categories, spelled as listed, `subcategory` one of its
  subcategories or null. `sources` are the URLs you relied on, from what you were shown.

`confidence` goes with every decision: 0 for a search or a fetch, and for a finish your honest
number between 0.0 and 1.0. 0.9 or more when the sources name the trade plainly, 0.7 when they
are convincing but indirect, 0.5 or less when you are guessing between two categories. A finish
with a confidence of 0 counts as no answer, and then the household is asked instead of the
booking being filed.

Rules:
- Stop as soon as you know. One search is usually enough, and finishing early is better than
  spending the budget.
- Never answer `Unknown`: it is a category only a human assigns. If the sources do not say what
  this merchant is, finish with the closest category and a low confidence.
- Money in (a refund, a salary) is never a spending category.
- If the search says nothing about the merchant, finish and say so in the summary.
"""


class Decision(BaseModel):
    """One step of the loop, as the model returns it."""

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
    sources: list[str] = Field(default_factory=list, description="The URLs you relied on, for a finish.")


lookup_agent = Agent(
    instructions=INSTRUCTIONS,
    output_type=ToolOutput(Decision, name=DECIDE_TOOL),
    name="finquery-web-lookup",
)


class Journal(Protocol):
    """Where a request is written before it is made. `finquery.weblookup.store` implements it."""

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
    error: str | None = None


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

        if decision.action == FINISH and decision.summary:
            if not decision.confidence and not nudged:
                nudged = True
                steps.append(
                    Step(
                        FINISH,
                        decision.category or "",
                        "  refused: a finish needs `confidence` between 0.0 and 1.0. Send the same "
                        "answer again with one.",
                    )
                )
                continue
            outcome.summary = decision.summary.strip()[:500]
            outcome.category = (decision.category or "").strip() or None
            outcome.subcategory = (decision.subcategory or "").strip() or None
            outcome.confidence = min(1.0, max(0.0, decision.confidence))
            outcome.sources = _sources_for(decision, seen, fetched)
            return outcome

        if decision.action == SEARCH and decision.query:
            if outcome.searches >= MAX_SEARCHES:
                steps.append(Step(SEARCH, decision.query, "  refused: no searches left in the budget"))
                continue
            query = safe_query(decision.query, token)
            handle = journal.before(SEARCH, query)
            outcome.searches += 1
            try:
                hits = await client.search(query)
            except SearchUnavailable as exc:
                journal.after(handle, str(exc)[:120])
                steps.append(Step(SEARCH, query, f"  failed: {exc}"))
                continue
            journal.after(handle, OK)
            for hit in hits:
                seen[hit.url] = Source(url=hit.url, title=hit.title or hit.url)
            steps.append(Step(SEARCH, query, f"  {len(hits)} result(s)\n{_hit_lines(hits)}"))
            continue

        if decision.action == FETCH and decision.url:
            url = decision.url.strip()
            if url not in seen:
                steps.append(Step(FETCH, url, "  refused: that URL was not in your results"))
                continue
            if outcome.fetches >= MAX_FETCHES:
                steps.append(Step(FETCH, url, "  refused: no page fetches left in the budget"))
                continue
            handle = journal.before(FETCH, url)
            outcome.fetches += 1
            try:
                page = await client.fetch(url)
            except Exception as exc:  # noqa: BLE001 - any transport or HTML failure is one observation
                journal.after(handle, f"failed: {type(exc).__name__}")
                steps.append(Step(FETCH, url, f"  failed: the page could not be read ({exc})"))
                continue
            journal.after(handle, OK)
            fetched.append(url)
            seen[url] = Source(url=url, title=page.title or seen[url].title)
            steps.append(Step(FETCH, url, f"  page text ({len(page.text)} characters):\n{page.text[:PAGE_CHARS]}"))
            continue

        steps.append(Step(decision.action, "", "  refused: that decision was missing what it needs"))

    outcome.error = "The lookup spent its budget without reaching a conclusion."
    outcome.sources = _sources_for(Decision(action=FINISH, confidence=0.0), seen, fetched)
    return outcome
