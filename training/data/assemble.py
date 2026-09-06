"""Kept rows into training samples, in the exact words production uses.

Every prompt here is built by the production builder, called with the household's own
`QueryContext`: `query_prompt` and `check_prompt` for the query adapter, `plan_prompt` and
`code_prompt` for the chart one. Nothing is reworded, nothing is templated a second time, and
`tests/test_training_data.py` compares the assembled text with the builder's output byte for
byte. A change to a prompt invalidates the set, which is the point.

Each adapter is attached for a whole run and not per call (`bench/finquery_bench/models.py`), so
each adapter is trained on all three prompts it will be attached over (ticket 57, section 1):

| adapter | samples |
| --- | --- |
| query | `write_sql`, `repair` after a refusal or a rewrite, `check_pass` (the judge prompt) |
| chart | `plan`, `code`, `repair` after a failed self-check |

The repair and check samples come from the gate's real drops, paired with the kept row for the
same question: hand in the wrong attempt and the right one for the same question and the gate
drops one, keeps the other, and this pairs them. Their share is capped at the rate the runtime
really fires them, because a model taught to expect a broken previous answer starts fixing
answers that were fine.

    uv run python -m training.data.assemble --query out/query --chart out/chart --out out/samples

The output is TRL's prompt-completion conversational format, one JSONL per adapter, so
`SFTTrainer` masks the loss to the completion by itself.
"""

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from finquery.chart.subagent import CODE_INSTRUCTIONS, PLAN_INSTRUCTIONS, ChartCode, code_prompt, plan_prompt
from finquery.local.gemma import QUOTE, TOOL_CALL_CLOSE, TOOL_CALL_OPEN
from finquery.query.check import CHECK_TOOL, causes, check_prompt
from finquery.query.check import INSTRUCTIONS as CHECK_INSTRUCTIONS
from finquery.query.runner import figures as figure_lines
from finquery.query.subagent import INSTRUCTIONS as QUERY_INSTRUCTIONS
from finquery.query.subagent import QueryContext, Rejection, Revision, query_prompt
from finquery_bench.run import PREFIX_HINT

from training.data import gate as gates
from training.data.households import context_of
from training.data.schema import ChartCandidate, QueryCandidate, read_jsonl, write_jsonl

QUERY = "query"
CHART = "chart"

WRITE_SQL = "write_sql"
REPAIR = "repair"
CHECK_PASS = "check_pass"
PLAN = "plan"
CODE = "code"

REPAIR_SHARE = 0.14
"""Repair samples per kept query row. The runtime fires 1.21 model calls per SQL datapoint
(`bench/README.md`), and ticket 57 puts the band at 12 to 15 percent."""

CHECK_SHARE = 0.17
"""Check-pass samples per kept query row: 150 against 900 in the plan of ticket 57."""

CHART_REPAIR_SHARE = 0.28
"""Repair samples per chart code row. The runtime fires 2.08 calls per chart, and ticket 57
puts the band at 25 to 30 percent."""

REFUSALS = (gates.GUARD_REFUSED, gates.SQL_FAILED)
"""Drops that produce the retry prompt: the guard or SQLite said no."""

REWRITES = (gates.DEGENERATE,)
"""Drops that produce the rewrite prompt: it ran, and it answered nothing."""


@dataclass
class Sample:
    """One training row: the messages the model sees and the one it should answer with."""

    id: str
    adapter: str
    task: str
    household: str
    language: str
    kind: str
    difficulty: int
    system: str
    user: str
    target: str
    source: str = ""
    """The id of the drop this sample was built from, for a repair or a revise verdict."""

    def payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "adapter": self.adapter,
            "task": self.task,
            "household": self.household,
            "language": self.language,
            "kind": self.kind,
            "difficulty": self.difficulty,
            "source": self.source,
            "prompt": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": self.user},
            ],
            "completion": [{"role": "assistant", "content": self.target}],
        }


def tool_call(name: str, arguments: dict[str, Any]) -> str:
    """One forced tool call, written the way Gemma 4 writes one on the wire.

    The local provider parses exactly this (`finquery.local.gemma.parse_tool_call`), so the
    target of a sample is the text the model has to produce, character for character, and not a
    JSON object somebody would have to translate at training time.
    """
    parts = []
    for key, value in arguments.items():
        parts.append(f"{key}:{_wire(value)}")
    return f"{TOOL_CALL_OPEN}call:{name}{{{','.join(parts)}}}{TOOL_CALL_CLOSE}"


def _wire(value: Any) -> str:
    if isinstance(value, str):
        if QUOTE in value:
            raise ValueError(f"a value carries the quote marker {QUOTE!r}, which cannot be written on the wire")
        return f"{QUOTE}{value}{QUOTE}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_wire(item) for item in value) + "]"
    if isinstance(value, bool) or value is None:
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return json.dumps(value)
    raise TypeError(f"a tool call argument may not be a {type(value).__name__}")


