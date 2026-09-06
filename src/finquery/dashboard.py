"""The dashboard: four tiles, the cards on it, and the six every profile starts with.

Nothing here is a cache. A card stores a title, a shape, the SQL and the checked JavaScript the
chart was drawn from, and every load runs that SQL through the same guard and the same
profile-scoped view as a question asked in the chat (`finquery.query.guard`, ADR 0004). The
numbers on the page are therefore always the numbers in the database, and a statement that no
longer runs becomes a sentence on its card rather than a broken page.

The six defaults are written here rather than asked of a model: they are the same house style
(`docs/chart-runtime.md`), and `tests/test_dashboard.py` runs each of them through
`finquery.chart.selfcheck` against the shipped dataset, so a rule that changes takes these six
with it instead of leaving them behind. They answer a household's questions in order: where is
the trend going, are we living within our income, where does the money go, what changed, what
is fixed, who gets the most (ticket 51, Proposal A of
`docs/research/charts-and-dashboard-2026-09-06.md`).

The tiles are one statement over the last seven months, not one figure: the page compares the
newest month with the one before it and with the mean of the earlier ones, and that arithmetic
is done on the returned rows in the browser the way `fold_rows` is done on them here. No figure
on this page was ever typed.

Both the tiles and the defaults read "this month" and "the last twelve months" from the newest
booking the profile has, not from today's date. A statement imported in January is still the
newest thing the household did in March, and a dashboard of six empty charts says nothing
about it.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finquery.chart.fold import fold_rows
from finquery.chart.shapes import Shape
from finquery.db import DashboardChart, Profile, Transaction, utcnow
from finquery.query.guard import SqlFailed, SqlRejected, execute_read_only, validate_sql
from finquery.query.runner import figures


@dataclass(frozen=True)
class Range:
    """The days the whole page is narrowed to, or neither, which is all of them.

    Nothing about it is stored: it arrives as two query parameters, is handed to the guard for
    every statement on the page, and comes back in the response so the page can label itself.
    """

    since: date | None = None
    until: date | None = None


NO_RANGE = Range()

# What the tiles and the twelve-month charts count as now: the day of the newest booking.
LATEST_DAY = "(SELECT MAX(booked_on) FROM transaction_view)"

TILE_MONTHS = 7
"""How many months the tiles' statement returns.

The newest is the month the tiles are about, the one before it is "last month", and the mean of
the rest is the six-month average. Seven rows is therefore the smallest statement that carries
both comparisons, and a profile with fewer months simply returns fewer rows: the page then says
what it averaged over instead of pretending to six.
"""

MONEY_SQL = f"""
SELECT strftime('%Y-%m', booked_on) AS month,
       ROUND(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 2) AS spent_eur,
       ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) AS income_eur,
       ROUND(SUM(amount), 2) AS net_eur
FROM transaction_view
WHERE booked_on >= date({LATEST_DAY}, 'start of month', '-{TILE_MONTHS - 1} months')
GROUP BY month
ORDER BY month
"""

REVIEW_SQL = """
SELECT COUNT(*) AS needs_review
FROM transaction_view
WHERE category IS NULL
"""


@dataclass(frozen=True)
class MonthFigures:
    """One month of the tiles' statement: what left, what came in, and the difference."""

    month: str
    spent_eur: float
    income_eur: float
    net_eur: float


@dataclass(frozen=True)
class Tiles:
    """The four plain figures above the charts, every one of them from an executed query.

    The three money figures are the newest month of `months`, which is the whole statement. The
    page draws the deltas from the same rows, so the figure and its comparison come from one
    query and never from two.
    """

    month: str | None = None
    """The month they are about, 'YYYY-MM', or null when the profile holds no booking."""
    spent_eur: float = 0.0
    income_eur: float = 0.0
    net_eur: float = 0.0
    needs_review: int = 0
    months: tuple[MonthFigures, ...] = ()
    """The last seven months the range holds, oldest first. The newest is the tiles' own month."""


