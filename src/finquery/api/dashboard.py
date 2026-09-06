"""The dashboard endpoints: the page, and the things that can be done to a card.

The page is one request (`GET /dashboard`): the tiles, and every card with the rows its stored
statement returns right now. Nothing is served from a cache, because a stored figure would be a
number that did not come from an executed query (ADR 0004).

A card arrives in one of two ways: seeded as one of the six defaults on the first visit
(`finquery.dashboard.ensure_defaults`), or kept from a chart in a chat, by the agent itself or
by Add to dashboard. Charts are asked for in words in a chat and nowhere else (ticket 44), so
this module no longer draws one.

`from` and `to` narrow the whole page: they reach the guard's temp view, so the tiles and every
stored statement see those days only, and nothing about them is stored.
"""

import json
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.api.preferences import chart_or_404, turn_or_404
from finquery.api.profiles import get_profile_or_404
from finquery.dashboard import (
    NO_RANGE,
    NothingToUndo,
    Range,
    Tiles,
    bounds,
    cards_of,
    ensure_defaults,
    has_data,
    keep_chat_chart,
    move,
    notes_of,
    read_tiles,
    remove,
    restore_defaults,
    run_card,
    touch,
    undo,
    undo_call_id,
)
from finquery.db import DashboardChart, Import, Transaction
from finquery.preferences import read_turn
from finquery.query.guard import SqlRejected, validate_sql

router = APIRouter()

REVERSED_RANGE = "The range starts after it ends: `from` must be on or before `to`."


def _window(since: date | None, until: date | None) -> Range:
    """The range the page asked for, refused as a whole when it reads backwards."""
    if since is not None and until is not None and since > until:
        raise HTTPException(status_code=422, detail=REVERSED_RANGE)
    return Range(since=since, until=until)


class MonthOut(BaseModel):
    """One month of the tiles' statement, so the page can subtract two of them."""

    month: str
    spent_eur: float
    income_eur: float
    net_eur: float


class TilesOut(BaseModel):
    """The four figures above the charts, what they are compared with, and where the fourth leads."""

    month: str | None
    """The month the three money figures are about: the newest one the profile has bookings in."""
    spent_eur: float
    income_eur: float
    net_eur: float
    needs_review: int
    months: list[MonthOut] = []
    """The last seven months the range holds, oldest first, from the one statement the three
    money figures come from. The page takes the last row as the month, the one before it as last
    month and the mean of the earlier rows as the average: the deltas are arithmetic on rows a
    query returned, never a second figure from somewhere else."""
    review_import_id: str | None = None
    """The newest import that still has bookings without a category, so the tile can open the
    conversation that asks about them. Null when nothing is waiting."""


class ChartCardOut(BaseModel):
    """One card: the stored definition, and the rows this load's query returned for it."""

    id: str
    position: int
    title: str
    shape: str
    language: str
    request: str
    plan: str
    sql: str | None
    code: str | None
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    notes: list[str]
    error: str | None
    """Why this card has no rows: the guard's refusal or SQLite's, in one sentence."""
    created_from: str
    default_key: str | None = None
    """Which shipped default this card is, or null for a card that came from a chat."""
    created_at: datetime
    refreshed_at: datetime | None
    removed_at: datetime | None = None
    """When it was taken off the dashboard, if it was. Only a card asked for by id can say so."""
    undo_call_id: str | None = None
    """The chat tool call whose change one Undo would take back, so the card in that transcript
    knows whether its own button still applies."""


class RangeOut(BaseModel):
    """What the page was narrowed to, and what there is to narrow.

    `since` and `until` are the range that was applied, both null for the whole history.
    `first_day` and `last_day` are the profile's own bookings, which bound the pickers and are
    what "All" means.
    """

    since: date | None
    until: date | None
    first_day: date | None
    last_day: date | None


class DashboardOut(BaseModel):
    has_data: bool
    """False for a profile with no bookings at all, which is what the empty state is about."""
    tiles: TilesOut
    charts: list[ChartCardOut]
    range: RangeOut


class ProfileBody(BaseModel):
    profile_id: str


class PinBody(ProfileBody):
    turn_id: str
    tool_call_id: str


class RangeBody(ProfileBody):
    """A body that may carry the range the page is showing, so a refresh returns those days."""

    since: date | None = None
    until: date | None = None


class UndoBody(ProfileBody):
    call_id: str | None = None
    """Which change is meant: the id of the chat tool call the card in the transcript belongs
    to. A card whose chart has changed again since is told so instead of rolling back the newer
    change."""


class PatchBody(ProfileBody):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    position: int | None = Field(default=None, ge=0)


class PinOut(BaseModel):
    """One chat chart that is on the dashboard: the call it was drawn by, the card it became."""

    call_id: str
    chart_id: str


