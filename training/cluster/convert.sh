#!/usr/bin/env bash
# One checkpoint to a GGUF adapter the product can attach, with the pitfalls checked.
#
#     bash training/cluster/convert.sh <checkpoint dir> <query|chart> [--base <hf base dir>] [--cases 5]
#
# Run it on a GPU node (it loads the base GGUF at the end), from the repository on scratch.
# Five steps, and every one of them is a failure and not a warning:
#
#   1. the PEFT config: no rslora, no dora, no per-module rank, no embeddings, no head;
#   2. convert_lora_to_gguf.py from the llama.cpp checkout on scratch, f16;
#   3. the converted file: no embedding tensors, exactly one global alpha;
#   4. a dry-run load through the product's own LlamaSlot and AdapterRegistry, one generation;
#   5. five benchmark cases with the adapter attached, through finquery-bench.
#
# Step 4 is there because `AdapterRegistry` treats a missing adapter as a supported state, so a
# conversion that produced something inert looks exactly like one that worked. Step 5 is there
# because a silently wrong adapter looks exactly like a working one until it is scored.
set -euo pipefail

if [ -n "${OPENROUTER_API_KEY:-}" ]; then
  echo "OPENROUTER_API_KEY is set. Nothing under training/cluster/ may use it." >&2
  exit 1
fi

ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
REPO=${FQ_REPO:-$ROOT/finquery}
MODELS=${FINQUERY_MODELS_DIR:-$ROOT/finquery-models}
HF=${FQ_HF:-$ROOT/finquery-hf}
LLAMA=${FQ_LLAMA:-$ROOT/llama.cpp}
CUDA_HOME=${FQ_CUDA_HOME:-$ROOT/cuda-12.8.1}
TRAINING=$REPO/training/cluster

CHECKPOINT=${1:?the checkpoint directory to convert}
NAME=${2:?the adapter name: query or chart}
shift 2

BASE=""
CASES=5
BENCH_MODEL=${FQ_BENCH_MODEL:-local:gemma-4-e4b}
while [ $# -gt 0 ]; do
  case "$1" in
    --base) BASE=$2; shift 2 ;;
    --cases) CASES=$2; shift 2 ;;
    --model) BENCH_MODEL=$2; shift 2 ;;
    *) echo "usage: convert.sh <checkpoint> <query|chart> [--base <dir>] [--cases N] [--model KEY]" >&2; exit 2 ;;
  esac
done

if [ -z "$BASE" ]; then
  # The base the checkpoint was trained on is written into its own config, which is the one
  # answer that cannot be wrong. A relative one would not resolve here, so it is checked.
  BASE=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['base_model_name_or_path'])" \
    "$CHECKPOINT/adapter_config.json")
  echo "base from the checkpoint: $BASE"
fi
if [ ! -f "$BASE/config.json" ]; then
  echo "$BASE is not a Hugging Face model directory. Pass --base, or run setup.sh --hf-bases." >&2
  echo "The bases live in $HF." >&2
  exit 1
fi

export PATH="$CUDA_HOME/bin:$ROOT/uv/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
export UV_CACHE_DIR="$ROOT/uv-cache"
export UV_PYTHON_INSTALL_DIR="$ROOT/uv-python"
export HF_HOME="$ROOT/hf-cache"

# One adapter file per base. `adapter_path` keys an adapter by its sub-agent and nothing else,
# because in the app there is one base for adapters, the fast slot. A comparison of two bases
# needs two query.gguf files, so the second base gets its own models directory whose weights are
# symlinks to the one copy on scratch and whose `adapters/` is its own.
if [ "$MODELS" != "$ROOT/finquery-models" ] && [ ! -d "$MODELS" ]; then
  echo "laying out $MODELS beside the shared weights"
  mkdir -p "$MODELS"
  for directory in "$ROOT"/finquery-models/*/; do
    [ -d "$directory" ] || continue
    [ "$(basename "$directory")" = "adapters" ] && continue
    ln -sfn "${directory%/}" "$MODELS/$(basename "$directory")"
  done
fi

OUT=$MODELS/adapters/$NAME.gguf
mkdir -p "$(dirname "$OUT")"

step() { printf '\n== %s\n' "$*"; }

step "convert 1/5: the PEFT config of $CHECKPOINT"
uv run --project "$TRAINING" python "$TRAINING/check_adapter.py" config "$CHECKPOINT"

step "convert 2/5: convert_lora_to_gguf.py, f16, into $OUT"
time uv run --project "$TRAINING" python "$LLAMA/convert_lora_to_gguf.py" \
  --base "$BASE" --outtype f16 --outfile "$OUT" "$CHECKPOINT"

step "convert 3/5: the converted file"
uv run --project "$TRAINING" python "$TRAINING/check_adapter.py" gguf "$OUT"

step "convert 4/5: a dry-run load through the product's own adapter path"
cd "$REPO"
# The dry run attaches to the same base the benchmark scores, not to the fast seat by default:
# an adapter trained on the 12B cannot load onto E4B (jobs 2515264 and 2515272, 2026-09-07).
FINQUERY_MODELS_DIR=$MODELS uv run --offline python training/cluster/dry_load.py --adapter "$NAME" --model "$BENCH_MODEL"

step "convert 5/5: $CASES benchmark cases with the adapter attached"
set_name=sql
if [ "$NAME" = "chart" ]; then set_name=chart; fi
FINQUERY_PROVIDER=local FINQUERY_MODELS_DIR=$MODELS \
  uv run --offline finquery-bench run --set "$set_name" --model "$BENCH_MODEL" --adapter "$NAME" --n "$CASES"

echo
echo "converted: $OUT"
