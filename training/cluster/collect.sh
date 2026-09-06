#!/usr/bin/env bash
# Bring the cluster's results home and write the comparison. Run it from the repo root on the
# laptop once the nine jobs have finished:
#
#     bash training/cluster/collect.sh
#
# It rsyncs the result JSON and markdown into bench/results/, writes a one line summary of the
# job logs beside them, and compares the three models per set into
# bench/results/<date>-cluster-compare.md. Nothing runs a model here.
set -euo pipefail

REMOTE=${FQ_REMOTE:-hpi-login}
ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
REPO=$ROOT/finquery
LOGS=$REPO/training/cluster/logs

mode=candidates
if [ "${1:-}" = "--adapters" ]; then
  mode=adapters
elif [ $# -gt 0 ]; then
  echo "usage: collect.sh [--adapters]" >&2
  exit 2
fi

here=$(cd "$(dirname "$0")/../.." && pwd)
cd "$here"
results=bench/results
today=$(date +%Y%m%d)
compare=$results/$today-cluster-compare.md
if [ "$mode" = adapters ]; then
  compare=$results/$today-adapters-compare.md
fi

echo "== results from $REMOTE"
rsync -az "$REMOTE:$REPO/bench/results/" "$results/"

echo "== the job logs, as one summary"
# The logs stay on the cluster; what comes back is the line per job that says how it went.
ssh "$REMOTE" "cd '$LOGS' && grep -H -e 'on the .* set' -e '^real' -e 'error' -e 'Traceback' *.out 2>/dev/null | tail -60" \
  > "$results/$today-cluster-jobs.txt" || true
wc -l < "$results/$today-cluster-jobs.txt" | xargs echo "lines:"

# The newest run of one model on one set, and nothing if there is none: a set whose jobs have
# not come back yet is a line in the document, not a dead script.
newest() { ls -1 "$results"/*"-$1-$2.json" 2> /dev/null | tail -1 || true; }

if [ "$mode" = adapters ]; then
  # Before and after per base per task. `finquery-bench compare` of two runs is exactly this
  # question: the two tables side by side, and the datapoints that changed hands.
  {
    cat <<'HEADER'
# The adapters against the vanilla bases

Each pair is one base on one set, once on the vanilla weights and once with the LoRA adapter of
that sub-agent attached, on the cluster GPU through llama-cpp with CUDA. Same set, same seed,
same database, one model per job, so the only thing that differs between the two columns of a
pair is the adapter.

These are the reported numbers. The quick evaluation in
`training/cluster/<run>/eval/curve.md` is what chose the checkpoint that was converted; it runs
on the HF weights with no grammar and is indicative only.
HEADER
    for base in local-gemma-4-e4b local-gemma-4-12b; do
      for pair in "sql query" "chart chart"; do
        set_name=${pair% *}
        adapter=${pair#* }
        before=$(newest "$base" "$set_name")
        after=$(newest "$base+$adapter" "$set_name")
        echo
        if [ -z "$before" ] || [ -z "$after" ]; then
          echo "### $base on the $set_name set"
          echo
          echo "Not both halves are back yet: before ${before:-missing}, after ${after:-missing}."
          continue
        fi
        uv run finquery-bench compare "$before" "$after"
      done
    done
  } > "$compare"
  echo "== written $compare"
  exit 0
fi

{
  cat <<'HEADER'
# The three local candidates on the HPI cluster

Gemma 4 E4B, Qwen3.5 9B and Gemma 4 12B, Q4_K_M through llama-cpp with CUDA, one RTX PRO 6000
per job, 32k context, the same wire formats and the same sub-agent paths the laptop runs. The
seconds are seconds on that one GPU, which is not the laptop's: the tokens per second table
below is what the laptop costs.

The SQL and chart tables are the primary numbers: they score the sub-agent, which is where an
adapter attaches. The end-to-end table runs the whole chat turn in front of the sub-agent on 30
training cases, so the gap between the two is routing and phrasing loss.
HEADER
  for set_name in sql chart e2e; do
    # A space separated list rather than an array: the laptop's bash is 3.2, where reading the
    # length of an empty array under `set -u` is itself an error. No result path has a space.
    files=""
    for model in local-gemma-4-e4b local-qwen3.5-9b local-gemma-4-12b; do
      file=$(newest "$model" "$set_name")
      if [ -n "$file" ]; then files="$files $file"; fi
    done
    if [ -z "$files" ]; then
      echo; echo "### $set_name set"; echo; echo "No run of this set has come back yet."
      continue
    fi
    echo
    # shellcheck disable=SC2086 - the splitting is the point
    uv run finquery-bench compare $files
  done
  cat <<'FOOTER'

## What each pair costs on the laptop

From `bench/results/20260906-local-tokens-per-second.md`, measured on the user's Mac with
Metal. The fast slot is Gemma 4 E4B either way, so the pair is E4B plus the chat model.

| pair | generation | prompt processing | both models at 32k |
| --- | ---: | ---: | ---: |
| E4B alone | 46.7 tok/s | 545 tok/s | 5.9 GB |
| E4B + Qwen3.5 9B | 29.5 tok/s | 329 tok/s | 13.5 GB |
| E4B + Gemma 4 12B | 22.4 tok/s | 205 tok/s | 12.9 GB |

## The decision rule

Accuracy first: the pair is the one with the highest figure match on the SQL set, then on the
chart set. Speed breaks a tie only inside about five points. The pair has to fit in about
13.5 GB, which is what the 24 GB Mac has left for weights and KV cache with both models
resident, so a pair that does not fit is not a candidate whatever it scores.
FOOTER
} > "$compare"

echo "== written $compare"
