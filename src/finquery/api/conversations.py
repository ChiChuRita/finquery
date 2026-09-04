"""Conversation REST endpoints for the default profile."""

import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from finquery.db import Conversation
from finquery.providers import ModelSlot

router = APIRouter()


class ConversationOut(BaseModel):
    id: str
    title: str
    model_slot: ModelSlot
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[dict[str, Any]]
    interrupted: bool


class ConversationCreate(BaseModel):
    model_slot: ModelSlot = "fast"


class ConversationPatch(BaseModel):
    model_slot: ModelSlot


def _out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
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


def get_conversation_or_404(session, conversation_id: str) -> Conversation:  # noqa: ANN001
    conversation = session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(request: Request) -> list[ConversationOut]:
    with request.app.state.session_factory() as session:
        rows = (
            session.query(Conversation)
            .filter_by(profile_id=request.app.state.profile_id)
            .order_by(Conversation.updated_at.desc())
            .all()
        )
        return [_out(row) for row in rows]


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(request: Request, body: ConversationCreate) -> ConversationOut:
    with request.app.state.session_factory() as session:
        conversation = Conversation(profile_id=request.app.state.profile_id, model_slot=body.model_slot)
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
        conversation.model_slot = body.model_slot
        session.commit()
        return _out(conversation)

