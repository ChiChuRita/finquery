"""Transactions the user types or pastes into the chat.

"I paid 12 EUR cash for lunch today" and a few lines copied out of a statement are the same
job: the fast slot reads them through one forced tool call, each booking becomes a draft, and
the drafts are shown as a preview card the user confirms row by row. Nothing is written until
they do.

The draft table is what keeps the model out of the arithmetic. The card carries a draft's
`ref`, the answer comes back with that ref, and `add_draft` writes the booking from the stored
columns, so a confirmed amount is the amount that was extracted and shown, never one the model
retyped on the way back.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finquery.ask_user import TRANSACTION_DRAFT, AskApply, AskOption, AskRow, AskUser
from finquery.categorize import categorize_rows
from finquery.db import (
    Account,
    Category,
    DuplicateCandidate,
    Subcategory,
    Transaction,
    TransactionDraft,
    ensure_account,
    fingerprint,
)
from finquery.ingest import duplicates
from finquery.ingest.csv_reader import parse_amount
from finquery.nullish import nullish_before
from finquery.providers import ModelResolver

MAX_DRAFTS = 5
"""Bookings one preview card asks about, which is also the cap on a card's rows."""

DEFAULT_ACCOUNT = "Cash"
"""Where a typed booking lands when the user named no account: cash spending is the case this
feature exists for."""

ADD = "add"
DISCARD = "discard"

INSTRUCTIONS = """\
You turn what a person typed or pasted into bookings for their own finance app. Call
`propose_transactions` exactly once, with one entry per booking you can read and nothing else.

Rules:
- `booked_on` is a real date as YYYY-MM-DD. You are given today's date: "today" is that date,
  "yesterday" the day before it, "last Friday" the most recent Friday before it. When no date
  is mentioned at all, use today.
- `amount` is the figure the person wrote, with no sign and no currency, decimals after a dot:
  `12`, `12.50`, `1234.56`. Never round it, never convert a currency and never invent one. A
  line with no amount is not a booking.
- `direction` is `out` when the money left the person (a payment, a purchase, a fee) and `in`
  when it reached them (a salary, a refund, money paid back).
- `description` says what the money was for, in the person's own words, at most 60 characters:
  `Lunch`, `Coffee at the station`, `REWE groceries`.
- `counterparty` is the shop, company or person named, or null.
- `account_name` is the account named (`Cash`, `Sparkasse`), or null when none was named.
- Ignore everything that is not a booking: balances, totals, headings, questions, greetings.
- At most five entries. If the text holds more bookings than that, take the first five.
"""


class ProposedTransaction(BaseModel):
    """One booking read out of the user's own words."""

    booked_on: date = Field(description="The booking date as YYYY-MM-DD.")
    amount: str = Field(description="The figure as written, unsigned, decimals after a dot.")
    direction: Literal["out", "in"] = Field(description="`out` when money left the person.")
    description: str = Field(description="What the money was for, at most 60 characters.")
    counterparty: str | None = Field(default=None, description="The shop, company or person, or null.")
    account_name: str | None = Field(default=None, description="The account named, or null.")

    # The fast slot answers a null field with the word: a cash lunch stored the counterparty
    # "null" (review of 2026-09-04).
    _nulls = nullish_before("counterparty", "account_name")


class ProposedTransactions(BaseModel):
    """One entry per booking in the text, at most five."""

    transactions: list[ProposedTransaction]


extraction_agent = Agent(
    instructions=INSTRUCTIONS,
    output_type=ToolOutput(ProposedTransactions, name="propose_transactions"),
    name="finquery-typed-transactions",
)


def extraction_prompt(text: str, today: date, accounts: list[str]) -> str:
    """The whole prompt the sub-agent sees. Pure, so a training row is this text plus the answer."""
    known = ", ".join(accounts) if accounts else "none yet"
    return (
        f"Today is {today.isoformat()}.\n"
        f"Accounts this household already has: {known}.\n\n"
        f"What the person wrote:\n{text.strip()}"
    )


