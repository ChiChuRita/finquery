"""Changesets: proposals in chat, deterministic apply, undo, and the taxonomy editor.

The chat model is scripted to call `propose_changeset` or `apply_simple_edit` with an intent,
which is how the real agent reaches them. Everything after that is deterministic code driven
over REST, so a test asserts on the transactions listing rather than on the model.
"""

import json
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, RetryPromptPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall
from sqlalchemy.orm import Session, sessionmaker

from finquery import changesets
from finquery.db import create_profile, ensure_account

from .conftest import Chat, Scripts, distilled, is_distillation_request, is_followup_request, new_conversation
from .test_data_model import add_transaction
from .test_transactions import first_account, import_synthetic, listing, scoped, taxonomy


def call_tool(name: str, args: dict[str, Any]):
    """A chat turn that calls one tool once, then reports what came back.

    A refusal reaches the agent as a retry prompt, so the second step echoes it: whatever the
    answer quotes is literally what the tool told the model.
    """

    async def fn(messages: list[ModelMessage], _info: AgentInfo) -> AsyncIterator[object]:
        if is_followup_request(messages):
            yield "No follow-ups."
            return
        if is_distillation_request(messages):
            yield distilled()
            return
        if refusal := _refusal(messages, name):
            yield f"That did not work: {refusal}"
            return
        if returned := _returned(messages, name):
            yield f"Proposed: {returned['title']} ({returned['status']})"
            return
        yield {0: DeltaToolCall(name=name, json_args=json.dumps(args))}

    return fn


def _returned(messages: list[ModelMessage], name: str) -> dict[str, Any] | None:
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, ToolReturnPart) and part.tool_name == name:
                assert isinstance(part.content, dict)
                return part.content
    return None


def _refusal(messages: list[ModelMessage], name: str) -> str | None:
    for message in reversed(messages):
        for part in message.parts:
            if isinstance(part, RetryPromptPart) and part.tool_name == name:
                return str(part.content)
    return None


def tool_output(chunks: list[dict[str, object]]) -> dict[str, Any]:
    outputs = [c["output"] for c in chunks if c["type"] == "tool-output-available"]
    assert len(outputs) == 1, chunks
    assert isinstance(outputs[0], dict)
    return outputs[0]


def answer(chunks: list[dict[str, object]]) -> str:
    return "".join(str(c["delta"]) for c in chunks if c["type"] == "text-delta").strip()


async def propose(client: httpx.AsyncClient, profile_id: str, intent: dict[str, Any]) -> dict[str, Any]:
    """The Settings taxonomy editor's path: propose over REST, look at the effect, then apply."""
    response = await client.post("/api/changesets", json={"profile_id": profile_id, "intent": intent})
    assert response.status_code == 201, response.text
    return response.json()


async def changeset(client: httpx.AsyncClient, profile_id: str, changeset_id: str) -> dict[str, Any]:
    response = await client.get(f"/api/changesets/{changeset_id}", params={"profile_id": profile_id})
    assert response.status_code == 200, response.text
    return response.json()


def after(preview: dict[str, Any], field: str) -> set[str | None]:
    return {row["after"][field] if row["after"] else None for row in preview["rows"]}


