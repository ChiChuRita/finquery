#!/usr/bin/env bash
# The whole harness on the committed sample batches, end to end, with no model.
#
# Ten hand-written query candidates and ten chart candidates, plus the wrong attempts that make
# the repair and rewrite samples, through: validate, gate, render, judge pack, judge apply,
# assemble, audit. Under two minutes on a laptop, and the first thing a writer or judge agent of
# ticket 64 runs: if this is green, the harness is not what is wrong with your batch.
#
#   training/data/smoke.sh [output folder]
#
# The render step needs the chart runtime built once (it is a build artifact, not committed):
#
#   npm --prefix frontend install && npm --prefix frontend run build

set -euo pipefail

cd "$(dirname "$0")/../.."
OUT="${1:-training/data/out/smoke}"
SAMPLES=training/data/samples
START=$SECONDS

say() { printf '\n== %s\n' "$1"; }

rm -rf "$OUT"
mkdir -p "$OUT"

say "1/7 validate"
uv run python -m training.data.schema validate --task query "$SAMPLES/query-smoke.jsonl" "$SAMPLES/query-wrong.jsonl"
uv run python -m training.data.schema validate --task chart "$SAMPLES/chart-smoke.jsonl" "$SAMPLES/chart-wrong.jsonl"

say "2/7 gate"
uv run python -m training.data.gate --task query --out "$OUT/query" \
  "$SAMPLES/query-smoke.jsonl" "$SAMPLES/query-wrong.jsonl" 2>/dev/null
uv run python -m training.data.gate --task chart --out "$OUT/chart" \
  "$SAMPLES/chart-smoke.jsonl" "$SAMPLES/chart-wrong.jsonl" 2>/dev/null

say "3/7 render"
uv run python -m training.data.render --kept "$OUT/chart/kept.jsonl" --out "$OUT/renders" --session ticket62

say "4/7 judge pack"
uv run python -m training.data.judge_pack pack --task query --batch "$OUT/query"
uv run python -m training.data.judge_pack pack --task chart --batch "$OUT/chart" --renders "$OUT/renders"

say "5/7 judge apply"
uv run python -m training.data.judge_pack apply --task query --batch "$OUT/query" \
  --verdicts "$SAMPLES/query-verdicts.jsonl"

say "6/7 assemble"
uv run python -m training.data.assemble --query "$OUT/query" --chart "$OUT/chart" --out "$OUT/samples"

say "7/7 audit"
uv run python -m training.data.audit duplicates --task query --out "$OUT/duplicates-query.md" "$OUT/query/kept.jsonl"
uv run python -m training.data.audit duplicates --task chart --out "$OUT/duplicates-chart.md" "$OUT/chart/kept.jsonl"
uv run python -m training.data.audit heldout --out "$OUT/heldout.md"
uv run python -m training.data.audit freeze --check

printf '\n== green in %s seconds. Everything is under %s\n' "$((SECONDS - START))" "$OUT"
