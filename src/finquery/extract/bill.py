"""A photo of a bill: line items in, and either a split of an existing booking or a new one.

The interesting half of this is what the bill is matched against. A card payment for the same
amount within three days is almost certainly this receipt, and then the useful thing to do is
not to add a second booking but to split the one that is already there into what was actually
bought: one Edeka receipt becomes groceries and household separately. So a match proposes a
split changeset (`finquery.changesets`), the legs grouped by what the categorizer makes of each
line item, and the user applies it from the card that every other changeset uses.

With no match the bill is a new booking, and that goes through the draft table of
`ingest.typed`: the amount that lands is the amount that was extracted and shown, never one the
model retyped.

The guard here is the total. The line items are added up in code and held to the printed total,
so a receipt the model misread does not silently become a split whose legs are wrong. A bill
with no total printed is flagged and says so, because then there is nothing to check against.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai.settings import ModelSettings
from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.categorize.rules import load_categories, taxonomy_of
from finquery.categorize.subagent import MerchantBatchEntry, categorize_merchants
from finquery.changesets import ChangesetIntent, SplitLeg, propose, to_out
from finquery.db import Transaction
from finquery.extract import pdf
from finquery.extract.guards import RowUnreadable, money, parse_statement_date
from finquery.extract.subagent import Bill, read_bill
from finquery.formats import day, eur
from finquery.ingest.typed import ProposedTransaction, preview_card, store_drafts
from finquery.providers import ModelResolver

logger = logging.getLogger(__name__)

MATCH_DAYS = 3
"""How far from the receipt's date a booking may sit and still be the same payment."""

MAX_LEG_DESCRIPTION = 120

BillFlag = Literal["no_total", "does_not_add_up", "no_date", "no_items"]

FLAG_REASONS: dict[BillFlag, str] = {
    "no_total": "No total is printed on this receipt, so the line items could not be checked.",
    "does_not_add_up": "The line items do not add up to the printed total.",
    "no_date": "The date on the receipt could not be read.",
    "no_items": "No line item could be read from this receipt.",
}


class BillLine(BaseModel):
    """One line item, after the cents were parsed from the span the model pointed at."""

    description: str
    amount_cents: int
    """Unsigned, as printed on a receipt."""


class BillExtraction(BaseModel):
    """One receipt, checked. `total_cents` is what a match is looked for by."""

    merchant: str
    booked_on: date
    total_cents: int
    items: list[BillLine] = Field(default_factory=list)
    total_printed: bool = True
    flags: list[BillFlag] = Field(default_factory=list)
    line: str = ""
    """The one sentence about the arithmetic, counted here and quoted by the tool."""

    @property
    def verified(self) -> bool:
        return not self.flags


def _line_of(extraction: BillExtraction) -> str:
    if extraction.verified:
        return (
            f"{len(extraction.items)} line items add up to the printed total of "
            f"{eur(extraction.total_cents)} EUR."
        )
    return " ".join(FLAG_REASONS[flag] for flag in extraction.flags)


def check_bill(bill: Bill, *, today: date) -> BillExtraction | None:
    """Parse the spans of a bill and hold its line items to its total.

    None when there is not even an amount to book: a photo of something that is not a receipt.
    """
    items: list[BillLine] = []
    for item in bill.items:
        try:
            items.append(BillLine(description=item.description.strip()[:120], amount_cents=abs(money(item.amount_text))))
        except ValueError:
            continue
    total = None
    if bill.total_text:
        try:
            total = abs(money(bill.total_text))
        except ValueError:
            total = None
    summed = sum(item.amount_cents for item in items)
    if total is None and not summed:
        return None

    flags: list[BillFlag] = []
    if total is None:
        # Nothing printed to check against, so the items are the total and the user is told.
        flags.append("no_total")
        total = summed
    elif not items:
        flags.append("no_items")
    elif summed != total:
        flags.append("does_not_add_up")
    try:
        booked_on = parse_statement_date(bill.date_text, year=today.year)
    except (RowUnreadable, ValueError):
        booked_on = today
        flags.append("no_date")
    extraction = BillExtraction(
        merchant=bill.merchant.strip()[:120] or "Receipt",
        booked_on=booked_on,
        total_cents=total,
        items=items,
        total_printed="no_total" not in flags,
        flags=flags,
    )
    extraction.line = _line_of(extraction)
    return extraction


