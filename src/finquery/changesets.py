"""Changesets: a proposal with an exact preview, applied by deterministic code.

The assistant describes an intent in words it has (category names, transaction ids it got from
a query, a filter). This module resolves that intent once, at proposal time, into a payload of
ids, computes the preview of exactly the rows it would touch, and stores both. Applying reads
the payload back and writes through `finquery.edits`, the same rules the transactions page
writes through. No model runs between Apply and the database.

Three things keep a preview honest:

- The payload freezes the rows. Applying touches exactly the ids the preview listed.
- `row_version` hashes those rows as they were, re-resolving a filter so a row that has since
  entered or left the selection counts as a change. A mismatch is `ChangesetStale`, never a
  quiet apply to a state nobody saw.
- A newer proposal that overlaps an older one supersedes it, so two cards can never both apply
  to the same rows.

`propose` refuses anything the data model would refuse (`TransactionEditError`, `SplitSumError`)
before a changeset exists, so the readable sentence goes back to the agent while it can still
correct itself.
"""

import json
from collections.abc import Sequence
from datetime import date, datetime
from hashlib import sha256
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finquery.db import (
    Account,
    Category,
    Changeset,
    Subcategory,
    Transaction,
    fingerprint,
    split_sum_error,
    utcnow,
)
from finquery.edits import (
    NEEDS_REVIEW,
    LegInput,
    TransactionEditError,
    clean_description,
    find_category,
    find_subcategory,
    find_transaction,
    listing_conditions,
    replace_split_legs,
    resolve_names,
    resolve_taxonomy,
)
from finquery.formats import eur
from finquery.nullish import empty_list_before, nullish_before

ChangesetKind = Literal["recategorize", "split", "edit", "delete", "taxonomy"]
TaxonomyOperation = Literal["add", "rename", "merge", "delete"]
# The statuses are on `db.Changeset.status` and in CONTEXT.md; nothing here takes one as an
# argument, so they stay strings rather than a Literal nobody would be checked against.

PREVIEW_ROWS = 50
"""How many affected rows the card tables. The payload always carries every one of them."""

FIELDS = ("date", "description", "amount", "category", "subcategory")
UNDOABLE = ("recategorize", "edit")
"""The kinds whose before state is enough to put the data back exactly as it was."""


class ChangesetError(ValueError):
    """A changeset that cannot be proposed, applied, discarded or undone. A 400."""


class ChangesetStale(ChangesetError):
    """The rows moved since the preview was computed. A 409, and the changeset turns stale."""


# --------------------------------------------------------------------------- intent


class Selection(BaseModel):
    """Which rows a proposal is about, when it names a filter instead of ids.

    The same filter the transactions page uses, by name rather than by id, and always over the
    split-aware row set: the legs of a split, never the booking they came from.
    """

    q: str | None = Field(default=None, description="Text that appears in the description, the counterparty or the title.")
    date_from: date | None = Field(default=None, description="Only bookings on or after this date.")
    date_to: date | None = Field(default=None, description="Only bookings on or before this date.")
    category: str | None = Field(default=None, description="Only bookings currently in this category.")
    account: str | None = Field(default=None, description="Only bookings in this account.")
    needs_review: bool = Field(default=False, description="Only bookings that have no category yet.")


class SplitLeg(BaseModel):
    """One part of a receipt. The legs of a split must add up to the booking exactly."""

    description: str = Field(description="What this part of the booking was for.")
    amount_cents: int = Field(description="This leg in cents, negative for spending, as in amount_cents.")
    category: str | None = Field(default=None, description="The category for this leg.")
    subcategory: str | None = Field(default=None, description="The subcategory, inside that category.")


class TaxonomyChange(BaseModel):
    """A change to the profile's own categories."""

    operation: TaxonomyOperation = Field(description="add, rename, merge or delete.")
    category: str = Field(description="The category the change is about, or the new one for add.")
    subcategory: str | None = Field(
        default=None, description="Set this to change a subcategory of that category instead of the category itself."
    )
    new_name: str | None = Field(default=None, description="The new name, for rename.")
    into: str | None = Field(
        default=None, description="For merge: the category (or subcategory) everything moves into."
    )


class ChangesetIntent(BaseModel):
    """What to change and which rows to change, in the words the assistant has.

    Name the rows either with `transaction_ids` from a query or with `where`, never both. Every
    category is named, not identified: the profile's own taxonomy is resolved here.
    """

    kind: ChangesetKind = Field(
        description="recategorize (move rows to a category), split (one booking into legs), "
        "edit (change fields of rows), delete (remove rows), taxonomy (change the categories)."
    )
    title: str = Field(description="A short title for the card, in the user's language.")
    transaction_ids: list[str] = Field(default_factory=list, description="The ids of the rows, from a query.")
    where: Selection | None = Field(default=None, description="A filter that selects the rows instead of ids.")
    category: str | None = Field(default=None, description="The category to put the rows into.")
    subcategory: str | None = Field(default=None, description="The subcategory to put the rows into.")
    description: str | None = Field(default=None, description="For edit: the new description.")
    amount_cents: int | None = Field(default=None, description="For edit: the new amount in cents.")
    booked_on: date | None = Field(default=None, description="For edit: the new booking date.")
    legs: list[SplitLeg] = Field(default_factory=list, description="For split: the parts, which must sum to the booking.")
    taxonomy: TaxonomyChange | None = Field(default=None, description="For taxonomy: the change to the categories.")

    # A model that writes "None" for a subcategory it does not want would have every row of the
    # preview carry that word as its subcategory (review of 2026-09-04).
    _nulls = nullish_before("category", "subcategory", "description", "amount_cents", "booked_on")
    # And a model that writes `legs: null` on a recategorize means it has no legs. Every field
    # here is optional per kind, so a null in any of them is the absence it looks like: the two
    # `propose_changeset` calls of the 9B review died on this one and left an empty turn.
    _empty = empty_list_before("transaction_ids", "legs")


