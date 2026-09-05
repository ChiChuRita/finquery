"""What counts as right.

One rule carries the whole benchmark: **every figure of the gold rows comes back, to the cent**.
Nothing else about a statement is judged, because two statements that answer the same question
name their columns differently, order their rows differently and often carry one column more
than the reference does. What they may not do is produce a different number.

The one thing the rule adds is that an answer is not a dump: a result more than three times the
reference's length has not answered the question, it has handed over the table.
"""

from typing import Any

from finquery_bench.datapoints import NO_ANSWER

WIDEST = 3
"""How many times the reference's rows an answer may carry before it is a dump, not an answer."""

WIDEST_FLOOR = 10
"""Below this, width says nothing: a one-row reference is often answered with a small ranking."""


def figures(rows: list[dict[str, Any]]) -> list[str]:
    """Every number in these rows, to the cent, as comparable strings.

    A bool is not a figure and neither is a missing value. An integer count and a euro amount
    are written the same way, so a count of 49 and 49,00 EUR compare equal: the questions that
    ask for both ask for two different columns, and confusing them is not a failure mode any
    model has.
    """
    found: list[str] = []
    for row in rows:
        for value in row.values():
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)):
                found.append(f"{round(float(value), 2):.2f}")
    return sorted(found)


def _contains(whole: list[str], part: list[str]) -> bool:
    """Multiset containment: every figure of `part` appears in `whole`, as often as it does there."""
    left = list(whole)
    for figure in part:
        if figure not in left:
            return False
        left.remove(figure)
    return True


def says_nothing(rows: list[dict[str, Any]]) -> bool:
    """True when a result is the honest 'the data holds none of that'."""
    return not rows or all(figure == "0.00" for figure in figures(rows))


def figure_match(gold_rows: list[dict[str, Any]], rows: list[dict[str, Any]], *, answer: str = "") -> bool:
    """Whether these rows carry the expected figures."""
    if answer == NO_ANSWER:
        return says_nothing(rows)
    if not rows:
        return False
    if len(rows) > max(WIDEST_FLOOR, WIDEST * len(gold_rows)):
        return False
    return _contains(figures(rows), figures(gold_rows))


def shape_match(expected: str, also: list[str], actual: str) -> bool:
    """The plan chose the shape the request asks for, or one that answers it as directly."""
    return actual == expected or actual in also


def columns_map(roles: list[str], columns: list[str], rows: list[dict[str, Any]]) -> bool:
    """The rows carry one column per role, in order: names first, the euro figure last.

    The roles are what the chart needs, not what the columns are called: a position or a label,
    an optional series, and the figure. So this checks the count and the kind of each column
    and never a name, because the model names its own.
    """
    if len(columns) != len(roles) or not rows:
        return False
    for column, role in zip(columns, roles, strict=True):
        values = [row.get(column) for row in rows]
        numeric = all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in values)
        if role == "value" and not numeric:
            return False
        if role != "value" and numeric:
            return False
    return True
