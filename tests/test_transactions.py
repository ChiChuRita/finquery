"""The transactions page over HTTP: filters, inline edits, splits, bulk actions, manual add.

Every test starts from the shipped synthetic CSV imported through the import endpoint, so the
listing is exercised against the same 433 bookings the demo uses.
"""

import json
from typing import Any

import httpx

from .conftest import SYNTHETIC

SPARKASSE = SYNTHETIC / "sparkasse-2025.csv"


async def import_synthetic(client: httpx.AsyncClient) -> str:
    """Import the shipped CSV with its preset and return the account id."""
    files = {"file": (SPARKASSE.name, SPARKASSE.read_bytes(), "text/csv")}
    mapping = (await client.post("/api/imports/preview", files=files)).json()["mapping"]
    committed = await client.post(
        "/api/imports",
        files=files,
        data={"mapping": json.dumps(mapping), "account_name": "Sparkasse Girokonto"},
    )
    assert committed.status_code == 201, committed.text
    return (await client.get("/api/accounts")).json()[0]["id"]


async def taxonomy(client: httpx.AsyncClient) -> dict[str, dict[str, Any]]:
    return {c["name"]: c for c in (await client.get("/api/categories")).json()}


async def listing(client: httpx.AsyncClient, **params: object) -> dict[str, Any]:
    response = await client.get("/api/transactions", params={"include_parents": True, **params})
    assert response.status_code == 200, response.text
    return response.json()


async def test_filters_narrow_the_listing(client: httpx.AsyncClient) -> None:
    await import_synthetic(client)
    account_id = (await client.get("/api/accounts")).json()[0]["id"]
    categories = await taxonomy(client)

    assert (await listing(client))["total"] == 433

    text = await listing(client, q="edeka", limit=500)
    assert 0 < text["total"] < 433
    assert all("edeka" in row["description"].casefold() for row in text["rows"])

    march = await listing(client, date_from="2025-03-01", date_to="2025-03-31", limit=500)
    assert march["total"] == len(march["rows"]) > 0
    assert all(row["booked_on"].startswith("2025-03") for row in march["rows"])

    # Every imported row starts as Needs review: an absent category, not a category.
    assert (await listing(client, needs_review=True))["total"] == 433
    assert (await listing(client, account_id=account_id))["total"] == 433
    assert (await listing(client, account_id="nope"))["total"] == 0

    groceries = categories["Groceries"]
    edited = await client.patch(
        f"/api/transactions/{text['rows'][0]['id']}", json={"category_id": groceries["id"]}
    )
    assert edited.status_code == 200, edited.text

    assert (await listing(client, needs_review=True))["total"] == 432
    only_groceries = await listing(client, category_id=groceries["id"])
    assert only_groceries["total"] == 1
    assert only_groceries["rows"][0]["category"] == "Groceries"

    # Filters combine, and paging still works on top of them.
    combined = await listing(client, q="edeka", date_from="2025-03-01", date_to="2025-03-31", limit=2)
    assert 2 < combined["total"] < min(text["total"], march["total"])
    assert len(combined["rows"]) == 2
    assert all("2025-03" in row["booked_on"] for row in combined["rows"])
    page_two = await listing(client, q="edeka", date_from="2025-03-01", date_to="2025-03-31", offset=1, limit=1)
    assert page_two["rows"][0]["id"] == combined["rows"][1]["id"]