# --------------------------------------------------------------------------- payload


class ResolvedLeg(BaseModel):
    description: str
    amount_cents: int
    category_id: str | None = None
    subcategory_id: str | None = None


class ResolvedTaxonomy(BaseModel):
    operation: TaxonomyOperation
    name: str
    """The subject's current name, or the new name for add."""
    category_id: str | None = None
    """The category the change is about. For add it is the parent of a new subcategory, else null."""
    subcategory_id: str | None = None
    """Set when the change is about a subcategory rather than a category."""
    new_name: str | None = None
    into_category_id: str | None = None
    into_subcategory_id: str | None = None
    into_name: str | None = None


class Payload(BaseModel):
    """The resolved intent. Applying reads only this, so it never needs a name or a model."""

    kind: ChangesetKind
    transaction_ids: list[str] = Field(default_factory=list)
    where: dict[str, Any] | None = None
    """The filter as ids, kept so the version can re-resolve it and notice a row that moved in."""
    category_id: str | None = None
    subcategory_id: str | None = None
    set_category: bool = False
    description: str | None = None
    amount_cents: int | None = None
    booked_on: date | None = None
    legs: list[ResolvedLeg] = Field(default_factory=list)
    taxonomy: ResolvedTaxonomy | None = None
    taxonomy_ids: list[str] = Field(default_factory=list)


class PreviewRow(BaseModel):
    """One affected row: what it says now, and what it would say. Values are display strings."""

    id: str | None = None
    """The transaction, or null for a row the changeset creates (a leg of a split)."""
    before: dict[str, str | None] | None = None
    after: dict[str, str | None] | None = None
    """Null when the row goes away: deleted, or replaced by the legs of a split."""


class Preview(BaseModel):
    kind: ChangesetKind
    title: str
    summary: str
    note: str | None = None
    total: int
    """Every affected row, even when the table below shows only the first PREVIEW_ROWS."""
    fields: list[str]
    rows: list[PreviewRow]


class ChangesetOut(BaseModel):
    """What the card renders and what a reload reads back. One shape for the tool and the API."""

    id: str
    profile_id: str
    conversation_id: str | None
    kind: str
    title: str
    status: str
    summary: str
    note: str | None
    total: int
    fields: list[str]
    rows: list[PreviewRow]
    undoable: bool
    created_at: datetime
    applied_at: datetime | None


def to_out(changeset: Changeset) -> ChangesetOut:
    preview = Preview.model_validate_json(changeset.preview_json)
    return ChangesetOut(
        id=changeset.id,
        profile_id=changeset.profile_id,
        conversation_id=changeset.conversation_id,
        kind=changeset.kind,
        title=changeset.title,
        status=changeset.status,
        summary=preview.summary,
        note=preview.note,
        total=preview.total,
        fields=preview.fields,
        rows=preview.rows,
        undoable=changeset.status == "applied" and changeset.undo_json is not None,
        created_at=changeset.created_at,
        applied_at=changeset.applied_at,
    )


# --------------------------------------------------------------------------- selection


def _names(session: Session, profile_id: str) -> tuple[dict[str, str], dict[str, str]]:
    categories = dict(session.execute(select(Category.id, Category.name).where(Category.profile_id == profile_id)).all())
    subcategories = dict(
        session.execute(select(Subcategory.id, Subcategory.name).where(Subcategory.profile_id == profile_id)).all()
    )
    return categories, subcategories


def _subcategories_of(session: Session, category_id: str | None) -> dict[str, str]:
    """A category's subcategories by folded name, so a merge maps names without a query per row."""
    if not category_id:
        return {}
    rows = session.execute(
        select(Subcategory.name, Subcategory.id).where(Subcategory.category_id == category_id)
    ).all()
    return {name.casefold(): identifier for name, identifier in rows}


def _ordered(session: Session, conditions: Sequence[Any]) -> list[Transaction]:
    """The listing's own order, so the card reads like the transactions table."""
    return list(
        session.scalars(
            select(Transaction).where(*conditions).order_by(Transaction.booked_on.desc(), Transaction.id)
        ).all()
    )


def _where_args(where: dict[str, Any]) -> dict[str, Any]:
    """The stored filter, with its dates back as dates. JSON has no date type."""
    return {
        **where,
        "date_from": date.fromisoformat(where["date_from"]) if where.get("date_from") else None,
        "date_to": date.fromisoformat(where["date_to"]) if where.get("date_to") else None,
    }