def hints_of(prefix: list[str]) -> str | None:
    """What the chat agent hands the sub-agent about the turns before a follow-up.

    The same sentence the benchmark uses, from the benchmark, so a follow-up sample and a
    follow-up datapoint are the same shape of prompt.
    """
    if not prefix:
        return None
    return PREFIX_HINT.format(questions=" ".join(f'"{question}"' for question in prefix))


def _key(household: str, question: str) -> tuple[str, str]:
    return household, " ".join(question.split()).casefold()


@dataclass
class Batch:
    """One task's kept and dropped rows, with the households they need."""

    kept: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    contexts: dict[str, QueryContext] = field(default_factory=dict)

    def context(self, slug: str) -> QueryContext:
        if slug not in self.contexts:
            session_factory, _profile_id, context, _entry = context_of(slug)
            session_factory.kw["bind"].dispose()
            self.contexts[slug] = context
        return self.contexts[slug]


def read_batch(folder: Path) -> Batch:
    kept = read_jsonl(folder / "kept.jsonl") if (folder / "kept.jsonl").exists() else []
    dropped = read_jsonl(folder / "dropped.jsonl") if (folder / "dropped.jsonl").exists() else []
    return Batch(kept=kept, dropped=dropped)


def query_samples(batch: Batch) -> list[Sample]:
    """`write_sql` for every kept question, then the repairs and the check-pass rows."""
    samples: list[Sample] = []
    kept_by_question: dict[tuple[str, str], dict[str, Any]] = {}
    for row in batch.kept:
        candidate = QueryCandidate.model_validate(row["candidate"])
        context = batch.context(candidate.household)
        hints = hints_of(candidate.prefix)
        kept_by_question[_key(candidate.household, candidate.question)] = row
        samples.append(
            Sample(
                id=candidate.id,
                adapter=QUERY,
                task=WRITE_SQL,
                household=candidate.household,
                language=candidate.language,
                kind=candidate.kind,
                difficulty=candidate.difficulty,
                system=QUERY_INSTRUCTIONS,
                user=query_prompt(candidate.question, context, hints=hints),
                target=tool_call("run_sql", {"reasoning": candidate.reasoning, "sql": candidate.sql}),
            )
        )
    samples.extend(_query_repairs(batch, kept_by_question))
    samples.extend(_check_samples(batch, kept_by_question))
    return samples


def _query_repairs(batch: Batch, kept_by_question: dict[tuple[str, str], dict[str, Any]]) -> list[Sample]:
    """A refused or degenerate attempt, then the statement that was kept for the same question."""
    made: list[Sample] = []
    for drop in sorted(batch.dropped, key=lambda row: row["candidate"]["id"]):
        judged = (drop.get("verdict") or {}).get("verdict") == "revise" and bool(drop.get("validated_sql"))
        if drop["reason"] not in (*REFUSALS, *REWRITES) and not judged:
            continue
        wrong = QueryCandidate.model_validate(drop["candidate"])
        right_row = kept_by_question.get(_key(wrong.household, wrong.question))
        if right_row is None:
            continue
        right = QueryCandidate.model_validate(right_row["candidate"])
        context = batch.context(right.household)
        hints = hints_of(right.prefix)
        if drop["reason"] in REFUSALS:
            user = query_prompt(
                right.question,
                context,
                hints=hints,
                rejected=Rejection(sql=wrong.sql, error=drop["detail"], reasoning=wrong.reasoning),
            )
        elif drop["reason"] in REWRITES:
            user = query_prompt(
                right.question,
                context,
                hints=hints,
                revised=Revision(
                    sql=drop["validated_sql"],
                    reason=drop["detail"],
                    advice=causes(context),
                    reasoning=wrong.reasoning,
                ),
            )
        else:
            # A statement that ran and answered a different question is rewritten with the
            # judge's own sentence and its corrected intent, exactly as `run_query` does after
            # a `revise` verdict.
            verdict = drop["verdict"]
            intent = " ".join(str(verdict.get("intent", "")).split())
            user = query_prompt(
                right.question,
                context,
                hints=hints,
                revised=Revision(
                    sql=drop["validated_sql"],
                    reason=" ".join(str(verdict.get("reason", "")).split()) or "the statement does not answer the question that was asked",
                    advice=f"Answer this instead: {intent}" if intent else "",
                    reasoning=wrong.reasoning,
                ),
            )
        made.append(
            Sample(
                id=f"{right.id}--repair-of-{wrong.id}",
                adapter=QUERY,
                task=REPAIR,
                household=right.household,
                language=right.language,
                kind=right.kind,
                difficulty=right.difficulty,
                system=QUERY_INSTRUCTIONS,
                user=user,
                target=tool_call("run_sql", {"reasoning": right.reasoning, "sql": right.sql}),
                source=wrong.id,
            )
        )
    return _capped(made, len(kept_by_question), REPAIR_SHARE)


