"""The dashboard: four tiles, the cards on it, and the four every profile starts with.

Nothing here is a cache. A card stores a title, a shape, the SQL and the checked JavaScript the
chart was drawn from, and every load runs that SQL through the same guard and the same
profile-scoped view as a question asked in the chat (`finquery.query.guard`, ADR 0004). The
numbers on the page are therefore always the numbers in the database, and a statement that no
longer runs becomes a sentence on its card rather than a broken page.

The four defaults are written here rather than asked of a model: they are the same house style
(`docs/chart-runtime.md`), and `tests/test_dashboard.py` runs each of them through
`finquery.chart.selfcheck` against the shipped dataset, so a rule that changes takes these four
with it instead of leaving them behind.

Both the tiles and the defaults read "this month" and "the last twelve months" from the newest
booking the profile has, not from today's date. A statement imported in January is still the
newest thing the household did in March, and a dashboard of four empty charts says nothing
about it.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finquery.chart.shapes import Shape
from finquery.db import DashboardChart, Profile, Transaction, utcnow
from finquery.query.guard import SqlFailed, SqlRejected, execute_read_only, validate_sql

# What the tiles and the twelve-month charts count as now: the day of the newest booking.
LATEST_DAY = "(SELECT MAX(booked_on) FROM transaction_view)"

MONEY_SQL = f"""
SELECT strftime('%Y-%m', booked_on) AS month,
       ROUND(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 2) AS spent_eur,
       ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) AS income_eur,
       ROUND(SUM(amount), 2) AS net_eur
FROM transaction_view
WHERE strftime('%Y-%m', booked_on) = strftime('%Y-%m', {LATEST_DAY})
GROUP BY month
"""

REVIEW_SQL = """
SELECT COUNT(*) AS needs_review
FROM transaction_view
WHERE category IS NULL
"""


@dataclass(frozen=True)
class Tiles:
    """The four plain figures above the charts, every one of them from an executed query."""

    month: str | None = None
    """The month they are about, 'YYYY-MM', or null when the profile holds no booking."""
    spent_eur: float = 0.0
    income_eur: float = 0.0
    net_eur: float = 0.0
    needs_review: int = 0


def read_tiles(session: Session, profile_id: str) -> Tiles:
    """Spent, earned, net and Needs review, from two guarded statements."""
    money = execute_read_only(session, validate_sql(MONEY_SQL), profile_id).rows
    review = execute_read_only(session, validate_sql(REVIEW_SQL), profile_id).rows
    needs_review = int(review[0]["needs_review"]) if review else 0
    if not money:
        return Tiles(needs_review=needs_review)
    row = money[0]
    return Tiles(
        month=str(row["month"]),
        spent_eur=float(row["spent_eur"] or 0),
        income_eur=float(row["income_eur"] or 0),
        net_eur=float(row["net_eur"] or 0),
        needs_review=needs_review,
    )


@dataclass(frozen=True)
class DefaultChart:
    """One of the four cards a profile's dashboard opens with."""

    title: str
    shape: Shape
    sql: str
    code: str


# The last twelve months of spending, one point per month.
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
const amounts = data.map((row) => row.total_eur);
return defineChart({
  marks: [
    lineY(data, { x: 'month', y: 'total_eur', stroke: palette[0], strokeWidth: 2.25, points: true }),
  ],
  scales: {
    x: {
      scale: () => scalePoint().padding(0.06),
      axis: { ticks: { format: monthShort }, tickLabels: { thin: { minGap: 6, priority: 'ends' } } },
    },
    y: {
      scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)]),
      nice: true,
      grid: true,
      axis: { ticks: { format: eurShort } },
    },
  },
  tooltip: {
    use: tooltip,
    format: (point) => monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});"""

# The last three months by category, five slices and the rest. The fold is in the statement
# because the rows are re-read on every load: a household that gains a category between two
# visits would otherwise hand a six-colour doughnut seven slices to draw.
CATEGORY_SQL = f"""
WITH by_category AS (
  SELECT coalesce(category, 'Needs review') AS name,
         ROUND(-SUM(amount), 2) AS total_eur
  FROM transaction_view
  WHERE amount < 0
    AND booked_on > date({LATEST_DAY}, '-3 months')
  GROUP BY name
),
ranked AS (
  SELECT name, total_eur, ROW_NUMBER() OVER (ORDER BY total_eur DESC) AS place
  FROM by_category
)
SELECT CASE WHEN place <= 5 THEN name ELSE 'Other' END AS category,
       ROUND(SUM(total_eur), 2) AS total_eur
