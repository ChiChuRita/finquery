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

from finquery.nullish import nullish_before

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

Fill `reasoning` first, in three to five very short lines: which layout this page is printed
in, which printed line the first booking starts on, where the date, the amount and the running
balance stand on such a line, and which lines of this page are headers or balances rather than
bookings.

A worked page, printed with its line numbers the way you get it:

  12 | 04.01.25  EDEKA SAGT DANKE                              -42,30      4.168,25
  13 |           KARTENZAHLUNG 04.01. 18:42
  14 | 06.01.25  MIETE WOHNUNG 12 01/2025                   -1.150,00      3.018,25
  15 | Alter Kontostand                                                    4.210,55

reasoning:
a Sparkasse page: date, text, amount, running balance, one booking per printed line
the first booking is on line 12, and line 13 is its reference line
the amount stands before the balance, both with a comma, the balance never negative here
line 15 is a balance line, so it is not a booking

rows:
  line 12, date_text "04.01.25", amount_text "-42,30", direction out, balance_text "4.168,25",
  description "EDEKA SAGT DANKE KARTENZAHLUNG 04.01. 18:42", counterparty "EDEKA"
  line 14, date_text "06.01.25", amount_text "-1.150,00", direction out,
  balance_text "3.018,25", description "MIETE WOHNUNG 12 01/2025", counterparty null
"""

BILL_INSTRUCTIONS = """\
You read a photo of a receipt or bill for the account holder's own finance app. Call
`read_bill` exactly once and nothing else.

- `merchant` is the shop's name as printed at the top.
- `date_text` is the date printed on the receipt, copied character by character. A German till
  prints it short, `04.09.26` or `04.09.2026`, usually with the time right after it
  (`04.09.26 20:00`), under a `Datum` or `Datum Uhrzeit` label, at the foot of the receipt
  near the barcode, the till number or the card payment block. Copy the date and the time that
  stands with it, and nothing else of that line.
  Look for it before you answer: almost every receipt carries one, and it is the date the
  booking gets. Never write today's date, never work a date out from anything and never invent
  a year. Only if the photo really shows no date at all, return an empty `date_text`: the app
  then asks the person for it rather than booking the wrong day.
- `total_text` is the figure printed next to the total (`SUMME`, `Summe`, `Total`, `Gesamt`,
  `zu zahlen`), exactly as printed, or null when no total is printed.
- `currency_text` is the currency as printed next to the total (`EUR`, `€`, `PLN`, `$`, `CHF`),
  or an empty string when none is printed.
- `tax_text` is the tax printed as a separate figure that is added to the articles to make the
  total (`TAX`, `Steuer`, `IVA` on a receipt whose prices are printed without it), and null on
  a German receipt, where the `MwSt.` table only says how much of the total is tax.
- `direction` is `out` on a normal purchase and `in` when the receipt pays money back: a
  `Leergutbon`, `Pfandbon`, `Retoure`, `Gutschrift`, `Rückgabe` or `Auszahlung`, or a total
  printed as a credit.
- `items` is one entry per line item, in the order they are printed, each with the article text
  and `amount_text` exactly as printed.
- `note` is one short line only when there is something about the photo the person has to know:
  it shows more than one receipt, it is cut off, it is not a receipt at all. Otherwise null.
- `several_receipts` is true when the photo shows more than one receipt. Read the first one and
  say so in `note`.

What is not a line item, and is never returned as one:
- a subtotal: `ZWI.SUMME`, `Zwischensumme`, `Zw.Summe`, `SUB TOTAL`, `Summe 9 Pos.`, `Posten: 3`,
  `SUMME NETTO`, and the total itself;
- a quantity or a measure line, which carries no price of its own: `2 x 0,49`, `4 x 1.29`,
  `0,208 KG x 19,90 EP`, `Säule 01 100,02 l 1,439 EUR/l`. The price of that article is the
  figure on the article line above or below it, never the number on this one;
- the VAT table (`MwSt.`, `A 19%`, `Netto`, `Brutto`), the payment lines (`Bar`, `Karte`, `EC`,
  `Geg. BAR`, `Rückgeld`, `Kartenzahlung`), the loyalty and points lines, the till, receipt and
  operator numbers, the address and the closing thanks.

