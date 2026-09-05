"""Folding rows a shape cannot draw as they came back: the stack's tail, the doughnut's tail, a self loop.

Folding is arithmetic and not a judgement, so it is done in code rather than asked of the SQL or
left to a repair round (`docs/chart-runtime.md`, "The check"). It lives here rather than in the
runner because it happens twice for the same chart: the runner folds once, before the code pass,
and the dashboard folds again on every load, because a card stores the statement and never the
figures. One function, so a chart pinned from a chat draws exactly the rows it drew in the chat
instead of eleven series over a palette of six (ticket 36 saw that, ticket 39 is this).

**The column roles.** Every fold needs to know which column is the position, which is the group
and which carries the euros. They are read off the order the query was asked for them in: the
plan lists its columns in that order and `runner._euro_last` puts the euro column last before the
statement is written, so a stored statement returns them in the same order that the runner read.
A card therefore needs to store nothing beyond its shape, its language and its SQL.
TODO: the ceiling is a statement whose SELECT order is not the plan's; today that only makes the
fold a no-op, because the value column would not hold numbers. If one ever has to be folded
anyway, record the roles on `dashboard_chart` when the card is stored and pass them in here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from finquery.chart.shapes import MAX_SERIES, MAX_SLICES, SHAPES

# What the folded-together tail is called, in the language the chart is captioned in.
REST_NAME = {"de": "Sonstige", "en": "Other"}


def rest_name(language: str) -> str:
    """The name of the rest slice or rest group, in the chart's own language."""
    return REST_NAME.get(language, REST_NAME["en"])


@dataclass(frozen=True)
class Folded:
    """The rows the chart draws, and the one sentence saying what was folded away.

    A shape has at most one fold, so there is at most one note. `note is None` means the rows
    are the query's own rows, unchanged and the same list object.
    """

    rows: list[dict[str, Any]]
    note: str | None = None


def fold_rows(
    shape: str, columns: Sequence[str], rows: list[dict[str, Any]], *, language: str = "en"
) -> Folded:
    """Fold what this shape cannot draw, keyed by the shape and by the columns' roles.

    Called by `runner.run_chart` before the rows are judged and the code is written, and by
    `dashboard.run_card` on every load and every refresh. A shape nobody recognises, or rows the
    fold cannot read, are handed back untouched: folding never fails a chart that would draw.
    """
    rule = SHAPES.get(shape)  # type: ignore[arg-type]
    if rule is None:
        return Folded(rows)
    if rule.crossed:
        return _fold_groups(columns, rows, language)
    if shape == "doughnut":
        return _fold_slices(columns, rows, language)
    if shape == "sankey":
        return _drop_self_loops(columns, rows)
    return Folded(rows)


def _numeric(rows: list[dict[str, Any]], column: str) -> bool:
    """Whether every row carries a figure in that column, so it can be summed."""
    return all(
        isinstance(row.get(column), (int, float)) and not isinstance(row.get(column), bool)
        for row in rows
    )


def _fold_slices(columns: Sequence[str], rows: list[dict[str, Any]], language: str) -> Folded:
    """A doughnut over more rows than it has slices: the smallest become one rest slice.

    Not left to a repair round: the local fast model drew twelve categories three rounds running
    and lost the chart, and a round that relabels instead of summing is what the browser threw
    on. The rows the chart draws are the rows the card shows, and the fold is narrated.
    """
    if len(rows) <= MAX_SLICES or len(columns) < 2:
        return Folded(rows)
    label, value = columns[0], columns[1]
    if not _numeric(rows, value):
        return Folded(rows)
    ranked = sorted(rows, key=lambda row: float(row[value]), reverse=True)
    kept, rest = ranked[: MAX_SLICES - 1], ranked[MAX_SLICES - 1 :]
    folded = {column: None for column in columns}
    folded[label] = rest_name(language)
    folded[value] = round(sum(float(row[value]) for row in rest), 2)
    note = (
        f"The query returned {len(rows)} slices and a doughnut shows {MAX_SLICES}, so the "
        f"{len(rest)} smallest are one '{folded[label]}' slice."
    )
    return Folded([*kept, folded], note)


def _fold_groups(columns: Sequence[str], rows: list[dict[str, Any]], language: str) -> Folded:
    """A grouped or stacked chart over more groups than the palette has colours.

    The same arithmetic as `_fold_slices`, and here for the same reason. Asking the query to keep
    the largest groups and relabel the rest is what broke the stacked bars three rounds running
    on 2026-09-05: the statement wrote `CASE ... ELSE 'Other'` but grouped by the month alone, so
    every month came back with several 'Other' rows and no definition could stack them. So the
    query is asked for each group as it is named, and the tail is folded here, where summing is a
    line of code rather than a repair round.
    """
    if len(columns) < 3:
        return Folded(rows)
    position, group, value = columns[0], columns[1], columns[2]
    if not _numeric(rows, value):
        return Folded(rows)
    totals: dict[str, float] = {}
    for row in rows:
        name = str(row.get(group))
        totals[name] = totals.get(name, 0.0) + float(row[value])
    if len(totals) <= MAX_SERIES:
        return Folded(rows)
    largest = sorted(totals.items(), key=lambda item: item[1], reverse=True)[: MAX_SERIES - 1]
    kept = {name for name, _ in largest}
    rest = rest_name(language)
    folded: list[dict[str, Any]] = []
    at: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        name = str(row.get(group))
        name = name if name in kept else rest
        key = (str(row.get(position)), name)
        if (seen := at.get(key)) is None:
            fresh = {**row, group: name}
            at[key] = fresh
            folded.append(fresh)
        else:
            seen[value] = round(float(seen[value]) + float(row[value]), 2)
    note = (
        f"The query returned {len(totals)} groups and a chart has {MAX_SERIES} colours, so the "
        f"{len(totals) - len(kept)} smallest are one '{rest}' group per {position}."
    )
    return Folded(folded, note)


def _drop_self_loops(columns: Sequence[str], rows: list[dict[str, Any]]) -> Folded:
    """A flow from a name into itself is a total row, and a sankey refuses the whole graph for it.

    "Show me where my income goes as a sankey" returned Income to Income beside the real flows on
    2026-09-05, and one row cost the chart. The row carries no flow, so it is left out here and
    the omission is narrated. Rows that are nothing but self loops are left alone: then there is
    no flow at all and `selfcheck.data_findings` says so.
    """
    if len(columns) < 3:
        return Folded(rows)
    source, target = columns[0], columns[1]
    loops = [row for row in rows if str(row.get(source)) == str(row.get(target))]
    kept = [row for row in rows if str(row.get(source)) != str(row.get(target))]
    if not loops or not kept:
        return Folded(rows)
    names = ", ".join(dict.fromkeys(str(row.get(source)) for row in loops))
    flowed = "One row flowed" if len(loops) == 1 else f"{len(loops)} rows flowed"
    note = (
        f"{flowed} from {names} into itself, which is a total and not a flow, so it is left out "
        f"and {len(kept)} flows are drawn."
    )
    return Folded(kept, note)