async def read_bill_image(
    data: bytes,
    *,
    today: date,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> BillExtraction | None:
    """The vision path for a receipt: the photo to the fast slot, then the total guard."""
    image = pdf.as_image(data)
    bill = await read_bill(resolve_model("fast"), image, today=today, model_settings=model_settings)
    return check_bill(bill, today=today)


def find_match(
    session: Session, profile_id: str, *, total_cents: int, booked_on: date, days: int = MATCH_DAYS
) -> Transaction | None:
    """The booking this receipt is, if the profile already has it.

    Money out, the same amount to the cent, within three days, and neither a leg of a split nor
    a booking that is already split: splitting one of those again is not a thing.
    """
    window = timedelta(days=days)
    candidates = session.scalars(
        select(Transaction).where(
            Transaction.profile_id == profile_id,
            Transaction.amount_cents == -abs(total_cents),
            Transaction.parent_id.is_(None),
            Transaction.booked_on >= booked_on - window,
            Transaction.booked_on <= booked_on + window,
        )
    ).all()
    children = {
        parent_id
        for (parent_id,) in session.execute(
            select(Transaction.parent_id).where(Transaction.parent_id.in_([row.id for row in candidates]))
        ).all()
    }
    open_rows = [row for row in candidates if row.id not in children]
    if not open_rows:
        return None
    return min(open_rows, key=lambda row: (abs((row.booked_on - booked_on).days), -row.created_at.timestamp()))


@dataclass(frozen=True)
class Group:
    """Line items that belong in the same category, which is what becomes one leg."""

    category: str | None
    subcategory: str | None
    descriptions: list[str]
    amount_cents: int


async def group_items(
    session: Session,
    profile_id: str,
    items: Sequence[BillLine],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> list[Group]:
    """Group the line items by what the categorizer makes of each one.

    The categorizer sub-agent is the same one the import uses, asked about article texts instead
    of merchants. A guess it is unsure about still groups: the legs of a split are shown to the
    user before anything is written, so a wrong category costs a click and not a wrong booking.
    """
    taxonomy = taxonomy_of(load_categories(session, profile_id))
    entries = [
        MerchantBatchEntry(
            key=f"i{index}",
            sample_description=item.description,
            counterparty=None,
            bookings=1,
            average_cents=-item.amount_cents,
            incoming=False,
        )
        for index, item in enumerate(items)
    ]
    try:
        guesses = await categorize_merchants(
            resolve_model("fast"), entries, taxonomy, model_settings=model_settings
        )
    except Exception as exc:  # noqa: BLE001 - a failed guess means one leg per item, not a crash
        logger.warning("the line items of a bill could not be categorized: %s", exc)
        guesses = {}

    known = {name.casefold(): (name, subs) for name, subs in taxonomy}
    groups: dict[tuple[str | None, str | None], Group] = {}
    for index, item in enumerate(items):
        guess = guesses.get(f"i{index}")
        category: str | None = None
        subcategory: str | None = None
        if guess is not None and guess.category.casefold() in known:
            category, subs = known[guess.category.casefold()]
            wanted = (guess.subcategory or "").casefold()
            subcategory = next((sub for sub in subs if sub.casefold() == wanted), None)
        key = (category, subcategory)
        existing = groups.get(key)
        if existing is None:
            groups[key] = Group(category, subcategory, [item.description], item.amount_cents)
        else:
            groups[key] = Group(
                category, subcategory, [*existing.descriptions, item.description], existing.amount_cents + item.amount_cents
            )
    return list(groups.values())


def _leg(description: str, amount_cents: int, category: str | None, subcategory: str | None) -> SplitLeg:
    return SplitLeg(
        description=description[:MAX_LEG_DESCRIPTION],
        amount_cents=-abs(amount_cents),
        category=category,
        subcategory=subcategory,
    )


async def split_intent(
    session: Session,
    profile_id: str,
    extraction: BillExtraction,
    booking: Transaction,
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> ChangesetIntent | None:
    """The split this receipt proposes for the booking it matched, or None when it has none.

    Legs are the categorizer's groups. One group means the whole receipt is one category, and
    then the line items themselves are the legs: an itemization is still worth having. A single
    line item is nothing to split, and that comes back as None.
    """
    groups = await group_items(
        session, profile_id, extraction.items, resolve_model=resolve_model, model_settings=model_settings
    )
    if len(groups) >= 2:
        legs = [
            _leg(", ".join(group.descriptions), group.amount_cents, group.category, group.subcategory)
            for group in groups
        ]
    elif len(extraction.items) >= 2:
        category = groups[0].category if groups else None
        subcategory = groups[0].subcategory if groups else None
        legs = [_leg(item.description, item.amount_cents, category, subcategory) for item in extraction.items]
    else:
        return None
    return ChangesetIntent(
        kind="split",
        title=f"Split the {extraction.merchant} booking into its {len(legs)} line items",
        transaction_ids=[booking.id],
        legs=legs,
    )


async def bill_outcome(
    session: Session,
    profile_id: str,
    conversation_id: str,
    extraction: BillExtraction,
    *,
    file_name: str,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> dict[str, Any]:
    """What a read receipt comes to: a proposed split, or a preview of a new booking.

    Nothing is written either way. The split is a changeset the user applies from its card; the
    new booking is a draft the user confirms on a preview card, which `add_transaction` then
    writes.
    """
    payload: dict[str, Any] = {
        "file": file_name,
        "bill": {
            "merchant": extraction.merchant,
            "booked_on": extraction.booked_on.isoformat(),
            "total_cents": extraction.total_cents,
            "total_printed": extraction.total_printed,
            "items": [item.model_dump() for item in extraction.items],
            "verified": extraction.verified,
            "check": extraction.line,
        },
    }
    booking = find_match(
        session, profile_id, total_cents=extraction.total_cents, booked_on=extraction.booked_on
    )
    if booking is not None:
        payload["matched"] = {
            "transaction_id": booking.id,
            "booked_on": booking.booked_on.isoformat(),
            "amount_cents": booking.amount_cents,
            "description": booking.description,
        }
        intent = (
            await split_intent(
                session,
                profile_id,
                extraction,
                booking,
                resolve_model=resolve_model,
                model_settings=model_settings,
            )
            if extraction.items and "does_not_add_up" not in extraction.flags
            else None
        )
        if intent is not None:
            changeset = propose(session, profile_id, intent, conversation_id=conversation_id)
            session.commit()
            return {
                **payload,
                "status": "bill_split",
                "changeset": to_out(changeset).model_dump(mode="json"),
                "instruction": (
                    "The split is proposed and the user sees it as a card with Apply and Discard. "
                    "Say in one line which booking it splits and into how many legs, quoting the "
                    "figures above, and never say it has been applied."
                ),
            }
        return {
            **payload,
            "status": "bill_matched",
            "message": (
                f"{extraction.merchant} for {eur(extraction.total_cents)} EUR is already in the "
                f"profile as the booking of {day(booking.booked_on)}, and this receipt gives "
                "nothing to split it into."
            ),
        }

    drafts, problems = store_drafts(
        session,
        profile_id,
        conversation_id,
        [
            ProposedTransaction(
                booked_on=extraction.booked_on,
                amount=f"{extraction.total_cents / 100:.2f}",
                direction="out",
                description=extraction.merchant,
                counterparty=extraction.merchant,
                account_name=None,
            )
        ],
    )
    if not drafts:
        return {**payload, "status": "nothing_found", "error": "The receipt held no bookable amount.", "problems": problems}
    return {
        **payload,
        "status": "bill_draft",
        "drafts": [
            {
                "ref": draft.ref,
                "booked_on": draft.booked_on.isoformat(),
                "amount_cents": draft.amount_cents,
                "description": draft.description,
                "counterparty": draft.counterparty,
                "account": draft.account_name,
            }
            for draft in drafts
        ],
        "card": preview_card(drafts).model_dump(mode="json"),
        "instruction": (
            "No booking of this profile matches the receipt, so it would be a new one. Show this "
            "`card` with `ask_user`, unchanged, and call `add_transaction` with the row's `ref` if "
            "the user confirms it."
        ),
    }
