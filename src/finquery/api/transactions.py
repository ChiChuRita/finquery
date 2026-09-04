"""The transactions page: listing with filters, inline edits, the split editor, bulk actions.

Two ways to look at a split, one query. `include_parents=false` is what every reader wants and
what `transaction_view` shows (ADR 0005): the children of a split, never the parent. The page
asks for `include_parents=true` instead, which lists the parent with a `split_count` and hides
its children, because there they are edited under the expanded row. Both modes read the base
tables rather than the view, since editing needs the ids the view joins away.

Refusals travel as a 400 with a readable `detail`: `TransactionEditError` for a pair the
taxonomy does not allow, `SplitSumError` from the session guard when children stop summing to
their parent. Both are mapped once in the app factory, so no endpoint here catches them.

Every endpoint is explicitly profile-scoped, the same convention as conversations and imports:
a read takes `profile_id` as a required query parameter, a write carries it in the body, an
unknown profile is a 404, and a transaction that belongs to another profile is a 404 too. No
endpoint reads an ambient profile, because there is none.
"""

from collections.abc import Sequence
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import ColumnElement, Select, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from finquery.api.profiles import get_profile_or_404
from finquery.db import Account, Category, Subcategory, Transaction, fingerprint

router = APIRouter()


class TransactionEditError(ValueError):
    """An edit the taxonomy or the profile refuses. Shown in place by the cell that caused it."""


class TransactionOut(BaseModel):
    id: str
    booked_on: date
    description: str
    counterparty: str | None
    title: str | None
    amount_cents: int
    category_id: str | None
    category: str | None
    subcategory_id: str | None
    subcategory: str | None
    account_id: str
    account: str
    source: str
    parent_id: str | None
    split_count: int


class TransactionPage(BaseModel):
    total: int
    rows: list[TransactionOut]


class AccountOut(BaseModel):
    id: str
    name: str


class TransactionIn(BaseModel):
    profile_id: str
    booked_on: date
    description: str
    amount_cents: int
    account_id: str
    category_id: str | None = None
    subcategory_id: str | None = None


class TransactionPatch(BaseModel):
    """Only the fields the request actually sent are applied, so null clears a category.

    `profile_id` is not one of them: it says which profile may edit the row, never what to write.
    """

    profile_id: str
    booked_on: date | None = None
    description: str | None = None
    amount_cents: int | None = None
    category_id: str | None = None
    subcategory_id: str | None = None
    account_id: str | None = None


class SplitChildIn(BaseModel):
    id: str | None = None
    description: str
    amount_cents: int
    category_id: str | None = None
    subcategory_id: str | None = None


class SplitsIn(BaseModel):
    profile_id: str
    children: list[SplitChildIn]


class BulkRecategorize(BaseModel):
    profile_id: str
    ids: list[str]
    category_id: str | None = None
    subcategory_id: str | None = None


class BulkDelete(BaseModel):
    profile_id: str
    ids: list[str]


def _like(text: str) -> str:
    """A contains-pattern for LIKE, with the wildcards a user may have typed escaped."""
    escaped = text.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def _conditions(
    profile_id: str,
    *,
    q: str | None,
    date_from: date | None,
    date_to: date | None,
    category_id: str | None,
    account_id: str | None,
    needs_review: bool,
    include_parents: bool,
) -> list[ColumnElement[bool]]:
    child = aliased(Transaction)
    conditions: list[ColumnElement[bool]] = [Transaction.profile_id == profile_id]
    conditions.append(
        Transaction.parent_id.is_(None)
        if include_parents
        else ~exists().where(child.parent_id == Transaction.id)
    )
    if q and q.strip():
        pattern = _like(q)
        conditions.append(
            or_(
                Transaction.description.ilike(pattern, escape="\\"),
                Transaction.counterparty.ilike(pattern, escape="\\"),
                Transaction.enriched_title.ilike(pattern, escape="\\"),
            )
        )
    if date_from:
        conditions.append(Transaction.booked_on >= date_from)
    if date_to:
        conditions.append(Transaction.booked_on <= date_to)
    if category_id:
        conditions.append(Transaction.category_id == category_id)
    if account_id:
        conditions.append(Transaction.account_id == account_id)
    if needs_review:
        # Needs review is the absence of a category, not a category.
        conditions.append(Transaction.category_id.is_(None))
    return conditions


Row = tuple[Transaction, str | None, str | None, str, int]


