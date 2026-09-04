"""Schema behaviour: the seeded taxonomy, and what a split does to the query view.

Splits have no endpoint yet (ticket 04 builds the editor), so these two tests arrange the rows
in the app's own database and then assert over HTTP, which is where the view is observable.
"""

from datetime import date

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

from finquery.db import SplitSumError, Transaction, ensure_account, fingerprint
from finquery.taxonomy import DEFAULT_TAXONOMY


def add_transaction(session: Session, profile_id: str, account_id: str, **fields: object) -> Transaction:
    booked_on = fields.pop("booked_on", date(2025, 3, 14))
    amount_cents = fields.pop("amount_cents", -2073)
    description = fields.pop("description", "EDEKA SAGT DANKE")
    row = Transaction(
        profile_id=profile_id,
        account_id=account_id,
        booked_on=booked_on,
        amount_cents=amount_cents,
        description=description,
        fingerprint=fingerprint(account_id, booked_on, amount_cents, description),
        **fields,
    )
    session.add(row)
    return row


async def test_default_taxonomy_is_seeded_for_the_profile(client: httpx.AsyncClient, profile_id: str) -> None:
    categories = (await client.get("/api/categories", params={"profile_id": profile_id})).json()

    assert [c["name"] for c in categories] == list(DEFAULT_TAXONOMY)
    assert len(categories) >= 15
    by_name = {c["name"]: c for c in categories}
    assert [s["name"] for s in by_name["Groceries"]["subcategories"]] == ["Supermarket", "Bakery", "Drugstore"]
    # Unknown is a category a human assigns, so it needs no subcategories.
    assert by_name["Unknown"]["subcategories"] == []
    assert all(c["subcategories"] or c["name"] == "Unknown" for c in categories)


async def test_split_children_replace_their_parent_in_the_query_view(
    client: httpx.AsyncClient, session_factory: sessionmaker[Session], profile_id: str
) -> None:
    with session_factory() as session:
        account = ensure_account(session, profile_id, "Sparkasse Girokonto")
        parent = add_transaction(session, profile_id, account.id, description="EDEKA receipt")
        session.flush()
        add_transaction(session, profile_id, account.id, amount_cents=-1674, description="Groceries", parent_id=parent.id)
        add_transaction(session, profile_id, account.id, amount_cents=-399, description="Household", parent_id=parent.id)
        session.commit()

    page = (await client.get("/api/transactions", params={"profile_id": profile_id})).json()

    assert page["total"] == 2
    assert sorted(row["description"] for row in page["rows"]) == ["Groceries", "Household"]
    assert sum(row["amount_cents"] for row in page["rows"]) == -2073


async def test_split_children_must_sum_to_their_parent(
    client: httpx.AsyncClient, session_factory: sessionmaker[Session], profile_id: str
) -> None:
    with session_factory() as session:
        account = ensure_account(session, profile_id, "Sparkasse Girokonto")
        parent = add_transaction(session, profile_id, account.id)
        session.flush()
        add_transaction(session, profile_id, account.id, amount_cents=-1000, description="Groceries", parent_id=parent.id)
        with pytest.raises(SplitSumError):
            session.commit()

    assert (await client.get("/api/transactions", params={"profile_id": profile_id})).json()["total"] == 0