def to_cents(amount: str, direction: str) -> int:
    """The signed cents of a written amount. Raises `ValueError` when there is no figure in it.

    The decimal separator is read off the string rather than assumed, because a model asked for
    `12.50` sometimes answers `12,50`, and reading that as 1250 EUR would be a silent disaster.
    """
    text = amount.strip()
    separator = "comma" if text.rfind(",") > text.rfind(".") else "dot"
    cents = abs(parse_amount(text, separator))
    return -cents if direction == "out" else cents


async def propose_transactions(
    text: str,
    *,
    today: date,
    accounts: list[str],
    model: Model,
    model_settings: ModelSettings | None = None,
) -> list[ProposedTransaction]:
    result = await extraction_agent.run(
        extraction_prompt(text, today, accounts), model=model, model_settings=model_settings
    )
    return result.output.transactions[:MAX_DRAFTS]


def store_drafts(
    session: Session,
    profile_id: str,
    conversation_id: str,
    proposals: list[ProposedTransaction],
) -> tuple[list[TransactionDraft], list[str]]:
    """Store what was extracted, and say which entries could not be read.

    The refs count up per conversation (`t1`, `t2`, ...), because that is the handle the card
    shows, the answer returns and the assistant passes to `add_transaction`.
    """
    taken = session.scalar(
        select(func.count(TransactionDraft.id)).where(TransactionDraft.conversation_id == conversation_id)
    )
    drafts: list[TransactionDraft] = []
    problems: list[str] = []
    for index, proposal in enumerate(proposals, start=int(taken or 0) + 1):
        try:
            amount_cents = to_cents(proposal.amount, proposal.direction)
        except ValueError:
            problems.append(f"{proposal.description}: {proposal.amount!r} is not an amount.")
            continue
        if amount_cents == 0:
            problems.append(f"{proposal.description}: the amount is zero.")
            continue
        draft = TransactionDraft(
            profile_id=profile_id,
            conversation_id=conversation_id,
            ref=f"t{index}",
            booked_on=proposal.booked_on,
            amount_cents=amount_cents,
            description=proposal.description.strip() or "Manual booking",
            counterparty=(proposal.counterparty or "").strip() or None,
            account_name=(proposal.account_name or "").strip() or DEFAULT_ACCOUNT,
        )
        session.add(draft)
        drafts.append(draft)
    session.commit()
    return drafts, problems


def preview_card(drafts: list[TransactionDraft]) -> AskUser:
    """The preview card: one row per booking, Confirm or Discard on each."""
    return AskUser(
        title="Add this transaction?" if len(drafts) == 1 else f"Add these {len(drafts)} transactions?",
        note="Nothing is written until you confirm. Discard leaves your data untouched.",
        rows=[
            AskRow(
                ref=draft.ref,
                label=draft.description,
                # The counterparty is dropped when it says nothing the account does not: a cash
                # lunch would otherwise read "Cash - Cash".
                description=" · ".join(
                    dict.fromkeys(part for part in (draft.counterparty, draft.account_name) if part)
                ),
                amount_cents=draft.amount_cents,
                date=draft.booked_on.isoformat(),
                options=[AskOption(label="Confirm", value=ADD), AskOption(label="Discard", value=DISCARD)],
            )
            for draft in drafts
        ],
        allow_free_text=False,
        # Nothing for the server to apply: a confirmed row is written by `add_transaction`. The
        # kind is here so Confirm and Discard are not read as category names.
        apply=AskApply(kind=TRANSACTION_DRAFT),
    )


def find_draft(session: Session, conversation_id: str, ref: str) -> TransactionDraft | None:
    wanted = ref.strip().strip("`\"'").casefold()
    return session.scalars(
        select(TransactionDraft).where(
            TransactionDraft.conversation_id == conversation_id,
            func.lower(TransactionDraft.ref) == wanted,
        )
    ).one_or_none()


