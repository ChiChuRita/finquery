#!/usr/bin/env bash
# Submit the nine benchmark jobs: three models on the SQL set, the chart set and the end-to-end
# subset. Run it from the repo root on the laptop, after `setup.sh`:
#
#     bash training/cluster/run_all.sh --after <setup job id>
#     bash training/cluster/run_all.sh --smoke        # five SQL cases on E4B, nothing else
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

MODELS=(local:gemma-4-e4b local:qwen3.5-9b local:gemma-4-12b)
# The SQL set is 152 questions, the chart set 63 whole charts, the subset 30 chat turns. The
# limits are what the smoke run's seconds per case say those need on an A100, roughly doubled.
declare -A LIMIT=([sql]=05:00:00 [chart]=06:00:00 [e2e]=05:00:00)

after=""
smoke=""
while [ $# -gt 0 ]; do
  case "$1" in
    --after) after="--dependency=afterok:$2"; shift 2 ;;
    --smoke) smoke=1; shift ;;
    *) echo "usage: run_all.sh [--after <job id>] [--smoke]" >&2; exit 2 ;;
  esac
done

submit() {
  local model=$1 set_name=$2 limit=$3 n=$4
  local name="fq-${model#local:}-$set_name"
  ssh "$REMOTE" "sbatch --parsable $after --job-name='$name' --time=$limit \
    --output='$LOGS/$name-%j.out' \
    --export=ALL,FQ_MODEL=$model,FQ_SET=$set_name,FQ_N=$n,FQ_ROOT=$ROOT \
    '$REPO/training/cluster/bench.sbatch'"
}

if [ -n "$smoke" ]; then
  job=$(submit local:gemma-4-e4b sql 00:40:00 5)
  echo "smoke $job  five SQL cases on Gemma 4 E4B"
  echo "  ssh $REMOTE tail -f $LOGS/fq-gemma-4-e4b-sql-$job.out"
  exit 0
fi

echo "model                set    job"
ids=()
for model in "${MODELS[@]}"; do
  for set_name in sql chart e2e; do
    job=$(submit "$model" "$set_name" "${LIMIT[$set_name]}" 0)
    ids+=("$job")
    printf '%-20s %-6s %s\n' "$model" "$set_name" "$job"
  done
done

echo
echo "${#ids[@]} jobs: ${ids[*]}"
echo "watch:   ssh $REMOTE squeue -u \$USER"
echo "collect: bash training/cluster/collect.sh"
