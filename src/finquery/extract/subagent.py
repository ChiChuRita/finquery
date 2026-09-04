"""The extraction sub-agent: a statement page or a bill in, rows out, on the fast slot.

Two jobs, one contract. Both run through a forced single tool, so the answer is a schema and
never prose (ADR 0002, and locally that is also what turns thinking off and builds a grammar).

- `read_statement` reads the bookings off one page. The page arrives as numbered printed lines
  for the text-layer path, or as an image for a page that has no text layer, and the row shape
  is the same either way.
- `read_bill` reads a receipt: the merchant, the date, the total and the line items.

The one rule that shapes the schema: **the model returns the spans it read, not figures it
worked out.** `date_text`, `amount_text` and `balance_text` are copied out of the page, the
cents are parsed from them in `finquery.extract.guards`, and a span that is not printed on the
page is what the verbatim guard rejects. So the model can point at a number and can never
invent one (ADR 0004, ADR 0011).

The prompts are pure functions of what the model sees, so a training row is that text plus the
answer it gave.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

MAX_ROWS_PER_PAGE = 60
"""Bookings one page can hold. The shipped statement prints 30 to a page."""

MAX_ITEMS = 40
"""Line items one bill can hold."""

STATEMENT_INSTRUCTIONS = """\
You read the bookings out of one page of a bank statement for the account holder's own finance
app. Call `read_statement` exactly once, with one entry per booking on the page and nothing
else. You never explain and never answer in words.

The rules that matter more than anything else:
- `date_text`, `amount_text` and `balance_text` are copied out of the page character by
  character, exactly as printed: `-1.150,00`, `79,90 €`, `04.01.25`, `15 Mai 2024`. Never
  reformat them, never add or remove a digit, a dot or a comma, never convert a currency and
  never work anything out. Every figure you return is checked against the page and a figure
  that is not printed there is thrown away.
- If a booking has no balance printed next to it, `balance_text` is null. Do not carry the
  balance of another row over.
- `direction` is `out` when the money left the account and `in` when it arrived.
- `description` is the booking text as printed, at most 120 characters, and includes the
  reference line under the booking when there is one.
- `counterparty` is the shop, company or person the money went to or came from, or null.
- `line` is the number of the printed line the amount stands on, from the numbers in front of
  each line.

What is not a booking: the page header and footer, the column headings, the IBAN and BIC line,
the account holder, the period, a page number, and every balance or summary line (`Alter
Kontostand`, `Neuer Kontostand`, `Summe der Buchungen`, `KONTOÜBERSICHT`, `ANFANGSSALDO`,
`ENDSALDO`, `SALDO`). Skip all of it.

If the page is not a bank statement at all (a receipt, a letter, an invoice), return no rows
and say what it is in `note`.
"""

BILL_INSTRUCTIONS = """\
You read a photo of a receipt or bill for the account holder's own finance app. Call
`read_bill` exactly once and nothing else.

- `merchant` is the shop's name as printed at the top.
- `date_text` is the date exactly as printed on the receipt (`14.03.2025`).
- `total_text` is the figure printed next to the total (`SUMME`, `Summe`, `Total`, `Gesamt`,
  `zu zahlen`), exactly as printed, or null when no total is printed.
- `items` is one entry per line item, in the order they are printed, each with the article text
  and `amount_text` exactly as printed. Leave out discounts you cannot read, deposit returns
  you are unsure about, the VAT line, the payment line and the total itself.
- Copy every figure character by character. Never add up anything, never round and never invent
  a figure you cannot see: the line items are added up and checked against the total, and a
  bill that does not add up is shown to the user instead of being trusted.