class PinsOut(BaseModel):
    """The chat charts that are on the dashboard, so their cards can say so after a reload.

    The card id rides along because the chart card in the transcript can take the chart off the
    dashboard again, and after a reload the call id is all it knows about itself.
    """

    charts: list[PinOut]


def _tiles_out(session: Session, profile_id: str, tiles: Tiles) -> TilesOut:
    """The tiles, plus the import whose questions the Needs review tile leads to."""
    waiting = None
    if tiles.needs_review:
        waiting = session.scalars(
            select(Import.id)
            .join(Transaction, Transaction.import_id == Import.id)
            .where(Import.profile_id == profile_id, Transaction.category_id.is_(None))
            .order_by(Import.created_at.desc())
            .limit(1)
        ).first()
    return TilesOut(
        month=tiles.month,
        spent_eur=tiles.spent_eur,
        income_eur=tiles.income_eur,
        net_eur=tiles.net_eur,
        needs_review=tiles.needs_review,
        months=[
            MonthOut(
                month=month.month,
                spent_eur=month.spent_eur,
                income_eur=month.income_eur,
                net_eur=month.net_eur,
            )
            for month in tiles.months
        ],
        review_import_id=waiting,
    )


def _out(session: Session, card: DashboardChart, window: Range = NO_RANGE) -> ChartCardOut:
    """One card with its numbers, freshly queried, over the days the page asked for."""
    result = run_card(session, card, window)
    return ChartCardOut(
        id=card.id,
        position=card.position,
        title=card.title,
        shape=card.shape,
        language=card.language,
        request=card.request,
        plan=card.plan,
        sql=card.sql,
        code=card.code,
        columns=result.columns,
        rows=result.rows,
        row_count=len(result.rows),
        notes=notes_of(card),
        error=result.error,
        created_from=card.created_from,
        default_key=card.default_key,
        created_at=card.created_at,
        refreshed_at=card.refreshed_at,
        removed_at=card.removed_at,
        undo_call_id=undo_call_id(card),
    )


def _card_or_404(
    session: Session, profile_id: str, chart_id: str, *, removed: bool = False
) -> DashboardChart:
    """The card, if it is this profile's. Another profile's card is simply not found.

    A removed card is not on the dashboard, so only the two endpoints a chat card uses (read it,
    undo the change) ask for one with `removed=True`.
    """
    get_profile_or_404(session, profile_id)
    card = session.get(DashboardChart, chart_id)
    if card is None or card.profile_id != profile_id or (card.removed_at is not None and not removed):
        raise HTTPException(status_code=404, detail="That chart is not on this dashboard")
    return card


def _validated_or_422(sql: str) -> str:
    """A statement the guard would refuse is refused before it is ever stored."""
    try:
        return validate_sql(sql)
    except SqlRejected as exc:
        raise HTTPException(status_code=422, detail=f"That chart's query cannot be stored: {exc}") from exc


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(
    request: Request,
    profile_id: str,
    since: date | None = Query(default=None, alias="from"),
    until: date | None = Query(default=None, alias="to"),
) -> DashboardOut:
    """The whole page: the tiles and every card, each with the rows its query returns now.

    `from` and `to` are ISO days. They are parsed before anything else happens, so a word or a
    reversed range is a 422 and never reaches a statement.
    """
    window = _window(since, until)
    with request.app.state.session_factory() as session:
        profile = get_profile_or_404(session, profile_id)
        ensure_defaults(session, profile)
        first_day, last_day = bounds(session, profile_id)
        return DashboardOut(
            has_data=has_data(session, profile_id),
            tiles=_tiles_out(session, profile_id, read_tiles(session, profile_id, window)),
            charts=[_out(session, card, window) for card in cards_of(session, profile_id)],
            range=RangeOut(
                since=window.since, until=window.until, first_day=first_day, last_day=last_day
            ),
        )


class RestoredOut(BaseModel):
    """What "Restore default cards" put back, and the page as it is now."""

    added: list[str]
    """The keys of the defaults that were missing, in the order they were added. Empty when the
    dashboard already had all of them, which is what the page says out loud."""
    charts: list[ChartCardOut]


@router.post("/dashboard/restore-defaults", response_model=RestoredOut)
async def restore_default_charts(
    request: Request,
    body: RangeBody,
) -> RestoredOut:
    """Add the shipped default cards this profile does not have, and nothing else.

    Matched by `default_key`, so a default that was renamed, moved or edited counts as present
    and no card the user made is ever touched. A profile that was seeded before ticket 51 has no
    key on any of its cards, so it gets the six next to the four it already keeps.
    """
    window = _window(body.since, body.until)
    with request.app.state.session_factory() as session:
        profile = get_profile_or_404(session, body.profile_id)
        added = restore_defaults(session, profile)
        return RestoredOut(
            added=added,
            charts=[_out(session, card, window) for card in cards_of(session, body.profile_id)],
        )


