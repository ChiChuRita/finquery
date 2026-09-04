"""Preference REST endpoints: the thumbs, the pairs, the two reruns and the export.

Rating is a read of a stored turn plus one row: the browser names the turn and, for a chart,
the tool call inside it, and the server takes the prompt and the output from what it stored, so
a record always says what really happened (`finquery.preferences`).

Two endpoints produce the second half of a pair, and neither one is a chat turn: nothing is
appended to the conversation, no follow-ups run and nothing is remembered.

- `chart-alternative` runs the chart sub-agent again for the same request on the fast slot,
  retrying until the definition differs from the one already on the card.
- `answer-alternative` runs the chat agent again for the same user message at a higher
  temperature, with only the read-only `query` tool. A turn that wrote something (a changeset, a
  rule) or that waited for a Question card is refused: rerunning it would either write twice or
  park forever.
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, model_validator
from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session

from finquery.agent import ChatDeps, chat_agent, query
from finquery.api.chat import load_history
from finquery.api.profiles import get_profile_or_404
from finquery.chart import ChartOutcome, run_chart
from finquery.context import assemble
from finquery.db import Conversation, PreferenceRecord, Turn
from finquery.memory import build_memory_block
from finquery.preferences import (
    Kind,
    Rating,
    TurnContent,
    answer_of,
    answer_side,
    chart_prompt,
    chart_side,
    export_jsonl,
    list_records,
    read_turn,
    store,
)
from finquery.providers import ProviderNotAvailable

router = APIRouter()

AB_TEMPERATURE = 1.2
"""What "a second answer" means: the same prompt, the same history, a hotter model.

The chat agent runs without a temperature otherwise, so this is the only knob the A/B turns.
"""

ALTERNATIVE_ATTEMPTS = 3
"""How many times Regenerate asks for a second chart before it admits it drew the same one."""

EXPORT_FILENAME = "finquery-preferences.jsonl"


class PreferenceOut(BaseModel):
    id: str
    profile_id: str
    conversation_id: str | None
    turn_id: str | None
    target: str | None
    kind: Kind
    rating: Rating
    prompt: str
    paired: bool
    """True when both sides are there, which is what a DPO export can use."""
    model_slot: str
    created_at: datetime


class RatingBody(BaseModel):
    profile_id: str
    turn_id: str
    target: str | None = None
    """The chart's tool call id. Left out, the record is about the answer of the turn."""
    rating: Literal["up", "down"]


class Candidate(BaseModel):
    """The half of a pair that was never a turn: a second answer, or a second chart.

    An answer candidate carries `text` (and the tool results the rerun produced), a chart
    candidate the `code` the sub-agent wrote the second time. The rest of the record, including
    the prompt, is read from the stored turn either way.
    """

    text: str | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    code: str | None = None
    shape: str | None = None
    title: str | None = None
    sql: str | None = None


class PairBody(BaseModel):
    profile_id: str
    turn_id: str
    target: str | None = None
    picked: Literal["original", "candidate"]
    """Which of the two the user pressed Pick on. The other one is the rejected side."""
    candidate: Candidate

    @model_validator(mode="after")
    def _candidate_fits_the_target(self) -> "PairBody":
        if self.target is None and not (self.candidate.text or "").strip():
            raise ValueError("An answer pair needs the text of the second answer")
        if self.target is not None and not (self.candidate.code or "").strip():
            raise ValueError("A chart pair needs the code of the second chart")
        return self


class AlternativeChartBody(BaseModel):
    profile_id: str
    turn_id: str
    tool_call_id: str


class AlternativeAnswerBody(BaseModel):
    profile_id: str
    turn_id: str


class AlternativeAnswerOut(BaseModel):
    text: str
    tools: list[dict[str, Any]]
    model_slot: str
    temperature: float


def _out(record: PreferenceRecord) -> PreferenceOut:
    return PreferenceOut(
        id=record.id,
        profile_id=record.profile_id,
        conversation_id=record.conversation_id,
        turn_id=record.turn_id,
        target=record.target,
        kind=record.kind,  # type: ignore[arg-type]
        rating=record.rating,  # type: ignore[arg-type]
        prompt=record.prompt,
        paired=record.chosen_json is not None and record.rejected_json is not None,
        model_slot=record.model_slot,
        created_at=record.created_at,
    )


