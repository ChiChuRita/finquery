#!/usr/bin/env bash
# One training job: one adapter, one base, one GPU.
#
#     sbatch --export=ALL,FQ_CONFIG=configs/query-e4b.yaml training/cluster/train.sbatch
#
# QLoRA on these sizes needs one card, not four: the research note puts an adapter at under two
# hours on one A100 and under an hour on one H100. Four of these run in parallel, one per
# adapter, which is the whole GPU budget of a training round.
#
# The partition is `aisc-batch`, where the H100 80 GB nodes are and which this account may use
# (probed on 2026-09-06, job 2514755 on gx08). `FQ_TRAIN_PARTITION=gpu-batch FQ_TRAIN_GPU=a100`
# is the fallback when aisc-batch is full; the RTX PRO 6000 nodes of gpu-batch work too and are
# slower.
#SBATCH --job-name=fq-train
#SBATCH --account=sci-lippert-intelligent-agents
#SBATCH --partition=aisc-batch
#SBATCH --nodes=1
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=16
#SBATCH --mem=96G
#SBATCH --time=12:00:00
#SBATCH --output=/sc/scratch/rahul.singh/finquery/training/cluster/logs/train-%j.out
set -euo pipefail

ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
REPO=$ROOT/finquery
CUDA_HOME=${FQ_CUDA_HOME:-$ROOT/cuda-12.8.1}
CONFIG=${FQ_CONFIG:?FQ_CONFIG is the YAML under training/cluster/configs}

# The one thing no job here may see.
if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  echo "OPENROUTER_API_KEY is set in this job. Nothing under training/cluster/ may use it." >&2
  exit 1
fi
if [ -f "$REPO/.env" ]; then
  echo "$REPO/.env exists on the cluster. The sync is meant to leave it on the laptop." >&2
  exit 1
fi

export PATH="$CUDA_HOME/bin:$ROOT/uv/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export UV_CACHE_DIR="$ROOT/uv-cache"
export UV_PYTHON_INSTALL_DIR="$ROOT/uv-python"
export HF_HOME="$ROOT/hf-cache"
# Nothing is downloaded during a run: the bases are on scratch and a job that reaches for the
# network is a job whose weights are not the ones that were checked.
export HF_HUB_OFFLINE=1
export HF_HUB_DISABLE_PROGRESS_BARS=1
export TOKENIZERS_PARALLELISM=false
# Triton compiles and then caches a shared object at the first backward pass. Its default cache
# is in the home directory, which is mounted noexec here, so the cache goes to scratch.
export TRITON_CACHE_DIR="$ROOT/triton-cache"
export XDG_CACHE_HOME="$ROOT/cache"

cd "$REPO/training/cluster"
echo "$(date -Is) ${SLURM_JOB_ID:-local} $CONFIG on $(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

extra=()
if [ -n "${FQ_SAMPLES:-}" ]; then extra+=(--samples "$FQ_SAMPLES"); fi
if [ -n "${FQ_OUTPUT:-}" ]; then extra+=(--output "$FQ_OUTPUT"); fi
if [ -n "${FQ_MAX_STEPS:-}" ]; then extra+=(--max-steps "$FQ_MAX_STEPS"); fi

uv run --offline python train.py "$CONFIG" "${extra[@]}"
echo "$(date -Is) done"
