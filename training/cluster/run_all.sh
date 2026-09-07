#!/usr/bin/env bash
# Submit the nine benchmark jobs: three models on the SQL set, the chart set and the end-to-end
# subset. Run it from the repo root on the laptop, after `setup.sh`:
#
#     bash training/cluster/run_all.sh --after <setup job id>
#     bash training/cluster/run_all.sh --smoke        # five SQL cases on E4B, nothing else
#     bash training/cluster/run_all.sh --adapters     # before and after, per base, per task
#     FQ_BENCH_MODELS="local:gemma-4-26b local:qwen3.8-27b" bash training/cluster/run_all.sh
#                                                     # other models on the three sets
#
# `--after` makes every job wait for the setup job to finish well, so the whole thing can be
# submitted in one go. Without it the jobs are submitted straight away, which is what a rerun on
# an environment that is already built wants.
#
# It prints the nine job ids and the collect command. Nothing here waits: the queue is shared.
set -euo pipefail

REMOTE=${FQ_REMOTE:-hpi-login}
ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
REPO=$ROOT/finquery
LOGS=$REPO/training/cluster/logs

# The three candidates of the 2026-09-06 comparison. `FQ_BENCH_MODELS` names others: a catalog
# key or a benchmark candidate (`bench/finquery_bench/candidates.py`), whose files `dl2.sh` in
# scratch fetched.
MODELS=${FQ_BENCH_MODELS:-"local:gemma-4-e4b local:qwen3.5-9b local:gemma-4-12b"}

# The two bases the adapters are trained for. Qwen is not one of them: llama.cpp cannot convert
# a Qwen3.5 LoRA at all (research note, section 9, pitfall 1).
ADAPTER_MODELS="local:gemma-4-e4b local:gemma-4-12b"

# The SQL set is 152 questions, the chart set 73 whole charts, the subset 30 chat turns. The
# limits are what the smoke run's seconds per case say those need, roughly doubled. A case
# statement rather than an associative array, because the laptop's bash is 3.2 and has none.
limit_for() {
  case "$1" in
    sql) echo 05:00:00 ;;
    chart) echo 06:00:00 ;;
    e2e) echo 05:00:00 ;;
    *) echo "no time limit for the $1 set" >&2; exit 2 ;;
  esac
}

after=""
smoke=""
adapters=""
while [ $# -gt 0 ]; do
  case "$1" in
    --after) after="--dependency=afterok:$2"; shift 2 ;;
    --smoke) smoke=1; shift ;;
    --adapters) adapters=1; shift ;;
    *) echo "usage: run_all.sh [--after <job id>] [--smoke] [--adapters]" >&2; exit 2 ;;
  esac
done

submit() {
  local model=$1 set_name=$2 limit=$3 n=$4 adapter=${5:-} models=${6:-}
  local name="fq-${model#local:}${adapter:+-$adapter}-$set_name"
  ssh "$REMOTE" "sbatch --parsable $after --job-name='$name' --time=$limit \
    --output='$LOGS/$name-%j.out' \
    --export=ALL,FQ_MODEL=$model,FQ_SET=$set_name,FQ_N=$n,FQ_ROOT=$ROOT,FQ_ADAPTER=$adapter,FQ_MODELS=$models \
    '$REPO/training/cluster/bench.sbatch'"
}

# The models directory a base's adapters live in. The shared one for E4B, its own for every
# other base, because `adapters/query.gguf` is keyed by sub-agent and not by base (`convert.sh`).
models_for() {
  case "$1" in
    local:gemma-4-e4b) echo "$ROOT/finquery-models" ;;
    *) echo "$ROOT/finquery-models-${1#local:}" ;;
  esac
}

if [ -n "$adapters" ]; then
  # Before and after, per base, per task: eight jobs. The SQL set is scored with the query
  # adapter and the chart set with the chart adapter, because that is what each is attached
  # over in the app. `collect.sh` writes the comparison.
  echo "model                     set    adapter job"
  ids=""
  for model in $ADAPTER_MODELS; do
    for pair in "sql query" "chart chart"; do
      set_name=${pair% *}
      adapter=${pair#* }
      for attached in "" "$adapter"; do
        job=$(submit "$model" "$set_name" "$(limit_for "$set_name")" 0 "$attached" "$(models_for "$model")")
        ids="$ids $job"
        printf '%-25s %-6s %-7s %s\n' "$model" "$set_name" "${attached:-none}" "$job"
      done
    done
  done
  echo
  echo "jobs:$ids"
  echo "watch:   ssh $REMOTE squeue -u \$USER"
  echo "collect: bash training/cluster/collect.sh --adapters"
  exit 0
fi

if [ -n "$smoke" ]; then
  job=$(submit local:gemma-4-e4b sql 00:40:00 5)
  echo "smoke $job  five SQL cases on Gemma 4 E4B"
  echo "  ssh $REMOTE tail -f $LOGS/fq-gemma-4-e4b-sql-$job.out"
  exit 0
fi

echo "model                set    job"
ids=""
for model in $MODELS; do
  for set_name in sql chart e2e; do
    job=$(submit "$model" "$set_name" "$(limit_for "$set_name")" 0)
    ids="$ids $job"
    printf '%-20s %-6s %s\n' "$model" "$set_name" "$job"
  done
done

echo
echo "jobs:$ids"
echo "watch:   ssh $REMOTE squeue -u \$USER"
echo "collect: bash training/cluster/collect.sh"
