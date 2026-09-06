"""What a writer agent hands in, and what makes a file of candidates malformed.

Two shapes, one per adapter, both JSONL: one candidate per line, no trailing commas, no array
around them. Nothing here judges a candidate, it only says whether the file can be read at all;
the judging is the execution gate (`gate.py`) and the second Opus pass (`judge_pack.py`).

    uv run python -m training.data.schema validate --task query batch.jsonl
    uv run python -m training.data.schema validate --task chart batch.jsonl
    uv run python -m training.data.schema example --task query

A malformed file is reported line by line and nothing else happens, so a writer agent fixes its
own file before a single database is opened.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Annotated, Any, Iterator, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from finquery.chart.shapes import SHAPE_NAMES

Language = Literal["de", "en"]
Task = Literal["query", "chart"]

KINDS = ("total", "breakdown", "comparison", "trend", "ranking", "entity", "follow-up", "period")
"""What a question asks for. The benchmark's eight kinds, so a set can be read per kind."""

Kind = Literal["total", "breakdown", "comparison", "trend", "ranking", "entity", "follow-up", "period"]
Difficulty = Annotated[int, Field(ge=1, le=3)]
"""1 one filter, 2 two things at once, 3 what the small models get wrong."""


class BatchInvalid(ValueError):
    """A file that cannot be read as candidates. Carries one message per bad line."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        self.path = path
        self.problems = problems
        super().__init__(f"{path}: {len(problems)} problem(s)\n" + "\n".join(problems))


class Expected(BaseModel):
    """The figure the question has, and a second statement that computes it differently.

    `check_sql` is the whole point of the query gate: two statements that agree on a figure were
    written from the same reading of the question, and one statement agreeing with itself is not
    evidence of anything. Write it differently on purpose, from the other end of the question.
    """

    model_config = ConfigDict(extra="forbid")

    figure: float | None = Field(
        default=None,
        description="The figure you expect, in euros, or null when the answer is several rows.",
    )
    check_sql: str = Field(
        min_length=1, description="A different statement over transaction_view computing the same figure."
    )


class QueryCandidate(BaseModel):
    """One question for the query adapter, with the statement that answers it."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9._-]+$")
    household: str = Field(min_length=1)
    language: Language
    kind: Kind
    difficulty: Difficulty
    question: str = Field(min_length=1)
    prefix: list[str] = Field(
        default_factory=list,
        description="The earlier questions of the conversation, for a follow-up. Empty otherwise.",
    )
    sql: str = Field(min_length=1)
    reasoning: str = Field(
        min_length=1,
        description="One short line each for the period, the filters, the sign and the grouping.",
    )
    expected: Expected

    @property
    def task(self) -> Task:
        return "query"


class Plan(BaseModel):
    """The half of the chart plan the code pass reads: the caption, the data question, the columns."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, description="A short caption without a figure in it, in `language`.")
    question: str = Field(min_length=1, description="The data question for the SQL writer, standing on its own.")
    columns: list[str] = Field(min_length=1, description="The columns the query returns, in order, the euros last.")


class ChartCandidate(BaseModel):
    """One chart request for the chart adapter: the plan, the statement and the code."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9._-]+$")
    household: str = Field(min_length=1)
    language: Language
    request: str = Field(min_length=1)
    shape: Literal[SHAPE_NAMES] = Field(description="One of: " + ", ".join(SHAPE_NAMES))  # type: ignore[valid-type]
    difficulty: Difficulty = 2
    plan: Plan
    sql: str = Field(min_length=1)
    code: str = Field(min_length=1, description="The body of a function of `data` returning defineChart(...).")
    reasoning_plan: str = Field(min_length=1, description="The plan pass's own three to five short steps.")
    reasoning_code: str = Field(min_length=1, description="The code pass's own three to five short steps.")

    @property
    def task(self) -> Task:
        return "chart"

    @property
    def kind(self) -> str:
        """A chart is read per shape the way a question is read per kind."""
        return self.shape


Candidate = QueryCandidate | ChartCandidate
MODELS: dict[str, type[BaseModel]] = {"query": QueryCandidate, "chart": ChartCandidate}


def _problem(line_number: int, error: ValidationError) -> list[str]:
    return [
        f"line {line_number}: {'.'.join(str(part) for part in item['loc']) or 'row'}: {item['msg']}"
        for item in error.errors()
    ]


