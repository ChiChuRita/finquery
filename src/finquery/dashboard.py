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


def read_tiles(session: Session, profile_id: str, window: Range = NO_RANGE) -> Tiles:
    """Spent, earned, net and Needs review, from two guarded statements.

    Inside the range, "this month" is the newest month the range holds: `LATEST_DAY` reads
    `MAX(booked_on)` of the same narrowed view the statement runs against, so a range that ends
    in March makes the tiles say March.
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

# The last three months by category, five slices and the rest. This one folds in the statement,
# which it can because the statement is ours: a household that gains a category between two
# visits would otherwise hand a six-colour doughnut seven slices to draw. `run_card` folds
# whatever comes back anyway (ticket 39), so the two agree; a statement the sub-agent wrote has
# only that second fold, because asking a model's SQL to fold is what broke the stacked bars.
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