def read_tiles(session: Session, profile_id: str, window: Range = NO_RANGE) -> Tiles:
    """Spent, earned, net and Needs review, from two guarded statements.

    Inside the range, "this month" is the newest month the range holds: `LATEST_DAY` reads
    `MAX(booked_on)` of the same narrowed view the statement runs against, so a range that ends
    in March makes the tiles say March, and the six months it compares with are the six before
    that one.
    """
    money = execute_read_only(
        session, validate_sql(MONEY_SQL), profile_id, since=window.since, until=window.until
    ).rows
    review = execute_read_only(
        session, validate_sql(REVIEW_SQL), profile_id, since=window.since, until=window.until
    ).rows
    needs_review = int(review[0]["needs_review"]) if review else 0
    if not money:
        return Tiles(needs_review=needs_review)
    months = tuple(
        MonthFigures(
            month=str(row["month"]),
            spent_eur=float(row["spent_eur"] or 0),
            income_eur=float(row["income_eur"] or 0),
            net_eur=float(row["net_eur"] or 0),
        )
        for row in money
    )
    newest = months[-1]
    return Tiles(
        month=newest.month,
        spent_eur=newest.spent_eur,
        income_eur=newest.income_eur,
        net_eur=newest.net_eur,
        needs_review=needs_review,
        months=months,
    )


@dataclass(frozen=True)
class DefaultChart:
    """One of the six cards a profile's dashboard opens with."""

    key: str
    """What this default is, whatever it was later renamed to: the stable identity a card keeps
    in `dashboard_chart.default_key`, so "Restore default cards" can tell which of the six a
    profile is missing."""
    title: str
    shape: Shape
    sql: str
    code: str
    plan: str = ""
    """What the card's details say about it. Empty means the plain one-liner every default gets;
    a card whose figures are a heuristic says so here, because a bar that looks like a fact has
    to name the rule it came from."""

    def plan_line(self) -> str:
        """The plan stored on the card: its own, or the sentence that names shape and origin."""
        return self.plan or (
            f"Chart plan: {self.shape}, columns from a fixed statement. A FinQuery default."
        )


# 1. Where is the trend going? The last twelve months of spending, one bar per month.
#
# Bars rather than a line, because a month is a discrete period and not a point on a
# continuum: a bar rests on zero by itself, and under the "This month" preset one bar still
# reads where a single point of a line says nothing (ticket 51, Proposal A).
MONTHLY_SQL = f"""
SELECT strftime('%Y-%m', booked_on) AS month,
       ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0
  AND booked_on > date({LATEST_DAY}, '-12 months')
GROUP BY month
ORDER BY month
"""

MONTHLY_CODE = """\
return defineChart({
  marks: [
    barY(data, { x: 'month', y: 'total_eur', fill: palette[0], maxThickness: 32 }),
  ],
  scales: {
    x: {
      scale: () => scaleBand().padding(0.2),
      axis: { ticks: { format: monthShort }, tickLabels: { thin: { minGap: 6, priority: 'ends' } } },
    },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});"""

# 2. Are we living within our income? Income and spending as two bars per month.
#
# Two figures cannot sit in one row and be drawn side by side, so the two halves are a UNION
# and the name of the half is a column of its own.
INCOME_SQL = f"""
SELECT strftime('%Y-%m', booked_on) AS month,
       'Income' AS topic,
       ROUND(SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount > 0
  AND booked_on > date({LATEST_DAY}, '-12 months')
GROUP BY month
UNION ALL
SELECT strftime('%Y-%m', booked_on) AS month,
       'Spending' AS topic,
       ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0
  AND booked_on > date({LATEST_DAY}, '-12 months')
GROUP BY month
ORDER BY month, topic
"""

INCOME_CODE = """\
return defineChart({
  marks: [
    barY(data, { x: 'month', y: 'total_eur', z: 'topic', color: (row) => row.topic, layout: group({ padding: 0.12 }), maxThickness: 32 }),
  ],
  scales: {
    x: {
      scale: () => scaleBand().padding(0.2),
      axis: { ticks: { format: monthShort }, tickLabels: { thin: { minGap: 6, priority: 'ends' } } },
    },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.topic + ' ' + monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});"""

