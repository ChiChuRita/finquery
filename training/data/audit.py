"""The three things the benchmark has to be protected from, and one report.

1. **Near-duplicates.** A training question that is a benchmark question with the merchant
   swapped is memorisation dressed as a score. `duplicates` compares every candidate against
   every datapoint of both sets, on character n-grams and on a masked normal form, and says
   which candidate is too close to which case.
2. **A split that moves.** `finquery_bench.splits` re-cuts a stratum when items are added, and
   a datapoint that moves into `heldout` after it seeded a training sample contaminates the
   held-out number (ticket 57, section 8). `freeze` writes the split's hash into
   `bench/SPLIT_FROZEN.md`, and `bench/split.py` refuses to re-cut while that file is there.
3. **A held-out third nobody has looked at.** `heldout` lists every held-out case with its kind,
   its difficulty, its language and whether each model of the cluster runs passed it, which is
   the table the fairness review of ticket 64 reads.

    uv run python -m training.data.audit duplicates --task query out/query/kept.jsonl
    uv run python -m training.data.audit heldout --out bench/heldout-review.md
    uv run python -m training.data.audit freeze
    uv run python -m training.data.audit freeze --check

No model runs here and nothing is written into a benchmark file except `SPLIT_FROZEN.md`.
"""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from finquery.categorize.merchants import DICTIONARY, fold
from finquery_bench.datapoints import CHART_SET, SQL_SET, load_charts, load_sql
from finquery_bench.splits import HELD

from training.data.households import TRUTH_FILE
from training.data.schema import read_jsonl

BENCH = SQL_SET.parent
FROZEN = BENCH / "SPLIT_FROZEN.md"
RESULTS = BENCH / "results"

GRAM = 4
"""The n of the character n-grams. Four holds a word stem together and still slides over a
changed number or a changed name."""

THRESHOLD = 0.6
"""Jaccard over those n-grams, above which two questions are the same question. Measured on the
benchmark against itself: unrelated questions of the same kind sit around 0.2 to 0.35, and the
German and English twins of one datapoint, which are the closest honest pair there is, sit
below this."""


@dataclass(frozen=True)
class Case:
    """One benchmark datapoint, as the audit compares against it."""

    id: str
    set_name: str
    kind: str
    difficulty: int
    language: str
    split: str
    question: str


@dataclass(frozen=True)
class Match:
    """One candidate beside the benchmark case it is closest to."""

    id: str
    question: str
    case: Case
    score: float
    same_normal_form: bool

    @property
    def too_close(self) -> bool:
        return self.same_normal_form or self.score >= THRESHOLD


def cases() -> list[Case]:
    """Every datapoint of both sets, questions and chart requests alike."""
    found = [
        Case(
            id=point.id,
            set_name="sql",
            kind=point.kind,
            difficulty=point.difficulty,
            language=point.language,
            split=point.split,
            question=point.question,
        )
        for point in load_sql()
    ]
    found += [
        Case(
            id=point.id,
            set_name="chart",
            kind=point.shape,
            difficulty=point.difficulty,
            language=point.language,
            split=point.split,
            question=point.prompt,
        )
        for point in load_charts()
    ]
    return found


def vocabulary() -> set[str]:
    """Every merchant word the audit masks, so two questions differing only in a name meet.

    The seed dictionary covers the shipped year's merchants and most of the households'; the
    truth file adds the names those households carry that no dictionary entry knows.
    """
    words = {word for entry in DICTIONARY for word in fold(entry.pattern).split()}
    words |= {word for entry in DICTIONARY for word in fold(entry.title).split()}
    payload = json.loads(TRUTH_FILE.read_text(encoding="utf-8"))
    for household in payload["households"]:
        for merchant in household["merchants"]:
            words |= set(fold(merchant["name"]).split())
    return {word for word in words if len(word) > 2}


def normal_form(text: str, words: set[str]) -> str:
    """The question with its numbers and its merchant names masked out.

    "How much did I spend at REWE in March 2025" and "How much did I spend at ALDI in May 2025"
    are the same question, and one of them being in the benchmark is enough.
    """
    parts = []
    for word in fold(text).split():
        if word.isdigit():
            parts.append("#")
        elif word in words:
            parts.append("@")
        else:
            parts.append(word)
    return " ".join(parts)


