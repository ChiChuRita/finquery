"""Per-profile settings, and the outbound log they govern.

Four settings: `web_lookup_enabled` (off by default), the two preferences onboarding collects
(`answer_language`, which the chat prompt reads, and `default_model_slot`, which a new
conversation starts on) and `onboarding_state` itself. The GET is what the Settings page and
the onboarding flow read, the PATCH writes any subset of them, and `GET /api/outbound-log` is
the record of every request that ever left this machine for that profile, newest first. See
finquery.weblookup and finquery.onboarding.
"""

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel

from finquery.api.profiles import get_profile_or_404
from finquery.db import Profile
from finquery.onboarding import AnswerLanguage, OnboardingState
from finquery.providers import ModelSlot
from finquery.weblookup import recent_log
from finquery.weblookup.store import LOG_PAGE

router = APIRouter()


class SettingsOut(BaseModel):
    profile_id: str
    web_lookup_enabled: bool
    onboarding_state: OnboardingState
    answer_language: AnswerLanguage
    default_model_slot: ModelSlot


class SettingsPatch(BaseModel):
    """Writes carry the profile in the body; nothing is implicitly profile scoped.

    Every field is optional and only what is sent is written, so one PATCH can carry a whole
    onboarding step and a switch on its own stays one field.
    """

    profile_id: str
    web_lookup_enabled: bool | None = None
    onboarding_state: OnboardingState | None = None
    answer_language: AnswerLanguage | None = None
    default_model_slot: ModelSlot | None = None


class OutboundOut(BaseModel):
    id: str
    kind: str
    target: str
    merchant_token: str
    status: str
    created_at: datetime


def _out(profile: Profile) -> SettingsOut:
    return SettingsOut(
        profile_id=profile.id,
        web_lookup_enabled=profile.web_lookup_enabled,
        onboarding_state=profile.onboarding_state,  # type: ignore[arg-type]
        answer_language=profile.answer_language,  # type: ignore[arg-type]
        default_model_slot=profile.default_model_slot,  # type: ignore[arg-type]
    )


@router.get("/settings", response_model=SettingsOut)
async def get_settings(request: Request, profile_id: str) -> SettingsOut:
    with request.app.state.session_factory() as session:
        return _out(get_profile_or_404(session, profile_id))


@router.patch("/settings", response_model=SettingsOut)
async def patch_settings(request: Request, body: SettingsPatch) -> SettingsOut:
    with request.app.state.session_factory() as session:
        profile = get_profile_or_404(session, body.profile_id)
        if body.web_lookup_enabled is not None:
            profile.web_lookup_enabled = body.web_lookup_enabled
        if body.onboarding_state is not None:
            profile.onboarding_state = body.onboarding_state
        if body.answer_language is not None:
            profile.answer_language = body.answer_language
        if body.default_model_slot is not None:
            profile.default_model_slot = body.default_model_slot
        session.commit()
        return _out(profile)


@router.get("/outbound-log", response_model=list[OutboundOut])
async def get_outbound_log(request: Request, profile_id: str, limit: int = LOG_PAGE) -> list[OutboundOut]:
    """Every request that left this machine for this profile, newest first."""
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        return [
            OutboundOut(
                id=entry.id,
                kind=entry.kind,
                target=entry.target,
                merchant_token=entry.merchant_token,
                status=entry.status,
                created_at=entry.created_at,
            )
            for entry in recent_log(session, profile_id, max(1, min(limit, 200)))
        ]