def _rows_of(session: Session, profile_id: str, payload: Payload) -> list[Transaction]:
    """The rows this payload is about, resolved the same way every time it is asked.

    A filter and a taxonomy change re-resolve, which is what lets the version notice a row that
    has since entered or left the selection. Explicit ids are looked up as they stand.
    """
    if payload.where is not None:
        return _ordered(session, listing_conditions(profile_id, **_where_args(payload.where)))
    if payload.taxonomy is not None:
        taxonomy = payload.taxonomy
        if taxonomy.subcategory_id is not None:
            return _ordered(
                session, [Transaction.profile_id == profile_id, Transaction.subcategory_id == taxonomy.subcategory_id]
            )
        if taxonomy.category_id is not None and taxonomy.operation != "add":
            return _ordered(
                session, [Transaction.profile_id == profile_id, Transaction.category_id == taxonomy.category_id]
            )
        return []
    if not payload.transaction_ids:
        return []
    return _ordered(session, [Transaction.profile_id == profile_id, Transaction.id.in_(payload.transaction_ids)])


def _state(row: Transaction) -> str:
    return "|".join(
        [
            row.id,
            row.booked_on.isoformat(),
            str(row.amount_cents),
            row.description,
            row.category_id or "-",
            row.subcategory_id or "-",
            row.account_id,
            row.parent_id or "-",
        ]
    )


def row_version(session: Session, profile_id: str, payload: Payload) -> str:
    """A hash of everything an apply depends on, as it stands right now.

    The union of the frozen ids and what the selection resolves to today, so a row that changed,
    vanished, left the filter or newly matched it all move the hash.
    """
    rows = {row.id: row for row in _rows_of(session, profile_id, payload)}
    lines = [f"kind:{payload.kind}"]
    for row_id in sorted(set(rows) | set(payload.transaction_ids)):
        row = rows.get(row_id)
        lines.append(_state(row) if row is not None else f"{row_id}|missing")
    if payload.kind == "split":
        for parent_id in sorted(payload.transaction_ids):
            legs = session.execute(
                select(Transaction.id, Transaction.amount_cents)
                .where(Transaction.parent_id == parent_id)
                .order_by(Transaction.id)
            ).all()
            lines.extend(f"leg|{leg_id}|{cents}" for leg_id, cents in legs)
    for handle in payload.taxonomy_ids:
        lines.append(f"{handle}|{_taxonomy_name(session, profile_id, handle) or 'missing'}")
    return sha256("\n".join(lines).encode()).hexdigest()[:32]


def _taxonomy_name(session: Session, profile_id: str, handle: str) -> str | None:
    kind, _, identifier = handle.partition(":")
    if kind == "cat":
        return session.scalar(
            select(Category.name).where(Category.profile_id == profile_id, Category.id == identifier)
        )
    return session.scalar(
        select(Subcategory.name).where(Subcategory.profile_id == profile_id, Subcategory.id == identifier)
    )


# --------------------------------------------------------------------------- preview


def _euro(cents: int) -> str:
    """The machine-readable amount of a preview row. The browser formats it for display."""
    return f"{cents / 100:.2f}"


def _display(
    row: Transaction, categories: dict[str, str], subcategories: dict[str, str]
) -> dict[str, str | None]:
    return {
        "date": row.booked_on.isoformat(),
        "description": row.description,
        "amount": _euro(row.amount_cents),
        "category": categories.get(row.category_id or ""),
        "subcategory": subcategories.get(row.subcategory_id or ""),
    }


def _bookings(count: int) -> str:
    return "1 booking" if count == 1 else f"{count} bookings"


def _verb(count: int, singular: str, plural: str) -> str:
    """A summary is a sentence somebody reads, so one booking does not "are"."""
    return singular if count == 1 else plural


def _taxonomy_label(name: str, subcategory: str | None) -> str:
    return f"{name} under {subcategory}" if subcategory else name


def _fields_shown(rows: Sequence[PreviewRow]) -> list[str]:
    """Every column but subcategory, which is only worth a column when a row has one."""
    used = {
        field
        for row in rows
        for side in (row.before, row.after)
        if side is not None
        for field, value in side.items()
        if value is not None
    }
    return [field for field in FIELDS if field != "subcategory" or "subcategory" in used]


# --------------------------------------------------------------------------- proposing


def _resolve_where(session: Session, profile_id: str, where: Selection) -> dict[str, Any]:
    # A filter with nothing in it selects the whole profile, which is never what a proposal
    # about "the Netflix bookings" means. A model that sends `where: {}` is told to name the
    # rows instead (ticket 37).
    if where == Selection():
        raise TransactionEditError(
            "That filter selects every booking in the profile, which is not a change anyone "
            "asked for. Call `query` for the rows you mean and pass their ids, or narrow the "
            "filter with the text, the period or the category."
        )
    category_id = None
    if where.category:
        category = find_category(session, profile_id, where.category)
        if category is None:
            raise TransactionEditError(f"There is no category called {where.category}.")
        category_id = category.id
    account_id = None
    if where.account:
        account = session.scalars(
            select(Account).where(
                Account.profile_id == profile_id, func.lower(Account.name) == where.account.strip().casefold()
            )
        ).one_or_none()
        if account is None:
            raise TransactionEditError(f"There is no account called {where.account}.")
        account_id = account.id
    return {
        "q": where.q,
        "date_from": where.date_from.isoformat() if where.date_from else None,
        "date_to": where.date_to.isoformat() if where.date_to else None,
        "category_id": category_id,
        "account_id": account_id,
        "needs_review": where.needs_review,
    }