FROM ranked
GROUP BY 1
ORDER BY MIN(place)
"""

CATEGORY_CODE = """\
const short = (name) => (name.length > 18 ? name.slice(0, 17) + '.' : name);
const slices = pie(data, { value: 'total_eur' });
return defineChart({
  marks: [
    polar({
      inset: 6,
      radiusRatio: 0.92,
      marks: [
        radialArc(slices, {
          innerRadius: ({ radius }) => radius * 0.62,
          cornerRadius: 3,
          color: (slice) => short(slice.category),
          key: 'category',
        }),
      ],
      scales: { angle: null, radius: null },
    }),
  ],
  scales: { x: null, y: null },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.category + ': ' + eur(point.datum.total_eur),
  },
});"""

# Income and spending as two groups per month. Two figures cannot sit in one row and be drawn
# side by side, so the two halves are a UNION and the name of the half is a column of its own.
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
    barY(data, { x: 'month', y: 'total_eur', z: 'topic', color: (row) => row.topic, layout: group({ padding: 0.12 }), radius: 2, maxThickness: 32 }),
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

# The ten merchants the newest year of data spent the most at. Long names, so the bars lie down.
MERCHANTS_SQL = f"""
SELECT coalesce(title, counterparty, description) AS merchant,
       ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0
  AND strftime('%Y', booked_on) = strftime('%Y', {LATEST_DAY})
GROUP BY merchant
ORDER BY total_eur DESC
LIMIT 10
"""

MERCHANTS_CODE = """\
return defineChart({
  marks: [
    barX(data, { x: 'total_eur', y: 'merchant', fill: palette[0], radius: 4, maxThickness: 32 }),
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

DEFAULTS: tuple[DefaultChart, ...] = (
    DefaultChart("Spending per month", "line", MONTHLY_SQL, MONTHLY_CODE),
    DefaultChart("Spending by category, last three months", "doughnut", CATEGORY_SQL, CATEGORY_CODE),
    DefaultChart("Income against spending per month", "bar_grouped", INCOME_SQL, INCOME_CODE),
    DefaultChart("Top ten merchants this year", "bar_horizontal", MERCHANTS_SQL, MERCHANTS_CODE),
)


def ensure_defaults(session: Session, profile: Profile) -> None:
    """Put the four default cards on a dashboard that has never had them.

    Once per profile, marked on the profile itself: a dashboard the user emptied stays empty.
    """
    if profile.dashboard_seeded:
        return
    profile.dashboard_seeded = True
    at = len(cards_of(session, profile.id))
    for index, default in enumerate(DEFAULTS):
        session.add(
            DashboardChart(
                profile_id=profile.id,
                position=at + index,
                title=default.title,
                shape=default.shape,
                language="en",
                request="",
                plan=f"Chart plan: {default.shape}, columns from a fixed statement. A FinQuery default.",
                sql=default.sql.strip(),
                code=default.code,
                created_from="default",
            )
        )
    session.commit()


def cards_of(session: Session, profile_id: str) -> list[DashboardChart]:
    """This profile's cards, left to right."""
    return list(
        session.scalars(
            select(DashboardChart)
            .where(DashboardChart.profile_id == profile_id)
            .order_by(DashboardChart.position, DashboardChart.created_at)
        )
    )


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


def run_card(session: Session, card: DashboardChart) -> CardRows:
    """Run one stored statement through the guard, scoped to the card's own profile."""
    try:
        validated = validate_sql(card.sql)
    except SqlRejected as exc:
        return CardRows(error=REJECTED.format(reason=exc))
    try:
        rows = execute_read_only(session, validated, card.profile_id)
    except SqlFailed as exc:
        return CardRows(error=FAILED.format(reason=exc))
    return CardRows(columns=rows.columns, rows=rows.rows)


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
