"""What happens when a chart that passed every check still fails in the browser.

The self-check judges intent against a QuickJS stub (`finquery.chart.selfcheck`), so a real
TanStack layout can still throw on rows the stub was happy with. The frame reports that error to
the card, and the card reports it here, which does two things the review of 2026-09-04 asked for:

- it **records the failure on the turn**, so the stored chart carries `rendered: false` and the
  reason. A reload shows the same failed card, and nothing can later claim a chart was drawn.
- it runs **one server-side retry** through `run_chart` with the same request. The chart
  sub-agent is not deterministic, so a second definition usually draws; when it does, the retry
  replaces the chart on the turn and the card swaps its content.

One retry per chart, ever: the recorded failure and the `retried` flag on whatever the retry
left behind are what say it has been spent, so a second report only records and returns.
"""

import json
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from finquery.api.preferences import chart_or_404, turn_or_404
from finquery.chart import run_chart
from finquery.db import Turn
from finquery.preferences import CHART_TOOL, read_turn

router = APIRouter()

RENDER_ERROR = "render_error"
"""The field that says the browser refused this chart, and the reason it gave."""

RETRIED = "retried"
"""Set on whatever the retry left on the turn, so this chart is never redrawn twice.

The failure alone cannot carry that: a retry that draws replaces the failed record, and the
chart it put there would otherwise be retried again the next time the browser refused it.
"""


class RenderFailureBody(BaseModel):
    profile_id: str
    turn_id: str
    tool_call_id: str
    message: str


class RenderFailureOut(BaseModel):
    retried: bool
    """True when a second definition was drawn and the card should show it instead."""
    chart: dict[str, Any]
    """What the card renders now: the retry's payload, or the original with the failure on it."""


def _failed_chart(chart: dict[str, Any], message: str) -> dict[str, Any]:
    """The stored chart, with the browser's refusal on it instead of a definition."""
    reason = f"The chart could not be drawn in the browser: {message}"
    return {
        **chart,
        "code": None,
        "rendered": False,
        "error": reason,
        "summary": reason,
        RENDER_ERROR: message,
    }


def _rewrite(payload: str, tool_call_id: str, chart: dict[str, Any], *, ui: bool) -> str:
    """Put one chart output back into a stored message dump, by tool call id.

    Both families carry the same payload under different names: the model messages hold it as a
    `tool-return` part's `content`, the UI messages as a `tool-chart` part's `output`.
    """
    messages = json.loads(payload)
    for message in messages:
        for part in message.get("parts", []):
            if ui:
                if part.get("type") == f"tool-{CHART_TOOL}" and part.get("toolCallId") == tool_call_id:
                    part["output"] = chart
            elif (
                part.get("part_kind") == "tool-return"
                and part.get("tool_name") == CHART_TOOL
                and part.get("tool_call_id") == tool_call_id
            ):
                part["content"] = chart
    return json.dumps(messages)


def record_chart(session: Session, turn: Turn, tool_call_id: str, chart: dict[str, Any]) -> None:
    """Store this chart output on the turn, in both message families."""
    turn.model_messages_json = _rewrite(turn.model_messages_json, tool_call_id, chart, ui=False)
    turn.ui_messages_json = _rewrite(turn.ui_messages_json, tool_call_id, chart, ui=True)
    session.commit()


@router.post("/charts/render-failure", response_model=RenderFailureOut)
async def render_failure(request: Request, body: RenderFailureBody) -> RenderFailureOut:
    """Record a chart the browser could not draw, and draw it once more on the server."""
    state = request.app.state
    with state.session_factory() as session:
        turn, conversation = turn_or_404(session, body.profile_id, body.turn_id)
        content = read_turn(turn)
        chart = chart_or_404(content, body.tool_call_id)
        spent = bool(chart.get(RENDER_ERROR) or chart.get(RETRIED))
        failed = _failed_chart(chart, body.message)
        record_chart(session, turn, body.tool_call_id, failed)
        profile_id = conversation.profile_id
        hints = content.chart_hints.get(body.tool_call_id)
    if spent:
        return RenderFailureOut(retried=False, chart=failed)

    outcome = await run_chart(
        resolve_model=state.resolve_model,
        model_settings=state.subagent_settings,
        session_factory=state.session_factory,
        profile_id=profile_id,
        request=str(chart.get("request") or ""),
        hints=hints,
    )
    if not outcome.rendered:
        return RenderFailureOut(retried=False, chart=failed)
    # The retry is a whole chart of its own, so it replaces the failed one on the turn: a
    # reload and this card then show the same drawing.
    drawn = {**outcome.payload(), RETRIED: True}
    with state.session_factory() as session:
        turn, _ = turn_or_404(session, body.profile_id, body.turn_id)
        record_chart(session, turn, body.tool_call_id, drawn)
    return RenderFailureOut(retried=True, chart=drawn)
