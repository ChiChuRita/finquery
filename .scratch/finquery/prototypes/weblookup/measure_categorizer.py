"""Step 3a: the categorizer with and without web knowledge, on merchants the dictionary does
not place, scored against a hand-assigned truth.

Three arms, all on the hosted fast slot (Gemini 3.8 Flash), same taxonomy, same batches:

  A  model only        the categorizer sub-agent as it runs today with web lookup off
  B  lookup, then model   today's stage 2b: the lookup's own category where it placed one, the
                          categorizer for what is left (a low-confidence lookup placement stays
                          a lookup placement and becomes a Question card, as in the pipeline)
  C  model with a brief   the categorizer only, but every entry carries the lookup's one-line
                          summary as extra context (the "shared knowledge" shape)
  B2 as B, with a person rule that reads the legal form first (`web_knowledge.widened_scrub`),
     so "Sixt GmbH & Co Autovermietung KG" is looked up instead of refused as a person

Scoring per merchant: placed = a valid category with confidence at or above the pipeline's
threshold (0.75); correct = the category is in the truth set; sub = the subcategory matches
where the truth names one. Reported over all, and per tier (chain, local).

    uv run python .scratch/finquery/prototypes/weblookup/measure_categorizer.py [--limit N]

Writes results/measure-categorizer.json and results/measure-categorizer.md.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from finquery.categorize.merchants import fold, lookup, merchant_of
from finquery.categorize.subagent import CONFIDENCE_THRESHOLD, MerchantBatchEntry, batched, categorize_merchants

from common import RESULTS, TAXONOMY, Sent, dump_json, fast_model, run
from merchants import LABELED, SYNTHETIC_UNKNOWN, Case
from web_knowledge import Knowledge, WebKnowledge

CATEGORIES = {name for name, _ in TAXONOMY}
SUBS = {name: set(subs) for name, subs in TAXONOMY}


@dataclass(frozen=True)
class BriefedEntry(MerchantBatchEntry):
    """A batch entry with one line of web knowledge under the booking text (arm C)."""

    web: str | None = None

    def as_prompt(self) -> str:
        base = super().as_prompt()
        return f"{base}\n  web: {self.web}" if self.web else base


def entry_for(case: Case, web: str | None = None) -> BriefedEntry:
    merchant = merchant_of(case.description, case.counterparty)
    return BriefedEntry(
        key=merchant.key,
        sample_description=case.description,
        counterparty=case.counterparty,
        bookings=3,
        average_cents=case.average_cents,
        incoming=case.incoming,
        via=merchant.via,
        web=web,
    )


def valid(category: str | None, subcategory: str | None) -> tuple[str | None, str | None]:
    """The placement as the pipeline's `resolve` would take it: a known category, a
    subcategory of it, never Unknown."""
    if not category:
        return None, None
    name = next((c for c in CATEGORIES if fold(c) == fold(category)), None)
    if name is None or name == "Unknown":
        return None, None
    sub = next((s for s in SUBS[name] if fold(s) == fold(subcategory or "")), None)
    return name, sub


def score(case: Case, category: str | None, subcategory: str | None, confidence: float) -> dict:
    name, sub = valid(category, subcategory)
    placed = name is not None and confidence >= CONFIDENCE_THRESHOLD
    correct = name is not None and name in case.truth
    sub_ok = None if case.sub is None else (sub == case.sub)
    return {
        "category": name,
        "subcategory": sub,
        "confidence": round(confidence, 2),
        "placed": placed,
        "correct": correct,
        "placed_and_correct": placed and correct,
        "placed_and_wrong": placed and not correct,
        "sub_ok": sub_ok,
    }


async def run_model(model, settings, cases: list[Case], briefs: dict[str, str] | None = None) -> dict[str, dict]:
    entries = [entry_for(c, (briefs or {}).get(c.counterparty)) for c in cases]
    out: dict[str, dict] = {}
    for batch in batched(entries):
        answers = await categorize_merchants(model, batch, TAXONOMY, model_settings=settings)
        for entry in batch:
            case = next(c for c in cases if merchant_of(c.description, c.counterparty).key == entry.key)
            answer = answers.get(entry.key)
            if answer is None:
                out[case.counterparty] = score(case, None, None, 0.0)
            else:
                out[case.counterparty] = score(case, answer.category, answer.subcategory, answer.confidence)
    return out


def summarize(name: str, results: dict[str, dict], cases: list[Case]) -> dict:
    def block(subset: list[Case]) -> dict:
        rows = [results[c.counterparty] for c in subset]
        with_sub = [(r, c) for r, c in zip(rows, subset) if c.sub is not None and r["category"] is not None]
        return {
            "n": len(rows),
            "placed": sum(r["placed"] for r in rows),
            "placed_correct": sum(r["placed_and_correct"] for r in rows),
            "placed_wrong": sum(r["placed_and_wrong"] for r in rows),
            "correct_any_confidence": sum(r["correct"] for r in rows),
            "sub_ok": sum(1 for r, _ in with_sub if r["sub_ok"]),
            "sub_n": len(with_sub),
        }

    return {
        "arm": name,
        "all": block(cases),
        "chain": block([c for c in cases if c.tier == "chain"]),
        "local": block([c for c in cases if c.tier == "local"]),
    }


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({a / b:.0%})" if b else "-"


async def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    model, settings = fast_model()
    candidates = SYNTHETIC_UNKNOWN + LABELED
    if limit:
        candidates = candidates[:limit]

    # Only what the dictionary does not place, as in the pipeline's stage 2.
    cases: list[Case] = []
    by_dictionary: list[str] = []
    for c in candidates:
        merchant = merchant_of(c.description, c.counterparty)
        if lookup(merchant.key) or lookup(f"{merchant.key} {fold(c.description)}"):
            by_dictionary.append(c.counterparty)
        else:
            cases.append(c)
    print(f"{len(candidates)} candidates, {len(by_dictionary)} placed by the dictionary: {by_dictionary}")
    print(f"{len(cases)} merchants go to the measurement\n")

    # Arm A.
    a0 = model.snapshot()
    arm_a = await run_model(model, settings, cases)
    a1 = model.snapshot()
    print(f"A done: {a1[0] - a0[0]} model calls")

    # The lookups, once, shared by B and C.
    entries: list[Sent] = []
    knowledge = WebKnowledge(model, settings, TAXONOMY, cache_path=RESULTS / "cache.json", journal_entries=entries)
    found: dict[str, Knowledge] = {}
    l0 = model.snapshot()
    for c in cases:
        k = await knowledge.about_one(c.description, c.counterparty)
        found[c.counterparty] = k
        state = "REFUSED" if k.refused else ("cache" if k.cached else f"{k.searches}s/{k.fetches}f {k.seconds:.0f}s")
        print(f"  lookup {c.counterparty[:36]:<36} {state:>14} -> {k.category}/{k.subcategory} {k.confidence:.2f}")
    l1 = model.snapshot()
    lookups_ran = [k for k in found.values() if not k.refused and not k.cached]
    refused = [c.counterparty for c in cases if found[c.counterparty].refused]
    print(f"lookups: {len(lookups_ran)} ran, {len(refused)} refused, {l1[0] - l0[0]} model calls")

    # The widened person rule, for what today's rule refused.
    found_w: dict[str, Knowledge] = dict(found)
    for c in cases:
        if found[c.counterparty].refused:
            k = await knowledge.about_one(c.description, c.counterparty, widened=True)
            found_w[c.counterparty] = k
            state = "REFUSED" if k.refused else ("cache" if k.cached else f"{k.searches}s/{k.fetches}f {k.seconds:.0f}s")
            print(f"  widened {c.counterparty[:35]:<35} {state:>14} -> {k.category}/{k.subcategory} {k.confidence:.2f}")
    refused_w = [c.counterparty for c in cases if found_w[c.counterparty].refused]

    async def arm_lookup_then_model(source: dict[str, Knowledge], label: str) -> dict[str, dict]:
        arm: dict[str, dict] = {}
        leftovers: list[Case] = []
        for c in cases:
            k = source[c.counterparty]
            name, _ = valid(k.category, k.subcategory)
            if name is not None:
                arm[c.counterparty] = {**score(c, k.category, k.subcategory, k.confidence), "by": "lookup"}
            else:
                leftovers.append(c)
        b0 = model.snapshot()
        if leftovers:
            for key, result in (await run_model(model, settings, leftovers)).items():
                arm[key] = {**result, "by": "model"}
        b1 = model.snapshot()
        print(f"{label} done: {len(cases) - len(leftovers)} by the lookup, {len(leftovers)} by the model, {b1[0] - b0[0]} model calls")
        return arm

    # Arm B: the lookup's placement where it placed, the model for the rest. B2: same with the
    # legal-form aware person rule.
    arm_b = await arm_lookup_then_model(found, "B")
    arm_b2 = await arm_lookup_then_model(found_w, "B2")

    # Arm C: the model with a one-line brief from the lookup.
    briefs = {c.counterparty: found[c.counterparty].summary for c in cases if found[c.counterparty].summary}
    c0 = model.snapshot()
    arm_c = await run_model(model, settings, cases, briefs)
    c1 = model.snapshot()
    print(f"C done: {len(briefs)} briefs, {c1[0] - c0[0]} model calls")

    summaries = [
        summarize("A model only", arm_a, cases),
        summarize("B lookup then model", arm_b, cases),
        summarize("B2 lookup (legal-form rule) then model", arm_b2, cases),
        summarize("C model with brief", arm_c, cases),
    ]
    lookup_only = {c.counterparty: score(c, found[c.counterparty].category, found[c.counterparty].subcategory, found[c.counterparty].confidence) for c in cases}
    summaries.append(summarize("lookup alone (today's rule)", lookup_only, cases))
    lookup_only_w = {c.counterparty: score(c, found_w[c.counterparty].category, found_w[c.counterparty].subcategory, found_w[c.counterparty].confidence) for c in cases}
    summaries.append(summarize("lookup alone (legal-form rule)", lookup_only_w, cases))

    lines = ["| arm | n | placed | placed and correct | placed and wrong | correct at any confidence | subcategory right |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in summaries:
        for tier in ("all", "chain", "local"):
            b = s[tier]
            lines.append(
                f"| {s['arm']} ({tier}) | {b['n']} | {pct(b['placed'], b['n'])} | {pct(b['placed_correct'], b['n'])} | "
                f"{b['placed_wrong']} | {pct(b['correct_any_confidence'], b['n'])} | {pct(b['sub_ok'], b['sub_n'])} |"
            )
    lines.append("")
    lines.append(
        f"Lookups: {len(lookups_ran)} ran, {len(refused)} refused by the person rule "
        f"({', '.join(refused)}); with the legal-form rule {len(refused_w)} stay refused ({', '.join(refused_w)}). "
        f"{sum(1 for k in lookups_ran if k.fetches)} of {len(lookups_ran)} lookups fetched a page, "
        f"mean {sum(k.seconds for k in lookups_ran) / max(1, len(lookups_ran)):.1f} s per lookup, "
        f"{l1[0] - l0[0]} model calls for the lookups against {a1[0] - a0[0]} for arm A."
    )
    lines.append(f"Model: {model.requests} requests, {model.input_tokens} in, {model.output_tokens} out, about {model.cost_usd:.3f} USD.")
    lines.append("")
    lines.append("| merchant | tier | truth | A model | B lookup then model | B2 legal-form rule | C model with brief | lookup queries / fetches |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")

    def cell(r: dict) -> str:
        if r["category"] is None:
            return "none"
        mark = "ok" if r["correct"] else "WRONG"
        sub = f" > {r['subcategory']}" if r["subcategory"] else ""
        by = f" [{r['by']}]" if "by" in r else ""
        return f"{r['category']}{sub} {r['confidence']:.2f} {mark}{by}"

    for c in cases:
        k = found_w[c.counterparty]
        evidence = "refused" if k.refused else f"{'; '.join(k.queries)}" + (f" / {len(k.fetched)} fetch" if k.fetched else "")
        if found[c.counterparty].refused and not k.refused:
            evidence = "(refused today) " + evidence
        if k.cached:
            evidence = "(cache) " + (k.summary[:60] if k.summary else "")
        lines.append(
            f"| {c.counterparty} | {c.tier} | {'/'.join(sorted(c.truth))}{' > ' + c.sub if c.sub else ''} | "
            f"{cell(arm_a[c.counterparty])} | {cell(arm_b[c.counterparty])} | {cell(arm_b2[c.counterparty])} | {cell(arm_c[c.counterparty])} | {evidence} |"
        )
    text = "\n".join(lines) + "\n"
    (RESULTS / "measure-categorizer.md").write_text(text, encoding="utf-8")
    dump_json(
        RESULTS / "measure-categorizer.json",
        {
            "cases": [c.__dict__ | {"truth": sorted(c.truth)} for c in cases],
            "by_dictionary": by_dictionary,
            "arm_a": arm_a,
            "arm_b": arm_b,
            "arm_b2": arm_b2,
            "arm_c": arm_c,
            "lookups": {k: v.as_row() for k, v in found.items()},
            "lookups_widened": {k: v.as_row() for k, v in found_w.items()},
            "summaries": summaries,
            "outbound": entries,
            "model": {"requests": model.requests, "input_tokens": model.input_tokens, "output_tokens": model.output_tokens, "cost_usd": model.cost_usd},
        },
    )
    print("\n" + "\n".join(lines[: 2 + 18]))
    print(lines[-len(cases) - 4])
    print(lines[-len(cases) - 3])


if __name__ == "__main__":
    run(main())
