"""Profile REST endpoints. A profile is the isolation boundary, see CONTEXT.md."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from finquery.db import Profile, create_profile
from finquery.providers import ModelResolver

router = APIRouter()


def profile_resolver(state: object, profile_id: str | None = None) -> ModelResolver:
    """The models an endpoint outside a conversation runs on: the profile's default entry.

    An import, an extraction or a mapping proposal has no conversation to take a catalog entry
    from, so it takes the one a new conversation of this profile would start on. Its provider is
    then the provider of the fast slot the sub-agent runs on, which is the same rule a turn
    follows. See finquery.catalog.
    """
    return state.models.resolver(profile_model_key(state, profile_id))  # type: ignore[attr-defined]


def profile_model_key(state: object, profile_id: str | None = None) -> str:
    """The catalog entry a new conversation of this profile starts on."""
    key: str | None = None
    if profile_id is not None:
        with state.session_factory() as session:  # type: ignore[attr-defined]
            profile = session.get(Profile, profile_id)
            key = profile.default_model_key if profile else None
    return state.models.key_of(key)  # type: ignore[attr-defined]


class ProfileOut(BaseModel):
    id: str
    name: str
    created_at: datetime


class ProfileWrite(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _stripped_and_not_empty(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("A profile needs a name")
        if len(name) > 120:
            raise ValueError("A profile name is at most 120 characters")
        return name


def _out(profile: Profile) -> ProfileOut:
    return ProfileOut(id=profile.id, name=profile.name, created_at=profile.created_at)


def get_profile_or_404(session: Session, profile_id: str) -> Profile:
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _reject_duplicate_name(session: Session, name: str, *, allow_id: str | None = None) -> None:
    existing = session.query(Profile).filter(Profile.name == name).one_or_none()
    if existing is not None and existing.id != allow_id:
        raise HTTPException(status_code=409, detail=f"A profile named {name!r} already exists")


@router.get("/profiles", response_model=list[ProfileOut])
async def list_profiles(request: Request) -> list[ProfileOut]:
    with request.app.state.session_factory() as session:
        rows = session.query(Profile).order_by(Profile.created_at, Profile.name).all()
        return [_out(row) for row in rows]


@router.post("/profiles", response_model=ProfileOut, status_code=201)
async def add_profile(request: Request, body: ProfileWrite) -> ProfileOut:
    """A new profile starts with the default category taxonomy already in it."""
    with request.app.state.session_factory() as session:
        _reject_duplicate_name(session, body.name)
        return _out(create_profile(session, body.name))


@router.patch("/profiles/{profile_id}", response_model=ProfileOut)
async def rename_profile(request: Request, profile_id: str, body: ProfileWrite) -> ProfileOut:
    with request.app.state.session_factory() as session:
        profile = get_profile_or_404(session, profile_id)
        _reject_duplicate_name(session, body.name, allow_id=profile.id)
        profile.name = body.name
        session.commit()
        return _out(profile)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(request: Request, profile_id: str) -> Response:
    """Takes the profile's conversations with it. There is always at least one profile left."""
    with request.app.state.session_factory() as session:
        profile = get_profile_or_404(session, profile_id)
        if session.query(Profile).count() == 1:
            raise HTTPException(status_code=409, detail="The last profile cannot be deleted")
        session.delete(profile)
        session.commit()
    return Response(status_code=204)
