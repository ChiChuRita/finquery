"""Turn the preference records into one DPO dataset per adapter.

Reads the app's own SQLite database and writes JSONL with the three columns TRL's DPOTrainer
reads, `prompt`, `chosen` and `rejected`, one file per fast-slot adapter:

- `chart.jsonl`: the chart sub-agent's code. The prompt is the request, the plan and the SQL the
  code was written against, the two sides are the two chart definitions.
- `query.jsonl`: the query sub-agent's SQL. It comes from an answer A/B where the two runs ran
  different statements for the same question, which is the only place two statements for one
  question exist side by side.

Only records with both sides are exported: a lone thumb is a signal, not a pair. Run it with

    uv run python training/preference/export_pairs.py --db data/finquery.db
"""

import argparse
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finquery.db import PreferenceRecord, make_session_factory
from finquery.preferences import QUERY_TOOL, loaded

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Pair:
    """One training example: what was asked, what the user kept, what they refused."""

    prompt: str
    chosen: str
    rejected: str

    def usable(self) -> bool:
        return bool(self.prompt.strip() and self.chosen.strip() and self.rejected.strip()) and (
            self.chosen.strip() != self.rejected.strip()
        )


def _sides(record: PreferenceRecord) -> tuple[dict[str, Any], dict[str, Any]] | None:
    chosen, rejected = loaded(record.chosen_json), loaded(record.rejected_json)
    if not isinstance(chosen, dict) or not isinstance(rejected, dict):
        return None
    return chosen, rejected


def chart_pairs(records: list[PreferenceRecord]) -> Iterator[Pair]:
    """Two chart definitions for the same rows: the code is the whole output."""
    for record in records:
        if record.kind != "chart":
            continue
        sides = _sides(record)
        if sides is None:
            continue
        chosen, rejected = sides
        yield Pair(
            prompt=record.prompt,
            chosen=str(chosen.get("code") or ""),
            rejected=str(rejected.get("code") or ""),
        )


def _statement(side: dict[str, Any]) -> tuple[str, str]:
    """The question the query sub-agent was given and the statement it wrote, from one side."""
    for call in side.get("tools", []):
        output = call.get("output")
        if call.get("tool") == QUERY_TOOL and isinstance(output, dict) and output.get("sql"):
            return str(output.get("request") or ""), str(output["sql"])
    return "", ""


def query_pairs(records: list[PreferenceRecord]) -> Iterator[Pair]:
    """Two statements for one question, from the two halves of an answer A/B."""
    for record in records:
        if record.kind != "answer":
            continue
        sides = _sides(record)
        if sides is None:
            continue
        chosen, rejected = sides
        request, kept = _statement(chosen)
        _, refused = _statement(rejected)
        yield Pair(prompt=request or record.prompt, chosen=kept, rejected=refused)


def write(path: Path, pairs: Iterator[Pair]) -> int:
    usable = [pair for pair in pairs if pair.usable()]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for pair in usable:
            handle.write(json.dumps(pair.__dict__, ensure_ascii=False) + "\n")
    return len(usable)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/finquery.db"), help="the app's SQLite file")
    parser.add_argument("--out", type=Path, default=HERE / "data", help="folder for the JSONL files")
    parser.add_argument("--profile", default=None, help="only this profile's records")
    arguments = parser.parse_args()

    if not arguments.db.is_file():
        raise SystemExit(f"No database at {arguments.db}. Use --db to point at one.")
    factory = make_session_factory(arguments.db)
    with factory() as session:
        query = session.query(PreferenceRecord).order_by(PreferenceRecord.created_at)
        if arguments.profile:
            query = query.filter_by(profile_id=arguments.profile)
        records = query.all()

    charts = write(arguments.out / "chart.jsonl", chart_pairs(records))
    queries = write(arguments.out / "query.jsonl", query_pairs(records))
    print(f"{len(records)} records read from {arguments.db}")
    print(f"chart: {charts} pairs -> {arguments.out / 'chart.jsonl'}")
    print(f"query: {queries} pairs -> {arguments.out / 'query.jsonl'}")
    if not charts and not queries:
        print("Nothing to train on yet. Rate a few answers and regenerate a chart or two first.")


if __name__ == "__main__":
    main()
