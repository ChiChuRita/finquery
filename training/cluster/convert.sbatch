#!/usr/bin/env bash
# One conversion job: a checkpoint to a GGUF adapter, checked and smoke-tested, on a GPU node.
#
#     sbatch --export=ALL,FQ_CHECKPOINT=<run>/checkpoint-N,FQ_ADAPTER=query[,FQ_BASE=<hf dir>,FQ_MODELS=<models dir>] \
#       training/cluster/convert.sbatch
#
# Wraps convert.sh with the environment train.sbatch uses. FQ_MODELS is where the adapter lands
# (`<models>/adapters/<name>.gguf`): the shared models directory for E4B, the 12B's own copy for
# the 12B (bench.sbatch explains why). The GPU is pinned to the RTX PRO 6000: the llama-cpp build
# on scratch was compiled on that card and aborts on an A100 (job 2515222, 2026-09-07).
#SBATCH --job-name=fq-convert
#SBATCH --account=sci-lippert-intelligent-agents
#SBATCH --partition=gpu-batch
#SBATCH --nodes=1
#SBATCH --gres=gpu:rtx_pro_6000:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=01:00:00
#SBATCH --output=/sc/scratch/rahul.singh/finquery/training/cluster/logs/convert-%j.out
set -euo pipefail

ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
REPO=$ROOT/finquery
CUDA_HOME=${FQ_CUDA_HOME:-$ROOT/cuda-12.8.1}
CHECKPOINT=${FQ_CHECKPOINT:?FQ_CHECKPOINT is the checkpoint directory}
ADAPTER=${FQ_ADAPTER:?FQ_ADAPTER is query or chart}

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
export TOKENIZERS_PARALLELISM=false
export XDG_CACHE_HOME="$ROOT/cache"
export FINQUERY_MODELS_DIR="${FQ_MODELS:-$ROOT/finquery-models}"

cd "$REPO"
echo "$(date -Is) ${SLURM_JOB_ID:-local} converting $CHECKPOINT as $ADAPTER into $FINQUERY_MODELS_DIR on $(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

extra=()
if [ -n "${FQ_BASE:-}" ]; then extra+=(--base "$FQ_BASE"); fi
bash training/cluster/convert.sh "$CHECKPOINT" "$ADAPTER" "${extra[@]}"
echo "$(date -Is) done"
