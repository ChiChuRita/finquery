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
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai.settings import ModelSettings
from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.categorize.merchants import fold, lookup, merchant_of
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

if TYPE_CHECKING:
    # Only a type here: the web lookup imports the categorizer's merchant helpers, and this
    # module is on the same side of that, so importing it back at runtime would close a circle.
    from finquery.weblookup import Lookup, Lookups

logger = logging.getLogger(__name__)

MATCH_DAYS = 3
"""How far from the receipt's date a booking may sit and still be the same payment."""

MAX_LEG_DESCRIPTION = 120

BillFlag = Literal["no_total", "does_not_add_up", "no_date", "no_items", "several_receipts", "foreign_currency"]

FLAG_REASONS: dict[BillFlag, str] = {
    "no_total": "No total is printed on this receipt, so the line items could not be checked.",
    "does_not_add_up": "The line items do not add up to the printed total.",
    "no_date": "The date on the receipt could not be read.",
    "no_items": "No line item could be read from this receipt.",
    "several_receipts": "This photo shows more than one receipt, so only the first one was read.",
    "foreign_currency": "This receipt is not in euros, so nothing was booked from it.",
}

# The currency a booking is written in. Another one is refused rather than booked at par: a
# receipt from Poland read as 8,27 EUR is the one kind of mistake nothing later would catch
# (twenty public receipts, 2026-09-05). Only a currency that can be named is refused, because
# the same run also had a reader answer this field with a stray comma, and a German receipt
# refused over a misread glyph would be the worse trade.
EURO_NAMES = {"", "eur", "euro", "eur.", "€", "e"}
FOREIGN_SIGNS = {"$", "us$", "£", "¥", "zł", "zl", "kč", "kc", "ft", "kr", "sfr", "fr."}
_CURRENCY_CODE = re.compile(r"^[a-z]{3}$")

# What a German till prints into the item list that is not an article. The model is told the
# same list; this is the second line, because a subtotal counted as an article doubles the
# basket and the receipt then "does not add up" for a reason the user cannot see.
SUBTOTAL_WORDS = (
    "zwi.summe",
    "zwi summe",
    "zwischensumme",
    "zw.summe",
    "zwsumme",
    "subtotal",
    "sub total",
    "zw. summe",
    "summe",
    "posten",
    "gesamtsumme",
    "total",
)


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
    """Unsigned. `direction` says which way the money went."""
    direction: Literal["out", "in"] = "out"
    """`in` for a receipt that pays money back: a Leergutbon, a Retoure, a refund."""
    currency: str = "EUR"
    """The currency as printed. Anything but euros is refused rather than booked at par."""
    items: list[BillLine] = Field(default_factory=list)
    total_printed: bool = True
    date_read: bool = True
    """False when the receipt's own date could not be read, so `booked_on` is only today."""
    note: str | None = None
    """What the reader wants to say about the photo itself, when there is anything."""
    flags: list[BillFlag] = Field(default_factory=list)
    line: str = ""
    """The one sentence about the arithmetic, counted here and quoted by the tool."""

    @property
    def verified(self) -> bool:
        return not self.flags


def _reason(extraction: BillExtraction, flag: BillFlag) -> str:
    if flag == "foreign_currency":
        return f"This receipt is in {extraction.currency}, not euros, so nothing was booked from it."
    return FLAG_REASONS[flag]


def _line_of(extraction: BillExtraction) -> str:
    """The one sentence under the items: what the arithmetic says, then what the photo does."""
    if extraction.verified:
        back = " back" if extraction.direction == "in" else ""
        said = [
            f"{len(extraction.items)} line items add up to the printed total of "
            f"{eur(extraction.total_cents)} EUR{back}."
        ]
    else:
        said = [_reason(extraction, flag) for flag in extraction.flags]
    if extraction.note:
        said.append(extraction.note.strip())
    return " ".join(said)


def bill_date(date_text: str, *, today: date) -> date | None:
    """The day this receipt was printed, or None when the span is not a printed date.

    The same discipline as every other figure (ADR 0011): the model points at the span and the
    day is parsed from it here. Two spans are not a date however well they parse: an empty one,
    and one naming a day that has not happened yet, which is what a model writing a plausible
    date rather than reading one produces. Neither becomes a booking date; both become a
    question.
    """
    try:
        read = parse_statement_date(date_text, year=today.year)
    except (RowUnreadable, ValueError):
        return None
    return None if read > today else read


def is_euro(currency_text: str) -> bool:
    """Whether the receipt is in the currency this app books in.

    True unless the span names another currency: a three letter code that is not EUR, or a sign
    that belongs to one. A span that names no currency at all is euros, because these receipts
    are German and a glyph the reader could not make out is not evidence of anything.
    """
    token = currency_text.strip().casefold()
    if token in EURO_NAMES or token.strip(".") in EURO_NAMES:
        return True
    if token in FOREIGN_SIGNS:
        return False
    return not _CURRENCY_CODE.match(token)


