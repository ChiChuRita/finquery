"""Turning a click into training data.

A thumb, a chart pick and an answer A/B all end up as the same row: a prompt, a chosen output,
a rejected output and which of the two the user actually said. That is the shape DPO wants, so
the export in `training/preference/` is a filter over this table rather than a transformation.

What a record is about is a stored turn (`turn_id`) and, for a chart, the tool call inside it
(`target`). Everything the record says about the output is read here from that turn, not sent by
the browser: the answer text, the tool outputs, the chart's plan, SQL and code. Only the second
half of a pair comes from the client, because a regenerated chart and a second answer are never
persisted as a turn.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from sqlalchemy.orm import Session

from finquery.db import PreferenceRecord, Turn

Kind = Literal["answer", "chart"]
Rating = Literal["up", "down", "pick"]

CHART_TOOL = "chart"
QUERY_TOOL = "query"

MUTATING_TOOLS = (
    "propose_changeset",
    "apply_simple_edit",
    "set_rule",
    "ask_user",
    "import_file",
    "add_transaction",
)
"""Tools a rerun must not repeat: they write, or they wait for a human.

A turn that used one of them gets no answer A/B. `query`, `chart` and `lookup_merchant` are
read-only, so a second answer may call them again. `extract_transaction` writes only inert
drafts and its card is an `ask_user` call, which is already in this list.
"""


@dataclass(frozen=True)
class TurnContent:
    """One stored turn, read for what a preference record needs from it."""

    prompt: str
    """The user request the turn answered."""
    text: str
    """The assistant's answer as it was written."""
    tools: list[dict[str, Any]] = field(default_factory=list)
    """Every tool call of the turn as `{"tool": name, "output": result}`, in order."""
    charts: dict[str, dict[str, Any]] = field(default_factory=dict)
    """The `chart` tool outputs of the turn, by tool call id."""
    chart_hints: dict[str, str | None] = field(default_factory=dict)
    """The hints each chart call was made with, so a rerun asks for the same thing."""
    mutating: list[str] = field(default_factory=list)
    """Which writing or deferred tools it used, which is what disables the A/B."""


def turn_messages(turn: Turn) -> list[ModelMessage]:
    return list(ModelMessagesTypeAdapter.validate_json(turn.model_messages_json))