def turn_or_404(session: Session, profile_id: str, turn_id: str) -> tuple[Turn, Conversation]:
    """The turn, if it is this profile's. Another profile's turn is simply not found."""
    turn = session.get(Turn, turn_id)
    conversation = session.get(Conversation, turn.conversation_id) if turn else None
    if turn is None or conversation is None or conversation.profile_id != profile_id:
        raise HTTPException(status_code=404, detail="That turn is not in this profile")
    return turn, conversation


def chart_or_404(content: TurnContent, tool_call_id: str) -> dict[str, Any]:
    chart = content.charts.get(tool_call_id)
    if chart is None:
        raise HTTPException(status_code=404, detail="That turn drew no such chart")
    return chart


def _sides(content: TurnContent, target: str | None) -> tuple[Kind, str, dict[str, Any], str | None]:
    """The stored half of a record: its kind, its prompt, its output and the slot behind it.

    The slot is `None` for an answer, meaning the turn's own, and `fast` for a chart, because
    every sub-agent runs there whatever the conversation is set to. It is the slot an adapter
    would be trained for, so it belongs on the record.
    """
    if target is None:
        return "answer", content.prompt, answer_side(content.text, content.tools), None
    chart = chart_or_404(content, target)
    return "chart", chart_prompt(chart), chart_side(chart), "fast"


@router.get("/preferences", response_model=list[PreferenceOut])
async def get_preferences(request: Request, profile_id: str, limit: int | None = None) -> list[PreferenceOut]:
    """Every rating and pick of the profile, newest first."""
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        return [_out(record) for record in list_records(session, profile_id, limit)]


@router.get("/preferences/export", response_class=PlainTextResponse)
async def export_preferences(request: Request, profile_id: str) -> PlainTextResponse:
    """The training set: one JSON object per line with prompt, chosen, rejected and kind."""
    with request.app.state.session_factory() as session:
        get_profile_or_404(session, profile_id)
        body = export_jsonl(list_records(session, profile_id))
    return PlainTextResponse(
        content=body,
        media_type="application/x-ndjson",
        headers={"content-disposition": f'attachment; filename="{EXPORT_FILENAME}"'},
    )


@router.post("/preferences/rating", response_model=PreferenceOut, status_code=201)
async def rate(request: Request, body: RatingBody) -> PreferenceOut:
    """Thumbs up or down on one answer or one chart.

    Up stores the output as the chosen side, down as the rejected one: a thumbs down is not a
    preference for anything, it is a rejection, and only a pair fills both sides.
    """
    with request.app.state.session_factory() as session:
        turn, conversation = turn_or_404(session, body.profile_id, body.turn_id)
        content = read_turn(turn)
        kind, prompt, side, slot = _sides(content, body.target)
        record = store(
            session,
            profile_id=body.profile_id,
            conversation_id=conversation.id,
            turn_id=turn.id,
            target=body.target,
            kind=kind,
            rating=body.rating,
            prompt=prompt,
            chosen=side if body.rating == "up" else None,
            rejected=side if body.rating == "down" else None,
            model_slot=slot or turn.model_slot,
        )
        out = _out(record)
        session.commit()
    return out


@router.post("/preferences/pair", response_model=PreferenceOut, status_code=201)
async def store_pair(request: Request, body: PairBody) -> PreferenceOut:
    """Store the pick of a pair: the stored output against the one that was regenerated."""
    candidate = body.candidate
    with request.app.state.session_factory() as session:
        turn, conversation = turn_or_404(session, body.profile_id, body.turn_id)
        content = read_turn(turn)
        kind, prompt, original, slot = _sides(content, body.target)
        if kind == "chart":
            other = chart_side(
                {
                    "code": candidate.code,
                    "shape": candidate.shape or original["shape"],
                    "title": candidate.title or original["title"],
                    # A pair shares the statement: the two charts drew the same rows.
                    "sql": original["sql"],
                }
            )
        else:
            other = answer_side(candidate.text or "", candidate.tools)
        chosen, rejected = (original, other) if body.picked == "original" else (other, original)
        record = store(
            session,
            profile_id=body.profile_id,
            conversation_id=conversation.id,
            turn_id=turn.id,
            target=body.target,
            kind=kind,
            rating="pick",
            prompt=prompt,
            chosen=chosen,
            rejected=rejected,
            model_slot=slot or turn.model_slot,
        )
        out = _out(record)
        session.commit()
    return out