def _reads_as_subtotal(description: str) -> bool:
    text = description.casefold()
    return any(word in text for word in SUBTOTAL_WORDS)


def _without_subtotals(items: list[BillLine]) -> list[BillLine]:
    """The articles, with the running subtotals a till prints between them left out.

    `ZWI.SUMME 25,74` under the last article of an ALDI receipt is the whole basket again, and
    counted as an article it doubles it (twenty public receipts, 2026-09-05). Two signals have
    to agree before a line is dropped: it reads like a subtotal, and its amount is exactly the
    sum of the articles before it. A real article whose price happens to equal what came before
    is therefore kept, and a subtotal that does not add up is kept and shows up as a receipt
    that does not add up, which is a question rather than a silent halving.
    """
    kept: list[BillLine] = []
    running = 0
    for item in items:
        if running and item.amount_cents == running and _reads_as_subtotal(item.description):
            continue
        kept.append(item)
        running += item.amount_cents
    return kept


def check_bill(bill: Bill, *, today: date) -> BillExtraction | None:
    """Parse the spans of a bill and hold its line items to its total.

    None when there is not even an amount to book: a photo of something that is not a receipt.
    """
    items: list[BillLine] = []
    for item in bill.items:
        try:
            # Signed, so a discount, a coupon or a deposit return subtracts the way it does on
            # the paper. Only the printed sign is used; nothing here decides what a line means.
            items.append(BillLine(description=item.description.strip()[:120], amount_cents=money(item.amount_text)))
        except ValueError:
            continue
    items = _without_subtotals(items)
    total = None
    if bill.total_text:
        try:
            total = abs(money(bill.total_text))
        except ValueError:
            total = None
    tax = None
    if bill.tax_text:
        try:
            tax = abs(money(bill.tax_text))
        except ValueError:
            tax = None
    summed = sum(item.amount_cents for item in items)
    if total is None and not summed:
        return None

    flags: list[BillFlag] = []
    if not is_euro(bill.currency_text):
        flags.append("foreign_currency")
    if bill.several_receipts:
        flags.append("several_receipts")
    if total is None:
        # Nothing printed to check against, so the items are the total and the user is told.
        flags.append("no_total")
        total = abs(summed)
    elif not items:
        flags.append("no_items")
    elif summed != total and summed + (tax or 0) != total:
        # A receipt whose prices are printed without tax adds it once at the foot, so the
        # articles plus that figure are the total. Every US receipt reads this way.
        flags.append("does_not_add_up")
    read = bill_date(bill.date_text, today=today)
    if read is None:
        flags.append("no_date")
    extraction = BillExtraction(
        merchant=bill.merchant.strip()[:120] or "Receipt",
        booked_on=read or today,
        date_read=read is not None,
        total_cents=abs(total),
        direction=bill.direction,
        currency=bill.currency_text.strip() or "EUR",
        items=items,
        total_printed="no_total" not in flags,
        note=(bill.note or "").strip() or None,
        flags=flags,
    )
    extraction.line = _line_of(extraction)
    return extraction


# The flags a second look at the same photo can do something about, and nothing else. A receipt
# with no total printed has none to find, a photo of three receipts is three whatever is asked,
# and a date that is not printed must stay unread: the card asks the user for it, and a second
# reading has nothing to check an invented date against (twenty public receipts, 2026-09-05).
REREADABLE: tuple[BillFlag, ...] = ("does_not_add_up", "no_items", "foreign_currency")


def _rereadable(extraction: BillExtraction) -> list[str]:
    """What to hand back about this reading, in the words the second one gets."""
    found: list[str] = []
    summed = sum(item.amount_cents for item in extraction.items)
    for flag in extraction.flags:
        if flag not in REREADABLE:
            continue
        if flag == "does_not_add_up":
            found.append(
                f"Your {len(extraction.items)} items add up to {eur(summed)} EUR and the total "
                f"you read is {eur(extraction.total_cents)} EUR, a difference of "
                f"{eur(abs(extraction.total_cents - summed))} EUR. One article is missing, one "
                f"is counted twice, a subtotal or a quantity line was taken for an article, or a "
                f"discount printed as a negative amount was left out."
            )
        elif flag == "no_items":
            found.append("Not one line item came back. A receipt with a total has articles above it.")
        else:
            found.append(
                f"You answered `{extraction.currency}` as the currency, so this receipt is "
                f"refused as foreign money and nothing is booked from it. Copy the currency "
                f"printed next to the total, and leave it empty when none is printed there."
            )
    return found


