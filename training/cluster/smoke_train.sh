#!/usr/bin/env bash
# The whole training loop end to end on one GPU, small enough to watch.
#
#     bash training/cluster/smoke_train.sh              # from the laptop: sync and submit
#     bash training/cluster/smoke_train.sh --on-gpu     # the job body itself
#
# Five steps, each one timed and each one a failure if it does not pass:
#
#   1. build the forty sample rows from samples/smoke-query.json with the product's own prompts;
#   2. train Gemma 4 E4B for twenty steps on them;
#   3. quick-evaluate the result on five held-out cases (three questions, two chart requests);
#   4. convert it to a GGUF adapter, with the pitfall checks and the dry-run load;
#   5. five benchmark cases with the adapter attached.
#
# Steps 4 and 5 are `convert.sh`, which does them itself. This must pass before a real training
# round is submitted: it is the difference between a broken recipe found in half an hour and one
# found after four adapters have trained overnight.
set -euo pipefail

REMOTE=${FQ_REMOTE:-hpi-login}
ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
ACCOUNT=${FQ_ACCOUNT:-sci-lippert-intelligent-agents}
PARTITION=${FQ_TRAIN_PARTITION:-aisc-batch}
GPU=${FQ_TRAIN_GPU:-h100}
REPO=$ROOT/finquery
LOGS=$REPO/training/cluster/logs
WORK=${FQ_TRAIN_ROOT:-$ROOT/finquery-training}
SMOKE=$WORK/smoke

step() { printf '\n== %s (%s)\n' "$*" "$(date -Is)"; }

on_gpu() {
  if [ -n "${OPENROUTER_API_KEY:-}" ]; then
    echo "OPENROUTER_API_KEY is set in this job. Nothing under training/cluster/ may use it." >&2
    exit 1
  fi
  if [ -f "$REPO/.env" ]; then
    echo "$REPO/.env exists on the cluster. The sync is meant to leave it on the laptop." >&2
    exit 1
  fi
  local cuda=${FQ_CUDA_HOME:-$ROOT/cuda-12.8.1}
  export PATH="$cuda/bin:$ROOT/uv/bin:$PATH"
  export LD_LIBRARY_PATH="$cuda/lib64:${LD_LIBRARY_PATH:-}"
  export UV_CACHE_DIR="$ROOT/uv-cache"
  export UV_PYTHON_INSTALL_DIR="$ROOT/uv-python"
  export HF_HOME="$ROOT/hf-cache"
  export HF_HUB_OFFLINE=1
  export HF_HUB_DISABLE_PROGRESS_BARS=1
  export TOKENIZERS_PARALLELISM=false
  # Triton compiles and then caches a shared object. Its default cache is in the home
  # directory, which is mounted noexec here, so the cache goes to scratch like everything else.
  export TRITON_CACHE_DIR="$ROOT/triton-cache"
  export XDG_CACHE_HOME="$ROOT/cache"
  export FINQUERY_MODELS_DIR=$ROOT/finquery-models

  local base=$ROOT/finquery-hf/gemma-4-E4B-it
  mkdir -p "$SMOKE"
  echo "smoke on $(hostname)"
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

  step "1/5 the forty samples"
  time uv run --offline --project "$REPO/training/cluster" python "$REPO/training/cluster/smoke_samples.py" \
    --out "$SMOKE/query.jsonl"

  step "2/5 twenty steps on Gemma 4 E4B"
  time uv run --offline --project "$REPO/training/cluster" python "$REPO/training/cluster/train.py" \
    "$REPO/training/cluster/configs/query-e4b.yaml" \
    --samples "$SMOKE/query.jsonl" --output "$SMOKE/run" --max-steps 20

  step "3/5 the quick evaluation, five held-out cases"
  time uv run --offline --project "$REPO/training/cluster" python "$REPO/training/cluster/quick_eval.py" \
    --base "$base" --checkpoint "$SMOKE/run/final" --label smoke-query-e4b \
    --sql 3 --chart 2 --out "$SMOKE/eval"

  step "4 and 5 of 5: convert, load and five benchmark cases"
  time bash "$REPO/training/cluster/convert.sh" "$SMOKE/run/final" query --base "$base" --cases 5

  step "smoke done"
  cat "$SMOKE/run/train-summary.json"
  cat "$SMOKE/eval/curve.md"
}

case "${1:-}" in
  --on-gpu)
    on_gpu
    ;;
  "")
    bash "$(dirname "$0")/setup.sh" --sync
    job=$(ssh "$REMOTE" "sbatch --parsable --account=$ACCOUNT --partition=$PARTITION --nodes=1 \
      --gres=gpu:$GPU:1 --job-name=fq-smoke-train --cpus-per-task=16 --mem=96G --time=01:00:00 \
      --output='$LOGS/smoke-train-%j.out' --wrap=\"bash '$REPO/training/cluster/smoke_train.sh' --on-gpu\"")
    echo "job $job runs the smoke; follow it with"
    echo "  ssh $REMOTE tail -f $LOGS/smoke-train-$job.out"
    ;;
  *)
    echo "usage: smoke_train.sh [--on-gpu]" >&2
    exit 2
    ;;
esac
