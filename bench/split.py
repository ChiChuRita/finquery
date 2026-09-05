"""Mark every datapoint of both sets `train` or `heldout`.

    uv run python bench/split.py

Stratified and reproducible: the rule is `finquery_bench.splits`, and running this twice writes
the same files. Run it after `bench/generate.py` has added datapoints, and commit the result.
"""

from finquery_bench.splits import write_splits


def main() -> int:
    for name, held, total in write_splits():
        print(f"{name}: {held} heldout of {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
