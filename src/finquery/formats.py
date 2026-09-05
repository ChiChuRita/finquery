"""How a figure and a date are written inside a sentence the user reads.

Most numbers reach the browser as machine-readable values (`_euro` in `finquery.changesets`,
an ISO date on a preview row) and `frontend/src/lib/format.ts` writes them out. A few never
pass through it: a summary sentence, a refusal, the line a receipt's own arithmetic produces.
Those are written here, in the same German format, so one card never carries `-20.73 EUR` next
to `-20,73 €`.
"""

from datetime import date


def eur(cents: int) -> str:
    """`-1.234,56`: comma for the decimals, dot for the thousands, minus in front."""
    grouped = f"{abs(cents) / 100:,.2f}".replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"-{grouped}" if cents < 0 else grouped


def day(value: date) -> str:
    """`04.09.2026`, the format every table and every card in the app uses."""
    return value.strftime("%d.%m.%Y")
