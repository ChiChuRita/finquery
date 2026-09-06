"""Reading a bank export that arrived as an Excel workbook.

The same engine as a CSV, one step earlier. openpyxl turns a sheet into rows of cells, this
module hands them on as a `Sniffed`, and everything after it is the CSV reader unchanged:
header detection, `detect_preset`, `mapping_for`, the mapping sub-agent for an unknown layout,
the Question card that confirms it, and `parse`. A workbook is a layout, not a second pipeline.

What a workbook has that a CSV has not is types. An amount is a number and a booking date is a
date, so neither has to be read back out of a string with a guessed separator. Those cells are
written here in the one unambiguous form (`-39.9`, `2025-01-04`) and the mapping is corrected
to match (`with_cell_types`), so a preset that says "German decimal comma" cannot turn a float
of 39,90 EUR into 3.990,00 EUR.

Formulas are not read: the workbook is opened with `data_only=True`, so a formula cell is the
value Excel last computed for it, and a cell that never was computed is empty rather than the
formula's text.
"""

import io
import logging
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from openpyxl import load_workbook

from finquery.ingest.csv_reader import CsvUnreadable, Mapping, Sniffed

logger = logging.getLogger(__name__)

MIN_SHEET_ROWS = 2
"""Rows a sheet needs before it counts as holding bookings: a header and something under it.
A cover sheet with a title on it is not a sheet the picker should offer."""

IGNORED = "Charts, pictures and macros in a workbook are not read, only its cells."
"""What a workbook holds that this reader passes over, for the answer to say in one line."""

_MIDNIGHT = time(0, 0)


class XlsxUnreadable(CsvUnreadable):
    """The upload is not a workbook we can read.

    A subclass, so every caller that already answers an unreadable CSV with one sentence
    answers an unreadable workbook with one too.
    """


@dataclass(frozen=True)
class Workbook:
    """One sheet of a workbook, read as if it were a delimited file."""

    sheet: str
    """The sheet these rows came from."""
    sheets: tuple[str, ...]
    """Every sheet with a header row and bookings under it, in the workbook's own order. More
    than one is what puts a sheet picker on the mapping card."""
    sniffed: Sniffed
    typed_dates: frozenset[str]
    """Columns holding at least one real date cell."""
    typed_numbers: frozenset[str]
    """Columns holding at least one real number cell."""
    text_columns: frozenset[str]
    """Columns holding at least one non-empty text cell. A column that is both text and numbers
    is a column nothing here can describe with one format, so it is left as the mapping says."""