def grams(text: str) -> set[str]:
    padded = f" {text} "
    return {padded[index : index + GRAM] for index in range(max(1, len(padded) - GRAM + 1))}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def nearest(questions: list[tuple[str, str]], against: list[Case] | None = None) -> list[Match]:
    """The closest benchmark case to each candidate question, with the score."""
    known = against if against is not None else cases()
    words = vocabulary()
    prepared = [(case, normal_form(case.question, words)) for case in known]
    grammed = [(case, normal, grams(normal)) for case, normal in prepared]
    matches: list[Match] = []
    for ident, question in questions:
        normal = normal_form(question, words)
        mine = grams(normal)
        best: Match | None = None
        for case, case_normal, case_grams in grammed:
            score = jaccard(mine, case_grams)
            same = case_normal == normal
            if best is None or (same, score) > (best.same_normal_form, best.score):
                best = Match(id=ident, question=question, case=case, score=round(score, 3), same_normal_form=same)
        if best is not None:
            matches.append(best)
    return matches


def questions_of(paths: list[Path]) -> list[tuple[str, str]]:
    """Every candidate question in these files, whether they are candidates or gate output."""
    found: list[tuple[str, str]] = []
    for path in paths:
        for row in read_jsonl(path):
            candidate = row.get("candidate", row)
            question = candidate.get("question") or candidate.get("request") or ""
            if question:
                found.append((candidate["id"], question))
    return found


def duplicates_report(matches: list[Match]) -> str:
    flagged = [match for match in matches if match.too_close]
    lines = [
        "# Near-duplicates against the benchmark",
        "",
        f"{len(matches)} candidates compared against {len(cases())} datapoints. "
        f"{len(flagged)} too close.",
        "",
    ]
    if flagged:
        lines += ["| candidate | benchmark case | split | score | same masked form |", "| --- | --- | --- | ---: | --- |"]
        for match in sorted(flagged, key=lambda item: -item.score):
            lines.append(
                f"| `{match.id}` | `{match.case.id}` | {match.case.split} | {match.score} | "
                f"{'yes' if match.same_normal_form else 'no'} |"
            )
        lines += ["", "Rewrite these, or drop them. A benchmark question in the training set is not a score.", ""]
    ranked = sorted(matches, key=lambda item: -item.score)[:5]
    lines += ["The five closest of all, flagged or not:", ""]
    for match in ranked:
        lines.append(f"- `{match.id}` {match.score} against `{match.case.id}` ({match.case.split})")
    lines.append("")
    return "\n".join(lines)


