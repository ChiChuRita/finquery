"""The dashboard: the six defaults, the tiles, and the four things a card can be told to do.

Every test drives the HTTP seam. Nothing here stores a figure: a card stores a statement, and
the assertions are about what that statement returns when the endpoint runs it, which is why
the refresh test changes the data between two calls.
"""

import json

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall
from sqlalchemy.orm import Session, sessionmaker

from finquery.chart.selfcheck import check_chart_code
from finquery.dashboard import DEFAULTS, cards_of, keep_chat_chart
from finquery.query.guard import SqlRejected

from .conftest import Chat, Scripts, new_conversation, tool_call_of, turn_of
from .test_chart import (
    MANY_SHOPS_SQL,
    MANY_TOPICS_SQL,
    MONTHLY_SQL,
    SHOPS_CODE,
    SHOPS_PLAN,
    STACKED_CODE,
    STACKED_PLAN,
    ask_chart_then_report,
    chart_output,
    narration,
    scripted_chart,
)
from .test_query import import_synthetic

LINE_PLAN = {
    "shape": "line",
    "language": "en",
    "title": "Groceries per month",
    "question": "spending on groceries per month",
    "columns": ["month", "total_eur"],
    "reasoning": "A month series reads as a line.",
}

LINE_CODE = """\
const amounts = data.map((row) => row.total_eur);
return defineChart({
  marks: [lineY(data, { x: 'month', y: 'total_eur', stroke: palette[0], strokeWidth: 2.25 })],
  scales: {
    x: { scale: () => scalePoint().padding(0.06), axis: { ticks: { format: monthShort } } },
    y: {
      scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)]),
      nice: true,
      grid: true,
      axis: { ticks: { format: eurShort } },
    },
  },
  tooltip: { use: tooltip, format: (point) => eur(point.datum.total_eur) },
});"""


async def dashboard(client: httpx.AsyncClient, profile_id: str) -> dict:
    response = await client.get("/api/dashboard", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return response.json()


async def spread_categories(client: httpx.AsyncClient, profile_id: str) -> list[str]:
    """Give the imported bookings real categories, six of them, round robin.

    The dataset is committed by the import endpoints, which categorize nothing, and a doughnut
    of one bucket is not a doughnut. Every profile is seeded with the same taxonomy, so this is
    the shipped categories over the shipped rows.
    """
    categories = (await client.get("/api/categories", params={"profile_id": profile_id})).json()[:6]
    rows = (
        await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})
    ).json()["rows"]
    for index, category in enumerate(categories):
        ids = [row["id"] for row in rows[index::6]]
        response = await client.post(
            "/api/transactions/bulk-recategorize",
            json={"profile_id": profile_id, "ids": ids, "category_id": category["id"]},
        )
        assert response.status_code == 200, response.text
    return [category["name"] for category in categories]


