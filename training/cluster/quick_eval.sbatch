#!/usr/bin/env bash
# One quick evaluation: a base with or without a checkpoint, on a fixed slice of the held-out set.
#
#     sbatch --export=ALL,FQ_BASE=<hf dir>,FQ_CHECKPOINT=<run>/checkpoint-N,FQ_LABEL=query-e4b-e1,FQ_OUT=<run>/eval,FQ_SQL=30,FQ_CHART=0 \
#       training/cluster/quick_eval.sbatch
#
# Leave FQ_CHECKPOINT empty for the vanilla base. The numbers are indicative: the reported
# figures come from the llama-cpp benchmark on the converted adapter (README, "The checkpoint
# rule"). One GPU, an hour at most for fifty cases of each kind.
#SBATCH --job-name=fq-qeval
#SBATCH --account=sci-lippert-intelligent-agents
#SBATCH --partition=aisc-batch
#SBATCH --nodes=1
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=/sc/scratch/rahul.singh/finquery/training/cluster/logs/qeval-%j.out
set -euo pipefail

ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
REPO=$ROOT/finquery
CUDA_HOME=${FQ_CUDA_HOME:-$ROOT/cuda-12.8.1}
BASE=${FQ_BASE:?FQ_BASE is the Hugging Face base directory}
LABEL=${FQ_LABEL:?FQ_LABEL names the run in the curve}
OUT=${FQ_OUT:?FQ_OUT is where the JSON and curve.md go}

if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  echo "OPENROUTER_API_KEY is set in this job. Nothing under training/cluster/ may use it." >&2
  exit 1
fi

export PATH="$CUDA_HOME/bin:$ROOT/uv/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export UV_CACHE_DIR="$ROOT/uv-cache"
export UV_PYTHON_INSTALL_DIR="$ROOT/uv-python"
export HF_HOME="$ROOT/hf-cache"
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_PROGRESS_BARS=1
export TOKENIZERS_PARALLELISM=false
export TRITON_CACHE_DIR="$ROOT/triton-cache"
export XDG_CACHE_HOME="$ROOT/cache"

cd "$REPO/training/cluster"
echo "$(date -Is) ${SLURM_JOB_ID:-local} $LABEL on $(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

extra=()
if [ -n "${FQ_CHECKPOINT:-}" ]; then extra+=(--checkpoint "$FQ_CHECKPOINT"); fi

uv run --offline python quick_eval.py --base "$BASE" --label "$LABEL" --out "$OUT" \
  --sql "${FQ_SQL:-50}" --chart "${FQ_CHART:-50}" "${extra[@]}"
echo "$(date -Is) done"