async def read_bill_image(
    data: bytes,
    *,
    today: date,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> BillExtraction | None:
    """The vision path for a receipt: the photo to the fast slot, then the total guard.

    A reading whose arithmetic did not come out is looked at once more with what did not come
    out written into the prompt, and the better of the two readings is the one that is kept.
    Eleven of the twenty public receipts were flagged on 2026-09-05, eight of them for a line
    the reader could have read again: a subtotal counted as an article, a quantity line taken
    for a price, a discount left out (ticket 42).
    """
    image = pdf.as_image(data)
    model = resolve_model("fast")
    bill = await read_bill(model, image, today=today, model_settings=model_settings)
    extraction = check_bill(bill, today=today)
    if extraction is None or not (findings := _rereadable(extraction)):
        return extraction
    logger.info("reading a receipt again: %s", "; ".join(findings))
    second = await read_bill(
        model, image, today=today, previous=bill, findings=findings, model_settings=model_settings
    )
    checked = check_bill(second, today=today)
    # Strictly better only: a second reading that trades one flag for another is not a repair,
    # and the first one is the one the guards have already been over.
    if checked is not None and len(checked.flags) < len(extraction.flags):
        return checked
    return extraction


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
class Store:
    """The shop a receipt was printed by, once it has been recognized.

    `via` says who recognized it: the seed dictionary, which costs nothing, or the web lookup,
    which costs a merchant token and only runs for a profile that switched it on. `lookup` is
    the whole web result when there was one, so the payload can show its evidence.
    """

    title: str
    category: str | None
    subcategory: str | None
    blurb: str
    via: str
    lookup: "Lookup | None" = None

    @property
    def line(self) -> str:
        """The one line of context the legs of a split are given. Never a figure, never an item."""
        place = f", filed under {self.category}" if self.category else ""
        return f"the receipt is from {self.title}, {self.blurb}{place}".strip()


@dataclass(frozen=True)
class Group:
    """Line items that belong in the same category, which is what becomes one leg."""

    category: str | None
    subcategory: str | None
    descriptions: list[str]
    amount_cents: int


def known_store(header: str) -> Store | None:
    """The shop behind a receipt header, from the seed dictionary alone. No request, no model.

    Both tries the import pipeline makes: the merchant key, and the key with the header behind
    it, because "Ecenter EDEKA" folds to a key the first try does not place.
    """
    merchant = merchant_of(header, None)
    entry = lookup(merchant.key) or lookup(f"{merchant.key} {fold(header)}")
    if entry is None:
        return None
    return Store(
        title=merchant.title if entry.generic else entry.title,
        category=entry.category,
        subcategory=entry.subcategory,
        blurb=entry.blurb,
        via="dictionary",
    )


async def resolve_store(header: str, session: Session, profile_id: str, lookups: "Lookups | None") -> Store | None:
    """Which shop this printed header is: the dictionary first, then the web.

    The web half only happens for a profile that switched web lookup on, and only ever with the
    header: a store's name is not personal, a basket is, so the line items never come near it.
    A header that reads as an address or a person is refused by the scrubber the way a booking
    is, and then this is simply None and the draft keeps the header as it was printed.
    """
    known = known_store(header)
    if known is not None or lookups is None:
        return known
    taxonomy = taxonomy_of(load_categories(session, profile_id))
    found = await lookups.store(header, taxonomy)
    if not found.token or not found.summary or not found.category:
        return None
    return Store(
        title=header.strip()[:60],
        category=found.category,
        subcategory=found.subcategory,
        blurb=found.summary,
        via="web",
        lookup=found,
    )


async def group_items(
    session: Session,
    profile_id: str,
    items: Sequence[BillLine],
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    store: Store | None = None,
) -> list[Group]:
    """Group the line items by what the categorizer makes of each one.

    The categorizer sub-agent is the same one the import uses, asked about article texts instead
    of merchants. A guess it is unsure about still groups: the legs of a split are shown to the
    user before anything is written, so a wrong category costs a click and not a wrong booking.

    `store` is one line about the shop the receipt was printed by, which is what tells `Bio 1L`
    on a supermarket receipt from `Bio 1L` on a petrol station's. Only the shop: not one item
    of the basket ever leaves this machine.
    """
    taxonomy = taxonomy_of(load_categories(session, profile_id))
    context = store.line if store is not None else None
    entries = [
        MerchantBatchEntry(
            key=f"i{index}",
            sample_description=item.description,
            counterparty=None,
            bookings=1,
            average_cents=-abs(item.amount_cents),
            incoming=False,
            web=context,
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
    # The receipt prints what was paid and a booking is money out, so the sign turns over. A
    # discount line is printed negative and therefore becomes a positive leg, which is what
    # makes the legs add up to the parent.
    return SplitLeg(
        description=description[:MAX_LEG_DESCRIPTION],
        amount_cents=-amount_cents,
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
    store: Store | None = None,
) -> ChangesetIntent | None:
    """The split this receipt proposes for the booking it matched, or None when it has none.

    Legs are the categorizer's groups. One group means the whole receipt is one category, and
    then the line items themselves are the legs: an itemization is still worth having. A single
    line item is nothing to split, and that comes back as None.
    """
    groups = await group_items(
        session,
        profile_id,
        extraction.items,
        resolve_model=resolve_model,
        model_settings=model_settings,
        store=store,
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
    lookups: "Lookups | None" = None,
) -> dict[str, Any]:
    """What a read receipt comes to: a proposed split, or a preview of a new booking.

    Nothing is written either way. The split is a changeset the user applies from its card; the
    new booking is a draft the user confirms on a preview card, which `add_transaction` then
    writes.

    The printed header is resolved to a shop first (`resolve_store`): the seed dictionary, then
    the web when the profile switched web lookup on. What that buys is a draft that reads
    "Combi, supermarket, Groceries" instead of "Combi. Frisch. Nebenan." with no category, and
    one line of shop context for the legs of a split. The header only: never an item, never the
    total, never the date.
    """
    store = await resolve_store(extraction.merchant, session, profile_id, lookups)
    payload: dict[str, Any] = {
        "file": file_name,
        "bill": {
            "merchant": extraction.merchant,
            "booked_on": extraction.booked_on.isoformat(),
            "total_cents": extraction.total_cents,
            "total_printed": extraction.total_printed,
            "date_read": extraction.date_read,
            "direction": extraction.direction,
            "currency": extraction.currency,
            "items": [item.model_dump() for item in extraction.items],
            "verified": extraction.verified,
            "check": extraction.line,
        },
    }
    if store is not None:
        payload["store"] = {
            "title": store.title,
            "category": store.category,
            "subcategory": store.subcategory,
            "summary": store.blurb,
            "via": store.via,
            "evidence": store.lookup.evidence if store.lookup else "",
            "sources": [source.payload() for source in store.lookup.sources] if store.lookup else [],
        }
    if "foreign_currency" in extraction.flags:
        # Booking 8,27 PLN as 8,27 EUR is the one mistake on this path that nothing later would
        # catch, so a receipt in another currency is refused with a sentence and never drafted.
        return {
            **payload,
            "status": "nothing_found",
            "error": (
                f"{_reason(extraction, 'foreign_currency')} FinQuery books euros only, so add "
                f"the booking yourself with the amount your account was charged."
            ),
        }
    # A Leergutbon pays money back, so it matches nothing that was paid: it is a new booking in
    # the other direction.
    booking = (
        find_match(session, profile_id, total_cents=extraction.total_cents, booked_on=extraction.booked_on)
        if extraction.direction == "out"
        else None
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
                store=store,
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

    # The draft's title is the shop's name when one was recognized, because "Combi. Frisch.
    # Nebenan." is the slogan the till prints and not what the household calls the shop. The
    # amount, the date and the direction are the receipt's own, as ever.
    titled = store.title if store is not None else extraction.merchant
    drafts, problems = store_drafts(
        session,
        profile_id,
        conversation_id,
        [
            ProposedTransaction(
                booked_on=extraction.booked_on,
                amount=f"{extraction.total_cents / 100:.2f}",
                direction=extraction.direction,
                description=titled,
                counterparty=extraction.merchant,
                account_name=None,
            )
        ],
    )
    if not drafts:
        return {**payload, "status": "nothing_found", "error": "The receipt held no bookable amount.", "problems": problems}
    instruction = (
        "No booking of this profile matches the receipt, so it would be a new one. Show this "
        "`card` with `ask_user`, unchanged, and call `add_transaction` with the row's `ref` if "
        "the user confirms it."
    )
    if store is not None:
        where = "the merchant dictionary" if store.via == "dictionary" else "a web lookup of the printed header"
        instruction += (
            f" The shop was recognized through {where}: {store.title}, {store.blurb}"
            f"{f', which belongs under {store.category}' if store.category else ''}. Say that in "
            f"one line, and name that category when the user asks where it goes. Only the shop's "
            f"name was looked up, never the line items."
        )
    if not extraction.date_read:
        instruction += (
            " The date could not be read off this receipt, so the row carries today's date and "
            "the card asks for the printed one. If the user types a date, pass it to "
            "`add_transaction` as `booked_on`, copied exactly as they wrote it."
        )
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
        "card": preview_card(drafts, ask_date=not extraction.date_read).model_dump(mode="json"),
        "instruction": instruction,
    }
