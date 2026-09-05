"""Recompute the expected rows of both benchmark sets.

    uv run python bench/build_gold.py

Every reference SQL goes through the same guard the app uses, against a fresh database holding
the shipped synthetic year, and the rows it returns are written back into the JSON. A statement
the guard refuses, a statement SQLite cannot run and a statement that answers nothing all stop
the build with the datapoint's id, because a gold row nobody can reproduce is worse than none.

Run it after editing a question's SQL, and after `bench/generate.py` adds datapoints.
"""

import sys

from finquery_bench.gold import GoldFailed, build


def main() -> int:
    try:
        built = build()
    except GoldFailed as exc:
        print(f"gold build failed: {exc}", file=sys.stderr)
        return 1
    for one in built:
        print(f"{one.path.name}: {one.datapoints} datapoints, {one.rows} expected rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