def _held_aside(
    session: Session, candidate: DuplicateCandidate, draft: TransactionDraft, *, asked: bool
) -> dict[str, Any]:
    """What `add_transaction` answers for a booking that may already be there.

    Nothing was written. A candidate the user has already decided about says so instead of
    asking again, which is what makes a repeated call harmless.
    """
    if candidate.decision is not None:
        kept = candidate.decision == duplicates.KEEP
        return {
            "status": "already_decided",
            "ref": draft.ref,
            "description": draft.description,
            "message": (
                f"{draft.description} was already decided: you "
                + ("kept it, so it is in the data." if kept else "removed it, so nothing was added.")
            ),
        }
    account = session.get(Account, candidate.account_id)
    return {
        "status": "duplicate_candidate",
        "ref": draft.ref,
        "candidate_ref": candidate.ref,
        "description": draft.description,
        "amount_cents": draft.amount_cents,
        "message": (
            f"{draft.description} looks like a booking this profile already has"
            + (f" in {account.name}" if account else "")
            + ", so nothing was written."
        ),
        "card": duplicates.one_card(candidate, account_name=account.name if account else None).model_dump(
            mode="json"
        ),
        "instruction": (
            "Show this `card` with `ask_user`, unchanged."
            if not asked
            else "This booking is already on a card the user has not answered yet."
        ),
    }


def _placement(session: Session, row: Transaction) -> tuple[str | None, str | None]:
    category = session.get(Category, row.category_id) if row.category_id else None
    subcategory = session.get(Subcategory, row.subcategory_id) if row.subcategory_id else None
    return (category.name if category else None, subcategory.name if subcategory else None)


async def add_draft(
    session: Session,
    profile_id: str,
    draft: TransactionDraft,
    *,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
) -> dict[str, Any]:
    """Write one confirmed draft as a manual transaction and categorize it.

    Confirming the same draft twice adds nothing: the draft remembers the booking it became.

    A booking the profile may already have is not written either. It is held aside as a
    duplicate candidate and comes back as a card of its own, so a payment typed twice by
    mistake and a genuinely repeated one are told apart by the user rather than by us. See
    `finquery.ingest.duplicates`.
    """
    if draft.transaction_id is not None:
        return {
            "status": "already_added",
            "ref": draft.ref,
            "description": draft.description,
            "message": f"{draft.description} was already added, so nothing was written again.",
        }
    held = duplicates.for_draft(session, draft.id)
    if held is not None:
        return _held_aside(session, held, draft, asked=True)
    account = ensure_account(session, profile_id, draft.account_name or DEFAULT_ACCOUNT)
    match = duplicates.Matcher(session, profile_id, account.id).take(
        draft.booked_on, draft.amount_cents, draft.description
    )
    if match is not None:
        candidate = duplicates.hold(
            session,
            profile_id,
            account_id=account.id,
            booked_on=draft.booked_on,
            amount_cents=draft.amount_cents,
            description=draft.description,
            counterparty=draft.counterparty,
            match=match,
            source="manual",
            draft_id=draft.id,
        )
        session.commit()
        return _held_aside(session, candidate, draft, asked=False)
    row = Transaction(
        profile_id=profile_id,
        account_id=account.id,
        booked_on=draft.booked_on,
        amount_cents=draft.amount_cents,
        description=draft.description,
        counterparty=draft.counterparty,
        source="manual",
        fingerprint=fingerprint(account.id, draft.booked_on, draft.amount_cents, draft.description),
    )
    session.add(row)
    session.commit()
    draft.transaction_id = row.id
    session.commit()

    report = await categorize_rows(
        session, profile_id, [row], resolve_model=resolve_model, model_settings=model_settings
    )
    category, subcategory = _placement(session, row)
    return {
        "status": "added",
        "ref": draft.ref,
        "transaction_id": row.id,
        "booked_on": row.booked_on.isoformat(),
        "amount_cents": row.amount_cents,
        "description": row.description,
        "account": account.name,
        "title": row.enriched_title,
        "category": category,
        "subcategory": subcategory,
        "needs_review": category is None,
        "error": report.error,
    }
