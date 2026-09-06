"""Step 1: run today's lookup loop, unchanged, on twenty synthetic booking strings and record
what it searched, fetched, concluded and how long it took.

    uv run python .scratch/finquery/prototypes/weblookup/run_lookups.py

Writes results/review-lookups.json (every step) and results/review-lookups.md (the table).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import RESULTS, TAXONOMY, Sent, dump_json, fast_model, run
from merchants import SYNTHETIC_REVIEW
from web_knowledge import WebKnowledge


async def main() -> None:
    model, settings = fast_model()
    entries: list[Sent] = []
    knowledge = WebKnowledge(
        model, settings, TAXONOMY, cache_path=RESULTS / "cache.json", journal_entries=entries
    )
    rows = []
    for description, counterparty in SYNTHETIC_REVIEW:
        before = model.snapshot()
        found = await knowledge.about_one(description, counterparty)
        after = model.snapshot()
        row = found.as_row()
        row.update(
            description=description,
            counterparty=counterparty,
            model_requests=after[0] - before[0],
            input_tokens=after[1] - before[1],
            output_tokens=after[2] - before[2],
        )
        rows.append(row)
        print(
            f"{(counterparty or description)[:34]:<34} token={found.token!r:28} "
            f"{'REFUSED' if found.refused else ('cached' if found.cached else f'{found.searches}s/{found.fetches}f')} "
            f"-> {found.category}/{found.subcategory} {found.confidence:.2f} {found.seconds:5.1f}s"
        )
        if found.queries:
            print(f"    queries: {found.queries}")
        if found.fetched:
            print(f"    fetched: {found.fetched}")
        if found.error:
            print(f"    error: {found.error}")

    dump_json(RESULTS / "review-lookups.json", {"rows": rows, "outbound": entries})
    lines = [
        "| merchant | token | steps | queries | fetched | conclusion | conf | s | model calls |",
        "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |",
    ]
    for r in rows:
        if r["refused"]:
            steps = "refused"
        elif r["cached"]:
            steps = "cache"
        else:
            steps = f"{r['searches']} search, {r['fetches']} fetch"
        conclusion = f"{r['category'] or '-'}" + (f" > {r['subcategory']}" if r["subcategory"] else "")
        lines.append(
            f"| {r['counterparty'] or r['description']} | `{r['token']}` | {steps} | "
            f"{'; '.join(r['queries']) or '-'} | {'; '.join(u.replace('https://', '')[:50] for u in r['fetched']) or '-'} | "
            f"{conclusion} | {r['confidence']:.2f} | {r['seconds']:.1f} | {r['model_requests']} |"
        )
    ran = [r for r in rows if not r["refused"] and not r["cached"]]
    lines.append("")
    lines.append(
        f"{len(rows)} strings, {len(ran)} lookups ran, "
        f"{sum(1 for r in ran if r['fetches'])} of them fetched a page, "
        f"mean {sum(r['seconds'] for r in ran) / max(1, len(ran)):.1f} s, "
        f"model requests {model.requests}, tokens in {model.input_tokens} out {model.output_tokens}, "
        f"about {model.cost_usd:.3f} USD."
    )
    (RESULTS / "review-lookups.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-1:]))


if __name__ == "__main__":
    run(main())
