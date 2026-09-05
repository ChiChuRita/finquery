"""The dashboard endpoints: the page, and the four things that can be done to a card.

The page is one request (`GET /dashboard`): the tiles, and every card with the rows its stored
statement returns right now. Nothing is served from a cache, because a stored figure would be a
number that did not come from an executed query (ADR 0004).

A card arrives in one of three ways: seeded as one of the four defaults on the first visit
(`finquery.dashboard.ensure_defaults`), pinned from a chart in a chat, or asked for here in
words, which runs the chart sub-agent through the same `run_chart` the chat tool calls. The last
one is shown first and stored only if the user keeps it, so the preview endpoint writes nothing.
"""

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.api.preferences import chart_or_404, turn_or_404
from finquery.api.profiles import get_profile_or_404
from finquery.chart import run_chart
from finquery.chart.shapes import SHAPE_NAMES
from finquery.dashboard import (
    Tiles,
    append,
    cards_of,
    ensure_defaults,
    has_data,
    move,
    notes_of,
    read_tiles,
    renumber,
    run_card,
    touch,
)
from finquery.db import DashboardChart, Import, Transaction
from finquery.preferences import read_turn
from finquery.query.guard import SqlRejected, validate_sql

router = APIRouter()


class TilesOut(BaseModel):
    """The four figures above the charts, and where the fourth one leads."""

    month: str | None
    """The month the three money figures are about: the newest one the profile has bookings in."""
    spent_eur: float
    income_eur: float
    net_eur: float
    needs_review: int
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
    created_at: datetime
    refreshed_at: datetime | None


class DashboardOut(BaseModel):
    has_data: bool
    """False for a profile with no bookings at all, which is what the empty state is about."""
    tiles: TilesOut
    charts: list[ChartCardOut]


class ProfileBody(BaseModel):
    profile_id: str


class PinBody(ProfileBody):
    turn_id: str
    tool_call_id: str


class RequestBody(ProfileBody):
    request: str = Field(min_length=1, max_length=500)


class ChartIn(BaseModel):
    """A chart the dashboard just drew, handed back to be kept.

    It is the payload of `run_chart` and nothing else is trusted about it: the statement is
    validated here and again on every load, and it can only ever read the profile it is stored
    under, because that is what the executing connection's view is filtered to.
    """

    title: str = Field(min_length=1, max_length=200)
    shape: str
    language: str = "en"
    request: str = ""
    plan: str = ""
    sql: str
    code: str
    notes: list[str] = Field(default_factory=list)


class KeepBody(ProfileBody):
    chart: ChartIn


class PatchBody(ProfileBody):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    position: int | None = Field(default=None, ge=0)


class PinsOut(BaseModel):
    """The chat charts that are on the dashboard, so their cards can say so after a reload."""

    call_ids: list[str]


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
        review_import_id=waiting,
    )


def _out(session: Session, card: DashboardChart) -> ChartCardOut:
    """One card with its numbers, freshly queried."""
    result = run_card(session, card)
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
        created_at=card.created_at,
        refreshed_at=card.refreshed_at,
    )


def _card_or_404(session: Session, profile_id: str, chart_id: str) -> DashboardChart:
    """The card, if it is this profile's. Another profile's card is simply not found."""
    get_profile_or_404(session, profile_id)
    card = session.get(DashboardChart, chart_id)
    if card is None or card.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="That chart is not on this dashboard")
    return card


def _validated_or_422(sql: str) -> str:
    """A statement the guard would refuse is refused before it is ever stored."""
    try:
        return validate_sql(sql)
    except SqlRejected as exc:
        raise HTTPException(status_code=422, detail=f"That chart's query cannot be stored: {exc}") from exc


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(request: Request, profile_id: str) -> DashboardOut:
    """The whole page: the tiles and every card, each with the rows its query returns now."""
    with request.app.state.session_factory() as session:
        profile = get_profile_or_404(session, profile_id)
        ensure_defaults(session, profile)
        return DashboardOut(
            has_data=has_data(session, profile_id),
            tiles=_tiles_out(session, profile_id, read_tiles(session, profile_id)),
            charts=[_out(session, card) for card in cards_of(session, profile_id)],
        )