A discount is a line item with a negative amount: `Rabatt -1,00`, `Rabat -2,00`, `Coupon -0,50`,
`MwSt.-Senkung -0,88`, a deposit return inside a purchase (`Leergut -0,25`). Return it exactly as
printed, minus sign included, because it is the difference between the articles and the total.

- Copy every figure character by character. Never add up anything, never round and never invent
  a figure you cannot see: the line items are added up and checked against the total, and a
  bill that does not add up is shown to the user instead of being trusted.

Fill `reasoning` first, in three to five very short lines: what kind of receipt this is, where
the total stands and what it is called, where the date stands, and which printed lines are not
articles. Only then read the fields.

A worked receipt, of the kind a German discounter prints:

  ALDI Im Brink 8
  Bananen              1,49
  2 x 0,49
  Gemuesemais          0,98
  ZWI.SUMME            2,47
  Joghurt              0,75
  Rabatt              -0,20
  ZU ZAHLEN            3,02
  MwSt A 7%  0,20
  Datum 04.05.2019 14:12

reasoning:
a discounter receipt: articles, then a total called ZU ZAHLEN
the date is at the foot, printed 04.05.2019 with the time next to it
ZWI.SUMME is a running subtotal and the MwSt line is the tax table, so neither is an article
the 2 x 0,49 line is a quantity line: its number is not a price, the 0,98 under it is
the Rabatt line is an article with a negative amount, which is what makes the items add up

fields: merchant "ALDI", date_text "04.05.2019 14:12", total_text "3,02", currency_text "",
tax_text null, direction out, items ("Bananen" 1,49), ("Gemuesemais" 0,98), ("Joghurt" 0,75),
("Rabatt" -0,20)

`currency_text` is the currency as printed and nothing else. Copy it whenever one is printed
anywhere near the total, the sign in front of the figure included (`€`, `$`, `12,50 PLN`,
`SUMA PLN`, `CHF`): a receipt in another currency is refused rather than booked as euros, and a
`$` that is not copied is a dollar amount booked as euros, which nothing later catches. Leave it
empty only when the receipt prints no currency at all, which is the ordinary German case, and
never fill it with a letter of the article line above it or with a guess: that refuses a euro
receipt as foreign money.
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
    """Every booking on one page, in the order they are printed.

    `reasoning` is first so the layout is read before the rows are: a model that starts with
    the rows reads the first line it sees as a booking, header or not (ticket 42).
    """

    reasoning: str = Field(
        description=(
            "Three to five very short lines, one each, written before the rows: the layout of "
            "this page, where the first booking starts, where the date, the amount and the "
            "balance stand on a line, and which lines are headers or balances."
        )
    )
    rows: list[StatementRow] = Field(default_factory=list)
    note: str | None = Field(default=None, description="Only when the page holds no bookings: what it is instead.")


class BillItem(BaseModel):
    """One line of a receipt."""

    description: str = Field(description="The article text as printed.")
    amount_text: str = Field(
        description="The price exactly as printed, with its minus sign when it is a discount."
    )


class Bill(BaseModel):
    """One receipt as the sub-agent read it.

    `reasoning` is first for the same reason as on a statement page: the lines that are not
    articles have to be recognized before the articles are copied (ticket 42).
    """

    reasoning: str = Field(
        description=(
            "Three to five very short lines, one each, written before the fields: what kind of "
            "receipt this is, where the total stands and what it is called, where the date "
            "stands, and which printed lines are not articles."
        )
    )
    merchant: str = Field(description="The shop's name as printed at the top.")
    date_text: str = Field(
        default="",
        description="The date exactly as printed, with its time if one stands there, or empty when none is printed.",
    )
    total_text: str | None = Field(default=None, description="The total exactly as printed, or null.")
    currency_text: str = Field(default="", description="The currency as printed (`EUR`, `€`, `PLN`), or empty.")
    tax_text: str | None = Field(
        default=None, description="A tax figure added to the articles to make the total, or null."
    )
    direction: Literal["out", "in"] = Field(
        default="out", description="`in` when the receipt pays money back (Leergutbon, Retoure)."
    )
    note: str | None = Field(default=None, description="One line about the photo, only when there is one.")
    several_receipts: bool = Field(default=False, description="True when the photo shows more than one receipt.")
    items: list[BillItem] = Field(default_factory=list)

    # The fast slot answers an empty field with the word `null`, and a note reading "null" would
    # be shown to the user as if the photo carried one.
    _nulls = nullish_before("total_text", "tax_text", "note")


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
        f"Today is {today.isoformat()}, which is not the receipt's date: the receipt prints its "
        f"own, and that is the one to copy. Read this receipt: the merchant, the printed date, "
        f"the total and every line item, at most {MAX_ITEMS}."
    )


