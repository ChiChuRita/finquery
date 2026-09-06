"""Self-directed web lookup, asserted at the HTTP seam with a scripted search and fetch client.

The stub is injected through the app factory (`web_client=`), so what "leaves the machine" in a
test is exactly the list of calls it recorded, and `GET /api/outbound-log` is what the user
would see in Settings. No test here touches the network: every other test module gets
`conftest.NoWeb`, which fails when it is called at all.

The loop's model is scripted through its forced `decide` tool. The scripts are stateless
functions of the prompt (the token and how many steps have run), so several lookups in one turn
can be answered in any order.
"""

import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall

from finquery.categorize.subagent import MerchantBatchEntry
from finquery.extract.bill import Store
from finquery.weblookup import Hit, Page, SearchUnavailable, has_legal_form, scrub

from .conftest import (
    Chat,
    Scripts,
    distilled,
    is_distillation_request,
    is_followup_request,
    new_conversation,
    parse_sse,
)
from .test_categorization import READING, categorize, keys_in, last_import, outputs_of, rows_of
from .test_chat_import import attach
from .test_extraction import OBI_BILL, bill_reader, importing
from .test_query import import_synthetic

TOKEN = re.compile(r"^The merchant token: (?P<token>.+)$", re.MULTILINE)
STEP = re.compile(r"^Step \d+:", re.MULTILINE)
URL = re.compile(r"https?://\S+")


def urls_in(prompt: str) -> list[str]:
    """The URLs this loop really saw, which is the steps section and not the worked example.

    The prompt teaches the shape of a lookup with a search result and a source in it, so a
    search over the whole text would hand the script a URL nobody was shown."""
    heading = "What your steps returned so far:"
    return URL.findall(prompt.rsplit(heading, 1)[-1]) if heading in prompt else []


KARLS = "KARTENZAHLUNG KARLS DANKT 12,50 EUR 03.05.2025"
KARLS_HITS = [
    Hit("Karls Erdbeerhof - Wikipedia", "https://de.wikipedia.org/wiki/Karls", "A chain of strawberry farms"),
    Hit("Karls Erlebnis-Dorf", "https://www.karls.de/", "Farm shop, jam, and an adventure village"),
]
KARLS_PAGE = "Karls Erlebnis-Dorf sells strawberries, jam and farm produce in its shops."


# The stub, and the fixture that puts it into the app in place of the real client.


@dataclass
class StubWeb:
    """A scripted search and fetch client that records every call it was asked to make."""

    hits: list[Hit] = field(default_factory=lambda: list(KARLS_HITS))
    by_query: dict[str, list[Hit]] = field(default_factory=dict)
    """Hits for a query whose results matter, matched on a word of it. Everything else gets
    `hits`, which is about Karls."""
    page: str = KARLS_PAGE
    calls: list[tuple[str, str]] = field(default_factory=list)
    fail_with: str | None = None
    fail_times: int | None = None
    """How many of the failures to raise before answering normally. None is forever."""
    watch: Callable[[], Awaitable[None]] | None = None
    """Run before a call is answered: how a test sees the world as the request goes out."""

    async def search(self, query: str) -> list[Hit]:
        self.calls.append(("search", query))
        if self.watch is not None:
            await self.watch()
        if self.fail_with is not None and (self.fail_times is None or self.fail_times > 0):
            if self.fail_times is not None:
                self.fail_times -= 1
            raise SearchUnavailable(self.fail_with)
        for word, hits in self.by_query.items():
            if word in query:
                return list(hits)
        return list(self.hits)

    async def fetch(self, url: str) -> Page:
        self.calls.append(("fetch", url))
        if self.watch is not None:
            await self.watch()
        return Page(url=url, title="Karls Erlebnis-Dorf", text=self.page)

    @property
    def searches(self) -> list[str]:
        return [target for kind, target in self.calls if kind == "search"]

    @property
    def fetches(self) -> list[str]:
        return [target for kind, target in self.calls if kind == "fetch"]


@pytest.fixture
def web_client() -> StubWeb:
    return StubWeb()


# The scripted models.


def _last_user_prompt(messages: Sequence[ModelMessage]) -> str:
    prompts = [
        part.content
        for message in messages
        for part in message.parts
        if part.part_kind == "user-prompt" and isinstance(part.content, str)
    ]
    return prompts[-1] if prompts else ""


def _decide(**decision: Any) -> ModelResponse:
    # `confidence` is required on every decision, so a search sends zero the way the prompt says,
    # and `reasoning` is the field the model fills before it decides anything.
    decision.setdefault("confidence", 0.0)
    decision.setdefault("reasoning", f"the token reads like a business\nso: {decision.get('action')}")
    return ModelResponse(parts=[ToolCallPart("decide", json.dumps(decision))])


Decider = Callable[[str, str, int], ModelResponse]
"""A decision as a function of the prompt, the merchant token and the steps taken so far."""


def fast_slot(decide: Decider, guesses: dict[str, tuple[str, str | None, float]] | None = None):
    """The fast slot for these tests: the lookup loop, the categorizer, and the post-turn steps.

    Everything the fast slot is asked in a turn is answered here, so what a test observes is
    only ever the lookup loop. `prompts` records every loop prompt, which is how a test sees
    what the model was shown at each step, and `categorizer` records what reached stage three.
    """
    prompts: list[str] = []
    categorizer: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if is_followup_request(messages):
            return ModelResponse(parts=[TextPart(content="No follow-ups.")])
        if is_distillation_request(messages):
            return ModelResponse(parts=[distilled()])
        tools = [tool.name for tool in info.output_tools]
        prompt = _last_user_prompt(messages)
        if tools == ["decide"]:
            assert info.allow_text_output is False, "the loop forces a single tool"
            prompts.append(prompt)
            match = TOKEN.search(prompt)
            assert match is not None, prompt
            return decide(prompt, match.group("token"), len(STEP.findall(prompt)))
        assert tools == ["categorize"], tools
        categorizer.append(prompt)
        merchants = [
            {
                "key": key,
                "category": (guesses or {}).get(key, ("Transfers", "Friends and family", 0.4))[0],
                "subcategory": (guesses or {}).get(key, ("Transfers", "Friends and family", 0.4))[1],
                "confidence": (guesses or {}).get(key, ("Transfers", "Friends and family", 0.4))[2],
                "title": key.title(),
                "description": "guessed by the model",
            }
            for key in keys_in(prompt)
        ]
        return ModelResponse(
            parts=[ToolCallPart("categorize", json.dumps({"reasoning": READING, "merchants": merchants}))]
        )

    respond.prompts = prompts  # type: ignore[attr-defined]
    respond.categorizer = categorizer  # type: ignore[attr-defined]
    return respond


