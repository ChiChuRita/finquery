import json

import httpx

from .conftest import SYNTHETIC, Chat, Scripts, default_profile_id, new_conversation, script


async def test_default_profile_is_seeded_and_can_be_managed(client: httpx.AsyncClient) -> None:
    listing = (await client.get("/api/profiles")).json()
    assert [p["name"] for p in listing] == ["Default"]

    created = await client.post("/api/profiles", json={"name": "Household"})
    assert created.status_code == 201
    assert created.json()["name"] == "Household"
    assert [p["name"] for p in (await client.get("/api/profiles")).json()] == ["Default", "Household"]

    assert (await client.post("/api/profiles", json={"name": "  Household  "})).status_code == 409
    assert (await client.post("/api/profiles", json={"name": "   "})).status_code == 422

    renamed = await client.patch(f"/api/profiles/{created.json()['id']}", json={"name": "Shared flat"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Shared flat"

    assert (await client.delete(f"/api/profiles/{created.json()['id']}")).status_code == 204
    assert [p["name"] for p in (await client.get("/api/profiles")).json()] == ["Default"]
    assert (await client.patch("/api/profiles/nope", json={"name": "x"})).status_code == 404


async def test_the_last_profile_cannot_be_deleted(client: httpx.AsyncClient) -> None:
    only = await default_profile_id(client)
    response = await client.delete(f"/api/profiles/{only}")
    assert response.status_code == 409
    assert "last profile" in response.json()["detail"]


async def test_conversations_belong_to_exactly_one_profile(
    client: httpx.AsyncClient, scripts: Scripts, chat: Chat
) -> None:
    scripts.fast = script("answer")
    first = await default_profile_id(client)
    second = (await client.post("/api/profiles", json={"name": "Household"})).json()["id"]

    mine = await new_conversation(client, first)
    theirs = await new_conversation(client, second)
    await chat(mine, "my question")
    await chat(theirs, "their question")

    assert [c["id"] for c in (await client.get("/api/conversations", params={"profile_id": first})).json()] == [mine]
    assert [c["id"] for c in (await client.get("/api/conversations", params={"profile_id": second})).json()] == [theirs]
    assert (await client.get("/api/conversations", params={"profile_id": "nope"})).status_code == 404
    assert (await client.post("/api/conversations", json={"profile_id": "nope"})).status_code == 404


async def test_deleting_a_profile_takes_its_conversations(client: httpx.AsyncClient, scripts: Scripts, chat: Chat) -> None:
    scripts.fast = script("answer")
    kept = await default_profile_id(client)
    doomed = (await client.post("/api/profiles", json={"name": "Household"})).json()["id"]
    kept_conversation = await new_conversation(client, kept)
    doomed_conversation = await new_conversation(client, doomed)
    await chat(doomed_conversation, "a question with a turn")

    assert (await client.delete(f"/api/profiles/{doomed}")).status_code == 204

    assert (await client.get(f"/api/conversations/{doomed_conversation}")).status_code == 404
    assert (await client.get(f"/api/conversations/{kept_conversation}")).status_code == 200


async def test_a_new_profile_starts_with_the_taxonomy_and_no_data_of_its_own(client: httpx.AsyncClient) -> None:
    """Everything profile-scoped is asked for by id, so two profiles never see each other's rows."""
    first = await default_profile_id(client)
    second = (await client.post("/api/profiles", json={"name": "Household"})).json()["id"]

    # The default taxonomy is seeded for a profile created over REST, not only for the first one.
    assert (await client.get("/api/categories", params={"profile_id": second})).json()[0]["name"] == (
        (await client.get("/api/categories", params={"profile_id": first})).json()[0]["name"]
    )

    csv = SYNTHETIC / "sparkasse-2025.csv"
    files = {"file": (csv.name, csv.read_bytes(), "text/csv")}
    mapping = (await client.post("/api/imports/preview", files=files)).json()["mapping"]
    committed = await client.post(
        "/api/imports",
        files=files,
        data={"profile_id": first, "mapping": json.dumps(mapping), "account_name": "Sparkasse Girokonto"},
    )
    assert committed.status_code == 201, committed.text

    for path, expected in (("/api/imports", []), ("/api/accounts", [])):
        assert (await client.get(path, params={"profile_id": second})).json() == expected
    assert (await client.get("/api/transactions", params={"profile_id": second})).json()["total"] == 0
    assert (await client.get("/api/transactions", params={"profile_id": first})).json()["total"] == 433
    assert (await client.get("/api/transactions", params={"profile_id": "nope"})).status_code == 404