def _resolve_taxonomy_change(session: Session, profile_id: str, change: TaxonomyChange) -> ResolvedTaxonomy:
    """Turn a named taxonomy change into ids, refusing anything the taxonomy will not allow."""
    name = change.category.strip()
    if not name:
        raise TransactionEditError("A category needs a name.")
    category = find_category(session, profile_id, name)

    if change.operation == "add":
        if change.subcategory:
            if category is None:
                raise TransactionEditError(f"There is no category called {name} to add a subcategory to.")
            if find_subcategory(session, category.id, change.subcategory) is not None:
                raise TransactionEditError(f"{category.name} already has a subcategory called {change.subcategory}.")
            return ResolvedTaxonomy(
                operation="add", name=change.subcategory.strip(), category_id=category.id
            )
        if category is not None:
            raise TransactionEditError(f"This profile already has a category called {category.name}.")
        return ResolvedTaxonomy(operation="add", name=name)

    if category is None:
        known = ", ".join(session.scalars(select(Category.name).where(Category.profile_id == profile_id)).all())
        raise TransactionEditError(f"There is no category called {name}. This profile has: {known}.")
    subcategory = None
    if change.subcategory:
        subcategory = find_subcategory(session, category.id, change.subcategory)
        if subcategory is None:
            raise TransactionEditError(f"{category.name} has no subcategory called {change.subcategory}.")

    resolved = ResolvedTaxonomy(
        operation=change.operation,
        name=subcategory.name if subcategory else category.name,
        category_id=category.id,
        subcategory_id=subcategory.id if subcategory else None,
    )
    if change.operation == "rename":
        new_name = (change.new_name or "").strip()
        if not new_name:
            raise TransactionEditError("A rename needs the new name.")
        if new_name == resolved.name:
            raise TransactionEditError(f"{resolved.name} is already called that, so there is nothing to rename.")
        clash = (
            find_subcategory(session, category.id, new_name) if subcategory else find_category(session, profile_id, new_name)
        )
        if clash is not None and clash.id != resolved.subcategory_id and clash.id != resolved.category_id:
            raise TransactionEditError(f"{new_name} is already taken.")
        resolved.new_name = new_name
    if change.operation == "merge":
        target = (change.into or "").strip()
        if not target:
            raise TransactionEditError("A merge needs the category everything moves into.")
        if subcategory is not None:
            into_subcategory = find_subcategory(session, category.id, target)
            if into_subcategory is None:
                raise TransactionEditError(f"{category.name} has no subcategory called {target} to merge into.")
            if into_subcategory.id == subcategory.id:
                raise TransactionEditError("A subcategory cannot be merged into itself.")
            resolved.into_subcategory_id = into_subcategory.id
            resolved.into_category_id = category.id
            resolved.into_name = into_subcategory.name
        else:
            into_category = find_category(session, profile_id, target)
            if into_category is None:
                raise TransactionEditError(f"There is no category called {target} to merge into.")
            if into_category.id == category.id:
                raise TransactionEditError("A category cannot be merged into itself.")
            resolved.into_category_id = into_category.id
            resolved.into_name = into_category.name
    return resolved