async def test_inline_edits_apply_and_bad_input_is_a_validation_error(client: httpx.AsyncClient) -> None:
    await import_synthetic(client)
    categories = await taxonomy(client)
    groceries, dining = categories["Groceries"], categories["Dining"]
    row = (await listing(client, q="edeka", limit=1))["rows"][0]

    patched = await client.patch(
        f"/api/transactions/{row['id']}",
        json={
            "booked_on": "2025-06-05",
            "description": "Edeka weekly shop",
            "amount_cents": -4211,
            "category_id": groceries["id"],
            "subcategory_id": groceries["subcategories"][0]["id"],
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert (body["booked_on"], body["description"], body["amount_cents"]) == ("2025-06-05", "Edeka weekly shop", -4211)
    assert (body["category"], body["subcategory"]) == ("Groceries", "Supermarket")

    stored = (await listing(client, q="weekly shop"))["rows"][0]
    assert stored == body

    # A subcategory belongs to exactly one category, so this pair cannot be stored.
    mismatch = await client.patch(
        f"/api/transactions/{row['id']}",
        json={"category_id": dining["id"], "subcategory_id": groceries["subcategories"][0]["id"]},
    )
    assert mismatch.status_code == 400
    assert "Supermarket" in mismatch.json()["detail"]

    unknown = await client.patch(f"/api/transactions/{row['id']}", json={"category_id": "nope"})
    assert unknown.status_code == 400
    assert "category" in unknown.json()["detail"]

    blank = await client.patch(f"/api/transactions/{row['id']}", json={"description": "   "})
    assert blank.status_code == 400
    assert "description" in blank.json()["detail"]

    assert (await client.patch(f"/api/transactions/{row['id']}", json={"account_id": "nope"})).status_code == 400
    assert (await client.patch("/api/transactions/nope", json={"description": "x"})).status_code == 404

    # Moving the category away drops a subcategory that no longer applies.
    moved = await client.patch(f"/api/transactions/{row['id']}", json={"category_id": dining["id"]})
    assert moved.status_code == 200
    assert (moved.json()["category"], moved.json()["subcategory"]) == ("Dining", None)

    # Needs review is reachable again by clearing the category.
    cleared = await client.patch(f"/api/transactions/{row['id']}", json={"category_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["category"] is None


async def test_split_children_must_sum_to_their_parent(client: httpx.AsyncClient) -> None:
    await import_synthetic(client)
    categories = await taxonomy(client)
    parent = (await listing(client, q="edeka", limit=1))["rows"][0]
    assert parent["split_count"] == 0
    total = parent["amount_cents"]

    refused = await client.put(
        f"/api/transactions/{parent['id']}/splits",
        json={"children": [{"description": "Groceries", "amount_cents": total + 100}]},
    )
    assert refused.status_code == 400
    assert "add up to" in refused.json()["detail"]
    assert (await client.get(f"/api/transactions/{parent['id']}/splits")).json() == []

    household = total // 3
    saved = await client.put(
        f"/api/transactions/{parent['id']}/splits",
        json={
            "children": [
                {
                    "description": "Edeka groceries",
                    "amount_cents": total - household,
                    "category_id": categories["Groceries"]["id"],
                },
                {
                    "description": "Edeka household",
                    "amount_cents": household,
                    "category_id": categories["Shopping"]["id"],
                },
            ]
        },
    )
    assert saved.status_code == 200, saved.text
    children = saved.json()
    assert sorted(child["description"] for child in children) == ["Edeka groceries", "Edeka household"]
    assert sum(child["amount_cents"] for child in children) == total
    # A child inherits the parent's date, account and source; only the money is divided.
    assert {child["booked_on"] for child in children} == {parent["booked_on"]}
    assert {child["parent_id"] for child in children} == {parent["id"]}
    assert children == (await client.get(f"/api/transactions/{parent['id']}/splits")).json()

    # The page listing shows the parent with a split count and hides its children.
    page = await listing(client, q="edeka", limit=500)
    listed = {row["id"]: row for row in page["rows"]}
    assert listed[parent["id"]]["split_count"] == 2
    assert not any(child["id"] in listed for child in children)

    # The split-aware view queries read is the mirror image: children, never the parent.
    view = (await client.get("/api/transactions", params={"q": "edeka", "limit": 500})).json()
    ids = {row["id"] for row in view["rows"]}
    assert parent["id"] not in ids
    assert {child["id"] for child in children} <= ids

    # The parent's amount is the total of its legs, so an inline edit of it alone is refused.
    stuck = await client.patch(f"/api/transactions/{parent['id']}", json={"amount_cents": total - 1000})
    assert stuck.status_code == 400
    assert "add up to" in stuck.json()["detail"]
    assert (await listing(client, q="edeka", limit=500))["rows"] == page["rows"]

    # Editing the split is the same call: ids that come back are updated, new ones inserted.
    reshuffled = await client.put(
        f"/api/transactions/{parent['id']}/splits",
        json={
            "children": [
                {"id": children[0]["id"], "description": "Edeka groceries", "amount_cents": total - 500},
                {"id": children[1]["id"], "description": "Edeka household", "amount_cents": 200},
            ]
        },
    )
    assert reshuffled.status_code == 400, "children that do not sum are refused on an edit too"
    fixed = await client.put(
        f"/api/transactions/{parent['id']}/splits",
        json={
            "children": [
                {"id": children[0]["id"], "description": "Edeka groceries", "amount_cents": total - 500},
                {"description": "Edeka drinks", "amount_cents": 500},
            ]
        },
    )
    assert fixed.status_code == 200, fixed.text
    assert sorted(child["description"] for child in fixed.json()) == ["Edeka drinks", "Edeka groceries"]
    assert (await client.get(f"/api/transactions/{fixed.json()[0]['id']}/splits")).json() == []

    # Removing every child makes it a plain booking again.
    assert (await client.put(f"/api/transactions/{parent['id']}/splits", json={"children": []})).status_code == 200
    again = await listing(client, q="edeka", limit=500)
    assert {row["id"] for row in again["rows"]} == {row["id"] for row in page["rows"]}
    assert all(row["split_count"] == 0 for row in again["rows"])
    view_again = (await client.get("/api/transactions", params={"limit": 500})).json()
    assert parent["id"] in {row["id"] for row in view_again["rows"]}


async def test_bulk_recategorize_and_delete(client: httpx.AsyncClient) -> None:
    await import_synthetic(client)
    categories = await taxonomy(client)
    groceries = categories["Groceries"]
    ids = [row["id"] for row in (await listing(client, limit=3))["rows"]]

    mismatch = await client.post(
        "/api/transactions/bulk-recategorize",
        json={
            "ids": ids,
            "category_id": categories["Dining"]["id"],
            "subcategory_id": groceries["subcategories"][0]["id"],
        },
    )
    assert mismatch.status_code == 400

    done = await client.post(
        "/api/transactions/bulk-recategorize",
        json={"ids": ids, "category_id": groceries["id"], "subcategory_id": groceries["subcategories"][0]["id"]},
    )
    assert done.status_code == 200, done.text
    assert done.json() == {"updated": 3}
    assert (await listing(client, category_id=groceries["id"]))["total"] == 3
    assert (await listing(client, needs_review=True))["total"] == 430

    # A parent and its children go together, so deleting the parent never leaves a broken split.
    parent = (
        await client.post(
            "/api/transactions",
            json={
                "booked_on": "2025-05-08",
                "description": "Receipt to split",
                "amount_cents": -1000,
                "account_id": (await client.get("/api/accounts")).json()[0]["id"],
            },
        )
    ).json()
    split = await client.put(
        f"/api/transactions/{parent['id']}/splits",
        json={
            "children": [
                {"description": "Groceries", "amount_cents": -700},
                {"description": "Household", "amount_cents": -300},
            ]
        },
    )
    assert split.status_code == 200, split.text
    assert (await listing(client))["total"] == 434

    deleted = await client.post("/api/transactions/bulk-delete", json={"ids": [parent["id"]]})
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": 1}
    assert (await listing(client))["total"] == 433
    assert (await client.get("/api/transactions")).json()["total"] == 433, "the children went with the parent"

    dropped = await client.post("/api/transactions/bulk-delete", json={"ids": ids})
    assert dropped.json() == {"deleted": 3}
    assert (await listing(client))["total"] == 430
    # Ids that are not in the profile are simply not there to delete.
    assert (await client.post("/api/transactions/bulk-delete", json={"ids": ["nope"]})).json() == {"deleted": 0}


async def test_a_transaction_can_be_added_by_hand(client: httpx.AsyncClient) -> None:
    account_id = await import_synthetic(client)
    categories = await taxonomy(client)

    created = await client.post(
        "/api/transactions",
        json={
            "booked_on": "2025-07-02",
            "description": "Lunch paid in cash",
            "amount_cents": -1200,
            "account_id": account_id,
            "category_id": categories["Dining"]["id"],
            "subcategory_id": categories["Dining"]["subcategories"][0]["id"],
        },
    )
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["source"] == "manual"
    assert (row["description"], row["amount_cents"], row["category"]) == ("Lunch paid in cash", -1200, "Dining")

    assert (await listing(client))["total"] == 434
    assert (await listing(client, q="cash", limit=10))["rows"][0]["id"] == row["id"]

    refused = await client.post(
        "/api/transactions",
        json={"booked_on": "2025-07-02", "description": "x", "amount_cents": -1, "account_id": "nope"},
    )
    assert refused.status_code == 400
    assert "account" in refused.json()["detail"]
