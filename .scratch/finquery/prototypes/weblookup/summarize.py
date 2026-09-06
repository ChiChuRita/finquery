"""Print the figures the report quotes from results/measure-categorizer.json."""

import json
from pathlib import Path

d = json.load(open(Path(__file__).resolve().parent / "results" / "measure-categorizer.json"))
L = d["lookups_widened"]
ran = [v for v in L.values() if not v["refused"] and not v["cached"]]
print("ran", len(ran), "zero-search", sum(1 for v in ran if v["searches"] == 0), "fetched", sum(1 for v in ran if v["fetches"]), "mean s", round(sum(v["seconds"] for v in ran) / len(ran), 1))
print("multi-search", [(v["token"], v["queries"]) for v in ran if v["searches"] > 1])
print("no sources", sum(1 for v in ran if not v["sources"]))
out = d["outbound"]
print("outbound", len(out), "failed", [(e["target"], e["status"][:60]) for e in out if e["status"] != "ok"])
print("low conf", [(v["token"], v["category"], v["confidence"]) for v in L.values() if v["category"] and v["confidence"] < 0.9])
for arm in ("arm_a", "arm_b", "arm_b2", "arm_c"):
    bad = {k: (r["category"], r["confidence"]) for k, r in d[arm].items() if not r["correct"] or not r["placed"]}
    print(arm, bad)