def _resolve(session: Session, profile_id: str, intent: ChangesetIntent) -> Payload:
    """Everything the assistant named, checked and turned into ids. Refuses before it stores."""
    if intent.transaction_ids and intent.where is not None:
        raise TransactionEditError("Name the rows either by id or with a filter, not both.")

    payload = Payload(kind=intent.kind)
    if intent.kind == "taxonomy":
        if intent.taxonomy is None:
            raise TransactionEditError("A taxonomy changeset needs the change to make.")
        payload.taxonomy = _resolve_taxonomy_change(session, profile_id, intent.taxonomy)
        payload.taxonomy_ids = [
            handle
            for handle in (
                f"sub:{payload.taxonomy.subcategory_id}" if payload.taxonomy.subcategory_id else None,
                f"cat:{payload.taxonomy.category_id}" if payload.taxonomy.category_id else None,
                f"sub:{payload.taxonomy.into_subcategory_id}" if payload.taxonomy.into_subcategory_id else None,
                f"cat:{payload.taxonomy.into_category_id}" if payload.taxonomy.into_category_id else None,
            )
            if handle
        ]
        return payload

    if intent.where is not None:
        payload.where = _resolve_where(session, profile_id, intent.where)
    else:
        # An id from another profile is refused, never quietly skipped.
        for transaction_id in intent.transaction_ids:
            if find_transaction(session, profile_id, transaction_id) is None:
                raise TransactionEditError(f"Transaction {transaction_id} is not in this profile.")
        payload.transaction_ids = list(dict.fromkeys(intent.transaction_ids))

    if intent.kind in {"recategorize", "edit"} and (intent.category or intent.subcategory):
        payload.category_id, payload.subcategory_id = resolve_names(
            session, profile_id, intent.category, intent.subcategory
        )
        payload.set_category = True
    if intent.kind == "recategorize" and not payload.set_category:
        raise TransactionEditError("A recategorize changeset needs the category to move the rows to.")
    if intent.kind == "edit":
        if intent.description is not None:
            payload.description = clean_description(intent.description)
        payload.amount_cents = intent.amount_cents
        payload.booked_on = intent.booked_on
        if not payload.set_category and payload.description is None and payload.amount_cents is None and payload.booked_on is None:
            raise TransactionEditError("An edit changeset needs at least one field to change.")
    if intent.kind == "split":
        for leg in intent.legs:
            category_id, subcategory_id = resolve_names(session, profile_id, leg.category, leg.subcategory)
            payload.legs.append(
                ResolvedLeg(
                    description=clean_description(leg.description),
                    amount_cents=leg.amount_cents,
                    category_id=category_id,
                    subcategory_id=subcategory_id,
                )
            )
        if len(payload.legs) < 2:
            raise TransactionEditError("A split needs at least two legs.")
    return payload


def _freeze(session: Session, profile_id: str, payload: Payload) -> list[Transaction]:
    """Resolve the selection once and write the ids into the payload: that is what applies."""
    rows = _rows_of(session, profile_id, payload)
    if payload.where is not None or payload.taxonomy is not None:
        payload.transaction_ids = [row.id for row in rows]
    return rows


def _preview(session: Session, profile_id: str, title: str, payload: Payload, rows: list[Transaction]) -> Preview:
    categories, subcategories = _names(session, profile_id)
    shown = rows[:PREVIEW_ROWS]
    note: str | None = None
    preview_rows: list[PreviewRow] = []

    if payload.kind == "recategorize":
        target = categories.get(payload.category_id or "")
        for row in shown:
            before = _display(row, categories, subcategories)
            preview_rows.append(
                PreviewRow(
                    id=row.id,
                    before=before,
                    after={
                        **before,
                        "category": target,
                        "subcategory": subcategories.get(payload.subcategory_id or ""),
                    },
                )
            )
        label = target or NEEDS_REVIEW
        if payload.subcategory_id:
            label = f"{label} / {subcategories.get(payload.subcategory_id)}"
        summary = f"{_bookings(len(rows))} {_verb(len(rows), 'moves', 'move')} to {label}."
    elif payload.kind == "edit":
        for row in shown:
            before = _display(row, categories, subcategories)
            after = dict(before)
            if payload.description is not None:
                after["description"] = payload.description
            if payload.amount_cents is not None:
                after["amount"] = _euro(payload.amount_cents)
            if payload.booked_on is not None:
                after["date"] = payload.booked_on.isoformat()
            if payload.set_category:
                after["category"] = categories.get(payload.category_id or "")
                after["subcategory"] = subcategories.get(payload.subcategory_id or "")
            preview_rows.append(PreviewRow(id=row.id, before=before, after=after))
        # The fields the changeset writes, from the payload rather than from the rows the table
        # happens to show, so a long selection still names them all.
        written = {
            "date": payload.booked_on is not None,
            "description": payload.description is not None,
            "amount": payload.amount_cents is not None,
            "category": payload.set_category,
            "subcategory": payload.set_category and payload.subcategory_id is not None,
        }
        edited = ", ".join(field for field in FIELDS if written[field]) or "nothing"
        summary = f"{_bookings(len(rows))} {_verb(len(rows), 'is', 'are')} edited: {edited}."
    elif payload.kind == "delete":
        preview_rows = [PreviewRow(id=row.id, before=_display(row, categories, subcategories)) for row in shown]
        summary = f"{_bookings(len(rows))} {_verb(len(rows), 'is', 'are')} deleted."
        note = "Deleting is not undoable, so discard this instead if you are unsure."
    elif payload.kind == "split":
        if len(rows) != 1:
            raise TransactionEditError("A split is about exactly one booking.")
        parent = rows[0]
        if parent.parent_id is not None:
            raise TransactionEditError("One leg of a split cannot be split again.")
        legs_total = sum(leg.amount_cents for leg in payload.legs)
        if legs_total != parent.amount_cents:
            raise split_sum_error(legs_total, parent.amount_cents)
        preview_rows = [PreviewRow(id=parent.id, before=_display(parent, categories, subcategories))]
        preview_rows.extend(
            PreviewRow(
                after={
                    "date": parent.booked_on.isoformat(),
                    "description": leg.description,
                    "amount": _euro(leg.amount_cents),
                    "category": categories.get(leg.category_id or ""),
                    "subcategory": subcategories.get(leg.subcategory_id or ""),
                }
            )
            for leg in payload.legs
        )
        summary = f"{parent.description} of {eur(parent.amount_cents)} EUR becomes {len(payload.legs)} legs."
        note = "Queries and charts count the legs of a split, never the booking they came from."
        # Splitting a booking that is already split replaces its legs rather than adding to
        # them, so the card says so before Apply instead of after.
        existing = session.scalar(
            select(func.count(Transaction.id)).where(Transaction.parent_id == parent.id)
        )
        if existing:
            note = f"This booking is already split, so its {existing} current legs are replaced. {note}"
    else:
        assert payload.taxonomy is not None
        taxonomy = payload.taxonomy
        after_name = _taxonomy_after(taxonomy)
        target_subcategories = _subcategories_of(session, taxonomy.into_category_id)
        for row in shown:
            before = _display(row, categories, subcategories)
            after = dict(before)
            if taxonomy.subcategory_id is not None:
                after["subcategory"] = after_name
            else:
                after["category"] = after_name
                if taxonomy.operation == "merge":
                    # A row keeps its subcategory only where the target has one of the same name.
                    kept = before["subcategory"] or ""
                    after["subcategory"] = kept if kept.casefold() in target_subcategories else None
                elif taxonomy.operation == "delete":
                    after["subcategory"] = None
            preview_rows.append(PreviewRow(id=row.id, before=before, after=after))
        summary, note = _taxonomy_summary(taxonomy, len(rows))

    fields = _fields_shown(preview_rows)
    if len(rows) > len(shown):
        extra = f"Showing the first {len(shown)} of {len(rows)} bookings."
        note = f"{note} {extra}" if note else extra
    return Preview(
        kind=payload.kind, title=title, summary=summary, note=note, total=len(rows), fields=fields, rows=preview_rows
    )


