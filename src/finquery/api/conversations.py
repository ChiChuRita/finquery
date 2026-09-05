"""Conversation REST endpoints. Every conversation belongs to exactly one profile."""

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from finquery.api.profiles import get_profile_or_404
from finquery.context import clean_summary
from finquery.db import Conversation
from finquery.preferences import Kind, Rating, records_of_conversation
from finquery.providers import ModelSlot

router = APIRouter()

TITLE_LENGTH = 200


class ConversationOut(BaseModel):
    id: str
    profile_id: str
    title: str
    model_slot: ModelSlot
    running: bool = False
    """Whether a turn of this conversation is being answered right now.

    A turn outlives the request that started it (ticket 33), so "is this chat busy" is a fact
    about the server rather than about the browser that asked. It is what the spinner on the tab
    and on the sidebar row is drawn from, wherever the user happens to be, and what tells a
    freshly opened chat to reattach to the stream instead of offering an empty composer.
    """
    created_at: datetime
    updated_at: datetime


class TurnRating(BaseModel):
    """One rating this chat collected, so a reloaded transcript shows the thumbs again.

    `target` is the tool call id of the chart it is about, or null for the answer of the turn.
    """

    turn_id: str
    target: str | None
    kind: Kind
    rating: Rating


class ConversationDetail(ConversationOut):
    messages: list[dict[str, Any]]
    interrupted: bool
    summary: str | None
    """The rolling summary standing in for the turns before the divider."""
    summarized_turns: int
    summarized_messages: int
    """How many messages of `messages` the summary replaces, so the transcript knows where the
    divider goes. Zero means nothing has been compressed yet."""
    ratings: list[TurnRating]
    """The thumbs and picks already given in this chat (ticket 15)."""


class ConversationCreate(BaseModel):
    profile_id: str
    model_slot: ModelSlot = "fast"


class ConversationPatch(BaseModel):
    title: str | None = None
    model_slot: ModelSlot | None = None
    summary: str | None = None
    """An edited rolling summary. The next turn sends this text instead of the older turns."""

    @field_validator("summary")
    @classmethod
    def _summary_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        summary = clean_summary(value)
        if summary is None:
            raise ValueError("A summary cannot be empty")
        return summary

    @field_validator("title")
    @classmethod
    def _stripped_and_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = " ".join(value.split())
        if not title:
            raise ValueError("A conversation needs a title")
        return title[:TITLE_LENGTH]


def _out(conversation: Conversation, *, running: bool = False) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        profile_id=conversation.profile_id,
        title=conversation.title,
        model_slot=conversation.model_slot,  # type: ignore[arg-type]
        running=running,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _detail(conversation: Conversation, session: Session, *, running: bool = False) -> ConversationDetail:
    messages: list[dict[str, Any]] = []
    summarized_turns = 0
    summarized_messages = 0
    for turn in conversation.turns:
        turn_messages = json.loads(turn.ui_messages_json)
        messages.extend(turn_messages)
        # Compressed turns stay in the transcript; only the prompt drops them.
        if turn.position <= conversation.summary_through:
            summarized_turns += 1
            summarized_messages += len(turn_messages)
    interrupted = bool(conversation.turns) and conversation.turns[-1].interrupted
    ratings = [
        TurnRating(
            turn_id=record.turn_id,
            target=record.target,
            kind=record.kind,  # type: ignore[arg-type]
            rating=record.rating,  # type: ignore[arg-type]
        )
        for record in records_of_conversation(session, conversation.id)
        if record.turn_id is not None
    ]
    return ConversationDetail(
        **_out(conversation, running=running).model_dump(),
        messages=messages,
        interrupted=interrupted,
        summary=conversation.summary,
        summarized_turns=summarized_turns,
        summarized_messages=summarized_messages,
        ratings=ratings,
    )


def get_conversation_or_404(session: Session, conversation_id: str) -> Conversation:
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(request: Request, profile_id: str) -> list[ConversationOut]:
    """The profile's conversations, most recent activity first."""
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        rows = (
            session.query(Conversation)
            .filter_by(profile_id=profile_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )
        running = request.app.state.running_turns
        return [_out(row, running=row.id in running) for row in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(request: Request, body: ConversationCreate) -> ConversationOut:
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, body.profile_id)
        conversation = Conversation(profile_id=body.profile_id, model_slot=body.model_slot)
        session.add(conversation)
        session.commit()
        return _out(conversation)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(request: Request, conversation_id: str) -> ConversationDetail:
    with request.app.state.session_factory() as session:
        conversation = get_conversation_or_404(session, conversation_id)
        return _detail(conversation, session, running=conversation_id in request.app.state.running_turns)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def patch_conversation(request: Request, conversation_id: str, body: ConversationPatch) -> ConversationOut:
    with request.app.state.session_factory() as session:
        conversation = get_conversation_or_404(session, conversation_id)
        if body.title is not None:
            conversation.title = body.title
        if body.model_slot is not None:
            conversation.model_slot = body.model_slot
        if body.summary is not None:
            conversation.summary = body.summary
        session.commit()
        return _out(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(request: Request, conversation_id: str) -> Response:
    with request.app.state.session_factory() as session:
        session.delete(get_conversation_or_404(session, conversation_id))
        session.commit()
    return Response(status_code=204)
