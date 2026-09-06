"""A run as a markdown table, and two runs side by side.

The JSON beside each table is the record; the table is what goes into the README and into a
ticket. Both are written from the same summary, so a number in the table is never one somebody
recomputed by hand.
"""

import json
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).resolve().parents[1] / "results"

COLUMNS: tuple[tuple[str, str], ...] = (
    ("figure_match", "figure match"),
    ("sql_valid", "SQL valid"),
    ("shape_match", "shape match"),
    ("columns_map", "columns map"),
    ("language_ok", "language"),
    ("drawn", "drawn"),
    ("first_attempt", "first attempt"),
)


def percent(value: float | None) -> str:
    return "-" if value is None else f"{round(value * 100)} %"


def _present(summary: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The measures this set has. A SQL run has no shape, a chart run has no follow-ups."""
    return tuple((key, label) for key, label in COLUMNS if summary.get(key) is not None)


def table(payload: dict[str, Any]) -> str:
    """One run as markdown: the headline, then per kind and per difficulty."""
    summary = payload["summary"]
    measures = _present(summary)
    lines = [
        f"### {payload['model']} on the {payload['set']} set",
        "",
        f"{payload['n']} datapoints, {payload['started_at']}, "
        f"{payload['seconds']} s in total, "
        f"{round(payload['seconds'] / max(1, payload['n']), 1)} s per datapoint, "
        f"median {summary['median_seconds']} s, p90 {summary['p90_seconds']} s.",
        "",
        "| | n | " + " | ".join(label for _, label in measures) + " | median s |",
        "| --- | ---: | " + " | ".join("---:" for _ in measures) + " | ---: |",
        "| **all** | "
        + f"{summary['n']} | "
        + " | ".join(percent(summary[key]) for key, _ in measures)
        + f" | {summary['median_seconds']} |",
    ]
    for title, groups in (("kind", summary["by_kind"]), ("difficulty", summary["by_difficulty"])):
        for name, group in groups.items():
            label = name if title == "kind" else f"difficulty {name}"
            lines.append(
                f"| {label} | {group['n']} | "
                + " | ".join(percent(group.get(key)) for key, _ in measures)
                + f" | {group['median_seconds']} |"
            )
    misses = [result for result in payload["results"] if not result["figure_match"]]
    if misses:
        lines += ["", f"Missed ({len(misses)}):", ""]
        for result in misses:
            reason = result["error"] or "wrong figures"
            lines.append(f"- `{result['id']}` {result['question'][:70]} - {reason[:110]}")
    return "\n".join(lines) + "\n"


def file_name(payload: dict[str, Any], slug: str) -> str:
    stamp = payload["started_at"].replace(":", "").replace("-", "").replace("+0000", "Z")
    return f"{stamp}-{slug}-{payload['set']}"


def save(payload: dict[str, Any], slug: str, directory: Path = RESULTS) -> tuple[Path, Path]:
    """Write the run's JSON and its markdown table, and return both paths."""
    directory.mkdir(parents=True, exist_ok=True)
    stem = file_name(payload, slug)
    as_json = directory / f"{stem}.json"
    as_markdown = directory / f"{stem}.md"
    as_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    as_markdown.write_text(table(payload), encoding="utf-8")
    return as_json, as_markdown


def across(payloads: list[dict[str, Any]]) -> str:
    """One row per model on one set: the table three candidates are read from.

    `compare` says which datapoints changed hands between two runs, which is what a before and
    after wants. This is the other question: three models on the same set, in one table.
    """
    measures = next((_present(payload["summary"]) for payload in payloads if _present(payload["summary"])), ())
    lines = [
        f"### {payloads[0]['set']} set",
        "",
        "| model | n | " + " | ".join(label for _, label in measures) + " | median s | total s |",
        "| --- | ---: | " + " | ".join("---:" for _ in measures) + " | ---: | ---: |",
    ]
    for payload in payloads:
        summary = payload["summary"]
        lines.append(
            f"| {payload['model']} | {summary['n']} | "
            + " | ".join(percent(summary.get(key)) for key, _ in measures)
            + f" | {summary['median_seconds']} | {round(payload['seconds'])} |"
        )
    return "\n".join(lines) + "\n"


def _by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {result["id"]: result for result in payload["results"]}


def compare(left: dict[str, Any], right: dict[str, Any]) -> str:
    """Two runs side by side, and the datapoints that changed hands."""
    measures = _present(left["summary"]) or _present(right["summary"])
    lines = [
        f"### {left['model']} vs {right['model']} on the {left['set']} set",
        "",
        "| | " + " | ".join(label for _, label in measures) + " | median s | n |",
        "| --- | " + " | ".join("---:" for _ in measures) + " | ---: | ---: |",
    ]
    for payload in (left, right):
        summary = payload["summary"]
        lines.append(
            f"| {payload['model']} | "
            + " | ".join(percent(summary.get(key)) for key, _ in measures)
            + f" | {summary['median_seconds']} | {summary['n']} |"
        )

    here, there = _by_id(left), _by_id(right)
    shared = [ident for ident in here if ident in there]
    fixed = [ident for ident in shared if not here[ident]["figure_match"] and there[ident]["figure_match"]]
    broken = [ident for ident in shared if here[ident]["figure_match"] and not there[ident]["figure_match"]]
    both = [ident for ident in shared if here[ident]["figure_match"] and there[ident]["figure_match"]]
    neither = [ident for ident in shared if not here[ident]["figure_match"] and not there[ident]["figure_match"]]
    lines += [
        "",
        f"{len(shared)} datapoints in both runs: {len(both)} right in both, {len(neither)} wrong in "
        f"both, {len(fixed)} only right in {right['model']}, {len(broken)} only right in {left['model']}.",
    ]
    only = set(here) ^ set(there)
    if only:
        lines.append(f"Not in both runs: {', '.join(sorted(only))}.")
    for title, idents, payload in (
        (f"Only {right['model']} gets right", fixed, there),
        (f"Only {left['model']} gets right", broken, here),
    ):
        if not idents:
            continue
        lines += ["", f"{title}:", ""]
        for ident in sorted(idents):
            lines.append(f"- `{ident}` {payload[ident]['question'][:80]}")
    return "\n".join(lines) + "\n"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
