"""Conversation REST endpoints. Every conversation belongs to exactly one profile."""

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from finquery.api.profiles import get_profile_or_404
from finquery.db import Conversation
from finquery.providers import ModelSlot

router = APIRouter()

TITLE_LENGTH = 200


class ConversationOut(BaseModel):
    id: str
    profile_id: str
    title: str
    model_slot: ModelSlot
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[dict[str, Any]]
    interrupted: bool


class ConversationCreate(BaseModel):
    profile_id: str
    model_slot: ModelSlot = "fast"


class ConversationPatch(BaseModel):
    title: str | None = None
    model_slot: ModelSlot | None = None

    @field_validator("title")
    @classmethod
    def _stripped_and_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = " ".join(value.split())
        if not title:
            raise ValueError("A conversation needs a title")
        return title[:TITLE_LENGTH]


def _out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        profile_id=conversation.profile_id,
        title=conversation.title,
        model_slot=conversation.model_slot,  # type: ignore[arg-type]
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _detail(conversation: Conversation) -> ConversationDetail:
    messages: list[dict[str, Any]] = []
    for turn in conversation.turns:
        messages.extend(json.loads(turn.ui_messages_json))
    interrupted = bool(conversation.turns) and conversation.turns[-1].interrupted
    return ConversationDetail(**_out(conversation).model_dump(), messages=messages, interrupted=interrupted)


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
        return [_out(row) for row in rows]


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
        return _detail(get_conversation_or_404(session, conversation_id))


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def patch_conversation(request: Request, conversation_id: str, body: ConversationPatch) -> ConversationOut:
    with request.app.state.session_factory() as session:
        conversation = get_conversation_or_404(session, conversation_id)
        if body.title is not None:
            conversation.title = body.title
        if body.model_slot is not None:
            conversation.model_slot = body.model_slot
        session.commit()
        return _out(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(request: Request, conversation_id: str) -> Response:
    with request.app.state.session_factory() as session:
        session.delete(get_conversation_or_404(session, conversation_id))
        session.commit()
    return Response(status_code=204)
