"""Which datapoints are held out of training, and which are examples.

A model fine-tuned on examples drawn from the set it is then scored on is scored on its memory.
So about thirty percent of each set is held out, and the split is written into the files rather
than drawn at run time: a number from the held-out half means the same thing in six months as it
does today.

Stratified over what a score is read per: the kind of question (the shape for charts), whether
the datapoint was written by hand or generated, its language and its difficulty. Inside a
stratum the choice is a hash of the id, so it does not move when a datapoint is added somewhere
else and it does not depend on the order of the file. A stratum of three would round its thirty
percent down to nothing, so the rounding is randomized by a hash of the stratum itself: over the
whole set that lands on thirty percent, and no stratum is systematically whole in the training
half.
"""

import hashlib
from collections.abc import Callable
from typing import Any

from finquery_bench.datapoints import CHART_SET, SQL_SET, read, write

HELDOUT = 0.3
SEED = "finquery-bench-2026-09-05"

TRAIN = "train"
HELD = "heldout"

SETS: tuple[tuple[Any, str, Callable[[dict[str, Any]], tuple]], ...] = (
    (SQL_SET, "datapoints", lambda item: (item["kind"], item.get("source", "hand"), item["language"], item["difficulty"])),
    (CHART_SET, "prompts", lambda item: (item["shape"], item.get("source", "hand"), item["language"], item["difficulty"])),
)


def _rank(key: str) -> str:
    return hashlib.sha256(f"{SEED}:{key}".encode()).hexdigest()


def assign(items: list[dict[str, Any]], stratum: Callable[[dict[str, Any]], Any]) -> dict[str, str]:
    """Map every id to `train` or `heldout`: the first thirty percent of each stratum by hash."""
    strata: dict[str, list[str]] = {}
    for item in items:
        strata.setdefault(str(stratum(item)), []).append(item["id"])
    splits: dict[str, str] = {}
    for name, ids in strata.items():
        ordered = sorted(ids, key=_rank)
        cut = int(HELDOUT * len(ordered) + int(_rank(name)[:8], 16) % 1000 / 1000)
        for index, ident in enumerate(ordered):
            splits[ident] = HELD if index < cut else TRAIN
    return splits


def write_splits() -> list[tuple[str, int, int]]:
    """Write the split of every datapoint of both sets back into the files."""
    written = []
    for path, key, stratum in SETS:
        payload = read(path)
        splits = assign(payload[key], stratum)
        for item in payload[key]:
            item["split"] = splits[item["id"]]
        write(path, payload)
        held = sum(1 for item in payload[key] if item["split"] == HELD)
        written.append((path.name, held, len(payload[key])))
    return written