def _check_samples(batch: Batch, kept_by_question: dict[tuple[str, str], dict[str, Any]]) -> list[Sample]:
    """The judge prompt, answered `ok` on a kept result and `revise` where a judge said so.

    The `ok` rows are free: a kept row is a result that answers its question, which is what the
    check pass exists to say. A `revise` row cannot be written by code, because the verdict
    carries a sentence about what the statement answered instead, so it comes from a judge's
    verdict on a drop (`judge_pack.py` writes it onto the dropped row). Only a drop that ran and
    was not degenerate can produce one: production never shows the judge a degenerate result.
    """
    made: list[Sample] = []
    for row in batch.kept:
        candidate = QueryCandidate.model_validate(row["candidate"])
        context = batch.context(candidate.household)
        made.append(
            Sample(
                id=f"{candidate.id}--check",
                adapter=QUERY,
                task=CHECK_PASS,
                household=candidate.household,
                language=candidate.language,
                kind=candidate.kind,
                difficulty=candidate.difficulty,
                system=CHECK_INSTRUCTIONS,
                user=_check_prompt(candidate, row, context),
                target=tool_call(CHECK_TOOL, {"verdict": "ok", "reason": "", "intent": ""}),
            )
        )
    capped = _capped(made, len(kept_by_question), CHECK_SHARE)
    return [*capped, *_revise_samples(batch)]


def _check_prompt(candidate: QueryCandidate, row: dict[str, Any], context: QueryContext) -> str:
    return check_prompt(
        candidate.question,
        context,
        row["validated_sql"],
        figure_lines(row["columns"], row["rows"]),
        hints=hints_of(candidate.prefix),
        reasoning=candidate.reasoning,
    )


def _revise_samples(batch: Batch) -> list[Sample]:
    """Every drop a judge marked `revise`, as the verdict the check pass should have given."""
    made: list[Sample] = []
    for drop in sorted(batch.dropped, key=lambda row: row["candidate"]["id"]):
        verdict = drop.get("verdict")
        if not verdict or verdict.get("verdict") != "revise" or not drop.get("validated_sql"):
            continue
        if drop["reason"] in REWRITES:
            # Production rewrites a degenerate result in code and never asks the judge, so a
            # judge sample about one would teach a prompt that is never sent.
            continue
        candidate = QueryCandidate.model_validate(drop["candidate"])
        context = batch.context(candidate.household)
        made.append(
            Sample(
                id=f"{candidate.id}--check-revise",
                adapter=QUERY,
                task=CHECK_PASS,
                household=candidate.household,
                language=candidate.language,
                kind=candidate.kind,
                difficulty=candidate.difficulty,
                system=CHECK_INSTRUCTIONS,
                user=_check_prompt(candidate, drop, context),
                target=tool_call(
                    CHECK_TOOL,
                    {
                        "verdict": "revise",
                        "reason": verdict.get("reason", ""),
                        "intent": verdict.get("intent", ""),
                    },
                ),
                source=candidate.id,
            )
        )
    return made


def chart_samples(batch: Batch) -> list[Sample]:
    """`plan` and `code` for every kept chart, then the repairs from the failed attempts."""
    samples: list[Sample] = []
    kept_by_request: dict[tuple[str, str], dict[str, Any]] = {}
    for row in batch.kept:
        candidate = ChartCandidate.model_validate(row["candidate"])
        context = batch.context(candidate.household)
        plan = gates.plan_of(candidate)
        kept_by_request[_key(candidate.household, candidate.request)] = row
        common = {
            "adapter": CHART,
            "household": candidate.household,
            "language": candidate.language,
            "kind": candidate.shape,
            "difficulty": candidate.difficulty,
        }
        samples.append(
            Sample(
                id=f"{candidate.id}--plan",
                task=PLAN,
                system=PLAN_INSTRUCTIONS,
                user=plan_prompt(candidate.request, context),
                target=tool_call(
                    "chart_plan",
                    {
                        "reasoning": candidate.reasoning_plan,
                        "shape": candidate.shape,
                        "language": candidate.language,
                        "title": candidate.plan.title,
                        "question": candidate.plan.question,
                        "columns": list(candidate.plan.columns),
                    },
                ),
                **common,
            )
        )
        samples.append(
            Sample(
                id=f"{candidate.id}--code",
                task=CODE,
                system=CODE_INSTRUCTIONS,
                user=code_prompt(plan, row["columns"], row["rows"]),
                target=tool_call(
                    "chart_code", {"reasoning": candidate.reasoning_code, "code": candidate.code}
                ),
                **common,
            )
        )
    samples.extend(_chart_repairs(batch, kept_by_request))
    return samples