def _taxonomy_after(taxonomy: ResolvedTaxonomy) -> str | None:
    if taxonomy.operation == "rename":
        return taxonomy.new_name
    if taxonomy.operation == "merge":
        return taxonomy.into_name
    if taxonomy.operation == "delete":
        return None
    return taxonomy.name


def _taxonomy_summary(taxonomy: ResolvedTaxonomy, affected: int) -> tuple[str, str | None]:
    nested = taxonomy.subcategory_id is not None or (taxonomy.operation == "add" and taxonomy.category_id)
    what = "subcategory" if nested else "category"
    if taxonomy.operation == "add":
        return (f"Adds the {what} {taxonomy.name}.", "No existing booking is touched.")
    if taxonomy.operation == "rename":
        keep = _verb(affected, "keeps its", "keep their")
        return (
            f"Renames the {what} {taxonomy.name} to {taxonomy.new_name}.",
            f"{_bookings(affected)} {keep} {what} under the new name." if affected else None,
        )
    if taxonomy.operation == "merge":
        note = f"{_bookings(affected)} {_verb(affected, 'moves', 'move')}, and {taxonomy.name} is removed."
        if taxonomy.subcategory_id is None:
            note += (
                " A booking keeps its subcategory only where "
                f"{taxonomy.into_name} has one with the same name."
            )
        return (f"Merges the {what} {taxonomy.name} into {taxonomy.into_name}.", note)
    lose = _verb(affected, "loses it and becomes", "lose it and become")
    return (
        f"Deletes the {what} {taxonomy.name}.",
        f"{_bookings(affected)} {lose} Needs review." if affected else "No booking uses it, so nothing else changes.",
    )


def propose(
    session: Session,
    profile_id: str,
    intent: ChangesetIntent,
    *,
    conversation_id: str | None = None,
) -> Changeset:
    """Resolve, validate, preview and store one proposal. Nothing is written to the data."""
    payload = _resolve(session, profile_id, intent)
    rows = _freeze(session, profile_id, payload)
    if not rows and payload.kind != "taxonomy":
        # An empty proposal is a card nobody can use, so the selection is sent back to be fixed.
        raise TransactionEditError(
            "That selection matches no booking in this profile. Call `query` first to find the "
            "rows and pass their ids, or widen the filter."
        )
    preview = _preview(session, profile_id, intent.title.strip() or "Proposed change", payload, rows)
    changeset = Changeset(
        profile_id=profile_id,
        conversation_id=conversation_id,
        kind=payload.kind,
        title=preview.title,
        status="proposed",
        payload_json=payload.model_dump_json(),
        preview_json=preview.model_dump_json(),
        row_version=row_version(session, profile_id, payload),
    )
    _supersede(session, profile_id, payload)
    session.add(changeset)
    session.flush()
    return changeset


def _supersede(session: Session, profile_id: str, payload: Payload) -> None:
    """A newer proposal about the same rows retires the older one, so only one card can apply."""
    fresh_rows, fresh_taxonomy = set(payload.transaction_ids), set(payload.taxonomy_ids)
    open_proposals = session.scalars(
        select(Changeset).where(Changeset.profile_id == profile_id, Changeset.status == "proposed")
    ).all()
    for other in open_proposals:
        older = Payload.model_validate_json(other.payload_json)
        if (fresh_rows & set(older.transaction_ids)) or (fresh_taxonomy & set(older.taxonomy_ids)):
            other.status = "superseded"


# --------------------------------------------------------------------------- applying