def quote_in(prompt: str) -> str:
    """A sentence out of what the steps really returned, which is what `evidence` has to be.

    The scripts quote the last line of the newest step, the way a model copying a snippet or a
    sentence of a page would. A script that quotes anything else is testing the guard.
    """
    heading = "What your steps returned so far:"
    tail = prompt.rsplit(heading, 1)[-1] if heading in prompt else ""
    # The budget sentence sits under the steps and is not something anybody returned.
    tail = tail.split("Budget left:")[0].split("You have no searches")[0]
    lines = [line.strip() for line in tail.splitlines() if len(line.strip()) >= 12 and "http" not in line]
    return lines[-1] if lines else ""


def searches_then_finishes(
    times: int = 1,
    *,
    summary: str = "Karls Erdbeerhof, a chain of strawberry farms with farm shops",
    category: str = "Groceries",
    subcategory: str | None = "Supermarket",
    confidence: float = 0.85,
) -> Decider:
    """Search `times` times, then finish, quoting what the last step returned."""

    def decide(prompt: str, token: str, steps: int) -> ModelResponse:
        if steps < times:
            return _decide(action="search", query=f"what is {token}")
        return _decide(
            action="finish",
            summary=summary,
            category=category,
            subcategory=subcategory,
            confidence=confidence,
            evidence=quote_in(prompt),
            sources=urls_in(prompt)[:2],
        )

    return decide


def searches_then_reads_then_finishes() -> Decider:
    """One search, one page, then finish citing the page it read."""

    def decide(prompt: str, token: str, steps: int) -> ModelResponse:
        if steps == 0:
            return _decide(action="search", query=f"what is {token}")
        if steps == 1:
            return _decide(action="fetch", url=urls_in(prompt)[-1])
        return _decide(
            action="finish",
            summary="Karls Erlebnis-Dorf sells strawberries and jam",
            category="Groceries",
            subcategory="Supermarket",
            confidence=0.9,
            evidence=KARLS_PAGE,
            sources=[urls_in(prompt)[-1]],
        )

    return decide


def finishes_with_no_confidence() -> Decider:
    """Finishes with a confidence of zero, then a real one once the loop hands the finish back."""

    def decide(prompt: str, token: str, steps: int) -> ModelResponse:
        if steps == 0:
            return _decide(action="search", query=f"what is {token}")
        return _decide(
            action="finish",
            summary="a chain of strawberry farms",
            category="Groceries",
            subcategory="Supermarket",
            evidence=quote_in(prompt),
            sources=urls_in(prompt)[:1],
            confidence=0.8 if "needs `confidence`" in prompt else 0.0,
        )

    return decide


def never_stops(action: str = "search") -> Decider:
    """A model that never decides it knows enough. The budget is what stops it."""

    def decide(prompt: str, token: str, _steps: int) -> ModelResponse:
        if action == "fetch":
            urls = urls_in(prompt)
            if not urls:
                return _decide(action="search", query=token)
            return _decide(action="fetch", url=urls[0])
        return _decide(action="search", query=f"{token} shop")

    return decide


# The chat turn that calls the tool.


def _tool_returns(messages: list[ModelMessage], name: str) -> list[dict[str, Any]]:
    """The results this turn's own tool calls came back with."""
    found: list[dict[str, Any]] = []
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == name and isinstance(part.content, dict):
                found.append(part.content)
            elif part.part_kind == "user-prompt":
                return list(reversed(found))
    return list(reversed(found))