@router.post("/preferences/chart-alternative")
async def chart_alternative(request: Request, body: AlternativeChartBody) -> dict[str, Any]:
    """Draw the same chart request a second time, so the user can pick the better one.

    The chart sub-agent runs on the fast slot with the sub-agent settings, the same way the
    `chart` tool runs it, up to `ALTERNATIVE_ATTEMPTS` times until the definition differs from
    the one on the turn. Nothing is appended to the conversation: the second chart lives in the
    card until it is picked or the page is left.
    """
    state = request.app.state
    with state.session_factory() as session:
        turn, conversation = turn_or_404(session, body.profile_id, body.turn_id)
        content = read_turn(turn)
        chart = chart_or_404(content, body.tool_call_id)
        profile_id = conversation.profile_id
    async def draw() -> ChartOutcome:
        return await run_chart(
            resolve_model=state.resolve_model,
            model_settings=state.subagent_settings,
            session_factory=state.session_factory,
            profile_id=profile_id,
            request=str(chart.get("request") or ""),
            hints=content.chart_hints.get(body.tool_call_id),
        )

    # The sub-agent is free to write the same definition again, and two identical charts are
    # nothing to pick between. The user pressed Regenerate once, so the further attempts happen
    # here rather than costing them three presses of about 45 seconds each (review of
    # 2026-09-04). A chart that could not be drawn at all is reported, not retried.
    outcome = await draw()
    for _ in range(ALTERNATIVE_ATTEMPTS - 1):
        if not outcome.rendered or outcome.code != chart.get("code"):
            break
        outcome = await draw()
    return outcome.payload()


@router.post("/preferences/answer-alternative", response_model=AlternativeAnswerOut)
async def answer_alternative(request: Request, body: AlternativeAnswerBody) -> AlternativeAnswerOut:
    """Answer the same user message a second time, hotter, for the A/B under a thumbs down.

    The history is the conversation up to that turn, assembled exactly as the turn itself was
    (the rolling summary, the memories, the recent turns), and the agent keeps only its
    read-only `query` tool, so a second answer can look up figures but can change nothing.
    """
    state = request.app.state
    with state.session_factory() as session:
        turn, conversation = turn_or_404(session, body.profile_id, body.turn_id)
        content = read_turn(turn)
        if not content.prompt:
            raise HTTPException(status_code=409, detail="That turn has no user message to answer again")
        if content.mutating:
            raise HTTPException(
                status_code=409,
                detail=f"This turn used {content.mutating[0]}, so it cannot be answered a second time",
            )
        earlier = [t for t in load_history(conversation).turns if t.position < turn.position]
        memory = build_memory_block(session, conversation.profile_id, content.prompt)
        prompt = assemble(earlier, conversation.summary, conversation.summary_through, memory)
        slot = turn.model_slot
        profile_id, conversation_id = conversation.profile_id, conversation.id

    try:
        model = state.resolve_model(slot)
    except ProviderNotAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    deps = ChatDeps(
        session_factory=state.session_factory,
        profile_id=profile_id,
        conversation_id=conversation_id,
        resolve_model=state.resolve_model,
        subagent_settings=state.subagent_settings,
        # Required since ticket 14. The rerun declares only `query`, so nothing here can reach
        # it, but the deps have to be whole.
        web_client=state.web_client,
    )
    # Only the read-only tool: `query` writes nothing, and everything that does is gone for
    # this run, including the Question card (which would park the run waiting for a human).
    with chat_agent.override(tools=[query], toolsets=[]):
        result = await chat_agent.run(
            content.prompt,
            message_history=prompt.history,
            instructions=prompt.instructions,
            model=model,
            deps=deps,
            model_settings=ModelSettings(temperature=AB_TEMPERATURE),
        )
    # Everything after the history and the prompt that was appended to it is the second answer.
    second = answer_of(result.all_messages()[len(prompt.history) + 1 :])
    return AlternativeAnswerOut(
        text=second["text"], tools=second["tools"], model_slot=slot, temperature=AB_TEMPERATURE
    )
