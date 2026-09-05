"""The two sets on disk, and the stratified sample the validation page reviews.

A datapoint is data, not code: the JSON files beside this package are the source of truth, this
module only reads them, gives them names and keeps the sampling reproducible.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

BENCH = Path(__file__).resolve().parents[1]
SQL_SET = BENCH / "sql-benchmark.json"
CHART_SET = BENCH / "chart-benchmark.json"

SetName = Literal["sql", "chart", "all"]

KINDS = ("total", "breakdown", "comparison", "trend", "ranking", "entity", "follow-up", "period")
"""What a SQL question asks for. One per datapoint, so a run can be read per kind."""

DIFFICULTIES = (1, 2, 3)

NO_ANSWER = "none"
"""`answer` of a datapoint whose honest result is that the data holds nothing.

The query prompt tells the sub-agent to return no rows when no booking carries the name it was
asked about, so a run that returns none of them is right, and so is one that returns a count of
zero. Every other datapoint has to produce the gold figures.
"""


@dataclass(frozen=True)
class Gold:
    """What the reference SQL returned when `build_gold.py` last ran it."""

    columns: list[str]
    rows: list[dict[str, Any]]

    @staticmethod
    def of(payload: dict[str, Any] | None) -> "Gold | None":
        if not payload:
            return None
        return Gold(columns=list(payload["columns"]), rows=list(payload["rows"]))


@dataclass(frozen=True)
class SqlPoint:
    """One question, the reference SQL that answers it, and the rows that SQL returned."""

    id: str
    kind: str
    difficulty: int
    language: str
    question: str
    sql: str
    tags: list[str] = field(default_factory=list)
    prefix: list[str] = field(default_factory=list)
    why: str = ""
    answer: str = ""
    source: str = "hand"
    gold: Gold | None = None

    @property
    def set_name(self) -> str:
        return "sql"


@dataclass(frozen=True)
class ChartPoint:
    """One chart request, the shape it should get, and the rows behind it."""

    id: str
    prompt: str
    language: str
    shape: str
    difficulty: int
    sql: str
    roles: list[str] = field(default_factory=list)
    also: list[str] = field(default_factory=list)
    covers: list[str] = field(default_factory=list)
    why: str = ""
    source: str = "hand"
    gold: Gold | None = None

    @property
    def set_name(self) -> str:
        return "chart"

    @property
    def question(self) -> str:
        return self.prompt

    @property
    def kind(self) -> str:
        """Charts are read per shape the way SQL datapoints are read per kind."""
        return self.shape


Point = SqlPoint | ChartPoint


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload: dict[str, Any]) -> None:
    """Write a set back. Every writer goes through here, so the file's shape never drifts."""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_sql(path: Path = SQL_SET) -> list[SqlPoint]:
    payload = read(path)
    return [
        SqlPoint(
            id=item["id"],
            kind=item["kind"],
            difficulty=int(item["difficulty"]),
            language=item["language"],
            question=item["question"],
            sql=item["sql"],
            tags=list(item.get("tags", [])),
            prefix=list(item.get("prefix", [])),
            why=item.get("why", ""),
            answer=item.get("answer", ""),
            source=item.get("source", "hand"),
            gold=Gold.of(item.get("gold")),
        )
        for item in payload["datapoints"]
    ]


def load_charts(path: Path = CHART_SET) -> list[ChartPoint]:
    payload = read(path)
    return [
        ChartPoint(
            id=item["id"],
            prompt=item["prompt"],
            language=item["language"],
            shape=item["shape"],
            difficulty=int(item.get("difficulty", 2)),
            sql=item["sql"],
            roles=list(item.get("roles", [])),
            also=list(item.get("also", [])),
            covers=list(item.get("covers", [])),
            why=item.get("why", ""),
            source=item.get("source", "hand"),
            gold=Gold.of(item.get("gold")),
        )
        for item in payload["prompts"]
    ]


def load(set_name: SetName) -> list[Point]:
    if set_name == "sql":
        return list(load_sql())
    if set_name == "chart":
        return list(load_charts())
    return [*load_sql(), *load_charts()]


def pick(points: list[Point], *, n: int | None, seed: int) -> list[Point]:
    """The n datapoints a run uses: a shuffle by seed, then the first n, in file order.

    A seeded sample rather than the first n, so a short run is not always the same easy dozen,
    and back in file order so two runs of the same seed read the same way side by side.
    """
    if n is None or n >= len(points):
        return points
    order = {point.id: index for index, point in enumerate(points)}
    shuffled = list(points)
    random.Random(seed).shuffle(shuffled)
    return sorted(shuffled[:n], key=lambda point: order[point.id])


SAMPLE_SQL = 20
SAMPLE_CHART = 10


def review_sample(seed: int, *, sql_count: int = SAMPLE_SQL, chart_count: int = SAMPLE_CHART) -> list[Point]:
    """The datapoints the validation page shows, stratified and stable for a seed.

    Stratified over the two things a reviewer's attention should be spread across: the kind of
    question for the SQL set (so no review is twelve totals) and the shape for the charts. Each
    stratum is shuffled by the seed, then taken round by round until the quota is full, so a
    kind with two datapoints contributes two and the rest of the quota goes to the others.
    """
    return [
        *_stratified(list(load_sql()), key=lambda point: point.kind, count=sql_count, seed=seed),
        *_stratified(list(load_charts()), key=lambda point: point.shape, count=chart_count, seed=seed + 1),
    ]


def _stratified(points: list[Point], *, key, count: int, seed: int) -> list[Point]:  # noqa: ANN001
    order = {point.id: index for index, point in enumerate(points)}
    strata: dict[str, list[Point]] = {}
    for point in points:
        strata.setdefault(str(key(point)), []).append(point)
    rng = random.Random(seed)
    for stratum in strata.values():
        rng.shuffle(stratum)
    taken: list[Point] = []
    names = sorted(strata)
    while len(taken) < count and any(strata[name] for name in names):
        for name in names:
            if strata[name] and len(taken) < count:
                taken.append(strata[name].pop())
    return sorted(taken, key=lambda point: order[point.id])