async def test_the_preview_of_a_proposal_is_what_applying_it_produces(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast = call_tool(
        "propose_changeset",
        {
            "kind": "recategorize",
            "title": "Netflix is a subscription",
            "where": {"q": "netflix"},
            "category": "Subscriptions",
            "subcategory": "Streaming",
        },
    )
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Put every Netflix booking into Subscriptions.")

    # The chat model, then the two post-turn steps. No model touches the proposal itself.
    assert scripts.roles == ["chat", "fast", "fast"]
    preview = tool_output(chunks)
    assert preview["status"] == "proposed"
    assert preview["kind"] == "recategorize"
    assert preview["total"] == 12
    assert len(preview["rows"]) == 12
    assert preview["fields"] == ["date", "description", "amount", "category", "subcategory"]
    # Every row is Needs review now and Subscriptions / Streaming afterwards.
    assert {row["before"]["category"] for row in preview["rows"]} == {None}
    assert after(preview, "category") == {"Subscriptions"}
    assert after(preview, "subcategory") == {"Streaming"}
    assert "12 bookings" in preview["summary"]
    # Nothing has changed yet: a proposal is inert.
    assert (await listing(client, profile_id, needs_review=True))["total"] == 433

    applied = await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    # The card reads the status from the server, so a reload shows applied too.
    assert (await changeset(client, profile_id, preview["id"]))["status"] == "applied"

    rows = {row["id"]: row for row in (await listing(client, profile_id, q="netflix", limit=500))["rows"]}
    assert len(rows) == 12
    for row in preview["rows"]:
        actual = rows[row["id"]]
        assert row["after"] == {
            "date": actual["booked_on"],
            "description": actual["description"],
            "amount": f"{actual['amount_cents'] / 100:.2f}",
            "category": actual["category"],
            "subcategory": actual["subcategory"],
        }
    assert (await listing(client, profile_id, needs_review=True))["total"] == 421


async def test_a_discarded_proposal_leaves_the_data_untouched(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    scripts.fast = call_tool(
        "propose_changeset",
        {"kind": "delete", "title": "Drop the cash withdrawals", "where": {"q": "geldautomat"}},
    )
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Delete every cash withdrawal.")

    preview = tool_output(chunks)
    assert preview["kind"] == "delete"
    assert preview["total"] == 20
    # A deleted row has no after.
    assert all(row["after"] is None for row in preview["rows"])

    discarded = await client.post(f"/api/changesets/{preview['id']}/discard", json={"profile_id": profile_id})
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["status"] == "discarded"
    assert discarded.json()["applied_at"] is None

    assert (await listing(client, profile_id))["total"] == 433
    # A discarded proposal cannot be applied afterwards.
    refused = await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})
    assert refused.status_code == 400
    assert "discarded" in refused.json()["detail"]
    assert (await listing(client, profile_id))["total"] == 433


async def test_a_changeset_whose_rows_moved_underneath_refuses_to_apply(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    categories = await taxonomy(client, profile_id)
    preview = await propose(
        client,
        profile_id,
        {
            "kind": "recategorize",
            "title": "Netflix is a subscription",
            "where": {"q": "netflix"},
            "category": "Subscriptions",
        },
    )
    assert preview["total"] == 12

    # Someone edits one of the rows on the transactions page in the meantime.
    moved = preview["rows"][0]["id"]
    patched = await client.patch(
        f"/api/transactions/{moved}", json=scoped(profile_id, category_id=categories["Dining"]["id"])
    )
    assert patched.status_code == 200, patched.text

    refused = await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})
    assert refused.status_code == 409, refused.text
    assert "changed since" in refused.json()["detail"]
    assert (await changeset(client, profile_id, preview["id"]))["status"] == "stale"

    # Not one row of the proposal was applied, and the edit that made it stale still stands.
    rows = {row["id"]: row for row in (await listing(client, profile_id, q="netflix", limit=500))["rows"]}
    assert rows[moved]["category"] == "Dining"
    assert [row["category"] for row in rows.values() if row["id"] != moved] == [None] * 11


