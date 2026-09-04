"""Which statement layout a file is, and what to tell the extraction sub-agent about it.

A layout is recognized from the header text the bank prints on every page, the same idea as
the CSV presets (`ingest.csv_reader.PRESETS`) and for the same reason: a known layout must not
cost a guess. What a layout buys is three things:

- `hint`, the paragraph the sub-agent is given about how this bank prints a booking. The two
  known layouts print one very differently, and a small model reads a hint about columns far
  better than it infers them.
- `opening` and `closing`, the printed balances the whole statement is reconciled against, but
  only when they really cover the rows on the pages. Trade Republic prints a `KONTOÜBERSICHT`
  on the first page of every export whose figures are the whole period of the export, so a
  slice of that export must not be reconciled against it: that layout deliberately declares no
  balance labels, and the running balance per row is what checks it (see ADR 0011).
- `columns`, what the printed columns mean, which is the mapping the Import record stores for a
  statement that has no CSV columns at all.
"""

import re
from dataclasses import dataclass, field

from finquery.ingest.csv_reader import Mapping, parse_amount

GENERIC_HINT = """\
This bank's layout is not one we know. Read the column headings on the page and work out which
column is the date, which is the amount and which is the running balance.
"""

SPARKASSE_HINT = """\
This is a Sparkasse Kontoauszug. Every booking is two printed lines:

  04.01.25  04.01.25  KARTENZAHLUNG  KAUFLAND BERLIN  -85,10  2.868,05
  KAUFLAND 4711 BERLIN

The first line is the booking date, the value date, the booking type, the counterparty, the
signed amount and the running balance. The line under it is the reference text and belongs to
the same booking. A minus in front of the amount means money out, no sign means money in.
`Alter Kontostand` and `Neuer Kontostand` are the balances of the statement, not bookings.
"""

TRADE_REPUBLIC_HINT = """\
This is a Trade Republic statement (UMSATZÜBERSICHT). One booking is spread over up to three
printed lines and the day, the month and the year are split across them:

  17 Mai
  KartenzahlungKAUFLAND POTSDAM INNENSTA  79,90 €  315,10 €
  2024

Read the date from the day and month line plus the year line under it. The booking type is
printed hard against the description with no space ("Kartenzahlung", "Überweisung",
"Handelsabrechnung", "Zinszahlung"), so the description is what follows it. The first money
figure is the amount and the second is the running balance. The two money columns are
`ZAHLUNGSEINGANG` (money in) and `ZAHLUNGSAUSGANG` (money out) and you often cannot tell them
apart from the text alone: report the amount and the balance, guess the direction, and the
running balance is what decides it. The `KONTOÜBERSICHT` block on the first page is a summary
of the whole export, not a booking, and neither is a `SALDO` or `ENDSALDO` line.
"""


@dataclass(frozen=True)
class Layout:
    """One recognized statement layout."""

    name: str
    label: str
    account_name: str
    markers: tuple[str, ...]
    """Header text every page of this bank carries. All of them have to appear."""
    hint: str
    opening_label: str | None = None
    """The printed opening balance, when it covers the pages being read. None means the running
    balance per row is the only whole-statement check there is."""
    closing_label: str | None = None
    columns: Mapping = field(
        default_factory=lambda: Mapping(
            date_column="date",
            amount_column="amount",
            description_column="description",
            counterparty_column="counterparty",
        )
    )

    def balance(self, text: str, label: str | None) -> int | None:
        """The cents printed after one of this layout's balance labels, or None."""
        if label is None:
            return None
        match = re.search(rf"{re.escape(label)}\s*:?\s*(-?[\d.]+,\d{{2}})", text)
        if match is None:
            return None
        try:
            return parse_amount(match.group(1), "comma")
        except ValueError:
            return None

    def opening(self, text: str) -> int | None:
        return self.balance(text, self.opening_label)

    def closing(self, text: str) -> int | None:
        return self.balance(text, self.closing_label)


SPARKASSE = Layout(
    name="sparkasse",
    label="Sparkasse Kontoauszug",
    account_name="Sparkasse Girokonto",
    markers=("kontoauszug", "saldo eur"),
    hint=SPARKASSE_HINT,
    opening_label="Alter Kontostand",
    closing_label="Neuer Kontostand",
    columns=Mapping(
        date_column="Buchung",
        amount_column="Betrag EUR",
        description_column="Buchungstext / Verwendungszweck",
        counterparty_column="Buchungstext / Verwendungszweck",
    ),
)

TRADE_REPUBLIC = Layout(
    name="traderepublic",
    label="Trade Republic statement",
    account_name="Trade Republic",
    markers=("trade republic bank", "umsatzübersicht"),
    hint=TRADE_REPUBLIC_HINT,
    # No balance labels on purpose: the KONTOÜBERSICHT of an export covers the whole export,
    # so a frame of it reconciles on its rows' running balance instead.
    columns=Mapping(
        date_column="DATUM",
        amount_column="ZAHLUNGSAUSGANG",
        description_column="BESCHREIBUNG",
        counterparty_column="BESCHREIBUNG",
    ),
)

UNKNOWN = Layout(
    name="unknown",
    label="an unknown layout",
    account_name="Imported account",
    markers=(),
    hint=GENERIC_HINT,
)

LAYOUTS: tuple[Layout, ...] = (SPARKASSE, TRADE_REPUBLIC)


def layout_named(name: str) -> Layout:
    """The layout a stored extraction says it was, or `UNKNOWN`. A commit reads its columns."""
    return next((layout for layout in LAYOUTS if layout.name == name), UNKNOWN)


def detect_layout(text: str) -> Layout:
    """The layout whose markers all appear in the file's text, or `UNKNOWN`.

    The most specific match wins, the same rule `detect_preset` uses for a CSV header.
    """
    folded = text.casefold()
    matches = [layout for layout in LAYOUTS if all(marker in folded for marker in layout.markers)]
    return max(matches, key=lambda layout: len(layout.markers)) if matches else UNKNOWN
