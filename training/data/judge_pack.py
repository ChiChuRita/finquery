"""What the second Opus pass reads, and what it writes back.

The judge agents never open `kept.jsonl`. They read one compact review file, one row per
candidate with the question, the statement, the rows it returned, the figure and the reasoning
line, and they answer with a verdict file. `apply` is the only thing that moves a row between
kept and dropped, and a `fix` is re-run through the gate before it is believed.

    uv run python -m training.data.judge_pack pack  --task query --batch out/query
    uv run python -m training.data.judge_pack apply --task query --batch out/query --verdicts v.jsonl

A verdict is one JSON object per line:

    {"id": "...", "verdict": "keep"}
    {"id": "...", "verdict": "drop",  "note": "the period is the quarter before, not this one"}
    {"id": "...", "verdict": "fix",   "note": "...", "fix": {"reasoning": "..."}}
    {"id": "...", "verdict": "revise", "reason": "it totals the year, not November",
                  "intent": "the spending of November 2025 only"}

`revise` is for a dropped row that ran and answered a different question: it is the verdict the
production check pass should have given, and `assemble.py` turns it into a check-pass sample and
a rewrite sample. It is the only way those two exist, because no code can write the sentence.

The reasoning line is judged as strictly as the SQL (ticket 57): a right statement with a
hand-wavy reasoning is a `fix` or a `drop`, never a `keep`.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from training.data import gate as gates
from training.data.gate import Dropped, Kept, Result, report, run_gate, write_out
from training.data.schema import ChartCandidate, QueryCandidate, read_jsonl, write_jsonl

REVIEW = "review.jsonl"
VERDICTS = "verdicts.jsonl"
JUDGED = "judged.md"

JUDGE_DROPPED = "judge-dropped"
FIX_FAILED = "fix-did-not-run"
gates.WHY[JUDGE_DROPPED] = "the judge dropped it"
gates.WHY[FIX_FAILED] = "the judge's fix did not survive the gate"

ROWS_SHOWN = 12
"""How many rows a review row carries. A judgement needs the shape of the result, not a dump."""


class Fix(BaseModel):
    """The fields a judge may correct. Anything else is a drop, not a fix."""

    model_config = ConfigDict(extra="forbid")

    question: str | None = None
    reasoning: str | None = None
    sql: str | None = None
    check_sql: str | None = None
    request: str | None = None
    title: str | None = None
    code: str | None = None
    reasoning_plan: str | None = None
    reasoning_code: str | None = None


class Verdict(BaseModel):
    """One judge's answer about one candidate."""

    model_config = ConfigDict(extra="forbid")

    id: str
    verdict: Literal["keep", "drop", "fix", "revise"]
    note: str = ""
    fix: Fix | None = None
    reason: str = Field(default="", description="On revise: one sentence about what it answered instead.")
    intent: str = Field(default="", description="On revise: what to ask instead, in plain words, never SQL.")