# 3. Where does the money go? The range's categories, the eight largest and the rest.
#
# Ranked bars and not a doughnut: a profile seeds about fifteen categories against a palette of
# six, a household thinks in euros rather than in percent, and area is the weakest comparison
# there is. The tail folds in the statement, which this one may because the statement is ours.
CATEGORY_SQL = """
WITH by_category AS (
  SELECT coalesce(category, 'Needs review') AS name,
         ROUND(-SUM(amount), 2) AS total_eur
  FROM transaction_view
  WHERE amount < 0
  GROUP BY name
),
ranked AS (
  SELECT name, total_eur, ROW_NUMBER() OVER (ORDER BY total_eur DESC) AS place
  FROM by_category
)
SELECT CASE WHEN place <= 8 THEN name ELSE 'Other' END AS category,
       ROUND(SUM(total_eur), 2) AS total_eur
FROM ranked
GROUP BY 1
ORDER BY MIN(place)
"""

CATEGORY_CODE = """\
return defineChart({
  marks: [
    barX(data, { x: 'total_eur', y: 'category', fill: palette[0], maxThickness: 32 }),
  ],
  scales: {
    x: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
    y: { scale: () => scaleBand().padding(0.22), axis: { tickLabels: { thin: false } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.category + ': ' + eur(point.datum.total_eur),
  },
});"""

# 4. What changed, and where? The newest month against the one before it, by category.
#
# Long rows, one figure per (period, category) pair, and the period is the series: two bars
# per category name. The statement returns every category and `run_card` folds the tail, which
# is why the columns are asked for in the order period, category, euros: `fold_rows` reads the
# position, the group and the figure off that order, so the five largest categories are kept
# and the rest becomes one 'Other' group per period (ticket 39's shared fold).
COMPARISON_SQL = f"""
WITH per_period AS (
  SELECT CASE
           WHEN strftime('%Y-%m', booked_on) = strftime('%Y-%m', {LATEST_DAY})
           THEN 'This month' ELSE 'Last month'
         END AS period,
         coalesce(category, 'Needs review') AS category,
         ROUND(-SUM(amount), 2) AS total_eur
  FROM transaction_view
  WHERE amount < 0
    AND booked_on >= date({LATEST_DAY}, 'start of month', '-1 month')
  GROUP BY period, category
)
SELECT period, category, total_eur
FROM per_period
ORDER BY SUM(total_eur) OVER (PARTITION BY category) DESC, category, period
"""

COMPARISON_CODE = """\
return defineChart({
  marks: [
    barY(data, { x: 'category', y: 'total_eur', z: 'period', color: (row) => row.period, layout: group({ padding: 0.12 }), maxThickness: 32 }),
  ],
  scales: {
    x: { scale: () => scaleBand().padding(0.2), axis: { tickLabels: { thin: false, rotate: -28 } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.period + ', ' + point.datum.category + ': ' + eur(point.datum.total_eur),
  },
});"""

# 5. What leaves every month regardless? The merchants that look like a standing payment.
#
# A heuristic and named as one on the card: seen in at least three of the last four months at
# an amount whose largest month is within fifteen percent of its smallest, drawn as the average
# of those months. We store no recurring flag and no contract, so this is what the bookings
# themselves can say.
REGULAR_MONTHS = 4
REGULAR_SEEN = 3
REGULAR_SPREAD = 1.15

REGULAR_SQL = f"""
WITH monthly AS (
  SELECT coalesce(title, counterparty, description) AS merchant,
         strftime('%Y-%m', booked_on) AS month,
         -SUM(amount) AS eur
  FROM transaction_view
  WHERE amount < 0
    AND booked_on > date({LATEST_DAY}, 'start of month', '-{REGULAR_MONTHS} months')
  GROUP BY merchant, month
)
SELECT merchant,
       ROUND(AVG(eur), 2) AS monthly_eur
FROM monthly
GROUP BY merchant
HAVING COUNT(*) >= {REGULAR_SEEN}
   AND MAX(eur) <= MIN(eur) * {REGULAR_SPREAD}
ORDER BY monthly_eur DESC
LIMIT 10
"""

REGULAR_CODE = """\
return defineChart({
  marks: [
    barX(data, { x: 'monthly_eur', y: 'merchant', fill: palette[0], maxThickness: 32 }),
  ],
  scales: {
    x: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
    y: { scale: () => scaleBand().padding(0.22), axis: { tickLabels: { thin: false } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.merchant + ': ' + eur(point.datum.monthly_eur),
  },
});"""