def statement_retry(previous: StatementPage, findings: list[str]) -> str:
    """A page whose figures the guards refused, handed back with what they refused (ticket 42).

    Every figure is checked against the printed text of the page it was read from, so a
    rejection names a span that is not on the page: the row was written rather than read, and
    the printed line it belongs to is right there to read again.
    """
    rows = "\n".join(
        f"  line {row.line}: {row.date_text} | {row.amount_text} | {row.description[:60]}"
        for row in previous.rows
    )
    return (
        "\n\nYour last answer was refused by the checks that hold every figure to the page. "
        "This is a correction of it, not a fresh reading: keep every row the points below do "
        "not name.\n\n"
        f"Your reasoning was:\n{previous.reasoning.strip()}\n\n"
        f"Your rows were:\n{rows}\n\n"
        "What the checks found:\n" + "\n".join(f"- {line}" for line in findings) + "\n\n"
        "Read those lines of the page again and answer with the corrected reasoning and the "
        "full set of rows. The first line of the reasoning says what you changed. Copy every "
        "figure from the printed line character by character: a figure that is not printed on "
        "this page is thrown away whatever you send."
    )


def bill_retry(previous: Bill, findings: list[str]) -> str:
    """A receipt whose arithmetic did not come out, handed back with the sum that did not."""
    items = "\n".join(f"  {item.description[:40]} | {item.amount_text}" for item in previous.items)
    return (
        "\n\nWhat you read off this receipt does not check out. This is a correction of it, not "
        "a fresh reading: keep every line the points below do not name.\n\n"
        f"Your reasoning was:\n{previous.reasoning.strip()}\n\n"
        f"You read the total as {previous.total_text!r} and these items:\n{items}\n\n"
        "What is wrong with it:\n" + "\n".join(f"- {line}" for line in findings) + "\n\n"
        "Look at the receipt again and answer with the corrected reasoning and the full set of "
        "fields. The first line of the reasoning says what you changed. Copy every figure as it "
        "is printed: never make the items add up by changing one."
    )


async def read_statement_text(
    model: Model,
    *,
    page: int,
    pages: int,
    layout_hint: str,
    year: int | None,
    lines: str,
    previous: StatementPage | None = None,
    findings: list[str] | None = None,
    model_settings: ModelSettings | None = None,
) -> StatementPage:
    """One page of a text PDF through the fast slot, or a second reading of the same page.

    `previous` and `findings` are what the guards refused about the first reading, which is the
    one thing that makes a second reading worth asking for.
    """
    prompt = statement_prompt(page=page, pages=pages, layout_hint=layout_hint, year=year, lines=lines)
    if previous is not None and findings:
        prompt += statement_retry(previous, findings)
    result = await statement_agent.run(prompt, model=model, model_settings=model_settings)
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
    previous: Bill | None = None,
    findings: list[str] | None = None,
    model_settings: ModelSettings | None = None,
) -> Bill:
    """One photo of a receipt through the fast slot's vision path.

    `previous` and `findings` are the arithmetic that did not come out on the first reading, so
    a second reading is a correction of an answer rather than the same guess again.
    """
    prompt = bill_prompt(today)
    if previous is not None and findings:
        prompt += bill_retry(previous, findings)
    result = await bill_agent.run(
        [prompt, BinaryContent(data=image, media_type=media_type)],
        model=model,
        model_settings=model_settings,
    )
    bill = result.output
    bill.items = bill.items[:MAX_ITEMS]
    return bill


def _capped(page: StatementPage) -> StatementPage:
    page.rows = page.rows[:MAX_ROWS_PER_PAGE]
    return page
