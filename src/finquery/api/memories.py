"""Memory REST endpoints: what the assistant remembers, and the user's control over it.

Reads take the profile explicitly, the same as conversations and transactions. A wrong memory
is edited or deleted here and is gone from the next turn's prompt.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from finquery.api.profiles import get_profile_or_404
from finquery.db import Memory
from finquery.memory import MemoryKind, MemorySource, clean_text, list_memories

router = APIRouter()


class MemoryOut(BaseModel):
    id: str
    profile_id: str
    text: str
    kind: MemoryKind
    source: MemorySource
    created_from: str | None
    created_at: datetime
    updated_at: datetime


class MemoryPatch(BaseModel):
    text: str | None = None
    kind: MemoryKind | None = None

    @field_validator("text")
    @classmethod
    def _stripped_and_not_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = clean_text(value)
        if not text:
            raise ValueError("A memory needs text")
        return text


def _out(memory: Memory) -> MemoryOut:
    return MemoryOut(
        id=memory.id,
        profile_id=memory.profile_id,
        text=memory.text,
        kind=memory.kind,  # type: ignore[arg-type]
        source=memory.source,  # type: ignore[arg-type]
        created_from=memory.created_from,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )


def get_memory_or_404(session: Session, memory_id: str) -> Memory:
    memory = session.get(Memory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.get("/memories", response_model=list[MemoryOut])
async def get_memories(request: Request, profile_id: str) -> list[MemoryOut]:
    """The profile's memories, newest first."""
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        return [_out(memory) for memory in list_memories(session, profile_id)]


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
async def patch_memory(request: Request, memory_id: str, body: MemoryPatch) -> MemoryOut:
    with request.app.state.session_factory() as session:
        memory = get_memory_or_404(session, memory_id)
        if body.text is not None:
            memory.text = body.text
        if body.kind is not None:
            memory.kind = body.kind
        session.commit()
        return _out(memory)


@router.delete("/memories/{memory_id}", status_code=204)
async def delete_memory(request: Request, memory_id: str) -> Response:
    with request.app.state.session_factory() as session:
        session.delete(get_memory_or_404(session, memory_id))
        session.commit()
    return Response(status_code=204)