async def test_the_defaults_are_created_once_per_profile_and_stay_removed(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    first = await dashboard(client, profile_id)
    assert [card["title"] for card in first["charts"]] == [default.title for default in DEFAULTS]
    assert [card["default_key"] for card in first["charts"]] == [default.key for default in DEFAULTS]
    assert [card["position"] for card in first["charts"]] == list(range(len(DEFAULTS)))
    assert {card["created_from"] for card in first["charts"]} == {"default"}

    again = await dashboard(client, profile_id)
    assert [card["id"] for card in again["charts"]] == [card["id"] for card in first["charts"]]

    removed = await client.delete(
        f"/api/dashboard/charts/{first['charts'][0]['id']}", params={"profile_id": profile_id}
    )
    assert removed.status_code == 204
    after = await dashboard(client, profile_id)
    assert len(after["charts"]) == len(DEFAULTS) - 1
    assert [card["position"] for card in after["charts"]] == list(range(len(DEFAULTS) - 1))


async def test_each_profile_has_its_own_dashboard(client: httpx.AsyncClient, profile_id: str) -> None:
    other = (await client.post("/api/profiles", json={"name": "Second"})).json()["id"]
    mine = await dashboard(client, profile_id)
    theirs = await dashboard(client, other)
    assert len(theirs["charts"]) == len(DEFAULTS)
    assert {card["id"] for card in mine["charts"]}.isdisjoint({card["id"] for card in theirs["charts"]})

    refused = await client.patch(
        f"/api/dashboard/charts/{mine['charts'][0]['id']}",
        json={"profile_id": other, "title": "Not yours"},
    )
    assert refused.status_code == 404


async def test_every_default_draws_from_the_rows_its_own_statement_returns(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """The four defaults are held to the same rules as anything the sub-agent writes.

    They are code in the repo, so nothing repairs them: this is what keeps them in step with
    `finquery.chart.selfcheck`, whose rules go on changing.
    """
    await import_synthetic(client, profile_id)
    await spread_categories(client, profile_id)

    page = await dashboard(client, profile_id)
    assert page["has_data"] is True
    for card in page["charts"]:
        assert card["error"] is None, f"{card['title']}: {card['error']}"
        assert card["row_count"] > 1, f"{card['title']} returned {card['row_count']} rows"
        result = await check_chart_code(card["code"], card["rows"], card["shape"])
        assert result.ok, f"{card['title']}: {result.findings}"

    by_key = {card["default_key"]: card for card in page["charts"]}
    assert set(by_key) == {default.key for default in DEFAULTS}
    # The eight largest categories and the rest, folded in this statement because it is ours.
    assert by_key["top_categories"]["row_count"] <= 9
    assert {row["topic"] for row in by_key["income_against_spending"]["rows"]} == {
        "Income",
        "Spending",
    }
    # The period is the series, the category is the position, and the shared fold read the
    # column order (period, category, euros) to keep the largest categories per period.
    comparison = by_key["month_over_month"]
    assert comparison["columns"] == ["period", "category", "total_eur"]
    assert {row["period"] for row in comparison["rows"]} == {"This month", "Last month"}
    assert len({row["category"] for row in comparison["rows"]}) <= 6
    pairs = [(row["period"], row["category"]) for row in comparison["rows"]]
    assert len(pairs) == len(set(pairs)), "grouped bars need one figure per pair"
    # The pacing line carries two series, which is what makes the self-check above demand the
    # legend it passed with, and each stroke is a running total that never falls.
    pacing = by_key["month_pacing"]
    assert pacing["columns"] == ["day", "period", "running_eur"]
    assert {row["period"] for row in pacing["rows"]} == {"This month", "Last month"}
    for period in ("This month", "Last month"):
        stroke = [row for row in pacing["rows"] if row["period"] == period]
        assert [row["day"] for row in stroke] == sorted(row["day"] for row in stroke)
        assert all(
            second["running_eur"] >= first["running_eur"]
            for first, second in zip(stroke, stroke[1:], strict=False)
        )
    # The newest stroke ends on the month's whole spending, which is the Spent tile itself.
    newest = [row for row in pacing["rows"] if row["period"] == "This month"][-1]
    assert newest["running_eur"] == page["tiles"]["spent_eur"]

    # The heuristic is named on the card, because a bar that looks like a fact has to say so.
    regular = by_key["regular_payments"]
    assert "heuristic" in regular["plan"]
    assert "at least 3 of the last 4 months" in regular["plan"]


async def test_the_tiles_are_the_newest_month_of_the_data(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    tiles = (await dashboard(client, profile_id))["tiles"]
    assert tiles["month"] == "2025-12"
    assert tiles["spent_eur"] > 0
    assert tiles["income_eur"] > 0
    assert round(tiles["income_eur"] - tiles["spent_eur"], 2) == tiles["net_eur"]
    # Nothing is categorized after an import over REST, so every booking needs review.
    total = (await client.get("/api/transactions", params={"profile_id": profile_id})).json()["total"]
    assert tiles["needs_review"] == total
    assert tiles["review_import_id"] is not None


async def test_the_tiles_carry_the_seven_months_their_deltas_are_computed_from(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """One statement, seven rows: the month, the one before it, and the six-month average.

    The page subtracts two of these rows and averages the earlier ones, the way `fold_rows`
    sums rows here. Nothing about a delta is a second query, and nothing about it is stored.
    """
    await import_synthetic(client, profile_id)
    tiles = (await dashboard(client, profile_id))["tiles"]
    months = tiles["months"]
    assert [month["month"] for month in months] == [
        "2025-06",
        "2025-07",
        "2025-08",
        "2025-09",
        "2025-10",
        "2025-11",
        "2025-12",
    ]
    newest = months[-1]
    assert (newest["spent_eur"], newest["income_eur"], newest["net_eur"]) == (
        tiles["spent_eur"],
        tiles["income_eur"],
        tiles["net_eur"],
    )
    for month in months:
        assert round(month["income_eur"] - month["spent_eur"], 2) == month["net_eur"]

    # A range narrower than seven months returns the months it holds, and the page then says
    # what it averaged over instead of claiming six.
    narrowed = (
        await client.get(
            "/api/dashboard",
            params={"profile_id": profile_id, "from": "2025-03-01", "to": "2025-05-31"},
        )
    ).json()["tiles"]
    assert [month["month"] for month in narrowed["months"]] == ["2025-03", "2025-04", "2025-05"]
    assert narrowed["month"] == "2025-05"


async def test_an_empty_profile_gets_zero_tiles_and_cards_without_rows(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    page = await dashboard(client, profile_id)
    assert page["has_data"] is False
    assert page["tiles"] == {
        "month": None,
        "spent_eur": 0.0,
        "income_eur": 0.0,
        "net_eur": 0.0,
        "needs_review": 0,
        "months": [],
        "review_import_id": None,
    }
    assert len(page["charts"]) == len(DEFAULTS)
    assert all(card["row_count"] == 0 and card["error"] is None for card in page["charts"])


async def test_a_chart_drawn_in_a_chat_is_pinned_to_the_dashboard(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast = ask_chart_then_report("spending per month")
    scripts.fast_call = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Draw my spending per month.")
    output = chart_output(chunks)
    assert output["code"] is not None
    turn_id, call_id = turn_of(chunks), tool_call_of(chunks, "chart")

    pinned = await client.post(
        "/api/dashboard/charts/from-turn",
        json={"profile_id": profile_id, "turn_id": turn_id, "tool_call_id": call_id},
    )
    assert pinned.status_code == 201, pinned.text
    card = pinned.json()
    assert card["created_from"] == "chat"
    assert card["title"] == output["title"]
    assert card["code"] == output["code"]
    # The rows are not the turn's rows: the card ran the statement again, just now.
    assert card["row_count"] == output["row_count"]

    pins = (await client.get("/api/dashboard/pins", params={"profile_id": profile_id})).json()
    assert pins["charts"] == [{"call_id": call_id, "chart_id": card["id"]}]

    # A second Add to dashboard finds the card it already made instead of a second one.
    twice = await client.post(
        "/api/dashboard/charts/from-turn",
        json={"profile_id": profile_id, "turn_id": turn_id, "tool_call_id": call_id},
    )
    assert twice.status_code == 201
    assert twice.json()["id"] == card["id"]
    assert len((await dashboard(client, profile_id))["charts"]) == len(DEFAULTS) + 1


async def test_a_pinned_stacked_chart_draws_the_rows_it_drew_in_the_chat(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """Seven groups over six colours, folded in the chat and folded again on every load.

    The fold is arithmetic in code (`finquery.chart.fold`), never in the stored statement, so a
    card that re-runs its own SQL has to fold what comes back: before this, a stack that showed
    six series in the chat showed eleven on the dashboard and cycled the palette (ticket 36).
    """
    await import_synthetic(client, profile_id)
    scripts.fast = ask_chart_then_report("spending per month and group in 2025 as stacked bars")
    scripts.fast_call = scripted_chart(plan=STACKED_PLAN, sql=MANY_TOPICS_SQL, codes=[STACKED_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Gestapelte Balken pro Monat und Gruppe bitte.")
    output = chart_output(chunks)
    assert "The query returned 7 groups and a chart has 6 colours" in narration(chunks)
    assert len({row["topic"] for row in output["rows"]}) == 6

    pinned = await client.post(
        "/api/dashboard/charts/from-turn",
        json={
            "profile_id": profile_id,
            "turn_id": turn_of(chunks),
            "tool_call_id": tool_call_of(chunks, "chart"),
        },
    )
    assert pinned.status_code == 201, pinned.text
    card = pinned.json()

    stored = next(
        other for other in (await dashboard(client, profile_id))["charts"] if other["id"] == card["id"]
    )
    assert stored["rows"] == output["rows"], "a stored chart draws the rows it drew in the chat"
    topics = {row["topic"] for row in stored["rows"]}
    assert len(topics) == 6 and "Sonstige" in topics
    pairs = [(row["month"], row["topic"]) for row in stored["rows"]]
    assert len(pairs) == len(set(pairs)), "one figure per month and group, which is what a stack needs"
    # The tail is summed and not dropped, on this load as in the chat: the card still holds
    # every euro its own statement returned.
    page = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})).json()
    spent = -sum(row["amount_cents"] for row in page["rows"] if row["amount_cents"] < 0) / 100
    assert round(sum(row["total_eur"] for row in stored["rows"]), 2) == round(spent, 2)

    refreshed = await client.post(
        f"/api/dashboard/charts/{card['id']}/refresh", json={"profile_id": profile_id}
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["rows"] == output["rows"]


async def test_a_pinned_line_with_several_series_draws_the_lines_it_drew_in_the_chat(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The five-shop line, pinned: the card re-runs the statement and folds it the same way.

    Nine shops come back and six are drawn, in the chat and again on every load, because the
    statement is stored unfolded and `fold_rows` is one function (ticket 39). A card that did
    not fold would cycle the palette and give two shops the same colour.
    """
    await import_synthetic(client, profile_id)
    scripts.fast = ask_chart_then_report("spending per month and shop in 2025 as lines")
    scripts.fast_call = scripted_chart(plan=SHOPS_PLAN, sql=MANY_SHOPS_SQL, codes=[SHOPS_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Ausgaben pro Monat und Laden als Linien bitte.")
    output = chart_output(chunks)
    assert output["shape"] == "line" and output["rendered"] is True
    assert len({row["merchant"] for row in output["rows"]}) == 6

    pinned = await client.post(
        "/api/dashboard/charts/from-turn",
        json={
            "profile_id": profile_id,
            "turn_id": turn_of(chunks),
            "tool_call_id": tool_call_of(chunks, "chart"),
        },
    )
    assert pinned.status_code == 201, pinned.text
    card = pinned.json()

    stored = next(
        other for other in (await dashboard(client, profile_id))["charts"] if other["id"] == card["id"]
    )
    assert stored["rows"] == output["rows"], "a stored line draws the lines it drew in the chat"
    assert len({row["merchant"] for row in stored["rows"]}) == 6
    pairs = [(row["month"], row["merchant"]) for row in stored["rows"]]
    assert len(pairs) == len(set(pairs)), "one figure per month and shop, which is what a stroke needs"


async def test_the_page_no_longer_draws_a_chart_of_its_own(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """Charts are asked for in a chat. The two routes the Add line used are gone (ticket 44)."""
    preview = await client.post(
        "/api/dashboard/charts/preview",
        json={"profile_id": profile_id, "request": "spending on groceries per month"},
    )
    # 405, not 404: "preview" now reads as a chart id, and that path has a GET and nothing else.
    assert preview.status_code == 405
    kept = await client.post(
        "/api/dashboard/charts",
        json={"profile_id": profile_id, "chart": {"title": "x", "shape": "line", "sql": "", "code": ""}},
    )
    assert kept.status_code == 404


async def test_a_card_is_renamed_and_moved(client: httpx.AsyncClient, profile_id: str) -> None:
    cards = (await dashboard(client, profile_id))["charts"]
    last = cards[-1]

    renamed = await client.patch(
        f"/api/dashboard/charts/{last['id']}", json={"profile_id": profile_id, "title": "  My merchants  "}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "My merchants"

    moved = await client.patch(
        f"/api/dashboard/charts/{last['id']}", json={"profile_id": profile_id, "position": 0}
    )
    assert moved.status_code == 200
    after = (await dashboard(client, profile_id))["charts"]
    assert [card["title"] for card in after][0] == "My merchants"
    assert [card["position"] for card in after] == list(range(len(DEFAULTS)))
    assert [card["id"] for card in after][1:] == [card["id"] for card in cards[:-1]]


async def test_refresh_runs_the_statement_again_and_says_when(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    card = next(
        card
        for card in (await dashboard(client, profile_id))["charts"]
        if card["default_key"] == "spending_per_month"
    )
    assert card["refreshed_at"] is None
    before = sum(float(row["total_eur"]) for row in card["rows"])

    rows = (
        await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})
    ).json()["rows"]
    spent = [row["id"] for row in rows if row["amount_cents"] < 0][:20]
    deleted = await client.post(
        "/api/transactions/bulk-delete", json={"profile_id": profile_id, "ids": spent}
    )
    assert deleted.status_code == 200, deleted.text

    refreshed = await client.post(
        f"/api/dashboard/charts/{card['id']}/refresh", json={"profile_id": profile_id}
    )
    assert refreshed.status_code == 200, refreshed.text
    after = refreshed.json()
    assert after["refreshed_at"] is not None
    assert sum(float(row["total_eur"]) for row in after["rows"]) < before


async def test_a_statement_that_no_longer_runs_says_so_on_its_card(
    client: httpx.AsyncClient, profile_id: str, session_factory: sessionmaker[Session]
) -> None:
    """A card whose query breaks is a sentence on that card, never a page that will not load."""
    await import_synthetic(client, profile_id)
    await dashboard(client, profile_id)
    with session_factory() as session:
        # A statement the guard admits and SQLite refuses: the column existed when the card was
        # made and does not now, which is what a deleted category looks like from here.
        keep_chat_chart(
            session,
            profile_id,
            {
                "title": "Groceries per month",
                "shape": "line",
                "language": "en",
                "request": "spending on groceries per month",
                "plan": "Chart plan: line",
                "sql": "SELECT month, total_eur FROM transaction_view WHERE grocery_flag = 1",
                "code": LINE_CODE,
                "notes": [],
            },
            call_id="call-broken",
        )

    page = await dashboard(client, profile_id)
    card = page["charts"][-1]
    assert card["error"] is not None
    assert "no longer runs" in card["error"]
    assert "no such column" in card["error"]
    assert card["rows"] == []
    # The rest of the page is unharmed.
    assert len(page["charts"]) == len(DEFAULTS) + 1
    assert [default["error"] for default in page["charts"][: len(DEFAULTS)]] == [None] * len(DEFAULTS)


async def test_a_statement_the_guard_refuses_is_never_stored(
    client: httpx.AsyncClient, profile_id: str, session_factory: sessionmaker[Session]
) -> None:
    """The guard runs before a card exists, whichever way the chart got here."""
    await dashboard(client, profile_id)
    with session_factory() as session:
        with pytest.raises(SqlRejected, match="profile may not be read"):
            keep_chat_chart(
                session,
                profile_id,
                {"title": "Everything", "shape": "bar", "sql": "SELECT * FROM profile", "code": LINE_CODE},
                call_id="call-refused",
            )
    assert len((await dashboard(client, profile_id))["charts"]) == len(DEFAULTS)


async def test_a_chart_that_was_never_drawn_cannot_be_pinned(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """An empty profile answers a chart request without a chart, and there is nothing to pin."""
    scripts.fast = ask_chart_then_report("spending per month")
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Draw my spending per month.")
    output = chart_output(chunks)
    assert output["code"] is None

    refused = await client.post(
        "/api/dashboard/charts/from-turn",
        json={
            "profile_id": profile_id,
            "turn_id": turn_of(chunks),
            "tool_call_id": tool_call_of(chunks, "chart"),
        },
    )
    assert refused.status_code == 422
    assert "never drawn" in refused.json()["detail"]


def test_every_default_has_a_key_of_its_own() -> None:
    """The key is the identity Restore default cards matches on, so no two may share one."""
    keys = [default.key for default in DEFAULTS]
    assert len(set(keys)) == len(keys)
    assert keys == [
        "spending_per_month",
        "income_against_spending",
        "top_categories",
        "month_over_month",
        "regular_payments",
        "top_merchants",
        "month_pacing",
    ]


# The long-term half of ticket 44: a chart the agent keeps, and the five tools that manage the
# cards from a chat. Every one of them is driven through the chat endpoint with the scripted
# model, so what is asserted is what the browser would have received.


def call_then_report(tool: str, arguments: dict[str, object]):
    """A chat turn that calls one tool once and then writes what came back."""

    async def fn(messages: list[ModelMessage], _info: AgentInfo):
        result = _last_return(messages, tool)
        if result is None:
            yield {0: DeltaToolCall(name=tool, json_args=json.dumps(arguments))}
            return
        yield str(result.get("say") or result.get("title") or result.get("count") or "done")

    return fn


def _last_return(messages: list[ModelMessage], tool: str) -> dict | None:
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == tool:
                assert isinstance(part.content, dict)
                return part.content
            if part.part_kind == "user-prompt":
                return None
    return None


def tool_output(chunks: list[dict[str, object]]) -> dict:
    outputs = [c["output"] for c in chunks if c["type"] == "tool-output-available"]
    assert len(outputs) == 1, chunks
    assert isinstance(outputs[0], dict)
    return outputs[0]


async def kept_chart(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, keep: bool = True
) -> tuple[dict, list[dict[str, object]]]:
    """One chat turn whose chart the agent decided to keep, and its chunks."""
    scripts.fast = ask_chart_then_report("spending on groceries per month", keep=keep)
    scripts.fast_call = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])  # type: ignore[assignment]
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Track my groceries per month, please.")
    return chart_output(chunks), chunks


async def test_a_chart_the_agent_keeps_is_stored_once_and_reported_by_the_pins(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """`keep=true` makes a dashboard card from inside the tool, under that call id alone.

    The turn row does not exist yet when the tool runs, so the card carries no turn id: the
    pins endpoint matches on the call id, which is what makes the card in the transcript read
    "On the dashboard" after a reload.
    """
    await import_synthetic(client, profile_id)
    output, chunks = await kept_chart(client, scripts, chat, profile_id)
    call_id = tool_call_of(chunks, "chart")
    assert output["kept"] is True
    assert output["dashboard_chart_id"]

    page = await dashboard(client, profile_id)
    assert len(page["charts"]) == len(DEFAULTS) + 1
    card = page["charts"][-1]
    assert card["id"] == output["dashboard_chart_id"]
    assert card["created_from"] == "chat"
    assert card["title"] == output["title"]
    assert card["row_count"] == output["row_count"]

    pins = (await client.get("/api/dashboard/pins", params={"profile_id": profile_id})).json()
    assert pins["charts"] == [{"call_id": call_id, "chart_id": card["id"]}]

    # Add to dashboard on the same chart finds the card the tool already made.
    again = await client.post(
        "/api/dashboard/charts/from-turn",
        json={"profile_id": profile_id, "turn_id": turn_of(chunks), "tool_call_id": call_id},
    )
    assert again.status_code == 201, again.text
    assert again.json()["id"] == card["id"]
    assert len((await dashboard(client, profile_id))["charts"]) == len(DEFAULTS) + 1


async def test_a_chart_the_agent_does_not_keep_is_not_stored(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    output, _ = await kept_chart(client, scripts, chat, profile_id, keep=False)
    assert output["kept"] is False
    assert output["dashboard_chart_id"] is None
    assert len((await dashboard(client, profile_id))["charts"]) == len(DEFAULTS)
    assert (await client.get("/api/dashboard/pins", params={"profile_id": profile_id})).json() == {
        "charts": []
    }


async def test_a_chart_that_was_never_drawn_is_not_kept(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """An empty profile draws nothing, and a card of a chart nobody saw is worse than none."""
    scripts.fast = ask_chart_then_report("spending on groceries per month", keep=True)
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Track my groceries per month, please.")
    output = chart_output(chunks)
    assert output["code"] is None
    assert output["kept"] is False
    assert len((await dashboard(client, profile_id))["charts"]) == len(DEFAULTS)


async def test_the_charts_on_the_dashboard_are_listed_and_shown_from_the_chat(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    cards = (await dashboard(client, profile_id))["charts"]

    scripts.fast = call_then_report("dashboard_charts", {})
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "What is on my dashboard?")
    listed = tool_output(chunks)
    assert listed["count"] == len(DEFAULTS)
    assert [chart["chart_id"] for chart in listed["charts"]] == [card["id"] for card in cards]
    assert [chart["position"] for chart in listed["charts"]] == list(range(len(DEFAULTS)))

    line = next(card for card in cards if card["default_key"] == "spending_per_month")
    scripts.fast = call_then_report("show_dashboard_chart", {"chart_id": line["id"]})
    _, chunks = await chat(conversation_id, "Show me the spending chart.")
    shown = tool_output(chunks)
    assert shown["card_id"] == line["id"]
    assert shown["rendered"] is True
    assert shown["code"] == line["code"]
    # The rows are this moment's, not the ones the card was made from.
    assert shown["rows"] == line["rows"]


async def test_a_chart_the_chat_edits_keeps_its_place_and_its_previous_version(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    cards = (await dashboard(client, profile_id))["charts"]
    target = cards[1]

    respond = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])
    scripts.fast_call = respond  # type: ignore[assignment]
    scripts.fast = call_then_report(
        "edit_dashboard_chart", {"chart_id": target["id"], "request": "as a line over twelve months"}
    )
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Make that one a line chart.")
    edited = tool_output(chunks)
    call_id = tool_call_of(chunks, "edit_dashboard_chart")
    assert edited["applied"] is True
    assert edited["previous_title"] == target["title"]
    assert edited["title"] == LINE_PLAN["title"]
    assert edited["undo_call_id"] == call_id

    # The sub-agent was told which chart it was changing.
    plan_prompt = respond.prompts["plan"][0]  # type: ignore[attr-defined]
    assert f'title: "{target["title"]}"' in plan_prompt
    assert "This chart already exists and the user is changing it" in plan_prompt

    page = await dashboard(client, profile_id)
    assert len(page["charts"]) == len(DEFAULTS)
    card = page["charts"][1]
    assert card["id"] == target["id"]
    assert card["position"] == 1, "an edit keeps the card where it was"
    assert card["title"] == LINE_PLAN["title"]
    assert card["code"] == LINE_CODE
    assert card["undo_call_id"] == call_id

    undone = await client.post(
        f"/api/dashboard/charts/{target['id']}/undo",
        json={"profile_id": profile_id, "call_id": call_id},
    )
    assert undone.status_code == 200, undone.text
    assert undone.json()["title"] == target["title"]
    assert undone.json()["code"] == target["code"]
    assert undone.json()["undo_call_id"] is None

    twice = await client.post(
        f"/api/dashboard/charts/{target['id']}/undo",
        json={"profile_id": profile_id, "call_id": call_id},
    )
    assert twice.status_code == 409
    assert "already undone" in twice.json()["detail"]


async def test_a_chart_is_renamed_and_removed_from_the_chat_with_an_undo_each(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    cards = (await dashboard(client, profile_id))["charts"]
    target = cards[0]
    conversation_id = await new_conversation(client, profile_id)

    scripts.fast = call_then_report(
        "rename_dashboard_chart", {"chart_id": target["id"], "title": "My monthly spending"}
    )
    _, chunks = await chat(conversation_id, "Call the first chart My monthly spending.")
    renamed = tool_output(chunks)
    rename_call = tool_call_of(chunks, "rename_dashboard_chart")
    assert renamed["applied"] is True
    assert renamed["previous_title"] == target["title"]
    assert renamed["title"] == "My monthly spending"
    assert (await dashboard(client, profile_id))["charts"][0]["title"] == "My monthly spending"

    back = await client.post(
        f"/api/dashboard/charts/{target['id']}/undo",
        json={"profile_id": profile_id, "call_id": rename_call},
    )
    assert back.status_code == 200, back.text
    assert (await dashboard(client, profile_id))["charts"][0]["title"] == target["title"]

    scripts.fast = call_then_report("remove_dashboard_chart", {"chart_id": target["id"]})
    _, chunks = await chat(conversation_id, "Take that chart off the dashboard.")
    removed = tool_output(chunks)
    remove_call = tool_call_of(chunks, "remove_dashboard_chart")
    assert removed["applied"] is True
    after = await dashboard(client, profile_id)
    assert [card["id"] for card in after["charts"]] == [card["id"] for card in cards[1:]]
    assert [card["position"] for card in after["charts"]] == list(range(len(DEFAULTS) - 1))

    # A removed card is not on the dashboard, and is still there to be put back.
    restored = await client.post(
        f"/api/dashboard/charts/{target['id']}/undo",
        json={"profile_id": profile_id, "call_id": remove_call},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["removed_at"] is None
    assert [card["id"] for card in (await dashboard(client, profile_id))["charts"]] == [
        card["id"] for card in cards
    ]


async def test_the_dashboard_narrows_to_a_date_range(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """The range reaches the guard's own view, so the tiles and every card see those days only."""
    await import_synthetic(client, profile_id)
    whole = await dashboard(client, profile_id)
    assert whole["range"] == {
        "since": None,
        "until": None,
        "first_day": "2025-01-01",
        "last_day": "2025-12-28",
    }
    assert whole["tiles"]["month"] == "2025-12"

    narrowed = (
        await client.get(
            "/api/dashboard",
            params={"profile_id": profile_id, "from": "2025-02-01", "to": "2025-04-30"},
        )
    ).json()
    assert narrowed["range"]["since"] == "2025-02-01"
    assert narrowed["range"]["until"] == "2025-04-30"
    assert narrowed["range"]["last_day"] == "2025-12-28", "the bounds are the data's, not the range's"
    # "This month" is the newest month the range holds, which is what the tiles say.
    assert narrowed["tiles"]["month"] == "2025-04"
    assert narrowed["tiles"]["spent_eur"] < whole["tiles"]["spent_eur"]

    line = next(card for card in narrowed["charts"] if card["default_key"] == "spending_per_month")
    months = [row["month"] for row in line["rows"]]
    assert months == ["2025-02", "2025-03", "2025-04"]
    assert len(months) < len(
        [
            row["month"]
            for c in whole["charts"]
            if c["default_key"] == "spending_per_month"
            for row in c["rows"]
        ]
    )

    # A refresh answers the same days as the page it was pressed on.
    refreshed = await client.post(
        f"/api/dashboard/charts/{line['id']}/refresh",
        json={"profile_id": profile_id, "since": "2025-02-01", "until": "2025-04-30"},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert [row["month"] for row in refreshed.json()["rows"]] == months


async def test_a_range_that_reads_backwards_is_refused(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    reversed_range = await client.get(
        "/api/dashboard", params={"profile_id": profile_id, "from": "2025-06-01", "to": "2025-03-01"}
    )
    assert reversed_range.status_code == 422
    assert "on or before" in reversed_range.json()["detail"]

    not_a_day = await client.get(
        "/api/dashboard", params={"profile_id": profile_id, "from": "last month"}
    )
    assert not_a_day.status_code == 422

async def test_the_month_comparison_folds_its_categories_the_way_the_chat_would(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """More categories than the palette has colours, folded by the shared fold, not by the SQL.

    The statement asks for the columns in the order period, category, euros, which is what
    `fold_rows` reads the position, the group and the figure off (ticket 39). So the tail
    becomes one 'Other' group per period, summed and not dropped, exactly as a stacked chart
    from a chat is folded.
    """
    await import_synthetic(client, profile_id)
    categories = (await client.get("/api/categories", params={"profile_id": profile_id})).json()[:9]
    rows = (
        await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1000})
    ).json()["rows"]
    spent = [row for row in rows if row["amount_cents"] < 0]
    for index, category in enumerate(categories):
        await client.post(
            "/api/transactions/bulk-recategorize",
            json={
                "profile_id": profile_id,
                "ids": [row["id"] for row in spent[index :: len(categories)]],
                "category_id": category["id"],
            },
        )

    card = next(
        card
        for card in (await dashboard(client, profile_id))["charts"]
        if card["default_key"] == "month_over_month"
    )
    names = {row["category"] for row in card["rows"]}
    assert len(names) == 6, names
    assert "Other" in names
    assert {row["period"] for row in card["rows"]} == {"This month", "Last month"}
    pairs = [(row["period"], row["category"]) for row in card["rows"]]
    assert len(pairs) == len(set(pairs))

    # Every euro the statement returned is still on the chart: the tail is summed, not dropped.
    two_months = [
        row for row in rows if row["booked_on"] >= "2025-11-01" and row["amount_cents"] < 0
    ]
    spent_eur = -sum(row["amount_cents"] for row in two_months) / 100
    assert round(sum(row["total_eur"] for row in card["rows"]), 2) == round(spent_eur, 2)


async def test_restore_default_cards_adds_only_what_is_missing(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """The overflow action puts back the shipped defaults, matched by their key and nothing else."""
    await import_synthetic(client, profile_id)
    cards = (await dashboard(client, profile_id))["charts"]
    removed = next(card for card in cards if card["default_key"] == "regular_payments")
    kept = next(card for card in cards if card["default_key"] == "top_merchants")

    assert (
        await client.delete(
            f"/api/dashboard/charts/{removed['id']}", params={"profile_id": profile_id}
        )
    ).status_code == 204
    renamed = await client.patch(
        f"/api/dashboard/charts/{kept['id']}", json={"profile_id": profile_id, "title": "Who I pay"}
    )
    assert renamed.status_code == 200, renamed.text

    restored = await client.post(
        "/api/dashboard/restore-defaults", json={"profile_id": profile_id}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["added"] == ["regular_payments"]
    after = restored.json()["charts"]
    assert len(after) == len(DEFAULTS)
    # A default the user renamed is present, so it is left alone rather than added again.
    assert [card["title"] for card in after if card["default_key"] == "top_merchants"] == [
        "Who I pay"
    ]
    back = next(card for card in after if card["default_key"] == "regular_payments")
    assert back["id"] != removed["id"]
    assert back["position"] == len(DEFAULTS) - 1, "a restored card lands at the end"
    assert back["row_count"] > 1, "and it is a query, not a copy of what was removed"

    # Nothing to do the second time.
    again = await client.post("/api/dashboard/restore-defaults", json={"profile_id": profile_id})
    assert again.status_code == 200
    assert again.json()["added"] == []
    assert len(again.json()["charts"]) == len(DEFAULTS)


async def test_restore_default_cards_leaves_a_profile_seeded_before_this_ticket_alone(
    client: httpx.AsyncClient, profile_id: str, session_factory: sessionmaker[Session]
) -> None:
    """The old four have no key, so they are the user's cards now and the six arrive beside them."""
    await import_synthetic(client, profile_id)
    await dashboard(client, profile_id)
    with session_factory() as session:
        older = cards_of(session, profile_id)[:4]
        for card in older:
            card.default_key = None
        for card in cards_of(session, profile_id)[4:]:
            session.delete(card)
        session.commit()
        old_ids = [card.id for card in older]

    restored = (
        await client.post("/api/dashboard/restore-defaults", json={"profile_id": profile_id})
    ).json()
    assert restored["added"] == [default.key for default in DEFAULTS]
    charts = restored["charts"]
    assert [card["id"] for card in charts[:4]] == old_ids
    assert [card["default_key"] for card in charts[:4]] == [None] * 4
    assert [card["position"] for card in charts] == list(range(len(DEFAULTS) + 4))
