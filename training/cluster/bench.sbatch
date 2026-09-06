#!/usr/bin/env bash
# One benchmark job: one model, one set, one GPU.
#
#     sbatch --export=ALL,FQ_MODEL=local:qwen3.5-9b,FQ_SET=sql training/cluster/bench.sbatch
#
# `run_all.sh` submits the nine of these. The partition is `gpu-batch` because `gpu-shortrun`
# takes no batch jobs (it is interactive only) and caps a job at an hour, which the SQL set on
# a 12B model does not fit into. Every job asks for one A100, so the seconds in two tables are
# seconds on the same GPU.
#SBATCH --job-name=fq-bench
#SBATCH --account=sci-lippert-intelligent-agents
#SBATCH --partition=gpu-batch
#SBATCH --nodes=1
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=05:00:00
#SBATCH --output=/sc/scratch/rahul.singh/finquery/training/cluster/logs/bench-%j.out
set -euo pipefail

ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
REPO=$ROOT/finquery
MODELS=$ROOT/finquery-models
CUDA_HOME=${FQ_CUDA_HOME:-$ROOT/cuda-12.8.1}
MODEL=${FQ_MODEL:?FQ_MODEL is the catalog key to benchmark}
SET=${FQ_SET:?FQ_SET is sql, chart or e2e}
N=${FQ_N:-0}

# The one thing this job must not do. Benchmarks run on the local weights; the key belongs to
# the dev server on the laptop and has no business on a cluster node.
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
# The product's own settings: the local provider, the weights in scratch, the context the
# laptop runs, so a number here is a number about the app and not about the cluster.
export FINQUERY_PROVIDER=local
export FINQUERY_MODELS_DIR="$MODELS"
export FINQUERY_LOCAL_N_CTX=${FQ_N_CTX:-32768}

cd "$REPO"
echo "$(date -Is) $SLURM_JOB_ID $MODEL on the $SET set, $(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

sample=()
if [ "$N" != "0" ]; then
  sample=(--n "$N")
fi

# `--offline` because everything is already in the scratch cache: a benchmark job has no
# business resolving packages, and a node that cannot reach PyPI should fail here, not later.
uv run --offline finquery-bench run --set "$SET" --model "$MODEL" "${sample[@]}"
echo "$(date -Is) done"