def refresh(session: Session, profile_id: str, changeset: Changeset) -> Changeset:
    """Turn a proposal whose rows have moved stale, so a reloaded card says so before Apply."""
    if changeset.status == "proposed":
        payload = Payload.model_validate_json(changeset.payload_json)
        if row_version(session, profile_id, payload) != changeset.row_version:
            changeset.status = "stale"
    return changeset


def apply(session: Session, profile_id: str, changeset: Changeset) -> Changeset:
    """Run the changeset. Deterministic code, the same resolvers the transactions page uses."""
    if changeset.status != "proposed":
        raise ChangesetError(_why_not(changeset, "applied"))
    payload = Payload.model_validate_json(changeset.payload_json)
    if row_version(session, profile_id, payload) != changeset.row_version:
        changeset.status = "stale"
        raise ChangesetStale(
            "Those bookings changed since this preview was computed, so it was not applied. "
            "Ask again for a fresh proposal."
        )

    rows = _ordered(session, [Transaction.profile_id == profile_id, Transaction.id.in_(payload.transaction_ids)])
    if payload.kind in UNDOABLE:
        changeset.undo_json = json.dumps([_undo_state(row, payload) for row in rows])
    if payload.kind == "recategorize":
        category_id, subcategory_id = resolve_taxonomy(
            session, profile_id, category_id=payload.category_id, subcategory_id=payload.subcategory_id
        )
        for row in rows:
            row.category_id, row.subcategory_id = category_id, subcategory_id
    elif payload.kind == "edit":
        _write_edit(session, profile_id, payload, rows)
    elif payload.kind == "delete":
        # A selected parent takes its children with it, so deleting a child explicitly would be
        # a second delete of a row that is already gone.
        selected = {row.id for row in rows}
        for row in rows:
            if row.parent_id not in selected:
                session.delete(row)
    elif payload.kind == "split":
        if not rows:
            raise ChangesetError("The booking this split is about is no longer in this profile.")
        replace_split_legs(
            session,
            profile_id,
            rows[0],
            [
                LegInput(
                    description=leg.description,
                    amount_cents=leg.amount_cents,
                    category_id=leg.category_id,
                    subcategory_id=leg.subcategory_id,
                )
                for leg in payload.legs
            ],
        )
    else:
        _write_taxonomy(session, profile_id, payload, rows)

    if (missed := _not_written(session, payload, rows)) is not None:
        raise ChangesetError(missed)
    changeset.status = "applied"
    changeset.applied_at = utcnow()
    return changeset


def _not_written(session: Session, payload: Payload, rows: Sequence[Transaction]) -> str | None:
    """Why this apply did not do what it said, read back from the database, or None.

    Deterministic code that writes through a session is still code that can write nothing, and a
    card that says Applied over an unchanged database is worse than a card that fails: a bill
    split flipped to Applied over a parent that never grew a leg (e2e of 2026-09-05, B3). So the
    write is flushed and read again here, in the same transaction and before the status is
    flipped, through column selects that go to the connection rather than to the identity map.
    A refusal leaves the changeset `proposed` and rolls the write back with the request.

    A taxonomy change is not checked here: its effect is on the category rows, which
    `_write_taxonomy` resolves and writes by id, and none of the three failures this guards
    against can leave it half done.
    """
    session.flush()
    ids = [row.id for row in rows]
    if payload.kind == "split":
        parent = rows[0]
        legs, total = session.execute(
            select(func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                Transaction.parent_id == parent.id
            )
        ).one()
        if legs != len(payload.legs):
            return f"The split was not written: {parent.description} has {legs} legs, not {len(payload.legs)}."
        if total != parent.amount_cents:
            return f"The legs written add up to {eur(total)} EUR, not {eur(parent.amount_cents)} EUR."
        return None
    if payload.kind == "delete":
        left = session.scalar(select(func.count(Transaction.id)).where(Transaction.id.in_(ids))) or 0
        return f"{left} of the {len(ids)} bookings are still there." if left else None
    if payload.kind in ("recategorize", "edit"):
        # `is_distinct_from` rather than `!=`: a row left at Needs review compares NULL against
        # the target and would drop out of a `!=` count, which is the row most worth catching.
        written = {
            "category": (Transaction.category_id, payload.category_id) if payload.set_category else None,
            "description": (Transaction.description, payload.description),
            "amount": (Transaction.amount_cents, payload.amount_cents),
            "date": (Transaction.booked_on, payload.booked_on),
        }
        for name, pair in written.items():
            if pair is None or (name != "category" and pair[1] is None):
                continue
            column, value = pair
            wrong = session.scalar(
                select(func.count(Transaction.id)).where(
                    Transaction.id.in_(ids), column.is_distinct_from(value)
                )
            ) or 0
            if wrong:
                return f"The {name} of {wrong} of the {len(ids)} bookings did not change."
    return None


def _why_not(changeset: Changeset, verb: str) -> str:
    """Why a changeset in this status cannot be applied, discarded or undone, in one sentence."""
    reasons = {
        "applied": "has already been applied",
        "discarded": "was discarded",
        "stale": "is stale, because those bookings changed after the preview",
        "superseded": "was superseded by a newer proposal for the same bookings",
        "proposed": "has not been applied",
    }
    return f"This changeset {reasons[changeset.status]}, so it cannot be {verb}."


