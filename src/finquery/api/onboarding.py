"""The two conversations onboarding opens, both seeded by the server.

`sample` is the "Load the sample year" button: the shipped synthetic CSV is attached to a new
conversation and imported through `ingest.chat_import`, the same function the `import_file`
tool calls for a file the user drops into the composer. Nothing about the import is new here;
what this endpoint adds is that the file comes from `fixtures/` instead of from a browser.

`welcome` is what Finish opens: one assistant turn, written from what the profile holds and
counted in code, with three suggested questions as the `data-followups` part the transcript
already renders as chips. No model runs for it.

Both seed their turn with `persist_turn`, the same way `imports.review-conversation` does, so a
reload renders exactly what the flow left behind.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart
from pydantic_ai.ui.vercel_ai.request_types import DataUIPart

from finquery.api.attachments import chips
from finquery.api.chat import FOLLOWUPS_PART, persist_turn
from finquery.api.profiles import get_profile_or_404
from finquery.ask_user import ASK_USER
from finquery.attachments import Upload, store
from finquery.db import Conversation, new_id
from finquery.ingest.chat_import import import_attachment
from finquery.onboarding import (
    SAMPLE_CSV,
    SAMPLE_PROMPT,
    SAMPLE_TITLE,
    WELCOME_TITLE,
    welcome_suggestions,
    welcome_text,
)
from finquery.query import load_query_context

router = APIRouter()

IMPORT_TOOL = "import_file"


class OnboardingBody(BaseModel):
    profile_id: str


class SampleOut(BaseModel):
    conversation_id: str
    imported: int
    needs_review: int
    duplicates: int


class WelcomeOut(BaseModel):
    conversation_id: str
    title: str
    suggestions: list[str]


@router.post("/onboarding/sample", response_model=SampleOut, status_code=201)
async def load_sample_year(request: Request, body: OnboardingBody) -> SampleOut:
    """Import the shipped synthetic year into a new conversation, as if it had been dropped in.

    The turn is written rather than streamed, but it is the turn a dropped file produces: the
    user's line, the `import_file` step with the figures the pipeline counted, the summary, and
    the Question card about whatever the import left undecided. Answering that card resumes
    this run through the same deferred `ask_user` path every other card uses.
    """
    state = request.app.state
    if not SAMPLE_CSV.is_file():
        raise HTTPException(status_code=404, detail="The sample year is not shipped with this installation.")
    with state.session_factory() as session:
        profile = get_profile_or_404(session, body.profile_id)
        model_key = state.models.key_of(profile.default_model_key)
        conversation = Conversation(profile_id=profile.id, model_key=model_key, title=SAMPLE_TITLE)
        session.add(conversation)
        session.flush()
        conversation_id = conversation.id
        record = store(
            session,
            profile.id,
            conversation_id,
            0,
            Upload(file_name=SAMPLE_CSV.name, media_type="text/csv", data=SAMPLE_CSV.read_bytes()),
        )
        attachment_chips = chips([record])
        session.commit()

        payload = await import_attachment(
            session,
            profile.id,
            conversation_id,
            file_name=SAMPLE_CSV.name,
            resolve_model=state.models.resolver(model_key),
            model_settings=state.subagent_settings,
        )
        session.commit()

    call_id = new_id()
    parts = [TextPart(content=str(payload.get("summary") or "The sample year is imported."))]
    if card := (payload.get("duplicate_card") or payload.get("card")):
        parts.append(ToolCallPart(tool_name=ASK_USER, args=card))
    persist_turn(
        state.session_factory,
        conversation_id,
        [
            ModelRequest(parts=[UserPromptPart(content=SAMPLE_PROMPT)]),
            ModelResponse(
                parts=[ToolCallPart(tool_name=IMPORT_TOOL, args={"file_name": SAMPLE_CSV.name}, tool_call_id=call_id)]
            ),
            ModelRequest(parts=[ToolReturnPart(tool_name=IMPORT_TOOL, content=payload, tool_call_id=call_id)]),
            ModelResponse(parts=parts),
        ],
        model_key=model_key,
        metadata={"model_key": model_key},
        attachments=attachment_chips,
    )
    return SampleOut(
        conversation_id=conversation_id,
        imported=int(payload.get("imported") or 0),
        needs_review=int((payload.get("categorized") or {}).get("needs_review") or 0),
        duplicates=int(payload.get("duplicates") or 0),
    )


@router.post("/onboarding/welcome", response_model=WelcomeOut, status_code=201)
async def open_welcome(request: Request, body: OnboardingBody) -> WelcomeOut:
    """The chat Finish lands in: one seeded turn saying what this profile holds and what to ask."""
    state = request.app.state
    with state.session_factory() as session:
        profile = get_profile_or_404(session, body.profile_id)
        language = profile.answer_language if profile.answer_language != "follow" else "en"
        model_key = state.models.key_of(profile.default_model_key)
        context = load_query_context(session, profile.id)
        text = welcome_text(
            language,
            profile_name=profile.name,
            transaction_count=context.transaction_count,
            first_booked_on=context.first_booked_on,
            last_booked_on=context.last_booked_on,
            accounts=context.accounts,
        )
        suggestions = welcome_suggestions(
            language, transaction_count=context.transaction_count, last_booked_on=context.last_booked_on
        )
        title = WELCOME_TITLE[language]
        conversation = Conversation(profile_id=profile.id, model_key=model_key, title=title)
        session.add(conversation)
        session.commit()
        conversation_id = conversation.id

    persist_turn(
        state.session_factory,
        conversation_id,
        [ModelResponse(parts=[TextPart(content=text)])],
        model_key=model_key,
        metadata={"model_key": model_key},
        data_parts=[DataUIPart(type=FOLLOWUPS_PART, data={"suggestions": suggestions})],
    )
    return WelcomeOut(conversation_id=conversation_id, title=title, suggestions=suggestions)