def _results() -> dict[str, dict[str, bool]]:
    """Every model's pass or fail per datapoint, newest run per model and set."""
    newest: dict[tuple[str, str], tuple[str, Path]] = {}
    for path in sorted(RESULTS.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "results" not in payload or "model" not in payload:
            continue
        key = (payload["model"], payload.get("set", "?"))
        stamp = payload.get("started_at", "")
        if key not in newest or stamp > newest[key][0]:
            newest[key] = (stamp, path)
    passed: dict[str, dict[str, bool]] = defaultdict(dict)
    for (model, _set_name), (_stamp, path) in newest.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        for result in payload["results"]:
            passed[model][result["id"]] = bool(result.get("figure_match")) and result.get("shape_match") is not False
    return dict(passed)


def heldout_report() -> str:
    """Every held-out case with what the models did to it, for the fairness review."""
    passed = _results()
    models = sorted(passed)
    held = [case for case in cases() if case.split == HELD]
    lines = [
        "# The held-out cases, and how the candidates did on them",
        "",
        f"{len(held)} held-out datapoints of {len(cases())}. A model column is the newest run of "
        f"that model in `bench/results/`, `pass`, `miss` or an empty cell when that run did not "
        f"cover the datapoint.",
        "",
        "| id | set | kind | difficulty | language | " + " | ".join(models) + " |",
        "| --- | --- | --- | ---: | --- | " + " | ".join("---" for _ in models) + " |",
    ]
    for case in held:
        cells = []
        for model in models:
            answer = passed[model].get(case.id)
            cells.append("" if answer is None else ("pass" if answer else "miss"))
        lines.append(
            f"| `{case.id}` | {case.set_name} | {case.kind} | {case.difficulty} | {case.language} | "
            + " | ".join(cells)
            + " |"
        )
    lines.append("")
    for model in models:
        seen = [case for case in held if case.id in passed[model]]
        if not seen:
            continue
        misses = [case for case in seen if not passed[model][case.id]]
        lines.append(
            f"- {model}: {len(seen) - len(misses)} of {len(seen)} held-out cases, "
            f"{len(misses)} missed"
        )
    lines.append("")
    return "\n".join(lines)


def split_hash() -> str:
    """A hash of which datapoint is in which half. It changes if and only if the split moves."""
    digest = hashlib.sha256()
    for case in sorted(cases(), key=lambda item: (item.set_name, item.id)):
        digest.update(f"{case.set_name}:{case.id}:{case.split}\n".encode())
    return digest.hexdigest()


FREEZE_TEXT = """\
# The split is frozen

Frozen on {day}, hash `{hash}`.

{sql} questions and {chart} chart requests, {held} of them held out. This file is what
`bench/split.py` refuses to run against: the split is a hash of the id inside a stratum, so
adding a datapoint re-cuts that stratum and can move an existing one from `train` to `heldout`
(ticket 57, section 8). A datapoint that moves after it has seeded a training sample or a worked
example makes the held-out number meaningless.

So, in this order and not another:

1. append every judged surplus datapoint to the sets;
2. `uv run python bench/build_gold.py`;
3. `uv run python bench/split.py --force`;
4. `uv run python -m training.data.audit freeze`;
5. only then generate training data.

`uv run python -m training.data.audit freeze --check` says whether the split still hashes to the
line above. It is what a training run should assert before it writes a single row.
"""


def freeze(*, check: bool = False) -> tuple[bool, str]:
    """Write the freeze file, or say whether the split still matches the one on disk."""
    current = split_hash()
    if check:
        if not FROZEN.exists():
            return False, f"{FROZEN.name} does not exist: the split has never been frozen."
        frozen = FROZEN.read_text(encoding="utf-8")
        if f"`{current}`" in frozen:
            return True, f"the split still hashes to {current}"
        return False, (
            f"the split has moved: it now hashes to {current}, which is not what {FROZEN.name} "
            f"records. Every held-out number taken since the freeze is suspect."
        )
    held = sum(1 for case in cases() if case.split == HELD)
    FROZEN.write_text(
        FREEZE_TEXT.format(
            day=date.today().isoformat(),
            hash=current,
            sql=len(load_sql()),
            chart=len(load_charts()),
            held=held,
        ),
        encoding="utf-8",
    )
    return True, f"{FROZEN} written, hash {current}"


def main(argv: list[str] | None = None) -> int:  # noqa: C901 - one branch per command
    parser = argparse.ArgumentParser(description="Keep the benchmark honest while the training set grows.")
    parser.add_argument("command", choices=("duplicates", "heldout", "freeze"))
    parser.add_argument("files", nargs="*", type=Path, help="candidate or gate files, for duplicates")
    parser.add_argument("--task", choices=("query", "chart"), default="query")
    parser.add_argument("--out", type=Path, default=None, help="write the report here as well")
    parser.add_argument("--check", action="store_true", help="freeze: verify instead of writing")
    args = parser.parse_args(argv)

    if args.command == "freeze":
        ok, message = freeze(check=args.check)
        print(message, file=sys.stdout if ok else sys.stderr)
        return 0 if ok else 1

    if args.command == "heldout":
        report = heldout_report()
        if args.out:
            args.out.write_text(report, encoding="utf-8")
            print(f"written to {args.out}")
        else:
            print(report)
        return 0

    if not args.files:
        print("duplicates needs at least one file", file=sys.stderr)
        return 2
    matches = nearest(questions_of(args.files))
    report = duplicates_report(matches)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    flagged = [match for match in matches if match.too_close]
    print(f"{len(matches)} compared, {len(flagged)} too close to a benchmark case")
    for match in flagged:
        print(f"  {match.id} is {match.score} against {match.case.id} ({match.case.split})", file=sys.stderr)
    return 1 if flagged else 0


if __name__ == "__main__":
    raise SystemExit(main())