def _undo_state(row: Transaction, payload: Payload) -> dict[str, Any]:
    """Exactly the fields this changeset writes, as they are now, so Undo restores them."""
    state: dict[str, Any] = {"id": row.id}
    if payload.set_category:
        state["category_id"] = row.category_id
        state["subcategory_id"] = row.subcategory_id
    if payload.description is not None:
        state["description"] = row.description
    if payload.amount_cents is not None:
        state["amount_cents"] = row.amount_cents
    if payload.booked_on is not None:
        state["booked_on"] = row.booked_on.isoformat()
    return state


def _write_edit(session: Session, profile_id: str, payload: Payload, rows: Sequence[Transaction]) -> None:
    category_id, subcategory_id = (
        resolve_taxonomy(session, profile_id, category_id=payload.category_id, subcategory_id=payload.subcategory_id)
        if payload.set_category
        else (None, None)
    )
    for row in rows:
        if payload.description is not None:
            row.description = payload.description
        if payload.amount_cents is not None:
            row.amount_cents = payload.amount_cents
        if payload.booked_on is not None:
            row.booked_on = payload.booked_on
        if payload.set_category:
            row.category_id, row.subcategory_id = category_id, subcategory_id
        # The fingerprint is the identity of the booking, so an edited booking gets a new one.
        row.fingerprint = fingerprint(row.account_id, row.booked_on, row.amount_cents, row.description)


def _write_taxonomy(session: Session, profile_id: str, payload: Payload, rows: Sequence[Transaction]) -> None:
    taxonomy = payload.taxonomy
    assert taxonomy is not None
    if taxonomy.operation == "add":
        if taxonomy.category_id is None:
            position = session.scalar(select(func.count()).select_from(Category).where(Category.profile_id == profile_id))
            session.add(Category(profile_id=profile_id, name=taxonomy.name, position=position or 0))
        else:
            position = session.scalar(
                select(func.count()).select_from(Subcategory).where(Subcategory.category_id == taxonomy.category_id)
            )
            session.add(
                Subcategory(
                    profile_id=profile_id,
                    category_id=taxonomy.category_id,
                    name=taxonomy.name,
                    position=position or 0,
                )
            )
        return

    if taxonomy.subcategory_id is not None:
        subcategory = session.get(Subcategory, taxonomy.subcategory_id)
        if subcategory is None or subcategory.profile_id != profile_id:
            raise TransactionEditError("That subcategory is not in this profile.")
        if taxonomy.operation == "rename":
            subcategory.name = taxonomy.new_name or subcategory.name
            return
        for row in rows:
            row.subcategory_id = taxonomy.into_subcategory_id if taxonomy.operation == "merge" else None
        session.flush()
        session.delete(subcategory)
        return

    category = session.get(Category, taxonomy.category_id)
    if category is None or category.profile_id != profile_id:
        raise TransactionEditError("That category is not in this profile.")
    if taxonomy.operation == "rename":
        category.name = taxonomy.new_name or category.name
        return
    target_subcategories = _subcategories_of(session, taxonomy.into_category_id)
    names = {identifier: name for name, identifier in _subcategories_of(session, category.id).items()}
    for row in rows:
        if taxonomy.operation == "merge":
            # The same rule the preview showed: a subcategory survives where the target has that name.
            kept = names.get(row.subcategory_id or "", "")
            row.category_id = taxonomy.into_category_id
            row.subcategory_id = target_subcategories.get(kept)
        else:
            row.category_id, row.subcategory_id = None, None
    # The rows are moved off the category before it goes, so no row is left pointing at it.
    session.flush()
    session.delete(category)


def discard(changeset: Changeset) -> Changeset:
    if changeset.status not in {"proposed", "stale", "superseded"}:
        raise ChangesetError(_why_not(changeset, "discarded"))
    changeset.status = "discarded"
    return changeset


def undo(session: Session, profile_id: str, changeset: Changeset) -> Changeset:
    """Put back what an applied edit changed. Only the kinds whose before state is enough."""
    if changeset.status != "applied" or changeset.undo_json is None:
        raise ChangesetError(_why_not(changeset, "undone") if changeset.status != "applied" else "This change cannot be undone.")
    for state in json.loads(changeset.undo_json):
        row = find_transaction(session, profile_id, state["id"])
        if row is None:
            continue  # The booking is gone; there is nothing left to put back.
        if "category_id" in state:
            row.category_id, row.subcategory_id = state["category_id"], state["subcategory_id"]
        if "description" in state:
            row.description = state["description"]
        if "amount_cents" in state:
            row.amount_cents = state["amount_cents"]
        if "booked_on" in state:
            row.booked_on = date.fromisoformat(state["booked_on"])
        row.fingerprint = fingerprint(row.account_id, row.booked_on, row.amount_cents, row.description)
    # It stays applied_at, which is what tells an undone edit from a discarded proposal.
    changeset.status = "discarded"
    return changeset
