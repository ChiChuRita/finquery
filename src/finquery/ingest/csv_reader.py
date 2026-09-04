"""Reading a bank CSV export: sniff the file, map its columns, parse its rows.

German exports are the hard case. Semicolons, cp1252, `1.234,56`, `DD.MM.YYYY`, sometimes a
preamble above the header and sometimes separate debit and credit columns instead of one signed
amount. The six named banks are recognized by their headers so the common case never asks the
model; anything else gets a mapping proposed by the fast slot (see `mapping_agent.py`) and
corrected by the user in the Import page preview.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

DELIMITERS = (";", ",", "\t", "|")
ENCODINGS = (("utf-8-sig", "utf-8"), ("cp1252", "cp1252"))
SNIFF_LINES = 40

DateFormat = Literal["DD.MM.YYYY", "DD.MM.YY", "YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY"]
DecimalSeparator = Literal["comma", "dot"]

STRPTIME: dict[DateFormat, str] = {
    "DD.MM.YYYY": "%d.%m.%Y",
    "DD.MM.YY": "%d.%m.%y",
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
}

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "é": "e"})
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


class CsvUnreadable(ValueError):
    """The upload is not a delimited text file we can read."""


def normalize(name: str) -> str:
    """Column names differ by punctuation, case and umlaut spelling between exports."""
    return _NOT_ALNUM.sub("", name.strip().lower().translate(_UMLAUTS))


class Mapping(BaseModel):
    """Which column means what, and how its values are written."""

    date_column: str
    amount_column: str | None = None
    debit_column: str | None = None
    credit_column: str | None = None
    description_column: str | None = None
    counterparty_column: str | None = None
    date_format: DateFormat = "DD.MM.YYYY"
    decimal_separator: DecimalSeparator = "comma"

    @model_validator(mode="after")
    def _needs_an_amount(self) -> Self:
        if not self.amount_column and not (self.debit_column or self.credit_column):
            raise ValueError("give either amount_column or debit_column and credit_column")
        return self


class ProposedMapping(BaseModel):
    """What the mapping sub-agent returns. Same fields plus its reasoning for the user."""

    mapping: Mapping
    account_name: str = Field(description="A short name for the account this file belongs to")
    note: str = Field(description="One sentence on how the columns were recognized")


@dataclass(frozen=True)
class Preset:
    """A bank recognized by its header. `columns` and `required` are normalized names."""

    name: str
    label: str
    account_name: str
    required: tuple[str, ...]
    columns: dict[str, str]
    date_format: DateFormat = "DD.MM.YYYY"
    decimal_separator: DecimalSeparator = "comma"


PRESETS: tuple[Preset, ...] = (
    Preset(
        name="sparkasse",
        label="Sparkasse",
        account_name="Sparkasse Girokonto",
        required=("auftragskonto", "buchungstag", "verwendungszweck", "betrag"),
        columns={
            "date_column": "buchungstag",
            "amount_column": "betrag",
            "description_column": "verwendungszweck",
            "counterparty_column": "beguenstigterzahlungspflichtiger",
        },
    ),
    Preset(
        name="dkb",
        label="DKB",
        account_name="DKB Girokonto",
        required=("buchungsdatum", "zahlungsempfaengerin", "betrag"),
        columns={
            "date_column": "buchungsdatum",
            "amount_column": "betrag",
            "description_column": "verwendungszweck",
            "counterparty_column": "zahlungsempfaengerin",
        },
        date_format="DD.MM.YY",
    ),
    Preset(
        name="ing",
        label="ING",
        account_name="ING Girokonto",
        required=("buchung", "auftraggeberempfaenger", "betrag"),
        columns={
            "date_column": "buchung",
            "amount_column": "betrag",
            "description_column": "verwendungszweck",
            "counterparty_column": "auftraggeberempfaenger",
        },
    ),
    Preset(
        name="n26",
        label="N26",
        account_name="N26 Main Account",
        required=("bookingdate", "partnername", "amount"),
        columns={
            "date_column": "bookingdate",
            "amount_column": "amount",
            "description_column": "paymentreference",
            "counterparty_column": "partnername",
        },
        date_format="YYYY-MM-DD",
        decimal_separator="dot",
    ),
    Preset(
        name="comdirect",
        label="comdirect",
        account_name="comdirect Girokonto",
        required=("buchungstag", "vorgang", "umsatzin"),
        columns={
            "date_column": "buchungstag",
            "amount_column": "umsatzin",
            "description_column": "buchungstext",
        },
    ),
    Preset(
        # `name` carries the merchant of a card payment and the person of a transfer; the
        # `description` column carries the booking text.
        name="traderepublic",
        label="Trade Republic",
        account_name="Trade Republic",
        required=("datetime", "amount", "counterpartyname", "mcccode"),
        columns={
            "date_column": "date",
            "amount_column": "amount",
            "description_column": "description",
            "counterparty_column": "name",
        },
        date_format="YYYY-MM-DD",
        decimal_separator="dot",
    ),
)


@dataclass
class Sniffed:
    """What reading the bytes told us before any column means anything."""

    encoding: str
    delimiter: str
    header: list[str]
    rows: list[list[str]]


@dataclass
class ParsedRow:
    booked_on: date
    amount_cents: int
    description: str
    counterparty: str | None


@dataclass
class Parsed:
    rows: list[ParsedRow] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def decode(data: bytes) -> tuple[str, str]:
    if b"\x00" in data[:4096]:
        raise CsvUnreadable("This looks like a binary file, not a CSV export.")
    for codec, label in ENCODINGS:
        try:
            return data.decode(codec), label
        except UnicodeDecodeError:
            continue
    raise CsvUnreadable("The file is neither UTF-8 nor Windows-1252 text.")


def _rows_for(text: str, delimiter: str) -> list[list[str]]:
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if any(cell.strip() for cell in row)]


def sniff(data: bytes) -> Sniffed:
    """Find the encoding, the delimiter and the header row, skipping any preamble above it."""
    text, encoding = decode(data)
    head = "\n".join(text.splitlines()[:SNIFF_LINES])

    best: tuple[int, int, str, list[list[str]]] | None = None
    for candidate in DELIMITERS:
        rows = _rows_for(head, candidate)
        widths = [len(row) for row in rows]
        if not widths:
            continue
        width = max(widths, key=lambda w: (widths.count(w), w))
        score = widths.count(width)
        if width >= 2 and (best is None or (width, score) > (best[0], best[1])):
            best = (width, score, candidate, rows)
    if best is None:
        raise CsvUnreadable("No delimited header row found. Expected a CSV with at least two columns.")

    width, _, found_delimiter, head_rows = best
    header_index = next(index for index, row in enumerate(head_rows) if len(row) == width)
    header = [cell.strip() for cell in head_rows[header_index]]

    all_rows = _rows_for(text, found_delimiter)
    data_rows = [row + [""] * (width - len(row)) for row in all_rows[header_index + 1 :] if len(row) <= width]
    if not data_rows:
        raise CsvUnreadable("The file has a header but no data rows.")
    return Sniffed(encoding=encoding, delimiter=found_delimiter, header=header, rows=data_rows)


def _find(header: list[str], key: str) -> str | None:
    """Resolve a normalized preset key to the actual column name in this header."""
    normalized = [normalize(name) for name in header]
    if key in normalized:
        return header[normalized.index(key)]
    prefixed = [name for name, norm in zip(header, normalized, strict=True) if norm.startswith(key)]
    return prefixed[0] if len(prefixed) == 1 else None


def detect_preset(header: list[str]) -> Preset | None:
    """The best preset whose required columns are all present, or None for an unknown bank."""
    matches = [preset for preset in PRESETS if all(_find(header, key) for key in preset.required)]
    return max(matches, key=lambda preset: len(preset.required)) if matches else None


def mapping_for(preset: Preset, header: list[str]) -> Mapping:
    columns = {field_name: _find(header, key) for field_name, key in preset.columns.items()}
    return Mapping(
        **{name: value for name, value in columns.items() if value},
        date_format=preset.date_format,
        decimal_separator=preset.decimal_separator,
    )


def parse_amount(text: str, decimal_separator: DecimalSeparator) -> int:
    """German exports write `1.234,56`, `-12,00` and sometimes a trailing minus. Returns cents."""
    cleaned = text.strip().replace("\xa0", "").replace(" ", "")
    cleaned = re.sub(r"[^0-9,.\-+]", "", cleaned)
    if cleaned.endswith(("-", "+")):
        cleaned = cleaned[-1] + cleaned[:-1]
    if decimal_separator == "comma":
        cleaned = cleaned.replace(".", "").replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    if not cleaned or cleaned in "+-":
        raise ValueError(f"no amount in {text.strip()!r}")
    try:
        return int((Decimal(cleaned) * 100).quantize(Decimal(1)))
    except InvalidOperation as exc:
        raise ValueError(f"cannot read the amount {text.strip()!r}") from exc


def parse_date(text: str, date_format: DateFormat) -> date:
    """Try the mapped format first, then the others, so a wrong guess still imports."""
    value = text.strip()
    formats = [STRPTIME[date_format], *(pattern for key, pattern in STRPTIME.items() if key != date_format)]
    for pattern in formats:
        for candidate in (value, value[:10]):
            try:
                return datetime.strptime(candidate, pattern).date()
            except ValueError:
                continue
    raise ValueError(f"cannot read the date {value!r}")


def parse(sniffed: Sniffed, mapping: Mapping, *, limit: int | None = None) -> Parsed:
    """Apply a mapping to sniffed rows. A row that cannot be read becomes an issue, not a crash."""
    index = {name: position for position, name in enumerate(sniffed.header)}
    for column in (
        mapping.date_column,
        mapping.amount_column,
        mapping.debit_column,
        mapping.credit_column,
        mapping.description_column,
        mapping.counterparty_column,
    ):
        if column and column not in index:
            raise CsvUnreadable(f"The file has no column {column!r}.")

    def cell(row: list[str], column: str | None) -> str:
        return row[index[column]].strip() if column else ""

    parsed = Parsed()
    for number, row in enumerate(sniffed.rows[: limit or len(sniffed.rows)], start=1):
        try:
            booked_on = parse_date(cell(row, mapping.date_column), mapping.date_format)
            if mapping.amount_column:
                amount_cents = parse_amount(cell(row, mapping.amount_column), mapping.decimal_separator)
            else:
                debit = cell(row, mapping.debit_column)
                credit = cell(row, mapping.credit_column)
                if debit and credit:
                    raise ValueError("both the debit and the credit column are filled")
                if debit:
                    amount_cents = -abs(parse_amount(debit, mapping.decimal_separator))
                elif credit:
                    amount_cents = abs(parse_amount(credit, mapping.decimal_separator))
                else:
                    raise ValueError("neither the debit nor the credit column is filled")
        except ValueError as exc:
            parsed.issues.append(f"Row {number}: {exc}")
            continue
        description = cell(row, mapping.description_column)
        counterparty = cell(row, mapping.counterparty_column)
        parsed.rows.append(
            ParsedRow(
                booked_on=booked_on,
                amount_cents=amount_cents,
                # Exports vary in which of the two carries the readable text, so each stands in
                # for the other when it is empty.
                description=description or counterparty or "(no description)",
                counterparty=counterparty or None,
            )
        )
    return parsed