def _figure(rows: list[dict[str, Any]]) -> float | None:
    """The one figure a result carries, when it carries exactly one."""
    numbers = [
        value
        for row in rows
        for value in row.values()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return round(float(numbers[0]), 2) if len(numbers) == 1 else None


def _renders(folder: Path) -> dict[str, str]:
    manifest = folder / "manifest.json"
    if not manifest.exists():
        return {}
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    return {row["id"]: row["file"] for row in payload["renders"] if row.get("file") and row["theme"] == "light"}


def review_rows(batch: Path, task: str, *, renders: Path | None = None) -> list[dict[str, Any]]:
    """One row per candidate a judge has to answer about: everything it needs, nothing else."""
    pictures = _renders(renders) if renders else {}
    rows: list[dict[str, Any]] = []
    for source, kept in ((batch / "kept.jsonl", True), (batch / "dropped.jsonl", False)):
        if not source.exists():
            continue
        for item in read_jsonl(source):
            candidate = item["candidate"]
            # A drop the judge can say something useful about: it ran and answered something.
            if not kept and not item.get("validated_sql"):
                continue
            row: dict[str, Any] = {
                "id": candidate["id"],
                "state": "kept" if kept else "dropped",
                "household": candidate["household"],
                "language": candidate["language"],
                "sql": item.get("validated_sql") or candidate["sql"],
                "columns": item.get("columns", []),
                "rows": item.get("rows", [])[:ROWS_SHOWN],
                "row_count": len(item.get("rows", [])),
            }
            if not kept:
                row["dropped_because"] = f"{item['reason']}: {item['why']}"
                row["detail"] = item.get("detail", "")
            if task == "query":
                row.update(
                    {
                        "kind": candidate["kind"],
                        "difficulty": candidate["difficulty"],
                        "question": candidate["question"],
                        "prefix": candidate["prefix"],
                        "reasoning": candidate["reasoning"],
                        "figure": _figure(item.get("rows", [])),
                        "expected_figure": candidate["expected"]["figure"],
                        "check_sql": candidate["expected"]["check_sql"],
                    }
                )
            else:
                row.update(
                    {
                        "shape": candidate["shape"],
                        "difficulty": candidate["difficulty"],
                        "request": candidate["request"],
                        "plan": candidate["plan"],
                        "code": candidate["code"],
                        "reasoning_plan": candidate["reasoning_plan"],
                        "reasoning_code": candidate["reasoning_code"],
                        "fold_note": item.get("fold_note"),
                        "render": pictures.get(candidate["id"]),
                    }
                )
            rows.append(row)
    return rows


def read_verdicts(path: Path) -> list[Verdict]:
    verdicts: list[Verdict] = []
    problems: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            verdicts.append(Verdict.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            problems.append(f"line {number}: {exc}")
    if problems:
        raise ValueError(f"{path}: {len(problems)} bad verdict(s)\n" + "\n".join(problems))
    return verdicts


def _fixed(payload: dict[str, Any], task: str, fix: Fix) -> dict[str, Any]:
    """The candidate with the judge's corrections in it, ready to be gated again."""
    corrected = json.loads(json.dumps(payload))
    for field, value in fix.model_dump(exclude_none=True).items():
        if field == "check_sql":
            corrected["expected"]["check_sql"] = value
        elif field == "title":
            corrected["plan"]["title"] = value
        else:
            corrected[field] = value
    model = QueryCandidate if task == "query" else ChartCandidate
    model.model_validate(corrected)
    return corrected


def apply(batch: Path, task: str, verdicts: list[Verdict]) -> Result:
    """Move rows between kept and dropped as the judge said, re-gating every fix."""
    by_id = {verdict.id: verdict for verdict in verdicts}
    model = QueryCandidate if task == "query" else ChartCandidate
    result = Result()
    to_regate: list[Any] = []
    for item in read_jsonl(batch / "kept.jsonl"):
        candidate = model.model_validate(item["candidate"])
        verdict = by_id.get(candidate.id)
        if verdict is None or verdict.verdict == "keep":
            result.kept.append(_kept(item, candidate))
        elif verdict.verdict == "fix" and verdict.fix is not None:
            to_regate.append(model.model_validate(_fixed(item["candidate"], task, verdict.fix)))
        else:
            result.dropped.append(Dropped(candidate, JUDGE_DROPPED, detail=verdict.note))
    for item in read_jsonl(batch / "dropped.jsonl"):
        candidate = model.model_validate(item["candidate"])
        verdict = by_id.get(candidate.id)
        if verdict is not None and verdict.verdict == "fix" and verdict.fix is not None:
            to_regate.append(model.model_validate(_fixed(item["candidate"], task, verdict.fix)))
            continue
        result.dropped.append(
            Dropped(
                candidate,
                item["reason"],
                detail=item.get("detail", ""),
                findings=item.get("findings", []),
                columns=item.get("columns", []),
                rows=item.get("rows", []),
                validated_sql=item.get("validated_sql", ""),
                verdict=(
                    {"verdict": "revise", "reason": verdict.reason, "intent": verdict.intent}
                    if verdict is not None and verdict.verdict == "revise"
                    else item.get("verdict")
                ),
            )
        )
    if to_regate:
        regated = run_gate(to_regate)
        result.kept.extend(regated.kept)
        for drop in regated.dropped:
            result.dropped.append(Dropped(drop.candidate, FIX_FAILED, detail=gates.WHY[drop.code]))
    return result


def _kept(item: dict[str, Any], candidate: Any) -> Kept:  # noqa: ANN401 - one of the two candidates
    return Kept(
        candidate=candidate,
        columns=item["columns"],
        rows=item["rows"],
        validated_sql=item["validated_sql"],
        check_columns=item.get("check_columns", []),
        check_rows=item.get("check_rows", []),
        fold_note=item.get("fold_note"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The review file for the judges, and their verdicts applied.")
    parser.add_argument("command", choices=("pack", "apply"))
    parser.add_argument("--task", choices=("query", "chart"), required=True)
    parser.add_argument("--batch", type=Path, required=True, help="a gate output folder")
    parser.add_argument("--out", type=Path, default=None, help="where the review file goes")
    parser.add_argument("--renders", type=Path, default=None, help="a renders folder with a manifest")
    parser.add_argument("--verdicts", type=Path, default=None)
    args = parser.parse_args(argv)

    if args.command == "pack":
        rows = review_rows(args.batch, args.task, renders=args.renders)
        target = args.out or args.batch / REVIEW
        write_jsonl(target, rows)
        kept = sum(1 for row in rows if row["state"] == "kept")
        print(f"{len(rows)} rows to review ({kept} kept, {len(rows) - kept} dropped) in {target}")
        return 0

    if args.verdicts is None:
        print("apply needs --verdicts", file=sys.stderr)
        return 2
    verdicts = read_verdicts(args.verdicts)
    result = apply(args.batch, args.task, verdicts)
    write_out(result, args.batch)
    (args.batch / JUDGED).write_text(report(result), encoding="utf-8")
    print(f"{len(verdicts)} verdicts applied: {len(result.kept)} kept, {len(result.dropped)} dropped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