def read_lines(path: Path) -> Iterator[tuple[int, str]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            yield line_number, line


def read_batch(path: Path, task: str) -> list[Any]:
    """Every candidate of one file, or `BatchInvalid` naming every bad line at once."""
    model = MODELS[task]
    problems: list[str] = []
    candidates: list[Any] = []
    seen: dict[str, int] = {}
    for line_number, line in read_lines(path):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append(f"line {line_number}: not JSON: {exc.msg} at column {exc.colno}")
            continue
        if not isinstance(payload, dict):
            problems.append(f"line {line_number}: a candidate is one JSON object, not {type(payload).__name__}")
            continue
        try:
            candidate = model.model_validate(payload)
        except ValidationError as exc:
            problems.extend(_problem(line_number, exc))
            continue
        first = seen.setdefault(candidate.id, line_number)  # type: ignore[attr-defined]
        if first != line_number:
            problems.append(f"line {line_number}: id {candidate.id!r} is already on line {first}")  # type: ignore[attr-defined]
            continue
        candidates.append(candidate)
    if problems:
        raise BatchInvalid(path, problems)
    if not candidates:
        raise BatchInvalid(path, ["the file holds no candidates"])
    return candidates


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Every writer of a JSONL file goes through here, so the files never drift in shape."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=False) + "\n" for row in rows), encoding="utf-8"
    )
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for _number, line in read_lines(path)]


QUERY_EXAMPLE = {
    "id": "q-student-de-001",
    "household": "student",
    "language": "de",
    "kind": "total",
    "difficulty": 2,
    "question": "Wie viel habe ich im Oktober 2025 fuer Lebensmittel ausgegeben?",
    "prefix": [],
    "sql": (
        "SELECT ROUND(-SUM(amount), 2) AS total_eur\nFROM transaction_view\n"
        "WHERE amount < 0 AND category = 'Groceries'\n"
        "  AND booked_on BETWEEN '2025-10-01' AND '2025-10-31'"
    ),
    "reasoning": (
        "period: October 2025, the month the question names; filters: category Groceries, which "
        "is the whole topic and not a list of shops; sign: spending, so amount < 0 reported "
        "positive; grouping: none, one figure."
    ),
    "expected": {
        "figure": None,
        "check_sql": (
            "SELECT ROUND(SUM(-amount), 2) AS total_eur\nFROM transaction_view\n"
            "WHERE booked_on >= '2025-10-01' AND booked_on < '2025-11-01'\n"
            "  AND amount < 0 AND category IS 'Groceries'"
        ),
    },
}

CHART_EXAMPLE = {
    "id": "c-student-en-001",
    "household": "student",
    "language": "en",
    "request": "Show me what I spent per month in 2025.",
    "shape": "line",
    "difficulty": 2,
    "plan": {
        "title": "Spending per month",
        "question": "Total spending per month in 2025, one row per month, columns month and total_eur.",
        "columns": ["month", "total_eur"],
    },
    "sql": (
        "SELECT strftime('%Y-%m', booked_on) AS month, ROUND(-SUM(amount), 2) AS total_eur\n"
        "FROM transaction_view\nWHERE amount < 0\nGROUP BY month\nORDER BY month"
    ),
    "code": "return defineChart({ /* ... */ });",
    "reasoning_plan": (
        "the request is English, so language en\nit compares months, which is a trend\n"
        "a line reads a trend most directly\nthe columns are month and total_eur\n"
        "the period is the whole year"
    ),
    "reasoning_code": (
        "the shape is line, so the mark is lineY over the rows\n"
        "the columns are month and total_eur, and total_eur holds the numbers\n"
        "months on x with monthShort, euros on y"
    ),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read a batch of candidates, or print an example.")
    parser.add_argument("command", choices=("validate", "example"))
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--task", choices=("query", "chart"), required=True)
    args = parser.parse_args(argv)

    if args.command == "example":
        print(json.dumps(QUERY_EXAMPLE if args.task == "query" else CHART_EXAMPLE, ensure_ascii=False, indent=2))
        return 0
    if not args.files:
        print("validate needs at least one file", file=sys.stderr)
        return 2
    failed = False
    for path in args.files:
        try:
            candidates = read_batch(path, args.task)
        except BatchInvalid as exc:
            failed = True
            print(f"{path}: not valid", file=sys.stderr)
            for problem in exc.problems:
                print(f"  {problem}", file=sys.stderr)
            continue
        print(f"{path}: {len(candidates)} candidates, valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
