#!/usr/bin/env bash
# One benchmark job: one model, one set, one GPU.
#
#     sbatch --export=ALL,FQ_MODEL=local:qwen3.5-9b,FQ_SET=sql training/cluster/bench.sbatch
#     sbatch --export=ALL,FQ_MODEL=local:gemma-4-e4b,FQ_SET=sql,FQ_ADAPTER=query ...
#
# `FQ_ADAPTER` attaches the LoRA adapter of that name to the model for the whole run, which is
# the after half of an adapter comparison. The adapter file has to be in
# `$FINQUERY_MODELS_DIR/adapters/<name>.gguf`, which is where `convert.sh` writes it; a missing
# file is a supported state in the app (it answers on the base weights and leaves an audit
# note) and would silently make the after run a second before run, so this job refuses it.
#
# `run_all.sh` submits the nine of these. The partition is `gpu-batch` because `gpu-shortrun`
# takes no batch jobs (it is interactive only) and caps a job at an hour, which the SQL set on
# a model of this size does not fit into. Every job asks for one RTX PRO 6000, so the seconds in two
# tables are seconds on the same GPU: all twenty A100s of the partition were allocated when
# these ran, and a comparison whose speed column mixes two GPUs says nothing.
#SBATCH --job-name=fq-bench
#SBATCH --account=sci-lippert-intelligent-agents
#SBATCH --partition=gpu-batch
#SBATCH --nodes=1
#SBATCH --gres=gpu:rtx_pro_6000:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=05:00:00
#SBATCH --output=/sc/scratch/rahul.singh/finquery/training/cluster/logs/bench-%j.out
set -euo pipefail

ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
REPO=$ROOT/finquery
# One models directory per base when adapters are being scored: `adapters/query.gguf` is keyed
# by sub-agent and not by base, so a second base's adapters live beside a symlinked copy of its
# weights (the 12B candidate is the one this was built for). See `convert.sh`.
MODELS=${FQ_MODELS:-$ROOT/finquery-models}
CUDA_HOME=${FQ_CUDA_HOME:-$ROOT/cuda-12.8.1}
MODEL=${FQ_MODEL:?FQ_MODEL is the catalog key to benchmark}
SET=${FQ_SET:?FQ_SET is sql, chart or e2e}
N=${FQ_N:-0}
ADAPTER=${FQ_ADAPTER:-}

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
# An adapter run on a chat model attaches to the chat seat, which the app itself never does.
if [ -n "$ADAPTER" ]; then export FINQUERY_ADAPTERS_ANY_SEAT=1; fi
export FINQUERY_LOCAL_N_CTX=${FQ_N_CTX:-32768}

cd "$REPO"
echo "$(date -Is) $SLURM_JOB_ID $MODEL on the $SET set, adapter ${ADAPTER:-none}, $(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

sample=()
if [ "$N" != "0" ]; then
  sample=(--n "$N")
fi

attached=()
if [ -n "$ADAPTER" ]; then
  # A missing adapter is a supported state in the app, so it would not fail: it would quietly
  # produce a second run on the base weights and call it the after column.
  if [ ! -f "$MODELS/adapters/$ADAPTER.gguf" ]; then
    echo "there is no adapter at $MODELS/adapters/$ADAPTER.gguf; run convert.sh first" >&2
    exit 1
  fi
  attached=(--adapter "$ADAPTER")
  ls -l "$MODELS/adapters/$ADAPTER.gguf"
fi

# `--offline` because everything is already in the scratch cache: a benchmark job has no
# business resolving packages, and a node that cannot reach PyPI should fail here, not later.
uv run --offline finquery-bench run --set "$SET" --model "$MODEL" "${sample[@]}" "${attached[@]}"
echo "$(date -Is) done"
