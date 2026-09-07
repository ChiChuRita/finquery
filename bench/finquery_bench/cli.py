"""`uv run finquery-bench`: run a set on a model, compare two runs, or cut a review sample.

    uv run finquery-bench --set sql --model google/gemini-3.8-flash
    uv run finquery-bench --set all --model google/gemma-4-26b-a4b-it --n 20 --seed 7
    uv run finquery-bench --set chart --model local:fast --adapter chart
    uv run finquery-bench --set e2e --model local:gemma-4-12b
    uv run finquery-bench --set sql --model google/gemma-4-26b-a4b-it --no-check
    uv run finquery-bench compare bench/results/A.json bench/results/B.json
    uv run finquery-bench compare bench/results/{A,B,C}-sql.json
    uv run finquery-bench sample --seed 7

`run` is the default, so the first line above needs no subcommand.
"""

import argparse
import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from finquery.settings import Settings
from finquery_bench.datapoints import SQL_SET, load, pick, read, review_sample
from finquery_bench.dataset import fresh_database
from finquery_bench.models import resolve_target
from finquery_bench.report import RESULTS, across, compare, save, table
from finquery_bench.report import read as read_run
from finquery_bench.run import Result, run_points

VALIDATE = Path(__file__).resolve().parents[1] / "validate"
DEFAULT_SEED = 7


def _today() -> date:
    """The date the query prompt is built with, so a relative period lands inside the data."""
    return date.fromisoformat(read(SQL_SET)["today"])


def _progress(result: Result) -> None:
    mark = "ok " if result.passed else "MISS"
    print(f"  {mark} {result.id:34s} {result.seconds:6.1f}s {result.error or ''}"[:140], flush=True)


def command_run(args: argparse.Namespace) -> int:
    settings = Settings()
    target = resolve_target(args.model, args.adapter, settings)
    points = pick(load(args.set), n=args.n, seed=args.seed)
    checked = "with the check" if args.check else "without the check"
    print(f"{len(points)} datapoints of the {args.set} set on {target.name}, {checked}", flush=True)
    with fresh_database() as (session_factory, profile_id):
        run = asyncio.run(
            run_points(
                points,
                target=target,
                session_factory=session_factory,
                profile_id=profile_id,
                today=_today(),
                seed=args.seed,
                set_name=args.set,
                check=args.check,
                on_result=_progress,
            )
        )
    payload = run.payload()
    # The two modes write two files: a run is only comparable with one of its own kind.
    as_json, as_markdown = save(payload, target.slug if args.check else f"{target.slug}-nocheck", args.out)
    print()
    print(table(payload))
    print(f"written: {as_json}\n         {as_markdown}")
    return 0


def command_compare(args: argparse.Namespace) -> int:
    payloads = [read_run(path) for path in args.runs]
    sets = {payload["set"] for payload in payloads}
    if len(sets) > 1:
        print(f"these runs are of different sets: {', '.join(sorted(sets))}", file=sys.stderr)
        return 1
    # Two runs is a before and after, so it prints what changed hands. More is a field of
    # candidates, so it prints the table they are chosen from and each one against the first.
    if len(payloads) == 2:
        print(compare(*payloads))
        return 0
    print(across(payloads))
    for payload in payloads[1:]:
        print()
        print(compare(payloads[0], payload))
    return 0


def command_sample(args: argparse.Namespace) -> int:
    """Write the stratified review sample the validation page loads."""
    points = review_sample(args.seed)
    payload = {
        "seed": args.seed,
        "about": (
            "The datapoints to check by hand before the sets are trusted and grown: a stratified "
            "sample chosen by seed, 20 of the SQL set spread over its kinds and 10 of the chart "
            "set spread over its shapes. Rewrite it with `uv run finquery-bench sample --seed N`."
        ),
        "datapoints": [
            {
                "id": point.id,
                "set": point.set_name,
                "kind": point.kind,
                "difficulty": point.difficulty,
                "language": point.language,
                "question": point.question,
                "prefix": list(getattr(point, "prefix", [])),
                "tags": list(getattr(point, "tags", []) or getattr(point, "covers", [])),
                "why": point.why,
                "shape": getattr(point, "shape", None),
                "also": list(getattr(point, "also", [])),
                "roles": list(getattr(point, "roles", [])),
                "answer": getattr(point, "answer", ""),
                "source": point.source,
                "split": point.split,
                "sql": point.sql,
                "gold": {
                    "columns": point.gold.columns if point.gold else [],
                    "rows": point.gold.rows if point.gold else [],
                },
            }
            for point in points
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    kinds = sorted({point.kind for point in points})
    print(f"{len(points)} datapoints over {len(kinds)} kinds and shapes, seed {args.seed}: {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finquery-bench", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    runner = commands.add_parser("run", help="score a model on a set")
    runner.add_argument("--set", default="sql", choices=("sql", "chart", "all", "e2e"))
    runner.add_argument(
        "--model",
        required=True,
        help="a catalog key (local:gemma-4-12b), a role on the current provider (fast, quality), an OpenRouter id, or local:fast",
    )
    runner.add_argument("--adapter", default=None, choices=("query", "chart"), help="a LoRA adapter, local only")
    runner.add_argument(
        "--no-check",
        dest="check",
        action="store_false",
        help="run without the query's check pass and its rewrite (the path before ticket 40)",
    )
    runner.add_argument("--n", type=int, default=None, help="run a sample of this many datapoints")
    runner.add_argument("--seed", type=int, default=DEFAULT_SEED, help="which sample --n takes")
    runner.add_argument("--out", type=Path, default=RESULTS, help="where the result files go")
    runner.set_defaults(run=command_run)

    comparison = commands.add_parser("compare", help="two or more result files side by side")
    comparison.add_argument("runs", type=Path, nargs="+")
    comparison.set_defaults(run=command_compare)

    sample = commands.add_parser("sample", help="write the validation page's review sample")
    sample.add_argument("--seed", type=int, default=DEFAULT_SEED)
    sample.add_argument("--out", type=Path, default=VALIDATE / "sample.json")
    sample.set_defaults(run=command_sample)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `finquery-bench --set sql --model X` means `run`, which is the only command anybody
    # types often enough to want the word gone.
    if argv and argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv.insert(0, "run")
    args = build_parser().parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":
    raise SystemExit(main())