def _chart_repairs(batch: Batch, kept_by_request: dict[tuple[str, str], dict[str, Any]]) -> list[Sample]:
    """A definition the self-check refused, its findings, and the one that passed."""
    made: list[Sample] = []
    for drop in sorted(batch.dropped, key=lambda row: row["candidate"]["id"]):
        if drop["reason"] != gates.SELFCHECK_FAILED or not drop["findings"]:
            continue
        wrong = ChartCandidate.model_validate(drop["candidate"])
        right_row = kept_by_request.get(_key(wrong.household, wrong.request))
        if right_row is None:
            continue
        right = ChartCandidate.model_validate(right_row["candidate"])
        plan = gates.plan_of(right)
        findings = "\n".join(f"- {finding}" for finding in drop["findings"])
        made.append(
            Sample(
                id=f"{right.id}--repair-of-{wrong.id}",
                adapter=CHART,
                task=REPAIR,
                household=right.household,
                language=right.language,
                kind=right.shape,
                difficulty=right.difficulty,
                system=CODE_INSTRUCTIONS,
                user=code_prompt(
                    plan,
                    right_row["columns"],
                    right_row["rows"],
                    previous=ChartCode(reasoning=wrong.reasoning_code, code=wrong.code),
                    findings=findings,
                ),
                target=tool_call("chart_code", {"reasoning": right.reasoning_code, "code": right.code}),
                source=wrong.id,
            )
        )
    return _capped(made, len(kept_by_request), CHART_REPAIR_SHARE)


def _capped(samples: list[Sample], base: int, share: float) -> list[Sample]:
    """At most this share of the kept rows, chosen by id so two runs choose the same ones."""
    ceiling = max(1, round(base * share)) if base else 0
    return sorted(samples, key=lambda sample: sample.id)[:ceiling]


def _table(title: str, counts: Counter) -> list[str]:
    if not counts:
        return []
    total = sum(counts.values())
    lines = [f"| {title} | rows | share |", "| --- | ---: | ---: |"]
    for name, count in sorted(counts.items(), key=lambda item: (-item[1], str(item[0]))):
        lines.append(f"| {name} | {count} | {round(100 * count / total)} % |")
    return [*lines, ""]


def stats(samples: dict[str, list[Sample]]) -> str:
    lines = [
        "# Training samples",
        "",
        "Every prompt below is the production builder's own output, and every target is the "
        "forced tool call written the way Gemma 4 writes one on the wire.",
        "",
        "TRL reads `prompt` and `completion` and masks the loss to the completion by itself. "
        "The other columns are for the report and the split; drop them before training.",
        "",
    ]
    for adapter, rows in samples.items():
        lines += [f"## {adapter}", "", f"{len(rows)} samples.", ""]
        lines += _table("task", Counter(row.task for row in rows))
        lines += _table("household", Counter(row.household for row in rows))
        lines += _table("kind", Counter(row.kind for row in rows))
        lines += _table("language", Counter(row.language for row in rows))
        lines += _table("difficulty", Counter(str(row.difficulty) for row in rows))
        if adapter == QUERY:
            revise = sum(1 for row in rows if row.task == CHECK_PASS and "revise" in row.target)
            if not revise:
                lines += [
                    "> No `revise` verdict is in this set. Every check-pass sample says `ok`, and a "
                    "check pass that has only ever seen `ok` stops sending anything back. The "
                    "judges of ticket 64 write a `revise` verdict onto the drops that ran and "
                    "answered a different question (`judge_pack.py`), and this is assembled again.",
                    "",
                ]
    return "\n".join(lines)


def assemble(query: Path | None, chart: Path | None, out: Path) -> dict[str, list[Sample]]:
    made: dict[str, list[Sample]] = {}
    if query is not None:
        made[QUERY] = query_samples(read_batch(query))
    if chart is not None:
        made[CHART] = chart_samples(read_batch(chart))
    out.mkdir(parents=True, exist_ok=True)
    for adapter, rows in made.items():
        write_jsonl(out / f"{adapter}.jsonl", [row.payload() for row in rows])
    (out / "stats.md").write_text(stats(made), encoding="utf-8")
    return made


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Turn kept rows into training samples.")
    parser.add_argument("--query", type=Path, help="a gate output folder for the query task")
    parser.add_argument("--chart", type=Path, help="a gate output folder for the chart task")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.query is None and args.chart is None:
        print("give --query, --chart, or both", file=sys.stderr)
        return 2
    made = assemble(args.query, args.chart, args.out)
    for adapter, rows in made.items():
        print(f"{adapter}: {len(rows)} samples ({Counter(row.task for row in rows)})")
    print(f"written to {args.out}")
    return 0 if any(made.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