REGULAR_PLAN = (
    f"Chart plan: bar_horizontal, columns merchant and monthly_eur. A FinQuery default, and a "
    f"heuristic rather than a list of contracts: a merchant counts as regular when it was paid "
    f"in at least {REGULAR_SEEN} of the last {REGULAR_MONTHS} months and its largest month is "
    f"within {round((REGULAR_SPREAD - 1) * 100)} percent of its smallest. The bar is the average "
    f"of those months. FinQuery stores no recurring flag, so a yearly bill, a first month and a "
    f"changed price are all outside it."
)

# 6. Who gets the most? The ten merchants the range spent the most at. Long names, so the bars
# lie down. Scoped by the range like every other card, rather than by the calendar year.
MERCHANTS_SQL = """
SELECT coalesce(title, counterparty, description) AS merchant,
       ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0
GROUP BY merchant
ORDER BY total_eur DESC
LIMIT 10
"""

MERCHANTS_CODE = """\
return defineChart({
  marks: [
    barX(data, { x: 'total_eur', y: 'merchant', fill: palette[0], maxThickness: 32 }),
  ],
  scales: {
    x: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
    y: { scale: () => scaleBand().padding(0.22), axis: { tickLabels: { thin: false } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.merchant + ': ' + eur(point.datum.total_eur),
  },
});"""

# 7. Am I ahead of last month today? Spending added up day by day, two months on one line
# chart (ticket 50 gave the line its optional series).
#
# The x axis is the day of the month and not a date, which is the whole point: the two months
# lie on top of each other, so the gap between the strokes on day 18 is what this month is
# ahead or behind by. The columns come in the order day, period, euros, which is what
# `fold_rows` reads a line's series off.
PACING_SQL = f"""
WITH per_day AS (
  SELECT CAST(strftime('%d', booked_on) AS INTEGER) AS day,
         CASE
           WHEN strftime('%Y-%m', booked_on) = strftime('%Y-%m', {LATEST_DAY})
           THEN 'This month' ELSE 'Last month'
         END AS period,
         ROUND(-SUM(amount), 2) AS eur
  FROM transaction_view
  WHERE amount < 0
    AND booked_on >= date({LATEST_DAY}, 'start of month', '-1 month')
  GROUP BY period, day
)
SELECT day,
       period,
       ROUND(SUM(eur) OVER (PARTITION BY period ORDER BY day), 2) AS running_eur
FROM per_day
ORDER BY day, period
"""

# The day numbers are printed every five days and on the first. Every label is kept
# (`thin: false`), because the layout dropping one would leave a stroke standing over blank
# space; which of them carries text is this code's decision, and thirty-one numbers under a
# 280 pixel frame is a smudge.
PACING_CODE = """\
const amounts = data.map((row) => row.running_eur);
return defineChart({
  marks: [
    lineY(data, { x: 'day', y: 'running_eur', z: 'period', color: 'period', strokeWidth: 2 }),
  ],
  scales: {
    x: {
      scale: () => scalePoint().padding(0.06),
      axis: {
        ticks: { format: (day) => (Number(day) === 1 || Number(day) % 5 === 0 ? String(day) : '') },
        tickLabels: { thin: false },
      },
    },
    y: {
      scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)]),
      nice: true,
      grid: true,
      axis: { ticks: { format: eurShort } },
    },
  },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.period + ', day ' + point.datum.day + ': ' + eur(point.datum.running_eur),
  },
});"""

PACING_PLAN = (
    "Chart plan: line, columns day, period and running_eur. A FinQuery default. Spending added "
    "up from the first of the month, the newest month of the range against the one before it, "
    "so the two strokes can be read against each other on the same day number. A month that is "
    "not over yet is a stroke that stops where the bookings stop."
)