"""


class StatementRow(BaseModel):
    """One booking as the sub-agent read it: the spans, not the cents."""

    line: int | None = Field(default=None, description="The numbered printed line the amount stands on.")
    date_text: str = Field(description="The booking date exactly as printed.")
    amount_text: str = Field(description="The amount exactly as printed, with its sign if it has one.")
    direction: Literal["out", "in"] = Field(description="`out` when the money left the account.")
    description: str = Field(description="The booking text as printed, at most 120 characters.")
    counterparty: str | None = Field(default=None, description="The shop, company or person, or null.")
    balance_text: str | None = Field(default=None, description="The running balance printed on this row, or null.")


class StatementPage(BaseModel):
    """Every booking on one page, in the order they are printed."""

    rows: list[StatementRow] = Field(default_factory=list)
    note: str | None = Field(default=None, description="Only when the page holds no bookings: what it is instead.")


class BillItem(BaseModel):
    """One line of a receipt."""

    description: str = Field(description="The article text as printed.")
    amount_text: str = Field(description="The price exactly as printed.")


class Bill(BaseModel):
    """One receipt as the sub-agent read it."""

    merchant: str = Field(description="The shop's name as printed at the top.")
    date_text: str = Field(description="The date exactly as printed.")
    total_text: str | None = Field(default=None, description="The total exactly as printed, or null.")
    items: list[BillItem] = Field(default_factory=list)


statement_agent = Agent(
    instructions=STATEMENT_INSTRUCTIONS,
    output_type=ToolOutput(StatementPage, name="read_statement"),
    name="finquery-extraction-statement",
)

bill_agent = Agent(
    instructions=BILL_INSTRUCTIONS,
    output_type=ToolOutput(Bill, name="read_bill"),
    name="finquery-extraction-bill",
)


def statement_prompt(*, page: int, pages: int, layout_hint: str, year: int | None, lines: str) -> str:
    """The whole prompt the text-layer path sees. Pure, so a training row is this plus the answer."""
    period = f"The statement is from {year}. " if year else ""
    return (
        f"{layout_hint}\n\n"
        f"{period}This is page {page} of {pages}. Every printed line of it, numbered:\n\n"
        f"{lines}\n\n"
        f"Return every booking on this page, at most {MAX_ROWS_PER_PAGE}."
    )


def image_prompt(*, page: int, pages: int, layout_hint: str, year: int | None) -> str:
    """The prompt for a page that has to be looked at: same job, no text to quote from."""
    period = f"The statement is from {year}. " if year else ""
    return (
        f"{layout_hint}\n\n"
        f"{period}This is page {page} of {pages}, as an image, because it has no text layer. "
        "Read the figures off the image exactly as they are printed and leave `line` null.\n\n"
        f"Return every booking you can see, at most {MAX_ROWS_PER_PAGE}."
    )


def bill_prompt(today: date) -> str:
    return (
        f"Today is {today.isoformat()}. Read this receipt: the merchant, the date, the total and "
        f"every line item, at most {MAX_ITEMS}."
    )


async def read_statement_text(
    model: Model,
    *,
    page: int,
    pages: int,
    layout_hint: str,
    year: int | None,
    lines: str,
    model_settings: ModelSettings | None = None,
) -> StatementPage:
    """One page of a text PDF through the fast slot."""
    result = await statement_agent.run(
        statement_prompt(page=page, pages=pages, layout_hint=layout_hint, year=year, lines=lines),
        model=model,
        model_settings=model_settings,
    )
    return _capped(result.output)


async def read_statement_image(
    model: Model,
    image: bytes,
    *,
    page: int,
    pages: int,
    layout_hint: str,
    year: int | None,
    media_type: str = "image/png",
    model_settings: ModelSettings | None = None,
) -> StatementPage:
    """One rendered page or photo of a statement through the fast slot's vision path.

    The image travels as `BinaryContent`, which is what both providers take: OpenRouter turns it
    into an image content part and the local Gemma handler into a data URL (`local/model.py`).
    """
    result = await statement_agent.run(
        [
            image_prompt(page=page, pages=pages, layout_hint=layout_hint, year=year),
            BinaryContent(data=image, media_type=media_type),
        ],
        model=model,
        model_settings=model_settings,
    )
    return _capped(result.output)


async def read_bill(
    model: Model,
    image: bytes,
    *,
    today: date,
    media_type: str = "image/png",
    model_settings: ModelSettings | None = None,
) -> Bill:
    """One photo of a receipt through the fast slot's vision path."""
    result = await bill_agent.run(
        [bill_prompt(today), BinaryContent(data=image, media_type=media_type)],
        model=model,
        model_settings=model_settings,
    )
    bill = result.output
    bill.items = bill.items[:MAX_ITEMS]
    return bill


def _capped(page: StatementPage) -> StatementPage:
    page.rows = page.rows[:MAX_ROWS_PER_PAGE]
    return page