def asks_about(*merchants: str):
    """A chat turn that looks each merchant up and then reports what came back.

    The report is read out of the tool results in the history, so anything the answer says
    provably came from the tool. `declared` is the tools the model was offered, which is how a
    test sees that `lookup_merchant` is absent while the switch is off.
    """
    declared: list[list[str]] = []

    async def fn(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        declared.append(sorted(tool.name for tool in info.function_tools))
        results = _tool_returns(messages, "lookup_merchant")
        if not results:
            for index, merchant in enumerate(merchants):
                yield {index: DeltaToolCall(name="lookup_merchant", json_args=json.dumps({"merchant": merchant}))}
            return
        yield " | ".join(f"{r['merchant']}: {r.get('summary') or r.get('error')}" for r in results)

    fn.declared = declared  # type: ignore[attr-defined]
    return fn


# Helpers over the endpoints.


async def settings_of(client: httpx.AsyncClient, profile_id: str) -> dict[str, Any]:
    response = await client.get("/api/settings", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return dict(response.json())


async def switch_web_lookup(client: httpx.AsyncClient, profile_id: str, on: bool) -> dict[str, Any]:
    response = await client.patch("/api/settings", json={"profile_id": profile_id, "web_lookup_enabled": on})
    assert response.status_code == 200, response.text
    return dict(response.json())


async def outbound_log(client: httpx.AsyncClient, profile_id: str) -> list[dict[str, Any]]:
    response = await client.get("/api/outbound-log", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return list(response.json())


def answer(chunks: list[dict[str, object]]) -> str:
    return "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta").strip()


def outputs(chunks: list[dict[str, object]]) -> list[dict[str, Any]]:
    return [c["output"] for c in chunks if c["type"] == "tool-output-available"]  # type: ignore[misc]


def instructions_of(messages: Sequence[ModelMessage]) -> str:
    return str(getattr(messages[-1], "instructions", "") or "")


# The tests.


async def test_off_by_default_means_no_tool_and_no_request(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    assert (await settings_of(client, profile_id))["web_lookup_enabled"] is False

    prompts: list[str] = []

    async def turn(messages: list[ModelMessage], info: AgentInfo) -> AsyncIterator[object]:
        if not is_followup_request(messages) and not is_distillation_request(messages):
            prompts.append(instructions_of(messages))
            assert "lookup_merchant" not in [tool.name for tool in info.function_tools]
        if is_distillation_request(messages):
            yield distilled()
            return
        yield "I cannot look that up."

    scripts.fast = turn
    conversation_id = await new_conversation(client, profile_id)
    await chat(conversation_id, "Was ist KARLS DANKT?")

    assert web_client.calls == [], "nothing may leave the machine while the switch is off"
    assert await outbound_log(client, profile_id) == []
    # The prompt says it is off and where to switch it on.
    assert "web lookup is switched off" in prompts[0]
    assert "Settings" in prompts[0]


async def test_switching_it_on_declares_the_tool_and_only_the_token_leaves(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    assert (await switch_web_lookup(client, profile_id, True))["web_lookup_enabled"] is True
    turn = asks_about(KARLS)
    scripts.fast = turn
    scripts.fast_call = fast_slot(searches_then_finishes())  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Was ist KARLS DANKT?")

    assert "lookup_merchant" in turn.declared[0]  # type: ignore[attr-defined]
    # The booking carried an amount and a date. Only the merchant token left.
    assert web_client.searches == ["what is karls"]
    # One of the results is a Wikipedia article about the token, so the loop read it before it
    # took the finish, whatever the model asked for. See the forced-fetch test below.
    assert web_client.fetches == ["https://de.wikipedia.org/wiki/Karls"]
    found = outputs(chunks)[0]
    assert found["merchant"] == "karls"
    assert found["category"] == "Groceries"
    assert found["subcategory"] == "Supermarket"
    assert found["confidence"] == 0.85
    assert found["searches"] == 1
    assert found["fetches"] == 1
    assert found["pages"] == ["https://de.wikipedia.org/wiki/Karls"]
    assert found["cached"] is False
    assert [source["url"] for source in found["sources"]] == [hit.url for hit in KARLS_HITS]
    assert "strawberry farms" in answer(chunks)

    entries = await outbound_log(client, profile_id)
    assert [(e["kind"], e["target"], e["merchant_token"], e["status"]) for e in entries] == [
        ("fetch", "https://de.wikipedia.org/wiki/Karls", "karls", "ok"),
        ("search", "what is karls", "karls", "ok"),
    ]


async def test_the_scrubber_keeps_amounts_dates_numbers_and_names_at_home(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    await switch_web_lookup(client, profile_id, True)
    scripts.fast = asks_about(
        "KARTENZAHLUNG XBOX GAME PASS 12,99 EUR 03.05.2025",
        "UEBERWEISUNG DE89370400440532013000 REF 8841",
        "PP.4711.PP . ANNA WEBER, Ihre Zahlung",
        "Mustermann Systems GmbH GEHALT 03/2025 PERS.NR 4711",
    )
    scripts.fast_call = fast_slot(searches_then_finishes())  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Was sind diese vier Buchungen?")

    # The amount, the date, the IBAN, the reference and the staff number are all gone, and the
    # person's name never became a request at all.
    assert sorted(web_client.searches) == [
        "what is mustermann systems gehalt",
        "what is xbox game pass",
    ]
    found = outputs(chunks)
    assert {row["merchant"] for row in found} == {"xbox game pass", "mustermann systems gehalt", ""}
    # Two of the four had nothing that could be sent, each for its own reason.
    refusals = " | ".join(str(row["error"]) for row in found if row["merchant"] == "")
    assert "person's name never leaves" in refusals
    assert "only numbers and dates" in refusals
    # Nothing but a merchant token is in the log, for any of them.
    entries = await outbound_log(client, profile_id)
    assert sorted(e["merchant_token"] for e in entries) == ["mustermann systems gehalt", "xbox game pass"]
    for entry in entries:
        assert not re.search(r"\d", entry["target"]), entry
        assert "weber" not in entry["target"].casefold()


async def test_the_log_entry_is_written_before_the_request(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    await switch_web_lookup(client, profile_id, True)
    seen: list[list[dict[str, Any]]] = []

    async def snapshot() -> None:
        """What Settings would show at the moment the request is going out."""
        seen.append(await outbound_log(client, profile_id))

    web_client.watch = snapshot
    scripts.fast = asks_about(KARLS)
    scripts.fast_call = fast_slot(searches_then_reads_then_finishes())  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    await chat(conversation_id, "Was ist KARLS DANKT?")

    # The search was already in the log when the search went out, and so was the fetch.
    assert [(e["kind"], e["status"]) for e in seen[0]] == [("search", "sent")]
    assert [(e["kind"], e["status"]) for e in seen[1]] == [("fetch", "sent"), ("search", "ok")]
    assert [(e["kind"], e["target"], e["status"]) for e in await outbound_log(client, profile_id)] == [
        ("fetch", KARLS_HITS[-1].url, "ok"),
        ("search", "what is karls", "ok"),
    ]


async def test_the_page_it_reads_reaches_the_next_step(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    await switch_web_lookup(client, profile_id, True)
    scripts.fast = asks_about(KARLS)
    slot = fast_slot(searches_then_reads_then_finishes())
    scripts.fast_call = slot  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Was ist KARLS DANKT?")

    prompts: list[str] = slot.prompts  # type: ignore[attr-defined]
    assert len(prompts) == 3, "one prompt per step: search, fetch, finish"
    assert "You have taken no step yet" in prompts[0]
    assert KARLS_HITS[0].snippet in prompts[1]
    assert KARLS_PAGE in prompts[2]
    assert "3 search(es) and 2 page fetch(es)" in prompts[2]
    found = outputs(chunks)[0]
    assert (found["searches"], found["fetches"]) == (1, 1)
    assert [source["url"] for source in found["sources"]] == [KARLS_HITS[-1].url]


async def test_a_finish_with_no_confidence_is_handed_back_once(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    await switch_web_lookup(client, profile_id, True)
    scripts.fast = asks_about(KARLS)
    slot = fast_slot(finishes_with_no_confidence())
    scripts.fast_call = slot  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Was ist KARLS DANKT?")

    found = outputs(chunks)[0]
    assert found["confidence"] == 0.8, "the second finish carried one"
    assert found["category"] == "Groceries"
    # Handing the finish back costs a model round trip, never a second request to the web: the
    # one search and the page the loop read for itself are all that went out.
    assert len(web_client.calls) == 2
    # The refusal is framed as a correction of that decision: what was wrong with it, the
    # model's own reasoning, and what to send instead (ticket 42).
    handed_back = slot.prompts[-1]  # type: ignore[attr-defined]
    assert "needs `confidence`" in handed_back
    assert "you reasoned: the token reads like a business so: finish" in handed_back
    assert "Send this same summary and category again with your honest confidence" in handed_back


async def test_a_cache_hit_avoids_a_second_request(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    await switch_web_lookup(client, profile_id, True)
    scripts.fast = asks_about(KARLS)
    scripts.fast_call = fast_slot(searches_then_finishes())  # type: ignore[assignment]
    first = await new_conversation(client, profile_id)
    await chat(first, "Was ist KARLS DANKT?")
    assert len(web_client.calls) == 2

    # The same merchant, spelled differently, in another conversation.
    scripts.fast = asks_about("KARLS DANKT 4,20 EUR")
    second = await new_conversation(client, profile_id)
    _, chunks = await chat(second, "Und was ist KARLS?")

    assert len(web_client.calls) == 2, "a merchant token leaves at most once per profile"
    assert len(await outbound_log(client, profile_id)) == 2
    found = outputs(chunks)[0]
    assert found["cached"] is True
    assert found["category"] == "Groceries"
    assert "strawberry farms" in found["summary"]
    assert [source["url"] for source in found["sources"]] == [hit.url for hit in KARLS_HITS]
    # The card of a cache hit says the same things as the card that filled it, so the evidence
    # and the page it read are kept with the summary.
    assert found["evidence"] == KARLS_PAGE
    assert found["pages"] == ["https://de.wikipedia.org/wiki/Karls"]


async def test_the_budget_is_the_ceiling_when_the_model_never_stops(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    await switch_web_lookup(client, profile_id, True)
    scripts.fast = asks_about(KARLS)
    slot = fast_slot(never_stops("search"))
    scripts.fast_call = slot  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Was ist KARLS DANKT?")

    assert web_client.searches == ["karls shop"] * 4, "four searches, the budget, and no more"
    found = outputs(chunks)[0]
    assert found["searches"] == 4
    assert found["error"] is not None and "budget" in found["error"]
    # It was told what it had left, and its refused steps are in front of it.
    last = slot.prompts[-1]  # type: ignore[attr-defined]
    assert "Budget left: 0 search(es)" in last
    assert "refused: no searches left in the budget" in last

    # The same for page reads: three, whatever the model asks for.
    scripts.fast = asks_about("KARTENZAHLUNG NORDSEE FILIALE 12")
    scripts.fast_call = fast_slot(never_stops("fetch"))  # type: ignore[assignment]
    await chat(await new_conversation(client, profile_id), "Und das?")

    assert len(web_client.fetches) == 3


async def test_a_search_that_fails_is_reported_and_not_cached(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    await switch_web_lookup(client, profile_id, True)
    web_client.fail_with = "the search backends are rate limiting us right now"
    scripts.fast = asks_about(KARLS)
    scripts.fast_call = fast_slot(never_stops("search"))  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Was ist KARLS DANKT?")

    # The sentence names what actually happened, not the budget it happened to spend.
    assert outputs(chunks)[0]["error"] == (
        "No web search went through: the search backends are rate limiting us right now. "
        "Nothing was learned about this merchant."
    )
    entries = await outbound_log(client, profile_id)
    # Four searches of the budget, and the free retry the first failure was given: five
    # requests, none of which came back with anything.
    assert [e["status"] for e in entries] == ["the search backends are rate limiting us right now"] * 5
    # Nothing was learned, so the next attempt is free to try again.
    web_client.fail_with = None
    scripts.fast = asks_about(KARLS)
    scripts.fast_call = fast_slot(searches_then_finishes())  # type: ignore[assignment]
    _, again = await chat(await new_conversation(client, profile_id), "Nochmal?")
    assert outputs(again)[0]["cached"] is False
    assert outputs(again)[0]["category"] == "Groceries"


async def test_the_categorizer_only_looks_up_when_the_switch_is_on(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str, web_client: StubWeb
) -> None:
    await import_synthetic(client, profile_id)
    slot = fast_slot(searches_then_finishes())
    scripts.fast_call = slot  # type: ignore[assignment]

    report = await categorize(client, profile_id, await last_import(client, profile_id))

    assert web_client.calls == []
    assert (report["lookups"], report["by_lookup"], report["lookups_refused"]) == (0, 0, 0)
    assert await outbound_log(client, profile_id) == []
    assert slot.prompts == [], "the loop never ran"  # type: ignore[attr-defined]
    # Every merchant the dictionary does not know went to the model instead.
    assert keys_in(slot.categorizer[0]) == {  # type: ignore[attr-defined]
        "hausverwaltung bergmann",
        "mustermann systems",
        "anna weber",
        "jonas keller",
        "max schulz",
        "lea hoffmann",
    }


async def test_the_lookup_stage_places_what_the_dictionary_does_not_know(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str, web_client: StubWeb
) -> None:
    await switch_web_lookup(client, profile_id, True)
    await import_synthetic(client, profile_id)
    # The results have to name the merchant, or the confidence is capped and the merchant goes
    # to the model with what was found as context instead (see the cap test below).
    web_client.by_query = {
        "hausverwaltung": [Hit("Hausverwaltung Bergmann", "https://example.org/bergmann", "A property manager")],
        "mustermann": [Hit("Mustermann Systems", "https://example.org/mustermann", "An IT company")],
    }
    slot = fast_slot(
        searches_then_finishes(summary="a Berlin property manager", category="Housing", subcategory="Rent")
    )
    scripts.fast_call = slot  # type: ignore[assignment]

    report = await categorize(client, profile_id, await last_import(client, profile_id))

    # The two businesses were looked up; the four payments to friends are names, so they were
    # refused before anything left.
    assert sorted(web_client.searches) == [
        "what is hausverwaltung bergmann",
        "what is mustermann systems",
    ]
    assert (report["lookups"], report["lookups_refused"]) == (2, 4)
    assert report["by_lookup"] == 24
    assert report["by_model"] == 0
    # A merchant the lookup placed never reached the categorizer: it was asked about the four
    # people and nothing else. (The two keys of the prompt's worked example are always in it,
    # which is why this reads the batch size rather than every key in the text.)
    batch = slot.categorizer[0]  # type: ignore[attr-defined]
    assert "Categorize these 4 merchant(s)" in batch
    assert "mustermann systems" not in batch

    rent = await rows_of(client, profile_id, "MIETE WOHNUNG")
    assert {(row["category"], row["subcategory"]) for row in rent} == {("Housing", "Rent")}
    assert {row["title"] for row in rent} == {"Hausverwaltung Bergmann"}
    assert sorted(e["merchant_token"] for e in await outbound_log(client, profile_id)) == [
        "hausverwaltung bergmann",
        "mustermann systems",
    ]


async def test_an_unsure_lookup_rides_along_as_context_instead_of_pre_empting_the_model(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str, web_client: StubWeb
) -> None:
    """F3 of the review: a lookup below the threshold used to take the merchant off the batch.

    The cost was measured on the synthetic employer: the lookup found nothing and said Shopping
    at 0.20, and the categorizer alone reads "GEHALT", money in, and files Income at 0.90. Now
    the unsure lookup is one `web:` line under the booking text and the model still answers.
    """
    await switch_web_lookup(client, profile_id, True)
    await import_synthetic(client, profile_id)
    slot = fast_slot(
        searches_then_finishes(summary="unclear, maybe a shop", category="Shopping", subcategory=None, confidence=0.4),
        guesses={"mustermann systems": ("Income", "Salary", 0.9)},
    )
    scripts.fast_call = slot  # type: ignore[assignment]

    report = await categorize(client, profile_id, await last_import(client, profile_id))

    assert report["by_lookup"] == 0, "below the threshold nothing is placed"
    # The merchant reached the categorizer, and what the lookup found came with it.
    batch = slot.categorizer[0]  # type: ignore[attr-defined]
    assert "mustermann systems" in batch
    assert "web: unclear, maybe a shop (Shopping)" in batch
    # And the model's own reading of the booking text is what was filed.
    salary = await rows_of(client, profile_id, "GEHALT")
    assert {(row["category"], row["subcategory"]) for row in salary} == {("Income", "Salary")}


# The scrubber, on its own. No app and no network: it is a pure function of two strings, and
# every case below is a row of F2 or F4 of the review of 2026-09-06.


COMPANIES = [
    # (description, counterparty, the token that may leave)
    ("SIXT AUTOVERMIETUNG", "Sixt GmbH & Co Autovermietung KG", "sixt autovermietung"),
    ("JET 3311 BERLIN", "JET Tankstellen Deutschland GmbH", "jet tankstellen"),
    ("HAFTPFLICHT BEITRAG", "ERGO Versicherung AG", "ergo versicherung"),
    ("FIVE GUYS BERLIN", "Five Guys Germany GmbH", "five guys"),
    ("CONRAD 0102", "Conrad Electronic SE", "conrad electronic"),
    ("SPARPLAN ETF", "Scalable Capital GmbH", "scalable capital"),
    ("KV BEITRAG", "Debeka Krankenversicherungsverein a.G.", "debeka krankenversicherungsverein"),
    ("ADAC MITGLIEDSBEITRAG", "ADAC e.V.", "adac"),
    ("SHOP APOTHEKE BESTELLUNG", "Shop Apotheke B.V.", "shop apotheke"),
    ("INTERSPORT VOSWINKEL", "Intersport Deutschland eG", "intersport"),
    # The stems, which have no legal form to lean on.
    ("PHYSIO REZEPT", "Physiotherapie Am Park", "physiotherapie park"),
    ("METZGEREI HUBER", "Metzgerei Huber", "metzgerei huber"),
    ("HIT TANKSTELLE", "HIT-Tankstelle", "hit tankstelle"),
    ("DOUGLAS 0455", "Parfuemerie Douglas GmbH", "parfuemerie douglas"),
    ("POCO 1180", "POCO Einrichtungsmaerkte GmbH", "poco einrichtungsmaerkte"),
    ("SKY ABO", "Sky Deutschland Fernsehen GmbH", "sky fernsehen"),
    ("MILES TRIP", "MILES Mobility GmbH", "miles mobility"),
    ("CINEMAXX 0510", "CinemaxX Entertainment GmbH", "cinemaxx entertainment"),
    # F4: a brand's short parts survive the fold.
    ("STROM ABSCHLAG", "E.ON Energie Deutschland GmbH", "eon energie"),
    ("DSL RECHNUNG", "1&1 Telecom GmbH", "1und1 telecom"),
    ("ZEIT DIGITAL ABO", "Zeit Online GmbH", "zeit online"),
]

PEOPLE = [
    # A person, however the export prints the name, and whatever the other word ends in.
    ("Anna Weber", None),
    ("ANNA WEBER", None),
    ("Weber Anna", None),
    ("Anna Bauer", None),
    ("Lea Hoffmann", None),
    ("PP.4711.PP . ANNA WEBER, Ihre Zahlung", "PayPal Europe S.a.r.l."),
    ("PP.4711.PP . MAX SCHULZ, Ihre Zahlung", "PayPal Europe S.a.r.l."),
    # Two words that say nothing about a trade: refused, which costs a lookup and never a name.
    ("ROFU Kinderland", None),
    ("BLUMEN RIEDEL", "Blumen Riedel"),
]


@pytest.mark.parametrize(("description", "counterparty", "token"), COMPANIES)
def test_a_company_is_not_read_as_a_person(description: str, counterparty: str, token: str) -> None:
    found = scrub(description, counterparty)
    assert bool(found), f"{counterparty} was refused as a person's name"
    assert found.text == token


@pytest.mark.parametrize(("description", "counterparty"), PEOPLE)
def test_a_person_is_refused_whole(description: str, counterparty: str | None) -> None:
    found = scrub(description, counterparty)
    assert not found, f"{description} produced the token {found.text!r}"
    assert found.reason


def test_the_legal_form_is_read_where_the_person_rule_reads() -> None:
    """The one way widening the rule could leak a name, asserted on its own.

    A PayPal booking names `PayPal Europe S.a.r.l.` as the counterparty and a friend in the
    text. The legal form is on the processor, not on the person, so it is read from the same
    string the person rule reads and the friend stays home.
    """
    assert has_legal_form("PayPal Europe S.a.r.l.") is True
    assert has_legal_form("PP.4711.PP . ANNA WEBER, Ihre Zahlung") is False
    assert not scrub("PP.4711.PP . ANNA WEBER, Ihre Zahlung", "PayPal Europe S.a.r.l.")


def test_a_receipt_header_that_is_an_address_or_a_person_is_refused() -> None:
    """A header is not always a shop: `extract.bill` sends it through the same rule."""
    assert not scrub("Kreiller Str. 81673 München", None)
    assert scrub("Combi. Frisch. Nebenan.", None).text == "combi frisch nebenan"
    assert scrub("Saurüsselalm", None).text == "sauruesselalm"


# The four rules that hold the loop to the web, each on its own.


def finishes_at_once() -> Decider:
    """A model that answers from memory: no search, no source, straight to a finish.

    It searches only once the loop has told it to, which is the behaviour the floor exists to
    produce: the hosted model's own recollection, turned into a lookup with a source under it.
    """

    def decide(prompt: str, token: str, steps: int) -> ModelResponse:
        if "you have not searched even once" in prompt and not urls_in(prompt):
            return _decide(action="search", query=f"what is {token}")
        return _decide(
            action="finish",
            summary=f"{token} is a well known chain, I know this one",
            category="Groceries",
            subcategory="Supermarket",
            confidence=0.95,
            evidence=quote_in(prompt),
            sources=urls_in(prompt)[:1],
        )

    return decide


INVENTED = "It is Germany's best loved chain of strawberry farms, founded in 1921."


def invents_its_evidence(real: str) -> Decider:
    """Searches, then quotes a sentence nobody showed it, then quotes the real one."""

    def decide(prompt: str, token: str, steps: int) -> ModelResponse:
        if steps == 0:
            return _decide(action="search", query=f"what is {token}")
        return _decide(
            action="finish",
            summary="a chain of strawberry farms",
            category="Groceries",
            subcategory="Supermarket",
            confidence=0.9,
            evidence=real if "`evidence` has to be" in prompt else INVENTED,
            sources=urls_in(prompt)[:1],
        )

    return decide


async def test_a_finish_before_any_search_is_handed_back_once(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    """F1: on the hosted model, 34 of 82 lookups answered from memory and never searched.

    "Stop as soon as you know" is the right product rule and the wrong elective rule, so the
    floor is in the code: the first finish with no search behind it is handed back.
    """
    await switch_web_lookup(client, profile_id, True)
    scripts.fast = asks_about(KARLS)
    slot = fast_slot(finishes_at_once())
    scripts.fast_call = slot  # type: ignore[assignment]

    _, chunks = await chat(await new_conversation(client, profile_id), "Was ist KARLS DANKT?")

    assert web_client.searches, "the floor turned a recollection into a search"
    found = outputs(chunks)[0]
    assert found["searches"] == 1
    assert found["sources"], "and the answer now carries a source"
    handed_back = slot.prompts[1]  # type: ignore[attr-defined]
    assert "you have not searched even once" in handed_back
    assert "you reasoned: the token reads like a business so: finish" in handed_back


async def test_the_merchants_own_page_is_read_before_a_finish_is_taken(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    """The forced fetch: not one lookup in the review ever read a page unprompted.

    The model here only ever searches and finishes. One of its results is a Wikipedia article
    about the token, so the loop fetches it, hands the text back and asks again, which is the
    difference between "it searched" and "it visits pages and uses what is on them".
    """
    await switch_web_lookup(client, profile_id, True)
    scripts.fast = asks_about(KARLS)
    slot = fast_slot(searches_then_finishes())
    scripts.fast_call = slot  # type: ignore[assignment]

    _, chunks = await chat(await new_conversation(client, profile_id), "Was ist KARLS DANKT?")

    # The script only ever searches and finishes, so this page was read by the loop itself.
    assert web_client.fetches == ["https://de.wikipedia.org/wiki/Karls"]
    read_step = slot.prompts[-1]  # type: ignore[attr-defined]
    assert "read for you, because it is this merchant's own site" in read_step
    assert KARLS_PAGE in read_step, "and its text is what the next decision was made on"
    found = outputs(chunks)[0]
    assert (found["searches"], found["fetches"]) == (1, 1)
    assert found["pages"] == ["https://de.wikipedia.org/wiki/Karls"]
    assert found["evidence"] == KARLS_PAGE
    assert found["evidence_url"] == "https://de.wikipedia.org/wiki/Karls"


async def test_a_token_with_no_own_page_among_its_results_forces_no_fetch(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    """The rule is "its own site or its Wikipedia article", not "always one more request"."""
    await switch_web_lookup(client, profile_id, True)
    web_client.hits = [Hit("Was ist das? - Forum", "https://forum.example.org/t/9", "Somebody asked about it")]
    scripts.fast = asks_about(KARLS)
    scripts.fast_call = fast_slot(searches_then_finishes())  # type: ignore[assignment]

    _, chunks = await chat(await new_conversation(client, profile_id), "Was ist KARLS DANKT?")

    assert web_client.fetches == []
    assert outputs(chunks)[0]["fetches"] == 0


async def test_the_evidence_has_to_occur_in_what_the_steps_returned(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    """The verbatim guard of the extraction path, applied to a quote instead of a figure.

    A sentence the model wrote reads exactly like a sentence it copied, so the card would show
    an invented quote with a real URL under it. The check is in code and it is one refusal.
    """
    await switch_web_lookup(client, profile_id, True)
    web_client.hits = [Hit("Karls Erdbeerhof", "https://example.org/karls", "A chain of strawberry farms")]
    scripts.fast = asks_about(KARLS)
    slot = fast_slot(invents_its_evidence("A chain of strawberry farms"))
    scripts.fast_call = slot  # type: ignore[assignment]

    _, chunks = await chat(await new_conversation(client, profile_id), "Was ist KARLS DANKT?")

    handed_back = slot.prompts[-1]  # type: ignore[attr-defined]
    assert "`evidence` has to be one sentence copied word for word" in handed_back
    assert "founded in 1921" in handed_back, "the refusal quotes back what was not there"
    found = outputs(chunks)[0]
    assert found["evidence"] == "A chain of strawberry farms"
    assert found["evidence_url"] == "https://example.org/karls"
    # Being handed back costs a model round trip and never a second request.
    assert len(web_client.calls) == 1


async def test_a_failed_search_is_retried_once_without_charging_the_budget(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    """F5: two of 51 requests failed with a connection error, and each cost a search and a call.

    The retry happens inside the same step, so the model is never told about a backend that
    dropped a connection and the budget still has all four searches in it.
    """
    await switch_web_lookup(client, profile_id, True)
    web_client.fail_with = "the search failed: connection reset"
    web_client.fail_times = 1
    scripts.fast = asks_about(KARLS)
    slot = fast_slot(searches_then_finishes())
    scripts.fast_call = slot  # type: ignore[assignment]

    _, chunks = await chat(await new_conversation(client, profile_id), "Was ist KARLS DANKT?")

    assert web_client.searches == ["what is karls", "what is karls"], "the same query, once more"
    found = outputs(chunks)[0]
    assert found["searches"] == 1, "the retry was free of the budget"
    assert found["category"] == "Groceries"
    assert "failed" not in "".join(slot.prompts), "and the model was never asked about it"  # type: ignore[attr-defined]
    # Both attempts are in the log, because both left the machine.
    assert [(e["kind"], e["status"]) for e in await outbound_log(client, profile_id)][-2:] == [
        ("search", "ok"),
        ("search", "the search failed: connection reset"),
    ]


async def test_the_confidence_is_capped_when_no_source_names_the_merchant(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    """A local token matches many real businesses, and the loop answered one of them at 0.95.

    Capped at 0.6 the answer is still shown, with its quote, and it is below the threshold the
    pipeline files at, so the household is asked instead of a booking going to the wrong place.
    """
    await switch_web_lookup(client, profile_id, True)
    web_client.hits = [Hit("Immobilien Muenchen", "https://example.org/muenchen", "A property manager in Munich")]
    scripts.fast = asks_about("Hausverwaltung Bergmann GmbH")
    scripts.fast_call = fast_slot(  # type: ignore[assignment]
        searches_then_finishes(summary="a property manager", category="Housing", subcategory="Rent", confidence=0.95)
    )

    _, chunks = await chat(await new_conversation(client, profile_id), "Was ist das?")

    found = outputs(chunks)[0]
    assert found["merchant"] == "hausverwaltung bergmann"
    assert found["confidence"] == 0.6, "no result named the merchant"
    assert found["capped"] is True
    assert found["category"] == "Housing", "it still says what it found, and shows its quote"
    assert found["evidence"] == "A property manager in Munich"


# The two callers beyond the chat tool.


async def test_an_import_looks_each_distinct_token_up_once(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str, web_client: StubWeb
) -> None:
    """The batch entry point: one lookup per token, whatever the rows do.

    The synthetic year's four payments to friends are four merchants and one refusal each, and
    they never reach the network; the two companies are two lookups.
    """
    await switch_web_lookup(client, profile_id, True)
    await import_synthetic(client, profile_id)
    scripts.fast_call = fast_slot(searches_then_finishes())  # type: ignore[assignment]

    report = await categorize(client, profile_id, await last_import(client, profile_id))

    assert sorted(web_client.searches) == ["what is hausverwaltung bergmann", "what is mustermann systems"]
    assert (report["lookups"], report["lookups_refused"]) == (2, 4)
    tokens = [e["merchant_token"] for e in await outbound_log(client, profile_id)]
    assert sorted(set(tokens)) == ["hausverwaltung bergmann", "mustermann systems"]

    # A second run over the same profile asks the same merchants again and nothing leaves: the
    # tokens are in this profile's cache.
    before = len(web_client.calls)
    await categorize(client, profile_id, await last_import(client, profile_id))
    assert len(web_client.calls) == before


COMBI = "Combi. Frisch. Nebenan."
COMBI_HITS = [
    Hit("Combi Verbrauchermarkt", "https://www.combi.de/", "Combi is a supermarket chain in northwestern Germany"),
]
COMBI_PAGE = "Combi Verbrauchermarkt: your supermarket around the corner, part of Bünting."


def bill_slot(decide: Decider, *, merchant: str):
    """The fast slot for a receipt whose header is looked up: the reader, the loop, the legs."""
    reader = bill_reader(
        items=(("Bio Milch 1L", "1,29"), ("Spuelmittel", "2,49")),
        total="3,78",
        date_text="19.07.2025",
        merchant=merchant,
    )
    loop = fast_slot(decide)
    legs: list[str] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tools = [tool.name for tool in info.output_tools]
        if tools == ["decide"]:
            return loop(messages, info)
        if tools == ["categorize"]:
            legs.append(_last_user_prompt(messages))
        return reader(messages, info)

    respond.prompts = loop.prompts  # type: ignore[attr-defined]
    respond.legs = legs  # type: ignore[attr-defined]
    return respond


async def _drop_the_receipt(client: httpx.AsyncClient, profile_id: str) -> dict[str, Any]:
    conversation_id = await new_conversation(client, profile_id)
    response = await client.post(
        f"/api/conversations/{conversation_id}/chat",
        json=attach(conversation_id, "book this receipt", OBI_BILL, media_type="image/png"),
    )
    assert response.status_code == 200, response.text
    return outputs_of(parse_sse(response.text))[0]


async def test_a_receipt_header_the_dictionary_does_not_know_is_resolved_on_the_web(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str, web_client: StubWeb
) -> None:
    """The second caller: the shop a receipt was printed by, never its basket.

    Without this the draft is "Combi. Frisch. Nebenan." with no category and the legs of a
    split are guessed from article texts alone. The header is the only thing that leaves.
    """
    await switch_web_lookup(client, profile_id, True)
    await import_synthetic(client, profile_id)
    web_client.hits = list(COMBI_HITS)
    web_client.page = COMBI_PAGE
    scripts.fast = importing(OBI_BILL.name)
    scripts.fast_call = bill_slot(searches_then_finishes(  # type: ignore[assignment]
        summary="a supermarket chain in northwestern Germany",
        category="Groceries",
        subcategory="Supermarket",
    ), merchant=COMBI)

    output = await _drop_the_receipt(client, profile_id)

    assert output["status"] == "bill_draft"
    assert output["store"]["via"] == "web"
    assert output["store"]["title"] == "Combi Frisch Nebenan"
    assert output["store"]["category"] == "Groceries"
    assert output["store"]["subcategory"] == "Supermarket"
    assert output["store"]["evidence"]
    # The draft carries the shop's name; the printed header stays on as the counterparty.
    assert output["drafts"][0]["description"] == "Combi Frisch Nebenan"
    assert output["drafts"][0]["counterparty"] == COMBI
    assert "The shop was recognized through a web lookup" in output["instruction"]

    # Only the header left, and neither line item is anywhere near what went out.
    entries = await outbound_log(client, profile_id)
    assert {e["merchant_token"] for e in entries} == {"combi frisch nebenan"}
    for entry in entries:
        assert "milch" not in entry["target"].casefold()
        assert "spuelmittel" not in entry["target"].casefold()
        assert not re.search(r"\d,\d", entry["target"]), entry


def test_the_legs_of_a_split_are_told_the_shop_and_never_the_basket() -> None:
    """One line of context per leg: what shop, never what was in it and never a figure."""
    store = Store(
        title="Combi Frisch Nebenan",
        category="Groceries",
        subcategory="Supermarket",
        blurb="a supermarket chain in northwestern Germany",
        via="web",
    )
    entry = MerchantBatchEntry(
        key="i0",
        sample_description="Bio Milch 1L",
        counterparty=None,
        bookings=1,
        average_cents=-129,
        incoming=False,
        web=store.line,
    )
    assert "web: the receipt is from Combi Frisch Nebenan" in entry.as_prompt()
    assert "filed under Groceries" in entry.as_prompt()
    assert "1,29" not in store.line and "Milch" not in store.line


async def test_a_receipt_sends_nothing_while_the_switch_is_off(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str, web_client: StubWeb
) -> None:
    """Off is the absence of the object, on this path as on the others."""
    await import_synthetic(client, profile_id)
    scripts.fast = importing(OBI_BILL.name)
    scripts.fast_call = bill_slot(searches_then_finishes(), merchant=COMBI)  # type: ignore[assignment]

    output = await _drop_the_receipt(client, profile_id)

    assert web_client.calls == []
    assert await outbound_log(client, profile_id) == []
    assert "store" not in output
    assert output["drafts"][0]["description"] == COMBI


async def test_switching_the_lookup_off_mid_loop_stops_the_next_request(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    """The switch is read per turn, so a loop already running has to be stopped where it sends.

    The journal is the loop's only route out, so the check sits there: the search that was
    already in flight finishes and no second one is made.
    """
    await switch_web_lookup(client, profile_id, True)
    made = 0

    async def flip_it_off() -> None:
        nonlocal made
        made += 1
        if made == 1:
            await switch_web_lookup(client, profile_id, False)

    web_client.watch = flip_it_off
    scripts.fast = asks_about(KARLS)
    scripts.fast_call = fast_slot(never_stops("search"))  # type: ignore[assignment]

    _, chunks = await chat(await new_conversation(client, profile_id), "Was ist KARLS DANKT?")

    assert web_client.searches == ["karls shop"], "the budget was four; the switch stopped it after one"
    assert outputs(chunks)[0]["error"] == (
        "Web lookup was switched off while this lookup was running, so nothing more left this machine."
    )
    # The one request that did go out is in the log, and nothing else is.
    assert [(e["kind"], e["target"]) for e in await outbound_log(client, profile_id)] == [("search", "karls shop")]


async def test_a_failure_nobody_wrote_copy_for_becomes_a_sentence_in_the_step(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, web_client: StubWeb
) -> None:
    """An exception inside a tool used to end the turn with the exception's own text.

    The search client is the one part of the app that talks to a machine we do not control, so
    it is where a failure nobody anticipated is easiest to reach. `agent.guarded` turns any of
    them into a tool result the transcript can render and the log keeps whole.
    """
    await switch_web_lookup(client, profile_id, True)

    async def unheard_of(query: str) -> list[Hit]:
        raise RuntimeError("the search library raised something new")

    web_client.search = unheard_of  # type: ignore[assignment]
    scripts.fast = asks_about(KARLS)
    scripts.fast_call = fast_slot(searches_then_finishes())  # type: ignore[assignment]

    response, chunks = await chat(await new_conversation(client, profile_id), "Was ist KARLS DANKT?")

    assert response.status_code == 200
    assert outputs(chunks) == [
        {
            "tool_failed": True,
            "error": (
                "The lookup merchant step could not be finished because something unexpected "
                "went wrong. Try it again, or ask for it in another way."
            ),
        }
    ]
    assert "the search library raised something new" not in response.text
