"""The two guards that decide whether an extracted statement can be trusted.

ADR 0011 is why they exist and ADR 0004 is the rule they serve: a figure the model returns is
never taken on its word.

**The verbatim guard.** Every amount, balance and date the sub-agent reports comes back as the
span it read, copied out of the page. The cents are then parsed here, from that span, so the
number that lands is the number that was printed. A span that does not occur in the source text
was not read, it was written, and the row is flagged. A date is the one exception to a plain
substring check, because Trade Republic prints the day and the year on different lines: for a
date, every digit group of the span has to appear in the lines around the one it was read from.

**The reconciliation guard.** A statement with a running balance checks itself: the balance of
a row minus the balance of the row before it is that row's amount. That catches a missed
booking, a misread digit and a wrong sign, and it does it per page as well as over the whole
statement. Where the two money columns of a layout cannot be told apart from the text (Trade
Republic again), the balance is also what decides the direction: an amount whose size is right
and whose sign is not is corrected here, in code, rather than trusted from the model.

A row that fails either guard is not dropped and not silently kept: it is flagged, and a
flagged row goes to the review step (`finquery.extract.review`) before anything is committed.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from finquery.extract.subagent import StatementRow
from finquery.ingest.csv_reader import parse_amount, parse_date

Flag = Literal["unreadable", "verbatim", "reconciliation", "unverified"]

FLAG_REASONS: dict[Flag, str] = {
    "unreadable": "The date or the amount could not be read.",
    "verbatim": "The figure is not printed on the page it was read from.",
    "reconciliation": "The running balance does not agree with this amount.",
    "unverified": "There is no balance or total on this page to check the figures against.",
}

DATE_WINDOW = 2
"""Printed lines above and below the one a date was read from that still count as its source.
Two, because a Trade Republic booking spreads its date over three lines."""

MONTHS: dict[str, int] = {
    "jan": 1, "feb": 2, "mar": 3, "mär": 3, "mrz": 3, "apr": 4, "mai": 5, "may": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}
"""The first three letters of a month name, German and English. Trade Republic prints
`15 Mai 2024` and `01 Sept. 2025`, and no other layout we know spells a month out."""

_MONTH_DATE = re.compile(r"(\d{1,2})\.?\s*([A-Za-zÄÖÜäöüéÉ]{3,9})\.?\s*(\d{2,4})")
_DIGITS = re.compile(r"\d+")


class RowUnreadable(ValueError):
    """The span the model returned is not a date or an amount."""


def money(text: str) -> int:
    """The cents printed in a span, sign included. Raises `ValueError` when there are none.

    The decimal separator is read off the span rather than assumed, the same way a typed
    transaction reads it (`ingest.typed.to_cents`): a statement that writes `1,234.56` must not
    become 123456 euros.
    """
    cleaned = unicodedata.normalize("NFKC", text).replace("−", "-").replace("−", "-")
    separator = "comma" if cleaned.rfind(",") > cleaned.rfind(".") else "dot"
    return parse_amount(cleaned, separator)


def has_sign(text: str) -> bool:
    """Whether the span itself says which way the money went."""
    cleaned = unicodedata.normalize("NFKC", text).replace("−", "-")
    return "-" in cleaned or "+" in cleaned


def parse_statement_date(text: str, *, year: int | None = None) -> date:
    """A date as a statement prints it: `04.01.25`, `2025-01-04`, `15 Mai 2024`, `01.04.`.

    `year` is the year the rest of the statement is in, which is what a German statement that
    prints `01.04.` without one means.
    """
    value = text.strip().strip(",;")
    try:
        return parse_date(value, "DD.MM.YYYY")
    except ValueError:
        pass
    named = _MONTH_DATE.search(value)
    if named is not None:
        month = MONTHS.get(named.group(2)[:3].casefold())
        if month is not None:
            found = int(named.group(3))
            return date(found + 2000 if found < 100 else found, month, int(named.group(1)))
    short = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.?", value)
    if short is not None and year is not None:
        return date(year, int(short.group(2)), int(short.group(1)))
    raise RowUnreadable(f"cannot read the date {value!r}")


def occurs(span: str, text: str) -> bool:
    """Whether a figure the model reported was really printed in the source text."""
    needle = span.strip().strip("€$ \t ")
    return bool(needle) and needle in text


def date_occurs(span: str, text: str, window: str) -> bool:
    """Whether a date was read rather than written.

    Either the span is printed as it stands, or every digit group of it appears in the lines
    around the one it was read from, which is what a date split over three printed lines looks
    like.
    """
    if occurs(span, text):
        return True
    groups = _DIGITS.findall(span)
    return bool(groups) and all(group in window for group in groups)


class ExtractedRow(BaseModel):
    """One booking out of a statement, after the guards have had it.

    `flags` empty means both guards passed and the row can be committed without asking. The
    fields the Import commits are the parsed ones; `source` and `line` are what the review step
    shows so a decision can be made by reading the page.
    """

    booked_on: date | None = None
    amount_cents: int | None = None
    description: str
    counterparty: str | None = None
    balance_cents: int | None = None
    page: int = 1
    line: int | None = None
    source: str = ""
    """The printed line this row was read from, verbatim."""
    date_text: str = ""
    amount_text: str = ""
    flags: list[Flag] = Field(default_factory=list)
    reason: str | None = None

    @property
    def flagged(self) -> bool:
        return bool(self.flags)

    @property
    def committable(self) -> bool:
        """A row with a date and an amount can be written, flagged or not."""
        return self.booked_on is not None and self.amount_cents is not None

    def flag(self, flag: Flag, reason: str | None = None) -> None:
        if flag not in self.flags:
            self.flags.append(flag)
        self.reason = reason or self.reason or FLAG_REASONS[flag]


def _window(lines: Sequence[str], line: int | None) -> str:
    if not line or line < 1:
        return "\n".join(lines)
    start = max(0, line - 1 - DATE_WINDOW)
    return "\n".join(lines[start : line + DATE_WINDOW])


def to_rows(
    raw: Iterable[StatementRow],
    *,
    page: int,
    lines: Sequence[str] = (),
    source_text: str | None,
    document_text: str = "",
    year: int | None = None,
) -> list[ExtractedRow]:
    """Parse what the sub-agent returned and run the verbatim guard over it.

    `source_text` is the page as it was printed, and None for a page that was read as an image:
    there is nothing to check a span against then, so the verbatim guard does not apply and the
    reconciliation guard is the only one those rows get.
    """
    rows: list[ExtractedRow] = []
    for entry in raw:
        line = entry.line if entry.line and 0 < entry.line <= len(lines) else None
        row = ExtractedRow(
            description=entry.description.strip()[:200] or "(no description)",
            counterparty=(entry.counterparty or "").strip()[:200] or None,
            page=page,
            line=line,
            source=lines[line - 1] if line else "",
            date_text=entry.date_text.strip(),
            amount_text=entry.amount_text.strip(),
        )
        try:
            row.booked_on = parse_statement_date(entry.date_text, year=year)
        except (RowUnreadable, ValueError) as exc:
            row.flag("unreadable", f"{exc}.")
        try:
            value = money(entry.amount_text)
            row.amount_cents = value if has_sign(entry.amount_text) else abs(value) * (-1 if entry.direction == "out" else 1)
        except ValueError:
            row.flag("unreadable", f"The amount {entry.amount_text.strip()!r} could not be read.")
        if entry.balance_text:
            try:
                row.balance_cents = money(entry.balance_text)
            except ValueError:
                row.balance_cents = None
        if source_text is not None:
            _verbatim(row, entry, source_text=source_text, document_text=document_text, lines=lines)
        rows.append(row)
    return rows


def _verbatim(
    row: ExtractedRow,
    entry: StatementRow,
    *,
    source_text: str,
    document_text: str,
    lines: Sequence[str],
) -> None:
    """Flag the row unless every figure on it is printed in the source text.

    The page comes first and the whole document second, so a booking the model attributed to
    the wrong page is not punished for it.
    """
    haystack = f"{source_text}\n{document_text}"
    if row.amount_cents is not None and not occurs(entry.amount_text, haystack):
        row.flag("verbatim", f"The amount {entry.amount_text.strip()!r} is not printed on this page.")
    if entry.balance_text and not occurs(entry.balance_text, haystack):
        row.flag("verbatim", f"The balance {entry.balance_text.strip()!r} is not printed on this page.")
    if row.booked_on is not None and not date_occurs(entry.date_text, haystack, _window(lines, row.line)):
        row.flag("verbatim", f"The date {entry.date_text.strip()!r} is not printed on this page.")


class Reconciliation(BaseModel):
    """What the arithmetic said about a statement, in one line the user and the Import record
    both read."""

    status: Literal["ok", "failed", "not_checkable"]
    line: str
    opening_cents: int | None = None
    closing_cents: int | None = None
    booked_cents: int = 0
    pages_failed: list[int] = Field(default_factory=list)
    rows_flagged: int = 0
    directions_fixed: int = 0
    """Rows whose money column could not be told apart from the text and whose direction the
    running balance decided."""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _euro(cents: int | None) -> str:
    if cents is None:
        return "unknown"
    whole, rest = divmod(abs(cents), 100)
    return f"{'-' if cents < 0 else ''}{whole:,}".replace(",", ".") + f",{rest:02d}"


def _chain(rows: Sequence[ExtractedRow]) -> int:
    """Walk the running balance and hold every row to it. Returns the signs it corrected."""
    fixed = 0
    previous: int | None = None
    for row in rows:
        balance, amount = row.balance_cents, row.amount_cents
        if balance is None or amount is None:
            previous = balance if balance is not None else previous
            continue
        if previous is not None:
            expected = balance - previous
            if expected != amount:
                if abs(expected) == abs(amount):
                    # The layout's two money columns are indistinguishable in the text (Trade
                    # Republic): the balance says which one this figure was in.
                    row.amount_cents = expected
                    fixed += 1
                else:
                    row.flag(
                        "reconciliation",
                        f"The balance moves by {_euro(expected)} but the amount reads "
                        f"{_euro(amount)}, so a booking is missing or misread here.",
                    )
        previous = balance
    return fixed


def _page_totals(rows: Sequence[ExtractedRow]) -> list[int]:
    """The pages whose own running balance does not add up. Checked per page as well as over
    the whole statement, because a frame of an export has no printed balances of its own."""
    failed: list[int] = []
    for page in sorted({row.page for row in rows}):
        on_page = [row for row in rows if row.page == page]
        with_balance = [row for row in on_page if row.balance_cents is not None and row.amount_cents is not None]
        if len(with_balance) < 2:
            continue
        first, last = with_balance[0], with_balance[-1]
        assert first.balance_cents is not None and first.amount_cents is not None
        assert last.balance_cents is not None
        opening = first.balance_cents - first.amount_cents
        booked = sum(row.amount_cents or 0 for row in on_page if row.amount_cents is not None)
        if opening + booked != last.balance_cents:
            failed.append(page)
    return failed


def reconcile(
    rows: Sequence[ExtractedRow], *, opening_cents: int | None = None, closing_cents: int | None = None
) -> Reconciliation:
    """Hold the extracted rows to their own arithmetic, per row, per page and as a whole.

    `opening_cents` and `closing_cents` are the balances the statement printed, and are passed
    only when the layout says they cover these pages (see `finquery.extract.layouts`). Without
    them the first row's balance minus its own amount is the opening and the last row's balance
    is the closing, which is the only honest way to reconcile a slice of a longer export.
    """
    directions = _chain(rows)
    balanced = [row for row in rows if row.balance_cents is not None and row.amount_cents is not None]
    booked = sum(row.amount_cents or 0 for row in rows if row.amount_cents is not None)
    opening = opening_cents
    if opening is None and balanced:
        assert balanced[0].amount_cents is not None and balanced[0].balance_cents is not None
        opening = balanced[0].balance_cents - balanced[0].amount_cents
    closing = closing_cents
    if closing is None and balanced:
        closing = balanced[-1].balance_cents

    pages_failed = _page_totals(rows)
    flagged = sum(1 for row in rows if row.flagged)
    if opening is None or closing is None:
        return Reconciliation(
            status="not_checkable",
            line=(
                f"No balance or total was printed with these {len(rows)} bookings, so the extraction "
                "could not be checked by arithmetic."
            ),
            booked_cents=booked,
            pages_failed=pages_failed,
            rows_flagged=flagged,
            directions_fixed=directions,
        )

    difference = opening + booked - closing
    whole = f"{_euro(opening)} + {_euro(booked)} = {_euro(closing)}"
    if difference == 0 and not pages_failed:
        return Reconciliation(
            status="ok",
            line=f"Reconciled: opening balance plus {len(rows)} bookings equals the closing balance ({whole}).",
            opening_cents=opening,
            closing_cents=closing,
            booked_cents=booked,
            rows_flagged=flagged,
            directions_fixed=directions,
        )
    pages = f" Pages that do not add up: {', '.join(str(page) for page in pages_failed)}." if pages_failed else ""
    return Reconciliation(
        status="failed",
        line=(
            f"Did not reconcile: opening {_euro(opening)} plus {len(rows)} bookings "
            f"({_euro(booked)}) is {_euro(opening + booked)}, but the closing balance is "
            f"{_euro(closing)}, a difference of {_euro(difference)}.{pages}"
        ),
        opening_cents=opening,
        closing_cents=closing,
        booked_cents=booked,
        pages_failed=pages_failed,
        rows_flagged=flagged,
        directions_fixed=directions,
    )


def flag_unverified(rows: Sequence[ExtractedRow], pages: Iterable[int]) -> None:
    """Flag the rows of pages that were read as an image with nothing to check them against.

    A photo has no text layer for the verbatim guard, so a balance or a total is the only proof
    there is. A page that offers neither gives rows nobody can vouch for, and the ticket's rule
    for those is that they are flagged rather than trusted.
    """
    wanted = set(pages)
    for row in rows:
        if row.page in wanted and row.balance_cents is None:
            row.flag("unverified")
