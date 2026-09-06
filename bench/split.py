"""Mark every datapoint of both sets `train` or `heldout`.

    uv run python bench/split.py

Stratified and reproducible: the rule is `finquery_bench.splits`, and running this twice writes
the same files. Run it after `bench/generate.py` has added datapoints, and commit the result.

Once `SPLIT_FROZEN.md` is there, this refuses to run without `--force`. Adding a datapoint
re-cuts its stratum, and an existing datapoint can move from `train` to `heldout`; one that
moves after it has seeded a training sample makes the held-out number meaningless (ticket 57,
section 8). After a forced re-cut, freeze it again:

    uv run python -m training.data.audit freeze
"""

import argparse
from pathlib import Path

from finquery_bench.splits import write_splits

FROZEN = Path(__file__).resolve().parent / "SPLIT_FROZEN.md"

REFUSED = f"""\
{FROZEN.name} is here, so the split is frozen and this would move datapoints between the halves.

Read it first. If the sets really have grown and every training row will be generated after
this, run `uv run python bench/split.py --force` and then
`uv run python -m training.data.audit freeze`.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Write the train and heldout split into both sets.")
    parser.add_argument("--force", action="store_true", help="re-cut even though the split is frozen")
    arguments = parser.parse_args()
    if FROZEN.exists() and not arguments.force:
        print(REFUSED)
        return 1
    for name, held, total in write_splits():
        print(f"{name}: {held} heldout of {total}")
    if FROZEN.exists():
        print(f"\n{FROZEN.name} is now stale. Run `uv run python -m training.data.audit freeze`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