def answer_side(text: str, tools: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """One side of an answer preference: what the user read, and what it was built from."""
    return {"text": text, "tools": list(tools)}


def answer_of(messages: Sequence[ModelMessage]) -> dict[str, Any]:
    """The answer one run produced: its text and its tool results, as a record's side.

    Used for both halves of an answer A/B: the stored turn and the second, hotter run.
    """
    texts: list[str] = []
    tools: list[dict[str, Any]] = []
    for message in messages:
        for part in message.parts:
            if part.part_kind == "text":
                texts.append(part.content)
            elif part.part_kind == "tool-return":
                tools.append({"tool": part.tool_name, "output": part.content})
    return answer_side("\n".join(texts).strip(), tools)


def read_turn(turn: Turn) -> TurnContent:
    """What the turn asked, what it answered and what its tools returned."""
    messages = turn_messages(turn)
    answer = answer_of(messages)
    prompts: list[str] = []
    charts: dict[str, dict[str, Any]] = {}
    hints: dict[str, str | None] = {}
    mutating: list[str] = []
    for message in messages:
        for part in message.parts:
            if part.part_kind == "user-prompt" and isinstance(part.content, str):
                prompts.append(part.content)
            elif part.part_kind == "tool-call" and part.tool_name in MUTATING_TOOLS:
                mutating.append(part.tool_name)
            elif part.part_kind == "tool-call" and part.tool_name == CHART_TOOL:
                arguments = part.args_as_dict()
                hint = arguments.get("hints")
                hints[part.tool_call_id] = hint if isinstance(hint, str) else None
            elif part.part_kind == "tool-return" and part.tool_name == CHART_TOOL:
                if isinstance(part.content, dict):
                    charts[part.tool_call_id] = part.content
    return TurnContent(
        prompt=prompts[0].strip() if prompts else "",
        text=answer["text"],
        tools=answer["tools"],
        charts=charts,
        chart_hints=hints,
        mutating=mutating,
    )


def chart_side(chart: dict[str, Any]) -> dict[str, Any]:
    """One side of a chart preference: the code, plus the SQL both sides of a pair share."""
    return {
        "code": chart.get("code"),
        "shape": chart.get("shape"),
        "title": chart.get("title"),
        "sql": chart.get("sql"),
    }


def chart_prompt(chart: dict[str, Any]) -> str:
    """What the chart sub-agent was working from: the request, its plan and the executed SQL.

    This is the prompt side of the chart adapter's training pair, so it holds everything the
    code was written against and nothing that came out of it.
    """
    lines = [f"Request: {chart.get('request', '')}".strip()]
    if plan := chart.get("plan"):
        lines.append(str(plan))
    if columns := chart.get("columns"):
        lines.append(f"Columns: {', '.join(str(column) for column in columns)}")
    if sql := chart.get("sql"):
        lines.append(f"SQL:\n{sql}")
    return "\n".join(lines)


def store(
    session: Session,
    *,
    profile_id: str,
    conversation_id: str | None,
    turn_id: str,
    target: str | None,
    kind: Kind,
    rating: Rating,
    prompt: str,
    chosen: dict[str, Any] | None,
    rejected: dict[str, Any] | None,
    model_slot: str,
) -> PreferenceRecord:
    """Write the record for one click, replacing the one that click already made.

    Clicking down after up, or picking after a thumb, is the user correcting themselves about
    the same output, so it is one row per (turn, target) rather than a log of clicks.
    """
    record = (
        session.query(PreferenceRecord)
        .filter_by(profile_id=profile_id, turn_id=turn_id, target=target)
        .one_or_none()
    )
    if record is None:
        record = PreferenceRecord(profile_id=profile_id, turn_id=turn_id, target=target)
        session.add(record)
    record.conversation_id = conversation_id
    record.kind = kind
    record.rating = rating
    record.prompt = prompt
    record.chosen_json = json.dumps(chosen) if chosen is not None else None
    record.rejected_json = json.dumps(rejected) if rejected is not None else None
    record.model_slot = model_slot
    session.flush()
    return record


def list_records(session: Session, profile_id: str, limit: int | None = None) -> list[PreferenceRecord]:
    """The profile's records, newest first."""
    query = (
        session.query(PreferenceRecord)
        .filter_by(profile_id=profile_id)
        .order_by(PreferenceRecord.created_at.desc(), PreferenceRecord.id.desc())
    )
    return query.limit(limit).all() if limit else query.all()


def records_of_conversation(session: Session, conversation_id: str) -> list[PreferenceRecord]:
    """What was rated in this chat, so a reload can show the thumbs the user pressed."""
    return (
        session.query(PreferenceRecord)
        .filter_by(conversation_id=conversation_id)
        .order_by(PreferenceRecord.created_at)
        .all()
    )


def loaded(text: str | None) -> dict[str, Any] | None:
    return json.loads(text) if text else None


def export_line(record: PreferenceRecord) -> dict[str, Any]:
    """One line of the JSONL training set: prompt, chosen, rejected, kind."""
    return {
        "kind": record.kind,
        "rating": record.rating,
        "prompt": record.prompt,
        "chosen": loaded(record.chosen_json),
        "rejected": loaded(record.rejected_json),
        "model_slot": record.model_slot,
        "created_at": record.created_at.isoformat(),
    }


def export_jsonl(records: Sequence[PreferenceRecord]) -> str:
    """The whole export as text: one JSON object per line, newest record last."""
    return "".join(f"{json.dumps(export_line(record), ensure_ascii=False)}\n" for record in reversed(records))