# The order is the order of the questions a household asks: where is the trend going, are we
# living within our income, where does the money go, what changed, what is fixed, who gets the
# most, and am I ahead of last month today. It is also the position order on the page.
DEFAULTS: tuple[DefaultChart, ...] = (
    DefaultChart("spending_per_month", "Spending per month", "bar", MONTHLY_SQL, MONTHLY_CODE),
    DefaultChart(
        "income_against_spending",
        "Income against spending per month",
        "bar_grouped",
        INCOME_SQL,
        INCOME_CODE,
    ),
    DefaultChart("top_categories", "Top categories", "bar_horizontal", CATEGORY_SQL, CATEGORY_CODE),
    DefaultChart(
        "month_over_month",
        "This month against last month",
        "bar_grouped",
        COMPARISON_SQL,
        COMPARISON_CODE,
    ),
    DefaultChart(
        "regular_payments",
        "Regular payments",
        "bar_horizontal",
        REGULAR_SQL,
        REGULAR_CODE,
        plan=REGULAR_PLAN,
    ),
    DefaultChart(
        "top_merchants", "Top ten merchants", "bar_horizontal", MERCHANTS_SQL, MERCHANTS_CODE
    ),
    DefaultChart("month_pacing", "Month pacing", "line", PACING_SQL, PACING_CODE, plan=PACING_PLAN),
)


def _seed(session: Session, profile_id: str, default: DefaultChart, position: int) -> None:
    """Write one default onto a dashboard, at a position the caller has counted."""
    session.add(
        DashboardChart(
            profile_id=profile_id,
            position=position,
            title=default.title,
            shape=default.shape,
            language="en",
            request="",
            plan=default.plan_line(),
            sql=default.sql.strip(),
            code=default.code,
            created_from="default",
            default_key=default.key,
        )
    )


def ensure_defaults(session: Session, profile: Profile) -> None:
    """Put the six default cards on a dashboard that has never had them.

    Once per profile, marked on the profile itself: a dashboard the user emptied stays empty,
    and a profile that was seeded before ticket 51 keeps the four it was given. Restoring the
    set is a deliberate action on the page (`restore_defaults`), never something a load does.
    """
    if profile.dashboard_seeded:
        return
    profile.dashboard_seeded = True
    at = len(cards_of(session, profile.id))
    for index, default in enumerate(DEFAULTS):
        _seed(session, profile.id, default, at + index)
    session.commit()


def restore_defaults(session: Session, profile: Profile) -> list[str]:
    """Add every default this profile does not have, and return the keys that were added.

    Matched by `default_key` and by nothing else, so a default the user renamed, moved or
    edited counts as present and a card the user made is never touched. A profile seeded before
    ticket 51 carries no key on any card, which is why the six arrive next to its old four: the
    old cards are the user's now.
    """
    profile.dashboard_seeded = True
    present = {card.default_key for card in cards_of(session, profile.id) if card.default_key}
    missing = [default for default in DEFAULTS if default.key not in present]
    at = len(cards_of(session, profile.id))
    for index, default in enumerate(missing):
        _seed(session, profile.id, default, at + index)
    session.commit()
    return [default.key for default in missing]


def cards_of(session: Session, profile_id: str) -> list[DashboardChart]:
    """This profile's cards, left to right. A removed one is not on the dashboard."""
    return list(
        session.scalars(
            select(DashboardChart)
            .where(DashboardChart.profile_id == profile_id, DashboardChart.removed_at.is_(None))
            .order_by(DashboardChart.position, DashboardChart.created_at)
        )
    )


BOUNDS_SQL = """
SELECT MIN(booked_on) AS first_day, MAX(booked_on) AS last_day
FROM transaction_view
"""


def bounds(session: Session, profile_id: str) -> tuple[str | None, str | None]:
    """The first and the last day this profile has a booking on, or two Nones.

    Through the guard like everything else on this page, so it counts the same bookings the
    cards do (a split counts as its children, never as its parent). The range picker is bounded
    by these two days and its presets are counted back from the last one, the way the tiles and
    the twelve-month defaults already count from the newest booking.
    """
    rows = execute_read_only(session, validate_sql(BOUNDS_SQL), profile_id).rows
    if not rows or rows[0]["first_day"] is None:
        return None, None
    return str(rows[0]["first_day"]), str(rows[0]["last_day"])


def has_data(session: Session, profile_id: str) -> bool:
    """Whether the profile holds a single booking. An empty one is told to import, once."""
    count = session.scalar(select(func.count(Transaction.id)).where(Transaction.profile_id == profile_id))
    return bool(count)


def append(session: Session, profile_id: str, **fields: Any) -> DashboardChart:
    """Store one card at the end of the profile's dashboard."""
    card = DashboardChart(profile_id=profile_id, position=len(cards_of(session, profile_id)), **fields)
    session.add(card)
    session.commit()
    return card