def _row_select(conditions: Sequence[ColumnElement[bool]]) -> Select[Row]:
    """The transaction with the names the page shows and how many legs it was split into."""
    child = aliased(Transaction)
    split_count = (
        select(func.count()).select_from(child).where(child.parent_id == Transaction.id).scalar_subquery()
    )
    return (
        select(Transaction, Category.name, Subcategory.name, Account.name, split_count)
        .join(Account, Account.id == Transaction.account_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .outerjoin(Subcategory, Subcategory.id == Transaction.subcategory_id)
        .where(*conditions)
    )


def _out(
    row: Transaction, category: str | None, subcategory: str | None, account: str, split_count: int
) -> TransactionOut:
    return TransactionOut(
        id=row.id,
        booked_on=row.booked_on,
        description=row.description,
        counterparty=row.counterparty,
        title=row.enriched_title,
        amount_cents=row.amount_cents,
        category_id=row.category_id,
        category=category,
        subcategory_id=row.subcategory_id,
        subcategory=subcategory,
        account_id=row.account_id,
        account=account,
        source=row.source,
        parent_id=row.parent_id,
        split_count=split_count,
    )


def _fetch_one(session: Session, profile_id: str, transaction_id: str) -> TransactionOut:
    conditions = [Transaction.profile_id == profile_id, Transaction.id == transaction_id]
    return _out(*session.execute(_row_select(conditions)).one())


def _children(session: Session, profile_id: str, parent_id: str) -> list[TransactionOut]:
    """The legs of a split, oldest first, so an added leg lands at the end of the editor."""
    conditions = [Transaction.profile_id == profile_id, Transaction.parent_id == parent_id]
    rows = session.execute(
        _row_select(conditions).order_by(Transaction.created_at, Transaction.id)
    ).all()
    return [_out(*row) for row in rows]


def _get(session: Session, profile_id: str, transaction_id: str) -> Transaction:
    row = session.scalars(
        select(Transaction).where(Transaction.profile_id == profile_id, Transaction.id == transaction_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="That transaction is not in this profile.")
    return row


def _resolve_account(session: Session, profile_id: str, account_id: str) -> str:
    known = session.scalar(select(Account.id).where(Account.profile_id == profile_id, Account.id == account_id))
    if known is None:
        raise TransactionEditError("That account is not in this profile.")
    return known


def _resolve_taxonomy(
    session: Session, profile_id: str, *, category_id: str | None, subcategory_id: str | None
) -> tuple[str | None, str | None]:
    """Check the pair a cell or a bulk action wants to store. No category means Needs review."""
    if category_id is not None:
        known = session.scalar(
            select(Category.id).where(Category.profile_id == profile_id, Category.id == category_id)
        )
        if known is None:
            raise TransactionEditError("That category is not in this profile.")
    if subcategory_id is None:
        return category_id, None
    found = session.execute(
        select(Subcategory.name, Subcategory.category_id).where(
            Subcategory.profile_id == profile_id, Subcategory.id == subcategory_id
        )
    ).first()
    if found is None:
        raise TransactionEditError("That subcategory is not in this profile.")
    name, owner = found
    if owner != category_id:
        raise TransactionEditError(f"{name} is not a subcategory of the chosen category.")
    return category_id, subcategory_id


def _description(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise TransactionEditError("A description cannot be empty.")
    return stripped


@router.get("/transactions", response_model=TransactionPage)
async def list_transactions(
    request: Request,
    profile_id: str,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: str | None = None,
    account_id: str | None = None,
    needs_review: bool = False,
    include_parents: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> TransactionPage:
    conditions = _conditions(
        profile_id,
        q=q,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        account_id=account_id,
        needs_review=needs_review,
        include_parents=include_parents,
    )
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        total = session.scalar(select(func.count()).select_from(Transaction).where(*conditions)) or 0
        rows = session.execute(
            _row_select(conditions)
            .order_by(Transaction.booked_on.desc(), Transaction.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return TransactionPage(total=total, rows=[_out(*row) for row in rows])


@router.post("/transactions", response_model=TransactionOut, status_code=201)
async def create_transaction(request: Request, payload: TransactionIn) -> TransactionOut:
    profile_id = payload.profile_id
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        account_id = _resolve_account(session, profile_id, payload.account_id)
        category_id, subcategory_id = _resolve_taxonomy(
            session, profile_id, category_id=payload.category_id, subcategory_id=payload.subcategory_id
        )
        description = _description(payload.description)
        row = Transaction(
            profile_id=profile_id,
            account_id=account_id,
            booked_on=payload.booked_on,
            amount_cents=payload.amount_cents,
            description=description,
            category_id=category_id,
            subcategory_id=subcategory_id,
            source="manual",
            fingerprint=fingerprint(account_id, payload.booked_on, payload.amount_cents, description),
        )
        session.add(row)
        session.commit()
        return _fetch_one(session, profile_id, row.id)


@router.patch("/transactions/{transaction_id}", response_model=TransactionOut)
async def patch_transaction(request: Request, transaction_id: str, patch: TransactionPatch) -> TransactionOut:
    profile_id = patch.profile_id
    fields = patch.model_dump(exclude_unset=True, exclude={"profile_id"})
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        row = _get(session, profile_id, transaction_id)
        # Everything is checked before anything is assigned: a query in between would autoflush
        # a half-applied row and let the split guard judge a state that was never asked for.
        updates: dict[str, object] = {}
        if "description" in fields:
            updates["description"] = _description(fields["description"] or "")
        if fields.get("booked_on") is not None:
            updates["booked_on"] = fields["booked_on"]
        if fields.get("amount_cents") is not None:
            updates["amount_cents"] = fields["amount_cents"]
        if fields.get("account_id") is not None:
            updates["account_id"] = _resolve_account(session, profile_id, fields["account_id"])
        if "category_id" in fields or "subcategory_id" in fields:
            category_id = fields.get("category_id", row.category_id)
            subcategory_id = fields.get("subcategory_id", row.subcategory_id)
            # Moving a row to another category drops a subcategory that no longer belongs to it.
            if "subcategory_id" not in fields and category_id != row.category_id:
                subcategory_id = None
            updates["category_id"], updates["subcategory_id"] = _resolve_taxonomy(
                session, profile_id, category_id=category_id, subcategory_id=subcategory_id
            )

        for name, value in updates.items():
            setattr(row, name, value)
        # The fingerprint is the identity of the booking, so an edited booking gets a new one.
        row.fingerprint = fingerprint(row.account_id, row.booked_on, row.amount_cents, row.description)
        session.commit()
        return _fetch_one(session, profile_id, transaction_id)


@router.get("/transactions/{transaction_id}/splits", response_model=list[TransactionOut])
async def list_splits(request: Request, transaction_id: str, profile_id: str) -> list[TransactionOut]:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        _get(session, profile_id, transaction_id)
        return _children(session, profile_id, transaction_id)


@router.put("/transactions/{transaction_id}/splits", response_model=list[TransactionOut])
async def replace_splits(request: Request, transaction_id: str, payload: SplitsIn) -> list[TransactionOut]:
    """Save the whole set of legs at once: an entry with an id is edited, one without is added,
    a missing id is removed, and an empty list turns the split back into a plain booking. The
    session guard then checks that what is left sums to the parent."""
    profile_id = payload.profile_id
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        parent = _get(session, profile_id, transaction_id)
        if parent.parent_id is not None:
            raise TransactionEditError("One leg of a split cannot be split again.")
        existing = {
            row.id: row
            for row in session.scalars(select(Transaction).where(Transaction.parent_id == parent.id)).all()
        }
        # Every leg is checked first, because a query in between would autoflush the legs
        # written so far and the split guard would judge a set that is still half saved.
        legs = []
        for child in payload.children:
            category_id, subcategory_id = _resolve_taxonomy(
                session, profile_id, category_id=child.category_id, subcategory_id=child.subcategory_id
            )
            description = _description(child.description)
            # A leg is the parent's booking with a share of its money, so date and account follow.
            legs.append(
                (
                    child.id,
                    {
                        "booked_on": parent.booked_on,
                        "description": description,
                        "amount_cents": child.amount_cents,
                        "category_id": category_id,
                        "subcategory_id": subcategory_id,
                        "fingerprint": fingerprint(
                            parent.account_id, parent.booked_on, child.amount_cents, description
                        ),
                    },
                )
            )

        for child_id, edited in legs:
            if child_id is None:
                session.add(
                    Transaction(
                        profile_id=profile_id,
                        account_id=parent.account_id,
                        source=parent.source,
                        import_id=parent.import_id,
                        parent_id=parent.id,
                        **edited,
                    )
                )
                continue
            row = existing.pop(child_id, None)
            if row is None:
                raise TransactionEditError("One of those split rows is no longer part of this transaction.")
            for name, value in edited.items():
                setattr(row, name, value)
        # Whatever the editor did not send back was removed from the split.
        for row in existing.values():
            session.delete(row)
        session.commit()
        return _children(session, profile_id, transaction_id)


@router.post("/transactions/bulk-recategorize")
async def bulk_recategorize(request: Request, payload: BulkRecategorize) -> dict[str, int]:
    profile_id = payload.profile_id
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        category_id, subcategory_id = _resolve_taxonomy(
            session, profile_id, category_id=payload.category_id, subcategory_id=payload.subcategory_id
        )
        rows = session.scalars(
            select(Transaction).where(Transaction.profile_id == profile_id, Transaction.id.in_(payload.ids))
        ).all()
        for row in rows:
            row.category_id, row.subcategory_id = category_id, subcategory_id
        session.commit()
        return {"updated": len(rows)}


@router.post("/transactions/bulk-delete")
async def bulk_delete(request: Request, payload: BulkDelete) -> dict[str, int]:
    profile_id = payload.profile_id
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        rows = session.scalars(
            select(Transaction).where(Transaction.profile_id == profile_id, Transaction.id.in_(payload.ids))
        ).all()
        # A selected parent takes its children with it through the foreign key, so deleting a
        # child of one explicitly would be a second delete of a row that is already gone.
        selected = {row.id for row in rows}
        doomed = [row for row in rows if row.parent_id not in selected]
        for row in doomed:
            session.delete(row)
        session.commit()
        return {"deleted": len(doomed)}


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(request: Request, profile_id: str) -> list[AccountOut]:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        rows = session.scalars(
            select(Account).where(Account.profile_id == profile_id).order_by(func.lower(Account.name))
        ).all()
        return [AccountOut(id=row.id, name=row.name) for row in rows]