def _text(value: object) -> str:
    """One cell as the CSV reader would have seen it, keeping what the cell's type already knew."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        # The clock is kept when there is one, and `parse_date` reads the day off the front of
        # it either way. Dropping it silently is not ours to do.
        return value.date().isoformat() if value.time() == _MIDNIGHT else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int | float | Decimal):
        # `-39.9`, never `-3.99E+01`: an exponent is not something `parse_amount` reads.
        return format(Decimal(str(value)).normalize(), "f")
    return str(value).strip()


def _grid(rows: list[tuple[object, ...]]) -> list[list[object]]:
    """The rows of a sheet with their trailing empty cells and their empty rows dropped.

    Excel hands out a rectangle: a sheet whose used range is wider than its table pads every row
    with `None`, and a blank line between two blocks is a row of them.
    """
    grid: list[list[object]] = []
    for row in rows:
        cells = list(row)
        while cells and (cells[-1] is None or str(cells[-1]).strip() == ""):
            cells.pop()
        if cells:
            grid.append(cells)
    return grid


def _header_index(grid: list[list[object]]) -> int:
    """Which row is the header, skipping a title block above the table.

    The same rule the CSV sniffer uses on a delimited file: the most common row width is the
    table's, and when two widths are equally common the one that occurs first wins, because
    that is the header.
    """
    widths = [len(row) for row in grid if len(row) >= 2]
    if not widths:
        raise XlsxUnreadable("No sheet of this workbook has a table with a header row in it.")
    first_at = {width: index for index, width in reversed(list(enumerate(widths)))}
    width = max(widths, key=lambda candidate: (widths.count(candidate), -first_at[candidate]))
    return next(index for index, row in enumerate(grid) if len(row) == width)


def read_xlsx(data: bytes, *, sheet: str | None = None) -> Workbook:
    """One sheet of a workbook as rows the CSV mapping engine can take.

    `sheet` picks a sheet by name; without one the first sheet that has bookings in it is read,
    which is where a bank export puts them.
    """
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - every failure to open is the same message here
        logger.warning("a workbook could not be opened", exc_info=True)
        raise XlsxUnreadable(
            "This file could not be opened as an Excel workbook. It may be damaged, or it may "
            "be an older .xls file. Save it again as .xlsx, or export the CSV instead."
        ) from exc
    try:
        grids = {name: _grid(list(book[name].iter_rows(values_only=True))) for name in book.sheetnames}
    finally:
        book.close()

    filled = tuple(name for name, grid in grids.items() if len(grid) >= MIN_SHEET_ROWS)
    if not filled:
        raise XlsxUnreadable("No sheet of this workbook has a header row with bookings under it.")
    if sheet is not None and sheet not in filled:
        raise XlsxUnreadable(f"This workbook has no sheet called {sheet!r}. Its sheets are: {', '.join(filled)}.")

    chosen = sheet or filled[0]
    grid = grids[chosen]
    index = _header_index(grid)
    # A nameless column still has to be nameable: the mapping names columns, and two empty
    # names would be one column to everything after this.
    header = [_text(cell) or f"Column {position}" for position, cell in enumerate(grid[index], start=1)]
    body = grid[index + 1 :]
    if not body:
        raise XlsxUnreadable(f"The sheet {chosen!r} has a header row but no bookings under it.")

    typed_dates: set[str] = set()
    typed_numbers: set[str] = set()
    text_columns: set[str] = set()
    rows: list[list[str]] = []
    for cells in body:
        for name, value in zip(header, cells, strict=False):
            if isinstance(value, date | datetime):
                typed_dates.add(name)
            elif isinstance(value, int | float | Decimal) and not isinstance(value, bool):
                typed_numbers.add(name)
            elif value is not None and str(value).strip():
                text_columns.add(name)
        # Short rows are padded and long ones kept as they are, exactly as `sniff` leaves them:
        # a row with more cells than the header becomes an issue in `parse`, never a silently
        # dropped booking.
        rows.append([_text(cell) for cell in cells] + [""] * (len(header) - len(cells)))

    return Workbook(
        sheet=chosen,
        sheets=filled,
        sniffed=Sniffed(encoding="xlsx", delimiter="", header=header, rows=rows),
        typed_dates=frozenset(typed_dates),
        typed_numbers=frozenset(typed_numbers),
        text_columns=frozenset(text_columns),
    )


def with_cell_types(mapping: Mapping, book: Workbook) -> Mapping:
    """The mapping as the cells of this sheet really are.

    A preset and the mapping sub-agent both describe how a *text* export writes its figures.
    Where the workbook already knows, that description does not apply: `read_xlsx` wrote a date
    cell as `2025-01-04` and a number cell as `-39.9`, so the mapping is switched to match.

    A column that also holds text is not switched, because one format has to fit every cell of
    it. An export with a money-out and a money-in column is judged on both together: only one of
    them is filled per row, and an empty column says nothing either way.

    TODO: one format per file. If a sheet ever turns up whose money columns disagree, this needs
    a format per column rather than a mapping-wide separator.
    """
    money = [
        column for column in (mapping.amount_column, mapping.debit_column, mapping.credit_column) if column
    ]
    changes: dict[str, str] = {}
    if mapping.date_column in book.typed_dates and mapping.date_column not in book.text_columns:
        changes["date_format"] = "YYYY-MM-DD"
    if any(column in book.typed_numbers for column in money) and not any(
        column in book.text_columns for column in money
    ):
        changes["decimal_separator"] = "dot"
    return mapping.model_copy(update=changes) if changes else mapping
