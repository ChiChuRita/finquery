"""Apply, discard and undo: the deterministic side of a proposal.

The model proposes; these endpoints run. Nothing here calls a model, which is the whole point
of a changeset: what the card previewed is what the code writes.

Profile-scoped like everything else: a read takes `profile_id` as a query parameter, a write
carries it in the body, and a changeset that belongs to another profile is a 404 rather than a
refusal, so a wrong profile cannot even learn that it exists.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from finquery.api.profiles import get_profile_or_404
from finquery.changesets import (
    ChangesetIntent,
    ChangesetOut,
    ChangesetStale,
    apply,
    discard,
    propose,
    refresh,
    to_out,
    undo,
)
from finquery.db import Changeset

router = APIRouter()


class ProposeIn(BaseModel):
    """What the Settings taxonomy editor posts. In chat the same intent arrives as a tool call."""

    profile_id: str
    conversation_id: str | None = None
    intent: ChangesetIntent


class ChangesetAction(BaseModel):
    profile_id: str


def _get(session: Session, profile_id: str, changeset_id: str) -> Changeset:
    row = session.scalars(
        select(Changeset).where(Changeset.profile_id == profile_id, Changeset.id == changeset_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="That changeset is not in this profile.")
    return row


@router.post("/changesets", response_model=ChangesetOut, status_code=201)
async def propose_changeset(request: Request, payload: ProposeIn) -> ChangesetOut:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, payload.profile_id)
        changeset = propose(
            session, payload.profile_id, payload.intent, conversation_id=payload.conversation_id
        )
        out = to_out(changeset)
        session.commit()
        return out


@router.get("/changesets/{changeset_id}", response_model=ChangesetOut)
async def read_changeset(request: Request, changeset_id: str, profile_id: str) -> ChangesetOut:
    """What the card shows after a reload, including a proposal whose rows have since moved."""
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        changeset = refresh(session, profile_id, _get(session, profile_id, changeset_id))
        out = to_out(changeset)
        session.commit()
        return out


@router.post("/changesets/{changeset_id}/apply", response_model=ChangesetOut)
async def apply_changeset(request: Request, changeset_id: str, payload: ChangesetAction) -> ChangesetOut:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, payload.profile_id)
        changeset = _get(session, payload.profile_id, changeset_id)
        try:
            apply(session, payload.profile_id, changeset)
        except ChangesetStale:
            # It really is stale, so that verdict is kept: the card says so after a reload.
            session.commit()
            raise
        out = to_out(changeset)
        session.commit()
        return out


@router.post("/changesets/{changeset_id}/discard", response_model=ChangesetOut)
async def discard_changeset(request: Request, changeset_id: str, payload: ChangesetAction) -> ChangesetOut:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, payload.profile_id)
        changeset = discard(_get(session, payload.profile_id, changeset_id))
        out = to_out(changeset)
        session.commit()
        return out


@router.post("/changesets/{changeset_id}/undo", response_model=ChangesetOut)
async def undo_changeset(request: Request, changeset_id: str, payload: ChangesetAction) -> ChangesetOut:
    """Revert a change that was applied straight away, which is what `apply_simple_edit` does."""
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, payload.profile_id)
        changeset = undo(session, payload.profile_id, _get(session, payload.profile_id, changeset_id))
        out = to_out(changeset)
        session.commit()
        return out
