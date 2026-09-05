"""The dashboard: the four defaults, the tiles, and the four things a card can be told to do.

Every test drives the HTTP seam. Nothing here stores a figure: a card stores a statement, and
the assertions are about what that statement returns when the endpoint runs it, which is why
the refresh test changes the data between two calls.
"""

import httpx

from finquery.chart.selfcheck import check_chart_code
from finquery.chart.shapes import Shape
from finquery.dashboard import DEFAULTS

from .conftest import Chat, Scripts, new_conversation, tool_call_of, turn_of
from .test_chart import (
    MANY_TOPICS_SQL,
    MONTHLY_SQL,
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
    "reason": "A month series reads as a line.",
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
    assert [card["position"] for card in first["charts"]] == [0, 1, 2, 3]
    assert {card["created_from"] for card in first["charts"]} == {"default"}

    again = await dashboard(client, profile_id)
    assert [card["id"] for card in again["charts"]] == [card["id"] for card in first["charts"]]

    removed = await client.delete(
        f"/api/dashboard/charts/{first['charts'][0]['id']}", params={"profile_id": profile_id}
    )
    assert removed.status_code == 204
    after = await dashboard(client, profile_id)
    assert len(after["charts"]) == 3
    assert [card["position"] for card in after["charts"]] == [0, 1, 2]


async def test_each_profile_has_its_own_dashboard(client: httpx.AsyncClient, profile_id: str) -> None:
    other = (await client.post("/api/profiles", json={"name": "Second"})).json()["id"]
    mine = await dashboard(client, profile_id)
    theirs = await dashboard(client, other)
    assert len(theirs["charts"]) == 4
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

    doughnut = next(card for card in page["charts"] if card["shape"] == "doughnut")
    assert doughnut["row_count"] <= 6, "a doughnut has six slices, so its statement folds the rest"
    grouped = next(card for card in page["charts"] if card["shape"] == "bar_grouped")
    assert {row["topic"] for row in grouped["rows"]} == {"Income", "Spending"}


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
        "review_import_id": None,
    }
    assert len(page["charts"]) == 4
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
    assert pins["call_ids"] == [call_id]

    # A second Add to dashboard finds the card it already made instead of a second one.
    twice = await client.post(
        "/api/dashboard/charts/from-turn",
        json={"profile_id": profile_id, "turn_id": turn_id, "tool_call_id": call_id},
    )
    assert twice.status_code == 201
    assert twice.json()["id"] == card["id"]
    assert len((await dashboard(client, profile_id))["charts"]) == 5


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


async def test_a_chart_asked_for_on_the_dashboard_is_previewed_before_it_is_kept(
    client: httpx.AsyncClient, scripts: Scripts, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast_call = scripted_chart(plan=LINE_PLAN, sql=MONTHLY_SQL, codes=[LINE_CODE])  # type: ignore[assignment]

    preview = await client.post(
        "/api/dashboard/charts/preview",
        json={"profile_id": profile_id, "request": "spending on groceries per month"},
    )
    assert preview.status_code == 200, preview.text
    chart = preview.json()
    assert chart["rendered"] is True
    assert chart["plan"]
    # Nothing is stored until the user keeps it.
    assert len((await dashboard(client, profile_id))["charts"]) == 4

    kept = await client.post(
        "/api/dashboard/charts",
        json={
            "profile_id": profile_id,
            "chart": {
                "title": chart["title"],
                "shape": chart["shape"],
                "language": chart["language"],
                "request": chart["request"],
                "plan": chart["plan"],
                "sql": chart["sql"],
                "code": chart["code"],
                "notes": chart["notes"],
            },
        },
    )
    assert kept.status_code == 201, kept.text
    assert kept.json()["created_from"] == "dashboard"
    assert kept.json()["position"] == 4
    assert [card["title"] for card in (await dashboard(client, profile_id))["charts"]][-1] == chart["title"]


async def test_a_card_is_renamed_and_moved(client: httpx.AsyncClient, profile_id: str) -> None:
    cards = (await dashboard(client, profile_id))["charts"]
    last = cards[3]

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
    assert [card["position"] for card in after] == [0, 1, 2, 3]
    assert [card["id"] for card in after][1:] == [card["id"] for card in cards[:3]]


async def test_refresh_runs_the_statement_again_and_says_when(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    card = next(
        card for card in (await dashboard(client, profile_id))["charts"] if card["shape"] == "line"
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
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """A card whose query breaks is a sentence on that card, never a page that will not load."""
    await import_synthetic(client, profile_id)
    kept = await client.post(
        "/api/dashboard/charts",
        json={
            "profile_id": profile_id,
            "chart": {
                "title": "Groceries per month",
                "shape": "line",
                "language": "en",
                "request": "spending on groceries per month",
                "plan": "Chart plan: line",
                "sql": "SELECT month, total_eur FROM transaction_view WHERE grocery_flag = 1",
                "code": LINE_CODE,
                "notes": [],
            },
        },
    )
    assert kept.status_code == 201, kept.text
    card = kept.json()
    assert card["error"] is not None
    assert "no longer runs" in card["error"]
    assert "no such column" in card["error"]
    assert card["rows"] == []
    # The rest of the page is unharmed.
    page = await dashboard(client, profile_id)
    assert len(page["charts"]) == 5
    assert [default["error"] for default in page["charts"][:4]] == [None] * 4


async def test_a_statement_the_guard_refuses_is_never_stored(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    refused = await client.post(
        "/api/dashboard/charts",
        json={
            "profile_id": profile_id,
            "chart": {
                "title": "Everything",
                "shape": "bar",
                "sql": "SELECT * FROM profile",
                "code": LINE_CODE,
            },
        },
    )
    assert refused.status_code == 422, refused.text
    assert "profile may not be read" in refused.json()["detail"]
    assert len((await dashboard(client, profile_id))["charts"]) == 4


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


SHAPES_WITH_A_DEFAULT: set[Shape] = {default.shape for default in DEFAULTS}


def test_the_defaults_cover_four_different_shapes() -> None:
    assert len(SHAPES_WITH_A_DEFAULT) == len(DEFAULTS)
