"""Build the smoke run's training file from `samples/smoke-query.json`.

    uv run python smoke_samples.py --out /sc/scratch/rahul.singh/finquery-training/smoke-query.jsonl

Forty rows in the chat format `train.py` reads, each one the prompt the query sub-agent would
really be sent for a benchmark question plus the tool call that answers it. The prompt is built
by the product's own `query_prompt` against the shipped synthetic year, so this file cannot
drift from the app: it is rebuilt before every smoke run rather than committed.

This exists so the training loop can be proven end to end before any real data does. Ticket
62's `training/data/assemble.py` writes the same shape from six households and thousands of
kept rows, and `train.py` cannot tell the two apart.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prompts  # noqa: E402 - it is what puts the product on sys.path

from finquery.query.subagent import load_query_context  # noqa: E402
from finquery_bench.datapoints import SQL_SET, load_sql, read  # noqa: E402
from finquery_bench.dataset import fresh_database  # noqa: E402
from finquery_bench.run import _hints as prefix_hints  # noqa: E402 - the benchmark's own builder

SEED = Path(__file__).resolve().parent / "samples" / "smoke-query.json"


def build(seed_path: Path) -> list[dict]:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    points = {point.id: point for point in load_sql()}
    rows = []
    with fresh_database() as (session_factory, profile_id):
        with session_factory() as session:
            context = load_query_context(
                session, profile_id, today=date.fromisoformat(read(SQL_SET)["today"])
            )
        for sample in seed["samples"]:
            point = points.get(sample["id"])
            if point is None:
                raise SystemExit(f"{sample['id']} is not in the SQL benchmark")
            if point.split != "train":
                raise SystemExit(f"{sample['id']} is held out, so it may not seed a training sample")
            request = prompts.query_request(point.question, context, hints=prefix_hints(point))
            rows.append(
                {
                    "id": point.id,
                    "adapter": seed["adapter"],
                    "messages": request.with_answer({"reasoning": sample["reasoning"], "sql": point.sql}),
                    "tools": request.tools,
                }
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=SEED)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    rows = build(args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(rows)} samples: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