def move(session: Session, card: DashboardChart, position: int) -> None:
    """Put one card at a position and renumber the rest, so the order stays dense."""
    others = [other for other in cards_of(session, card.profile_id) if other.id != card.id]
    at = max(0, min(position, len(others)))
    for index, other in enumerate(others[:at] + [card] + others[at:]):
        other.position = index
    session.commit()


def renumber(session: Session, profile_id: str) -> None:
    """Close the gap a removed card left behind."""
    for index, card in enumerate(cards_of(session, profile_id)):
        card.position = index
    session.commit()


# What a card says instead of drawing, when the statement behind it cannot be run any more. The
# guard's refusal and SQLite's error are both one sentence, and both are the user's business:
# a chart of a category that no longer exists is a card that has to explain itself.
REJECTED = "This chart's query is no longer allowed to run: {reason}"
FAILED = "This chart's query no longer runs against this profile: {reason}"


@dataclass(frozen=True)
class CardRows:
    """What one card's statement returned this time, or why it returned nothing."""

    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def run_card(session: Session, card: DashboardChart, window: Range = NO_RANGE) -> CardRows:
    """Run one stored statement through the guard, scoped to the card's own profile, and fold it.

    The fold is the same function the runner ran before the definition was ever written
    (`finquery.chart.fold`), over this load's rows: the statement is stored unfolded, because
    folding is arithmetic this app does after the query rather than in it. Without it a stack
    that showed six series in the chat showed eleven here and cycled the palette (ticket 36),
    and the household could gain a category between two visits anyway.
    """
    try:
        validated = validate_sql(card.sql)
    except SqlRejected as exc:
        return CardRows(error=REJECTED.format(reason=exc))
    try:
        result = execute_read_only(
            session, validated, card.profile_id, since=window.since, until=window.until
        )
    except SqlFailed as exc:
        return CardRows(error=FAILED.format(reason=exc))
    folded = fold_rows(card.shape, result.columns, result.rows, language=card.language)
    return CardRows(columns=result.columns, rows=folded.rows)


def card_chart(session: Session, card: DashboardChart) -> dict[str, Any]:
    """One card as a chart payload, in the shape the `chart` tool returns.

    The chat tools that show or edit a card answer with this, so the card in the transcript is
    the same component as any other chart and the figures the model quotes come from a statement
    that ran just now, like everywhere else.
    """
    result = run_card(session, card)
    return {
        "card_id": card.id,
        "on_dashboard": True,
        "request": card.request,
        "title": card.title,
        "shape": card.shape,
        "language": card.language,
        "plan": card.plan,
        "sql": card.sql,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": len(result.rows),
        "figures": figures(result.columns, result.rows),
        "code": card.code if result.error is None else None,
        "notes": notes_of(card),
        "error": result.error,
        "rendered": result.error is None and bool(result.rows),
    }


def notes_of(card: DashboardChart) -> list[str]:
    """The stored notes, and never a crash over a column a hand wrote into the database."""
    try:
        notes = json.loads(card.notes_json)
    except ValueError:
        return []
    return [str(note) for note in notes] if isinstance(notes, list) else []


def touch(session: Session, card: DashboardChart) -> datetime:
    """Mark that the user asked for this card's numbers again."""
    card.refreshed_at = utcnow()
    session.commit()
    return card.refreshed_at


# What a change from a chat can take back: everything about the drawing, and nothing about where
# the card sits. An edit keeps its position, so Undo has no position to restore.
VERSIONED = ("title", "shape", "language", "plan", "sql", "code", "notes_json")


class NothingToUndo(ValueError):
    """This card has no stored previous version, or the one it has belongs to another change."""


def _version(card: DashboardChart) -> dict[str, Any]:
    return {name: getattr(card, name) for name in VERSIONED}


def _previous(card: DashboardChart) -> dict[str, Any] | None:
    """The stored previous version, and never a crash over a column a hand wrote."""
    if not card.previous_json:
        return None
    try:
        previous = json.loads(card.previous_json)
    except ValueError:
        return None
    return previous if isinstance(previous, dict) else None


def undo_call_id(card: DashboardChart) -> str | None:
    """The chat tool call whose change one Undo on this card would take back.

    A card in a transcript compares it with its own call id: equal means its Undo still applies,
    anything else (a newer change on the same card, an Undo that already ran) means the button
    reads Undone.
    """
    previous = _previous(card)
    return str(previous["call_id"]) if previous and previous.get("call_id") else None