@router.get("/dashboard/charts/{chart_id}", response_model=ChartCardOut)
async def get_chart(request: Request, chart_id: str, profile_id: str) -> ChartCardOut:
    """One card by id, removed or not.

    This is what a card in a transcript asks for: it owns no state of its own, so whether its
    Undo still applies is the server's answer (`undo_call_id`), the way a changeset card reads
    its status from the server rather than from the tool output it was drawn from.
    """
    with request.app.state.session_factory() as session:
        return _out(session, _card_or_404(session, profile_id, chart_id, removed=True))


@router.get("/dashboard/pins", response_model=PinsOut)
async def get_pins(request: Request, profile_id: str) -> PinsOut:
    """Which chat charts of this profile are already on the dashboard.

    The transcript asks for this and nothing else, so a chat with charts in it costs one cheap
    query rather than running every card's statement.
    """
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        rows = session.execute(
            select(DashboardChart.source_call_id, DashboardChart.id).where(
                DashboardChart.profile_id == profile_id,
                DashboardChart.source_call_id.is_not(None),
                DashboardChart.removed_at.is_(None),
            )
        ).all()
        return PinsOut(charts=[PinOut(call_id=str(row[0]), chart_id=str(row[1])) for row in rows])


@router.post("/dashboard/charts/from-turn", response_model=ChartCardOut, status_code=201)
async def pin_from_turn(request: Request, body: PinBody) -> ChartCardOut:
    """Put a chart that was drawn in a chat on the dashboard, definition and statement and all.

    A second Add to dashboard on the same card finds the one it already made: the card in the
    transcript says it is on the dashboard, and a page that was open elsewhere cannot make a
    duplicate out of it.
    """
    with request.app.state.session_factory() as session:
        # A dashboard nobody has opened yet gets its four defaults now, so a pinned chart lands
        # after them rather than in front of them.
        ensure_defaults(session, get_profile_or_404(session, body.profile_id))
        turn, _ = turn_or_404(session, body.profile_id, body.turn_id)
        chart = chart_or_404(read_turn(turn), body.tool_call_id)
        if not chart.get("code") or chart.get("error"):
            raise HTTPException(
                status_code=422, detail="That chart was never drawn, so there is nothing to pin."
            )
        _validated_or_422(str(chart.get("sql") or ""))
        card = keep_chat_chart(
            session,
            body.profile_id,
            chart,
            call_id=body.tool_call_id,
            turn_id=body.turn_id,
        )
        return _out(session, card)


@router.patch("/dashboard/charts/{chart_id}", response_model=ChartCardOut)
async def patch_chart(request: Request, chart_id: str, body: PatchBody) -> ChartCardOut:
    """Rename a card, move it, or both."""
    with request.app.state.session_factory() as session:
        card = _card_or_404(session, body.profile_id, chart_id)
        if body.title is not None:
            card.title = body.title.strip()
        session.commit()
        if body.position is not None:
            move(session, card, body.position)
        return _out(session, card)


@router.delete("/dashboard/charts/{chart_id}", status_code=204)
async def delete_chart(request: Request, chart_id: str, profile_id: str) -> Response:
    """Take one card off the dashboard. The chat turn it was drawn in is untouched.

    Removed on the page, so it is not undoable and the row keeps no previous version: the button
    asked for a confirmation first.
    """
    with request.app.state.session_factory() as session:
        remove(session, _card_or_404(session, profile_id, chart_id))
    return Response(status_code=204)


@router.post("/dashboard/charts/{chart_id}/undo", response_model=ChartCardOut)
async def undo_chart(request: Request, chart_id: str, body: UndoBody) -> ChartCardOut:
    """Take back the edit, the rename or the removal a chat applied to this card. Once.

    A second Undo is a 409, which is what the card in the transcript reads to disable its button
    and say Undone.
    """
    with request.app.state.session_factory() as session:
        card = _card_or_404(session, body.profile_id, chart_id, removed=True)
        try:
            undo(session, card, call_id=body.call_id)
        except NothingToUndo as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _out(session, card)


@router.post("/dashboard/charts/{chart_id}/refresh", response_model=ChartCardOut)
async def refresh_chart(request: Request, chart_id: str, body: RangeBody) -> ChartCardOut:
    """Run this card's statement again. Every load does it too; this one says when it happened.

    Over the same days the page is showing, so a refresh cannot quietly answer a wider question
    than the card next to it.
    """
    window = _window(body.since, body.until)
    with request.app.state.session_factory() as session:
        card = _card_or_404(session, body.profile_id, chart_id)
        touch(session, card)
        return _out(session, card, window)