@router.get("/dashboard/pins", response_model=PinsOut)
async def get_pins(request: Request, profile_id: str) -> PinsOut:
    """Which chat charts of this profile are already on the dashboard.

    The transcript asks for this and nothing else, so a chat with charts in it costs one cheap
    query rather than running every card's statement.
    """
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        ids = session.scalars(
            select(DashboardChart.source_call_id).where(
                DashboardChart.profile_id == profile_id, DashboardChart.source_call_id.is_not(None)
            )
        ).all()
        return PinsOut(call_ids=[str(call_id) for call_id in ids])


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
        existing = session.scalars(
            select(DashboardChart).where(
                DashboardChart.profile_id == body.profile_id,
                DashboardChart.source_turn_id == body.turn_id,
                DashboardChart.source_call_id == body.tool_call_id,
            )
        ).first()
        if existing is not None:
            return _out(session, existing)
        card = append(
            session,
            body.profile_id,
            title=str(chart.get("title") or chart.get("request") or "Chart"),
            shape=str(chart.get("shape") or "bar"),
            language=str(chart.get("language") or "en"),
            request=str(chart.get("request") or ""),
            plan=str(chart.get("plan") or ""),
            sql=_validated_or_422(str(chart.get("sql") or "")),
            code=str(chart["code"]),
            notes_json=json.dumps(list(chart.get("notes") or [])),
            created_from="chat",
            source_turn_id=body.turn_id,
            source_call_id=body.tool_call_id,
        )
        return _out(session, card)


@router.post("/dashboard/charts/preview")
async def preview_chart(request: Request, body: RequestBody) -> dict[str, Any]:
    """Draw a chart from a line of words, and store nothing.

    The same `run_chart` the chat tool calls, on the fast slot: the plan, the query behind it,
    the definition and up to two repair rounds. The card that comes back has Keep and Discard
    under it, and Keep is what stores it.
    """
    state = request.app.state
    with state.session_factory() as session:
        get_profile_or_404(session, body.profile_id)
    outcome = await run_chart(
        resolve_model=state.resolve_model,
        model_settings=state.subagent_settings,
        session_factory=state.session_factory,
        profile_id=body.profile_id,
        request=body.request.strip(),
    )
    return outcome.payload()


@router.post("/dashboard/charts", response_model=ChartCardOut, status_code=201)
async def keep_chart(request: Request, body: KeepBody) -> ChartCardOut:
    """Keep the chart the preview drew."""
    if body.chart.shape not in SHAPE_NAMES:
        raise HTTPException(status_code=422, detail=f"{body.chart.shape} is not a chart shape.")
    with request.app.state.session_factory() as session:
        ensure_defaults(session, get_profile_or_404(session, body.profile_id))
        card = append(
            session,
            body.profile_id,
            title=body.chart.title,
            shape=body.chart.shape,
            language=body.chart.language,
            request=body.chart.request,
            plan=body.chart.plan,
            sql=_validated_or_422(body.chart.sql),
            code=body.chart.code,
            notes_json=json.dumps(body.chart.notes),
            created_from="dashboard",
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
    """Take one card off the dashboard. The chat turn it was pinned from is untouched."""
    with request.app.state.session_factory() as session:
        card = _card_or_404(session, profile_id, chart_id)
        session.delete(card)
        session.commit()
        renumber(session, profile_id)
    return Response(status_code=204)


@router.post("/dashboard/charts/{chart_id}/refresh", response_model=ChartCardOut)
async def refresh_chart(request: Request, chart_id: str, body: ProfileBody) -> ChartCardOut:
    """Run this card's statement again. Every load does it too; this one says when it happened."""
    with request.app.state.session_factory() as session:
        card = _card_or_404(session, body.profile_id, chart_id)
        touch(session, card)
        return _out(session, card)