def stash(card: DashboardChart, call_id: str | None) -> None:
    """Keep the version this card has now, so the change about to happen can be undone once."""
    card.previous_json = json.dumps({"call_id": call_id, **_version(card)}) if call_id else None


def undo(session: Session, card: DashboardChart, *, call_id: str | None = None) -> DashboardChart:
    """Put the card back the way it was before its last change from a chat. Once.

    A removal stashed the version it removed, so restoring that version and clearing
    `removed_at` is one operation for all three changes. `call_id` is the caller saying which
    change it means: a card that has moved on since is not silently rolled back to something
    else, it says so.
    """
    previous = _previous(card)
    if previous is None:
        raise NothingToUndo("That change was already undone.")
    if call_id is not None and previous.get("call_id") != call_id:
        raise NothingToUndo("This chart changed again after that, so that change cannot be undone.")
    for name in VERSIONED:
        if name in previous:
            setattr(card, name, previous[name])
    card.removed_at = None
    card.previous_json = None
    session.commit()
    renumber(session, card.profile_id)
    return card


def apply_edit(
    session: Session, card: DashboardChart, chart: Mapping[str, Any], call_id: str
) -> DashboardChart:
    """Replace the drawing on a card with a freshly written one, keeping its place."""
    stash(card, call_id)
    card.title = str(chart.get("title") or card.title)
    card.shape = str(chart.get("shape") or card.shape)
    card.language = str(chart.get("language") or card.language)
    card.request = str(chart.get("request") or card.request)
    card.plan = str(chart.get("plan") or "")
    card.sql = validate_sql(str(chart.get("sql") or ""))
    card.code = str(chart["code"])
    card.notes_json = json.dumps(list(chart.get("notes") or []))
    card.refreshed_at = utcnow()
    session.commit()
    return card


def rename(session: Session, card: DashboardChart, title: str, call_id: str) -> DashboardChart:
    """A new title, no model call, and nothing else about the card touched."""
    stash(card, call_id)
    card.title = title.strip()
    session.commit()
    return card


def remove(session: Session, card: DashboardChart, *, call_id: str | None = None) -> DashboardChart:
    """Take a card off the dashboard, keeping the row so an Undo has something to restore.

    Removed from a chat it is undoable, which is what `call_id` stores. Removed on the page it
    is not: that button asks for a confirmation first, and a previous version left on the row
    would let some older card in some transcript restore the wrong thing.
    """
    stash(card, call_id)
    card.removed_at = utcnow()
    session.commit()
    renumber(session, card.profile_id)
    return card


def keep_chat_chart(
    session: Session,
    profile_id: str,
    chart: Mapping[str, Any],
    *,
    call_id: str,
    turn_id: str | None = None,
) -> DashboardChart:
    """Put a chart drawn in a chat on the dashboard, once per tool call.

    The tool call id is the identity, because the `chart` tool stores a kept chart while its own
    turn row is still being written: the same call arriving again (Add to dashboard on a chart
    the agent already kept, a second browser tab) finds the card it already made. A card that was
    removed comes back at the end rather than being made a second time.
    """
    existing = session.scalars(
        select(DashboardChart).where(
            DashboardChart.profile_id == profile_id, DashboardChart.source_call_id == call_id
        )
    ).first()
    if existing is not None:
        if turn_id and existing.source_turn_id is None:
            existing.source_turn_id = turn_id
        if existing.removed_at is not None:
            existing.removed_at = None
            existing.previous_json = None
            session.commit()
            move(session, existing, len(cards_of(session, profile_id)))
        session.commit()
        return existing
    return append(
        session,
        profile_id,
        title=str(chart.get("title") or chart.get("request") or "Chart"),
        shape=str(chart.get("shape") or "bar"),
        language=str(chart.get("language") or "en"),
        request=str(chart.get("request") or ""),
        plan=str(chart.get("plan") or ""),
        sql=validate_sql(str(chart.get("sql") or "")),
        code=str(chart["code"]),
        notes_json=json.dumps(list(chart.get("notes") or [])),
        created_from="chat",
        source_turn_id=turn_id,
        source_call_id=call_id,
    )
