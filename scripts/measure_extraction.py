"""Measure the extraction sub-agent: receipts against their printed truth, and the shipped PDF.

Not part of the app. It exists so the extraction prompt can be judged on real weights before and
after a change, the way `measure_categorization.py` judges the categorizer.

The receipts are the twenty freely licensed photos of `fixtures/private/receipts-web/`, which is
gitignored. Their printed merchant, date, total and item count are in the `SOURCES.md` of that
folder, and that file is the truth this script scores against, so nothing here holds an image or
a person.

    uv run python scripts/measure_extraction.py --receipts fixtures/private/receipts-web
    uv run python scripts/measure_extraction.py --pdf fixtures/synthetic/sparkasse-kontoauszug-2025.pdf
"""

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from finquery.extract.bill import read_bill_image
from finquery.extract.statement import extract_statement
from finquery.providers import build_resolver, subagent_settings
from finquery.settings import Settings

TODAY = date(2026, 9, 5)
"""The day the receipt set was collected. Fixed, so a rerun scores the same dates."""

_SECTION = re.compile(r"^## (\S+)$")
_FIELD = re.compile(r"^- (Date|Total|Line items): (.+)$")
_DATE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})|(\d{4})-(\d{2})-(\d{2})")
_MONEY = re.compile(r"(\d+)[.,](\d{2})")


@dataclass
class Printed:
    """What SOURCES.md says is on the paper."""

    name: str
    day: date | None
    total_cents: int | None
    items: int | None


def printed_truth(sources: Path) -> list[Printed]:
    """Every receipt of the folder with what is printed on it, read out of SOURCES.md."""
    receipts: list[Printed] = []
    current: dict[str, str] = {}
    name = ""
    for raw in sources.read_text().splitlines():
        section = _SECTION.match(raw.strip())
        if section:
            if name:
                receipts.append(_printed(name, current))
            name, current = section.group(1), {}
            continue
        field = _FIELD.match(raw.strip())
        if field and name:
            current[field.group(1)] = field.group(2)
    if name:
        receipts.append(_printed(name, current))
    return receipts


def _printed(name: str, fields: dict[str, str]) -> Printed:
    return Printed(
        name=name,
        day=_day(fields.get("Date", "")),
        total_cents=_cents(fields.get("Total", "")),
        items=int(match.group()) if (match := re.match(r"\d+", fields.get("Line items", ""))) else None,
    )


def _day(text: str) -> date | None:
    found = _DATE.search(text)
    if not found or "not printed" in text:
        return None
    if found.group(1):
        year = int(found.group(3))
        return date(year + 2000 if year < 100 else year, int(found.group(2)), int(found.group(1)))
    return date(int(found.group(4)), int(found.group(5)), int(found.group(6)))


def _cents(text: str) -> int | None:
    if "not printed" in text:
        return None
    found = _MONEY.search(text)
    return int(found.group(1)) * 100 + int(found.group(2)) if found else None


async def receipts(folder: Path) -> None:
    settings = Settings()
    resolve = build_resolver(settings)
    model_settings = subagent_settings(settings)
    truth = printed_truth(folder / "SOURCES.md")
    totals = dates = adds_up = 0
    scored_totals = scored_dates = 0
    print(f"{'receipt':<30} {'total':<18} {'date':<24} {'items':<14} flags")
    for printed in truth:
        path = folder / printed.name
        if not path.exists():
            print(f"{printed.name:<30} missing")
            continue
        try:
            read = await read_bill_image(
                path.read_bytes(), today=TODAY, resolve_model=resolve, model_settings=model_settings
            )
        except Exception as exc:  # noqa: BLE001 - one receipt failing is a line, not a crash
            print(f"{printed.name:<30} failed: {exc}")
            continue
        if read is None:
            print(f"{printed.name:<30} nothing readable")
            continue
        total_ok = printed.total_cents is None or read.total_cents == printed.total_cents
        date_ok = read.booked_on == printed.day if printed.day else not read.date_read
        if printed.total_cents is not None:
            scored_totals += 1
            totals += total_ok
        if printed.day is not None:
            scored_dates += 1
        dates += date_ok
        sums = "does_not_add_up" not in read.flags
        adds_up += sums
        print(
            f"{printed.name:<30} "
            f"{read.total_cents / 100:>8.2f} {'ok' if total_ok else 'MISS':<8} "
            f"{read.booked_on.isoformat()} {'ok' if date_ok else 'MISS':<12} "
            f"{len(read.items):>3} of {printed.items or '?':<7} "
            f"{','.join(read.flags) or '-'}"
        )
    print(
        f"\n{len(truth)} receipts: totals {totals}/{scored_totals} to the cent, "
        f"dates {dates}/{len(truth)} right ({scored_dates} printed), "
        f"items add up on {adds_up}/{len(truth)}"
    )


async def statement(path: Path) -> None:
    settings = Settings()
    extraction = await extract_statement(
        path.read_bytes(),
        file_name=path.name,
        kind="pdf",
        resolve_model=build_resolver(settings),
        model_settings=subagent_settings(settings),
    )
    print(f"{path.name}: {extraction.pages} pages, {len(extraction.rows)} rows, {len(extraction.flagged)} flagged")
    print(f"  reconciliation: {extraction.reconciliation.status} - {extraction.reconciliation.line}")
    for row in extraction.flagged[:10]:
        print(f"  flagged p{row.page}: {row.date_text} {row.amount_text} {row.description[:40]} - {row.reason}")
    if extraction.errors:
        print(f"  errors: {extraction.errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipts", type=Path, help="the folder of receipts and its SOURCES.md")
    parser.add_argument("--pdf", type=Path, help="a statement PDF to read")
    args = parser.parse_args()
    if not args.receipts and not args.pdf:
        parser.error("give --receipts, --pdf or both")
    if args.receipts:
        asyncio.run(receipts(args.receipts))
    if args.pdf:
        asyncio.run(statement(args.pdf))


if __name__ == "__main__":
    sys.exit(main())
