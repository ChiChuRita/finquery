"""Step 3b: resolve the store or chain behind a receipt header.

The receipt reader returns the header as printed ("Combi. Frisch. Nebenan.", "HIT-Tankstelle").
Today that string becomes the draft's description and counterparty with no category. This
prototype does what a store resolver would: the seed dictionary first (free, no request), then
`WebKnowledge.resolve_store` for what the dictionary does not know.

    uv run python .scratch/finquery/prototypes/weblookup/resolve_receipts.py

Writes results/resolve-receipts.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from finquery.categorize.merchants import lookup, merchant_of

from common import RESULTS, TAXONOMY, Sent, fast_model, run
from merchants import RECEIPT_HEADERS
from web_knowledge import WebKnowledge


async def main() -> None:
    model, settings = fast_model()
    entries: list[Sent] = []
    knowledge = WebKnowledge(model, settings, TAXONOMY, cache_path=RESULTS / "cache.json", journal_entries=entries)
    lines = ["| header | dictionary | token | web result | conf | steps | s |", "| --- | --- | --- | --- | ---: | --- | ---: |"]
    for header in RECEIPT_HEADERS:
        merchant = merchant_of(header, None)
        known = lookup(merchant.key)
        if known is not None:
            line = f"| {header} | {known.title}: {known.category}{' > ' + known.subcategory if known.subcategory else ''} | `{merchant.key}` | not needed | | | |"
            print(f"{header:<32} dictionary -> {known.title} ({known.category})")
        else:
            found = await knowledge.resolve_store(header)
            if found.refused:
                line = f"| {header} | no | refused | {found.refused[:60]} | | | |"
                print(f"{header:<32} REFUSED: {found.refused}")
            else:
                place = f"{found.category or '-'}" + (f" > {found.subcategory}" if found.subcategory else "")
                steps = "cache" if found.cached else f"{found.searches} search, {found.fetches} fetch"
                line = f"| {header} | no | `{found.token}` | {place}: {found.summary[:90]} | {found.confidence:.2f} | {steps} | {found.seconds:.0f} |"
                print(f"{header:<32} {steps:>18} -> {place} {found.confidence:.2f}: {found.summary[:80]}")
        lines.append(line)
    lines.append("")
    lines.append(f"Model: {model.requests} requests, {model.input_tokens} in, {model.output_tokens} out, about {model.cost_usd:.3f} USD.")
    (RESULTS / "resolve-receipts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    run(main())