async def test_a_simple_edit_applies_at_once_and_undo_reverts_it(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    row = (await listing(client, profile_id, q="vapiano", limit=1))["rows"][0]
    assert row["category"] is None
    scripts.fast = call_tool(
        "apply_simple_edit",
        {"transaction_id": row["id"], "title": "Vapiano is Dining", "category": "Dining", "subcategory": "Restaurant"},
    )
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Set that Vapiano booking to Dining.")

    edit = tool_output(chunks)
    assert edit["status"] == "applied"
    assert edit["kind"] == "edit"
    assert edit["undoable"] is True
    # The undo token the tool hands back is the changeset the Undo button posts to.
    assert edit["undo_token"] == edit["id"]
    assert edit["rows"][0]["before"]["category"] is None
    assert edit["rows"][0]["after"]["category"] == "Dining"
    assert edit["summary"] == "1 booking is edited: category, subcategory."

    applied = {r["id"]: r for r in (await listing(client, profile_id, q="vapiano", limit=20))["rows"]}
    assert (applied[row["id"]]["category"], applied[row["id"]]["subcategory"]) == ("Dining", "Restaurant")

    undone = await client.post(f"/api/changesets/{edit['id']}/undo", json={"profile_id": profile_id})
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "discarded"
    # It was applied once, which is what tells an undone edit from a discarded proposal.
    assert undone.json()["applied_at"] is not None

    reverted = {r["id"]: r for r in (await listing(client, profile_id, q="vapiano", limit=20))["rows"]}
    assert (reverted[row["id"]]["category"], reverted[row["id"]]["subcategory"]) == (None, None)
    # Undoing twice is refused rather than repeated.
    again = await client.post(f"/api/changesets/{edit['id']}/undo", json={"profile_id": profile_id})
    assert again.status_code == 400


async def test_a_split_summary_writes_a_four_figure_amount_the_german_way(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The thousands separator is the half of the format the small Edeka booking never shows."""
    await import_synthetic(client, profile_id)
    row = (await listing(client, profile_id, q="miete wohnung", limit=1))["rows"][0]
    assert row["amount_cents"] == -115000
    scripts.fast = call_tool(
        "propose_changeset",
        {
            "kind": "split",
            "title": "Split the rent",
            "transaction_ids": [row["id"]],
            "legs": [
                {"description": "Flat", "amount_cents": -100000, "category": "Housing"},
                {"description": "Garage", "amount_cents": -15000, "category": "Housing"},
            ],
        },
    )
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Split the January rent into the flat and the garage.")

    assert "1.150,00 EUR" in tool_output(chunks)["summary"]


async def test_a_split_from_chat_creates_legs_that_sum_to_the_parent(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    row = (await listing(client, profile_id, q="edeka", limit=1))["rows"][0]
    groceries = row["amount_cents"] + 500
    scripts.fast = call_tool(
        "propose_changeset",
        {
            "kind": "split",
            "title": "Split the Edeka receipt",
            "transaction_ids": [row["id"]],
            "legs": [
                {"description": "Groceries", "amount_cents": groceries, "category": "Groceries"},
                {"description": "Household", "amount_cents": -500, "category": "Shopping", "subcategory": "Home"},
            ],
        },
    )
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Split that Edeka receipt into groceries and household.")

    preview = tool_output(chunks)
    assert preview["kind"] == "split"
    # The one amount the browser never reformats, so the server writes it the German way the
    # rest of the app reads in: "-20,73 EUR", never "-20.73 EUR".
    cents = abs(row["amount_cents"])
    assert f"{cents // 100},{cents % 100:02d} EUR" in preview["summary"]
    # The parent as it is, then the legs it becomes: a new leg has no id yet.
    assert preview["rows"][0]["id"] == row["id"]
    assert preview["rows"][0]["after"] is None
    assert [leg["id"] for leg in preview["rows"][1:]] == [None, None]
    assert after(preview, "category") == {None, "Groceries", "Shopping"}

    applied = await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text

    legs = (await client.get(f"/api/transactions/{row['id']}/splits", params={"profile_id": profile_id})).json()
    assert [leg["description"] for leg in legs] == ["Groceries", "Household"]
    assert [leg["category"] for leg in legs] == ["Groceries", "Shopping"]
    assert sum(leg["amount_cents"] for leg in legs) == row["amount_cents"]
    # Queries count the legs and never the parent.
    view = (await client.get("/api/transactions", params={"profile_id": profile_id, "limit": 1})).json()
    assert view["total"] == 434


async def test_an_apply_that_writes_nothing_leaves_the_changeset_proposed(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card never says Applied over an unchanged database (e2e of 2026-09-05, B3).

    The bill split that flipped to Applied and wrote no legs was not reproducible on demand, so
    the write is taken away here instead: `apply` reads its own effect back inside the same
    transaction, and a split with no legs behind it is a refusal, not a green badge. The status
    stays `proposed`, so Apply is still there to press.
    """
    await import_synthetic(client, profile_id)
    row = (await listing(client, profile_id, q="edeka", limit=1))["rows"][0]
    scripts.fast = call_tool(
        "propose_changeset",
        {
            "kind": "split",
            "title": "Split the Edeka receipt",
            "transaction_ids": [row["id"]],
            "legs": [
                {"description": "Groceries", "amount_cents": row["amount_cents"] + 500, "category": "Groceries"},
                {"description": "Household", "amount_cents": -500, "category": "Shopping"},
            ],
        },
    )
    conversation_id = await new_conversation(client, profile_id)
    _, chunks = await chat(conversation_id, "Split that Edeka receipt into groceries and household.")
    changeset_id = tool_output(chunks)["id"]

    # The write silently does nothing, which is exactly what the run of 2026-09-05 saw.
    monkeypatch.setattr(changesets, "replace_split_legs", lambda *_args, **_kwargs: None)
    refused = await client.post(f"/api/changesets/{changeset_id}/apply", json={"profile_id": profile_id})
    assert refused.status_code == 400, refused.text
    assert "has 0 legs, not 2" in refused.json()["detail"]

    reread = await client.get(f"/api/changesets/{changeset_id}", params={"profile_id": profile_id})
    assert reread.json()["status"] == "proposed"
    assert (await client.get(f"/api/transactions/{row['id']}/splits", params={"profile_id": profile_id})).json() == []

    # With the write back, the same Apply goes through.
    monkeypatch.undo()
    applied = await client.post(f"/api/changesets/{changeset_id}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text
    assert applied.json()["status"] == "applied"
    legs = (await client.get(f"/api/transactions/{row['id']}/splits", params={"profile_id": profile_id})).json()
    assert len(legs) == 2


async def test_a_split_whose_legs_do_not_sum_is_refused_with_the_reason(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    row = (await listing(client, profile_id, q="edeka", limit=1))["rows"][0]
    scripts.fast = call_tool(
        "propose_changeset",
        {
            "kind": "split",
            "title": "Split the Edeka receipt",
            "transaction_ids": [row["id"]],
            "legs": [
                {"description": "Groceries", "amount_cents": -1000, "category": "Groceries"},
                {"description": "Household", "amount_cents": -500, "category": "Shopping"},
            ],
        },
    )
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Split that Edeka receipt into 10 and 5 euros.")

    # The refusal reached the agent in words, and the agent reported it, in the app's own money
    # format rather than the en-US one the split editor's live hint never used.
    cents = abs(row["amount_cents"])
    assert "add up to -15,00 EUR" in answer(chunks)
    assert f"the transaction is -{cents // 100},{cents % 100:02d} EUR" in answer(chunks)
    # Nothing was proposed and nothing was written.
    assert (await client.get(f"/api/transactions/{row['id']}/splits", params={"profile_id": profile_id})).json() == []
    assert (await listing(client, profile_id))["total"] == 433


async def test_a_taxonomy_merge_moves_the_rows_and_removes_the_old_category(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    categories = await taxonomy(client, profile_id)
    dining, restaurant = categories["Dining"]["id"], categories["Dining"]["subcategories"][0]["id"]
    takeaway = (await listing(client, profile_id, q="doener", limit=500))["rows"]
    assert len(takeaway) == 13
    recategorized = await client.post(
        "/api/transactions/bulk-recategorize",
        json=scoped(profile_id, ids=[r["id"] for r in takeaway], category_id=dining, subcategory_id=restaurant),
    )
    assert recategorized.json() == {"updated": 13}

    preview = await propose(
        client,
        profile_id,
        {
            "kind": "taxonomy",
            "title": "Dining is Groceries",
            "taxonomy": {"operation": "merge", "category": "Dining", "into": "Groceries"},
        },
    )
    # The effect on existing rows is on the card before anything is confirmed.
    assert preview["total"] == 13
    assert {row["before"]["category"] for row in preview["rows"]} == {"Dining"}
    assert after(preview, "category") == {"Groceries"}
    # Restaurant is not a subcategory of Groceries, so those rows lose it.
    assert after(preview, "subcategory") == {None}
    assert "Dining" in preview["note"] and "removed" in preview["note"]

    applied = await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text

    names = [c["name"] for c in (await client.get("/api/categories", params={"profile_id": profile_id})).json()]
    assert "Dining" not in names
    assert "Groceries" in names
    moved = (await listing(client, profile_id, q="doener", limit=500))["rows"]
    assert {row["category"] for row in moved} == {"Groceries"}
    assert {row["subcategory"] for row in moved} == {None}


async def test_a_merge_keeps_a_subcategory_the_target_also_has(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """The rule the preview states: a name the target category also has survives the merge."""
    await import_synthetic(client, profile_id)
    added = await propose(
        client,
        profile_id,
        {
            "kind": "taxonomy",
            "title": "Dining sells bread too",
            "taxonomy": {"operation": "add", "category": "Dining", "subcategory": "Bakery"},
        },
    )
    await client.post(f"/api/changesets/{added['id']}/apply", json={"profile_id": profile_id})
    categories = await taxonomy(client, profile_id)
    bakery = next(s["id"] for s in categories["Dining"]["subcategories"] if s["name"] == "Bakery")
    delivery = next(s["id"] for s in categories["Dining"]["subcategories"] if s["name"] == "Delivery")
    rows = (await listing(client, profile_id, q="steinecke", limit=500))["rows"]
    lieferando = (await listing(client, profile_id, q="lieferando", limit=500))["rows"]
    for ids, subcategory_id in ((rows, bakery), (lieferando, delivery)):
        recategorized = await client.post(
            "/api/transactions/bulk-recategorize",
            json=scoped(
                profile_id,
                ids=[row["id"] for row in ids],
                category_id=categories["Dining"]["id"],
                subcategory_id=subcategory_id,
            ),
        )
        assert recategorized.json()["updated"] == len(ids)

    preview = await propose(
        client,
        profile_id,
        {
            "kind": "taxonomy",
            "title": "Dining is Groceries",
            "taxonomy": {"operation": "merge", "category": "Dining", "into": "Groceries"},
        },
    )
    # Groceries has a Bakery, so those rows keep it; it has no Delivery, so those rows lose it.
    kept = {row["id"] for row in preview["rows"] if row["after"]["subcategory"] == "Bakery"}
    assert kept == {row["id"] for row in rows}
    assert {row["after"]["subcategory"] for row in preview["rows"] if row["id"] not in kept} == {None}

    assert (await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})).status_code == 200
    applied = (await listing(client, profile_id, q="steinecke", limit=500))["rows"]
    assert {(row["category"], row["subcategory"]) for row in applied} == {("Groceries", "Bakery")}
    moved = (await listing(client, profile_id, q="lieferando", limit=500))["rows"]
    assert {(row["category"], row["subcategory"]) for row in moved} == {("Groceries", None)}


async def test_add_rename_and_delete_of_a_category_show_their_effect_first(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    categories = await taxonomy(client, profile_id)
    subscriptions = categories["Subscriptions"]["id"]
    netflix = (await listing(client, profile_id, q="netflix", limit=500))["rows"]
    await client.post(
        "/api/transactions/bulk-recategorize",
        json=scoped(profile_id, ids=[r["id"] for r in netflix], category_id=subscriptions),
    )

    added = await propose(
        client,
        profile_id,
        {
            "kind": "taxonomy",
            "title": "A category for donations",
            "taxonomy": {"operation": "add", "category": "Donations"},
        },
    )
    # Adding touches no existing row, so the card says so instead of showing a table.
    assert added["total"] == 0
    assert added["rows"] == []
    assert (await client.post(f"/api/changesets/{added['id']}/apply", json={"profile_id": profile_id})).status_code == 200
    assert "Donations" in [c["name"] for c in (await client.get("/api/categories", params={"profile_id": profile_id})).json()]

    renamed = await propose(
        client,
        profile_id,
        {
            "kind": "taxonomy",
            "title": "Subscriptions are memberships",
            "taxonomy": {"operation": "rename", "category": "Subscriptions", "new_name": "Memberships"},
        },
    )
    assert renamed["total"] == 12
    assert after(renamed, "category") == {"Memberships"}
    assert (await client.post(f"/api/changesets/{renamed['id']}/apply", json={"profile_id": profile_id})).status_code == 200
    assert {row["category"] for row in (await listing(client, profile_id, q="netflix", limit=500))["rows"]} == {
        "Memberships"
    }

    deleted = await propose(
        client,
        profile_id,
        {
            "kind": "taxonomy",
            "title": "Drop Memberships",
            "taxonomy": {"operation": "delete", "category": "Memberships"},
        },
    )
    assert deleted["total"] == 12
    # Deleting a category leaves its rows as Needs review, which is an absence, not a category.
    assert after(deleted, "category") == {None}
    assert "Needs review" in deleted["note"]
    assert (await client.post(f"/api/changesets/{deleted['id']}/apply", json={"profile_id": profile_id})).status_code == 200
    assert "Memberships" not in [
        c["name"] for c in (await client.get("/api/categories", params={"profile_id": profile_id})).json()
    ]
    assert (await listing(client, profile_id, needs_review=True))["total"] == 433


async def test_a_selection_that_matches_nothing_is_refused(client: httpx.AsyncClient, profile_id: str) -> None:
    """An empty card is a card nobody can use, so the selection comes back to be corrected."""
    await import_synthetic(client, profile_id)
    response = await client.post(
        "/api/changesets",
        json={
            "profile_id": profile_id,
            "intent": {
                "kind": "recategorize",
                "title": "Nothing at all",
                "where": {"q": "no merchant is called this"},
                "category": "Groceries",
            },
        },
    )
    assert response.status_code == 400
    assert "matches no booking" in response.json()["detail"]


async def test_a_newer_proposal_supersedes_the_one_it_overlaps(client: httpx.AsyncClient, profile_id: str) -> None:
    await import_synthetic(client, profile_id)
    first = await propose(
        client,
        profile_id,
        {"kind": "recategorize", "title": "Netflix", "where": {"q": "netflix"}, "category": "Subscriptions"},
    )
    untouched = await propose(
        client,
        profile_id,
        {"kind": "recategorize", "title": "Spotify", "where": {"q": "spotify"}, "category": "Subscriptions"},
    )
    second = await propose(
        client,
        profile_id,
        {"kind": "recategorize", "title": "Netflix again", "where": {"q": "netflix"}, "category": "Leisure"},
    )

    assert (await changeset(client, profile_id, first["id"]))["status"] == "superseded"
    assert (await changeset(client, profile_id, untouched["id"]))["status"] == "proposed"
    assert second["status"] == "proposed"

    refused = await client.post(f"/api/changesets/{first['id']}/apply", json={"profile_id": profile_id})
    assert refused.status_code == 400
    assert "superseded" in refused.json()["detail"]
    assert (await client.post(f"/api/changesets/{second['id']}/apply", json={"profile_id": profile_id})).status_code == 200
    assert {row["category"] for row in (await listing(client, profile_id, q="netflix", limit=500))["rows"]} == {"Leisure"}


async def test_a_changeset_cannot_touch_another_profiles_rows(
    client: httpx.AsyncClient, session_factory: sessionmaker[Session], profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    with session_factory() as session:
        other = create_profile(session, "Housemate")
        account = ensure_account(session, other.id, "Other bank")
        theirs = add_transaction(
            session, other.id, account.id, booked_on=date(2025, 5, 4), amount_cents=-999999, description="NOT MINE"
        )
        session.commit()
        other_id, their_row = other.id, theirs.id

    # Naming a row of another profile is refused, not silently skipped.
    refused = await client.post(
        "/api/changesets",
        json={
            "profile_id": profile_id,
            "intent": {
                "kind": "recategorize",
                "title": "Reach across",
                "transaction_ids": [their_row],
                "category": "Groceries",
            },
        },
    )
    assert refused.status_code == 400
    assert "not in this profile" in refused.json()["detail"]

    # A filter only ever sees the proposing profile's rows. It has to narrow something (an
    # empty filter is refused, ticket 37), so this one is wide enough to hold both profiles.
    mine = await propose(
        client,
        profile_id,
        {
            "kind": "recategorize",
            "title": "Everything",
            "where": {"date_from": "2020-01-01"},
            "category": "Groceries",
        },
    )
    assert mine["total"] == 433

    # And the changeset itself belongs to its profile: another profile cannot see or apply it.
    assert (await client.get(f"/api/changesets/{mine['id']}", params={"profile_id": other_id})).status_code == 404
    assert (
        await client.post(f"/api/changesets/{mine['id']}/apply", json={"profile_id": other_id})
    ).status_code == 404
    assert (await client.get("/api/transactions", params={"profile_id": other_id})).json()["rows"][0]["category"] is None
    assert (await listing(client, profile_id, needs_review=True))["total"] == 433


async def test_a_bulk_edit_of_fields_previews_and_applies_every_row(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    account_id = await first_account(client, profile_id)
    assert account_id
    rows = (await listing(client, profile_id, q="adobe", limit=500))["rows"]
    assert len(rows) == 12

    preview = await propose(
        client,
        profile_id,
        {
            "kind": "edit",
            "title": "Adobe is a software subscription",
            "transaction_ids": [row["id"] for row in rows],
            "description": "Adobe CC subscription",
            "category": "Subscriptions",
            "subcategory": "Software",
        },
    )
    assert preview["total"] == 12
    assert after(preview, "description") == {"Adobe CC subscription"}
    assert after(preview, "category") == {"Subscriptions"}
    # An edit leaves the fields it does not name alone.
    assert after(preview, "amount") == {row["before"]["amount"] for row in preview["rows"]}

    assert (await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})).status_code == 200
    edited = (await listing(client, profile_id, q="Adobe CC subscription", limit=500))["rows"]
    assert len(edited) == 12
    assert {row["category"] for row in edited} == {"Subscriptions"}
    assert {row["subcategory"] for row in edited} == {"Software"}


async def test_a_subcategory_the_model_wrote_as_the_word_none_is_stored_as_no_subcategory(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat, profile_id: str
) -> None:
    """The fast slot fills an optional field with the word instead of leaving it out.

    A bulk recategorize then put the literal string "None" on every row, which the transactions
    table dutifully printed (review of 2026-09-04). The word is read as the absence it meant.
    """
    await import_synthetic(client, profile_id)
    scripts.fast = call_tool(
        "propose_changeset",
        {
            "kind": "recategorize",
            "title": "Netflix is a subscription",
            "where": {"q": "netflix"},
            "category": "Subscriptions",
            "subcategory": "None",
        },
    )
    conversation_id = await new_conversation(client, profile_id)

    _, chunks = await chat(conversation_id, "Recategorize the Netflix rows as Subscriptions.")

    preview = tool_output(chunks)
    assert preview["status"] == "proposed"
    assert after(preview, "category") == {"Subscriptions"}
    assert after(preview, "subcategory") == {None}, "the word None is not a subcategory"

    applied = await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text
    rows = (await listing(client, profile_id, q="netflix", limit=500))["rows"]
    assert {row["subcategory"] for row in rows} == {None}

# The awkward corners of a data operation: a second Apply, a second Undo, a card whose rows are
# already gone, and the taxonomy changes that mean nothing.


async def test_a_changeset_can_only_be_applied_discarded_and_undone_once(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """Every second press says which of the four states the card is in, in one sentence."""
    await import_synthetic(client, profile_id)
    preview = await propose(
        client,
        profile_id,
        {"kind": "recategorize", "title": "Netflix", "where": {"q": "netflix"}, "category": "Subscriptions"},
    )
    changeset_id = preview["id"]

    applied = await client.post(f"/api/changesets/{changeset_id}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text
    twice = await client.post(f"/api/changesets/{changeset_id}/apply", json={"profile_id": profile_id})
    assert twice.status_code == 400
    assert twice.json()["detail"] == "This changeset has already been applied, so it cannot be applied."

    undone = await client.post(f"/api/changesets/{changeset_id}/undo", json={"profile_id": profile_id})
    assert undone.status_code == 200, undone.text
    assert undone.json()["status"] == "discarded"
    rows = (await listing(client, profile_id, q="netflix", limit=500))["rows"]
    assert {row["category"] for row in rows} == {None}, "undo put all twelve rows back"

    for action, verb in (("undo", "undone"), ("apply", "applied"), ("discard", "discarded")):
        again = await client.post(f"/api/changesets/{changeset_id}/{action}", json={"profile_id": profile_id})
        assert again.status_code == 400, again.text
        assert again.json()["detail"] == f"This changeset was discarded, so it cannot be {verb}."
    # Undoing twice did not move the data a second time either.
    assert {row["category"] for row in (await listing(client, profile_id, q="netflix", limit=500))["rows"]} == {None}


async def test_a_taxonomy_change_that_would_do_nothing_is_refused(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """A card with nothing on it to decide is never drawn: the refusal says why instead."""
    for intent, detail in (
        (
            {"operation": "merge", "category": "Groceries", "into": "Groceries"},
            "A category cannot be merged into itself.",
        ),
        (
            {"operation": "merge", "category": "Groceries", "subcategory": "Supermarket", "into": "Supermarket"},
            "A subcategory cannot be merged into itself.",
        ),
        (
            {"operation": "rename", "category": "Groceries", "new_name": "Groceries"},
            "Groceries is already called that, so there is nothing to rename.",
        ),
        (
            {"operation": "add", "category": "Groceries"},
            "This profile already has a category called Groceries.",
        ),
    ):
        refused = await client.post(
            "/api/changesets",
            json={"profile_id": profile_id, "intent": {"kind": "taxonomy", "title": "Nothing", "taxonomy": intent}},
        )
        assert refused.status_code == 400, refused.text
        assert refused.json()["detail"] == detail


async def test_deleting_a_category_in_use_leaves_its_bookings_needing_review(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    categories = await taxonomy(client, profile_id)
    row = (await listing(client, profile_id, q="netflix", limit=1))["rows"][0]
    await client.patch(
        f"/api/transactions/{row['id']}", json=scoped(profile_id, category_id=categories["Leisure"]["id"])
    )

    preview = await propose(
        client,
        profile_id,
        {"kind": "taxonomy", "title": "Drop Leisure", "taxonomy": {"operation": "delete", "category": "Leisure"}},
    )
    assert preview["summary"] == "Deletes the category Leisure."
    assert preview["note"] == "1 booking loses it and becomes Needs review."
    assert after(preview, "category") == {None}

    applied = await client.post(f"/api/changesets/{preview['id']}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text
    assert "Leisure" not in await taxonomy(client, profile_id)
    moved = (await listing(client, profile_id, q="netflix", limit=1))["rows"][0]
    assert moved["category"] is None, "the booking is Needs review, not deleted"


async def test_splitting_a_booking_that_is_already_split_says_its_legs_are_replaced(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """Applying replaces the legs rather than adding to them, so the card says so before Apply."""
    await import_synthetic(client, profile_id)
    row = (await listing(client, profile_id, q="edeka", limit=1))["rows"][0]

    def legs(count: int) -> list[dict[str, Any]]:
        share = row["amount_cents"] // count
        rest = row["amount_cents"] - share * (count - 1)
        return [{"description": f"Teil {index + 1}", "amount_cents": share} for index in range(count - 1)] + [
            {"description": f"Teil {count}", "amount_cents": rest}
        ]

    first = await propose(
        client, profile_id, {"kind": "split", "title": "Zwei Teile", "transaction_ids": [row["id"]], "legs": legs(2)}
    )
    assert first["note"] == "Queries and charts count the legs of a split, never the booking they came from."
    first_applied = await client.post(f"/api/changesets/{first['id']}/apply", json={"profile_id": profile_id})
    assert first_applied.status_code == 200, first_applied.text

    second = await propose(
        client, profile_id, {"kind": "split", "title": "Drei Teile", "transaction_ids": [row["id"]], "legs": legs(3)}
    )
    assert second["note"].startswith("This booking is already split, so its 2 current legs are replaced.")
    second_applied = await client.post(f"/api/changesets/{second['id']}/apply", json={"profile_id": profile_id})
    assert second_applied.status_code == 200, second_applied.text

    children = (await client.get(f"/api/transactions/{row['id']}/splits", params={"profile_id": profile_id})).json()
    assert len(children) == 3, "the legs were replaced, not added to"
    assert sum(child["amount_cents"] for child in children) == row["amount_cents"]


async def test_a_split_of_one_leg_is_refused_wherever_it_is_asked_for(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    await import_synthetic(client, profile_id)
    row = (await listing(client, profile_id, q="edeka", limit=1))["rows"][0]

    refused = await client.post(
        "/api/changesets",
        json={
            "profile_id": profile_id,
            "intent": {
                "kind": "split",
                "title": "Ein Teil",
                "transaction_ids": [row["id"]],
                "legs": [{"description": "Alles", "amount_cents": row["amount_cents"]}],
            },
        },
    )
    assert refused.status_code == 400
    assert refused.json()["detail"] == "A split needs at least two legs."


async def test_deleting_an_import_takes_the_legs_of_its_split_bookings_with_it(
    client: httpx.AsyncClient, profile_id: str
) -> None:
    """The way back out of an import into the wrong profile, after the rows were worked on."""
    await import_synthetic(client, profile_id)
    categories = await taxonomy(client, profile_id)
    row = (await listing(client, profile_id, q="edeka", limit=1))["rows"][0]
    split = await propose(
        client,
        profile_id,
        {
            "kind": "split",
            "title": "Zwei Teile",
            "transaction_ids": [row["id"]],
            "legs": [
                {"description": "Lebensmittel", "amount_cents": row["amount_cents"] + 500},
                {"description": "Haushalt", "amount_cents": -500},
            ],
        },
    )
    applied = await client.post(f"/api/changesets/{split['id']}/apply", json={"profile_id": profile_id})
    assert applied.status_code == 200, applied.text
    other = (await listing(client, profile_id, q="netflix", limit=1))["rows"][0]
    await client.patch(
        f"/api/transactions/{other['id']}", json=scoped(profile_id, category_id=categories["Leisure"]["id"])
    )

    imports = (await client.get("/api/imports", params={"profile_id": profile_id})).json()
    assert len(imports) == 1
    deleted = await client.delete(f"/api/imports/{imports[0]['id']}", params={"profile_id": profile_id})
    assert deleted.status_code == 200, deleted.text
    assert (await listing(client, profile_id, limit=1))["total"] == 0
    assert (await listing(client, profile_id, include_parents=True, limit=1))["total"] == 0

    # The card of a change whose rows are gone says so rather than pretending it can be undone.
    stale = await client.post(f"/api/changesets/{split['id']}/undo", json={"profile_id": profile_id})
    assert stale.status_code == 400
    assert stale.json()["detail"] == "This change cannot be undone."
