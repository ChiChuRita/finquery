"""Reading the profile's transactions and its accounts.

The listing reads `transaction_view`, the same split-aware view the query sub-agent is allowed
to see, so a split parent never shows up twice. Ticket 04 adds the filters, inline edits and
the split editor on top of this.
"""

from datetime import date

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select, text

from finquery.api.profiles import get_profile_or_404
from finquery.db import QUERY_VIEW, Account

router = APIRouter()


class TransactionOut(BaseModel):
    id: str
    booked_on: date
    description: str
    counterparty: str | None
    title: str | None
    amount_cents: int
    category: str | None
    subcategory: str | None
    account: str
    source: str


class TransactionPage(BaseModel):
    total: int
    rows: list[TransactionOut]


class AccountOut(BaseModel):
    id: str
    name: str


@router.get("/transactions", response_model=TransactionPage)
async def list_transactions(
    request: Request,
    profile_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TransactionPage:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        total = session.execute(
            text(f"SELECT count(*) FROM {QUERY_VIEW} WHERE profile_id = :profile_id"), {"profile_id": profile_id}
        ).scalar_one()
        rows = session.execute(
            text(
                f"""
                SELECT id, booked_on, description, counterparty, title, amount_cents,
                       category, subcategory, account, source
                FROM {QUERY_VIEW}
                WHERE profile_id = :profile_id
                ORDER BY booked_on DESC, id
                LIMIT :limit OFFSET :offset
                """
            ),
            {"profile_id": profile_id, "limit": limit, "offset": offset},
        ).mappings()
        return TransactionPage(total=total, rows=[TransactionOut(**row) for row in rows])


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(request: Request, profile_id: str) -> list[AccountOut]:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        rows = session.scalars(
            select(Account).where(Account.profile_id == profile_id).order_by(func.lower(Account.name))
        ).all()
        return [AccountOut(id=row.id, name=row.name) for row in rows]
