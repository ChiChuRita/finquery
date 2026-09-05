"""What the data model allows to be written, in one place.

The transactions page (`finquery.api.transactions`) and changesets (`finquery.changesets`)
mutate the same rows, so the rules about what may be written live here rather than in either
caller: which taxonomy pair is legal, which account and which row belong to the profile, what a
description has to look like, how the legs of a split are replaced, and how a filter narrows the
listing. Every refusal is a `TransactionEditError`, which the app factory turns into a 400 with
the sentence in it.

Nothing here reads an ambient profile. A caller passes the profile it is allowed to touch.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from finquery.db import Account, Category, Subcategory, Transaction, fingerprint

NEEDS_REVIEW = "Needs review"
"""The absence of a category, as the UI and the previews spell it. Never a category row."""

MAX_DESCRIPTION = 500
MAX_COUNTERPARTY = 200
"""The widths of `db.Transaction.description` and `.counterparty`. SQLite does not enforce a
column width, so the limit is enforced here, once, for every path that writes one."""

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def clean_text(text: str, limit: int = MAX_DESCRIPTION) -> str:
    """One storable line: no control characters, no runs of whitespace, capped at the column.

    A bank's Verwendungszweck arrives with the line breaks it was printed with, occasionally
    with a stray control character, and occasionally very long. All three would otherwise reach
    the table, the prompt and the card as they came.
    """
    return " ".join(_CONTROL.sub(" ", text).split())[:limit].strip()


class TransactionEditError(ValueError):
    """An edit the taxonomy or the profile refuses. Shown in place by whatever caused it."""


def find_transaction(session: Session, profile_id: str, transaction_id: str) -> Transaction | None:
    """The row, if this profile owns it. Ownership is the lookup, never a separate check."""
    return session.scalars(
        select(Transaction).where(Transaction.profile_id == profile_id, Transaction.id == transaction_id)
    ).one_or_none()


def resolve_account(session: Session, profile_id: str, account_id: str) -> str:
    known = session.scalar(select(Account.id).where(Account.profile_id == profile_id, Account.id == account_id))
    if known is None:
        raise TransactionEditError("That account is not in this profile.")
    return known


def resolve_taxonomy(
    session: Session, profile_id: str, *, category_id: str | None, subcategory_id: str | None
) -> tuple[str | None, str | None]:
    """Check the pair a cell, a bulk action or a changeset wants to store.

    No category means Needs review, and a subcategory only exists inside its own category.
    """
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


def find_category(session: Session, profile_id: str, name: str) -> Category | None:
    """A category by name, case-insensitively: what the assistant and the taxonomy editor have."""
    return session.scalars(
        select(Category).where(Category.profile_id == profile_id, func.lower(Category.name) == name.strip().casefold())
    ).one_or_none()


def find_subcategory(session: Session, category_id: str, name: str) -> Subcategory | None:
    return session.scalars(
        select(Subcategory).where(
            Subcategory.category_id == category_id, func.lower(Subcategory.name) == name.strip().casefold()
        )
    ).one_or_none()


def resolve_names(
    session: Session, profile_id: str, category: str | None, subcategory: str | None
) -> tuple[str | None, str | None]:
    """Turn the names the assistant knows into the ids an apply writes.

    The taxonomy is what the profile actually holds, so a name that is not in it is refused with
    the list of names that are, and the agent can correct itself.
    """
    if category is None:
        if subcategory is not None:
            raise TransactionEditError("A subcategory needs the category it belongs to.")
        return None, None
    found = find_category(session, profile_id, category)
    if found is None:
        known = ", ".join(session.scalars(select(Category.name).where(Category.profile_id == profile_id)).all())
        raise TransactionEditError(f"There is no category called {category}. This profile has: {known}.")
    if subcategory is None:
        return found.id, None
    child = find_subcategory(session, found.id, subcategory)
    if child is None:
        known = ", ".join(sub.name for sub in found.subcategories) or "none"
        raise TransactionEditError(
            f"{found.name} has no subcategory called {subcategory}. Its subcategories are: {known}."
        )
    return found.id, child.id


def clean_description(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned:
        raise TransactionEditError("A description cannot be empty.")
    return cleaned


def like(text: str) -> str:
    """A contains-pattern for LIKE, with the wildcards a user may have typed escaped."""
    escaped = text.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return f"%{escaped}%"


def listing_conditions(
    profile_id: str,
    *,
    q: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: str | None = None,
    account_id: str | None = None,
    needs_review: bool = False,
    include_parents: bool = False,
) -> list[ColumnElement[bool]]:
    """The filter the transactions page and a changeset selection share.

    `include_parents=false` is the row set of `transaction_view` (ADR 0005): the children of a
    split, never the parent. That is what a query returns and therefore what a proposal that
    names a filter has to select.
    """
    child = aliased(Transaction)
    conditions: list[ColumnElement[bool]] = [Transaction.profile_id == profile_id]
    conditions.append(
        Transaction.parent_id.is_(None) if include_parents else ~exists().where(child.parent_id == Transaction.id)
    )
    if q and q.strip():
        pattern = like(q)
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


@dataclass(frozen=True)
class LegInput:
    """One leg of a split as a caller wants it: with an id it is edited, without one it is added."""

    description: str
    amount_cents: int
    category_id: str | None = None
    subcategory_id: str | None = None
    id: str | None = None


def replace_split_legs(session: Session, profile_id: str, parent: Transaction, legs: Sequence[LegInput]) -> None:
    """Save the whole set of legs of one transaction at once.

    An entry with an id is edited, one without is added, an id that is not sent is removed, and
    an empty list turns the split back into a plain booking. The session guard of ADR 0005 then
    checks that what is left sums to the parent.
    """
    if parent.parent_id is not None:
        raise TransactionEditError("One leg of a split cannot be split again.")
    # A split is at least two parts, whichever door it arrives through: the changeset, the
    # split editor and the legs a receipt proposes all land here.
    if len(legs) == 1:
        raise TransactionEditError(
            "A split needs at least two legs. Save no legs at all to turn it back into one booking."
        )
    existing = {
        row.id: row for row in session.scalars(select(Transaction).where(Transaction.parent_id == parent.id)).all()
    }
    # Every leg is checked first, because a query in between would autoflush the legs written so
    # far and the split guard would judge a set that is still half saved.
    checked = []
    for leg in legs:
        category_id, subcategory_id = resolve_taxonomy(
            session, profile_id, category_id=leg.category_id, subcategory_id=leg.subcategory_id
        )
        description = clean_description(leg.description)
        # A leg is the parent's booking with a share of its money, so date and account follow.
        checked.append(
            (
                leg.id,
                {
                    "booked_on": parent.booked_on,
                    "description": description,
                    "amount_cents": leg.amount_cents,
                    "category_id": category_id,
                    "subcategory_id": subcategory_id,
                    "fingerprint": fingerprint(parent.account_id, parent.booked_on, leg.amount_cents, description),
                },
            )
        )

    for leg_id, edited in checked:
        if leg_id is None:
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
        row = existing.pop(leg_id, None)
        if row is None:
            raise TransactionEditError("One of those split rows is no longer part of this transaction.")
        for name, value in edited.items():
            setattr(row, name, value)
    # Whatever the caller did not send back was removed from the split.
    for row in existing.values():
        session.delete(row)
