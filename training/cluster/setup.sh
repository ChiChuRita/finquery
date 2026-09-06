#!/usr/bin/env bash
# Put FinQuery on the HPI cluster: the repo, uv, a CUDA build of llama-cpp-python, the GGUFs.
#
# Run it from the repo root on the laptop:
#
#     bash training/cluster/setup.sh
#
# It syncs the repo over ssh, does the login-node half (uv, the CUDA toolkit and the three GGUF
# models into scratch) and submits one GPU job that builds the environment and proves the build
# can offload to the GPU. It prints that job's id, which `run_all.sh` takes as its dependency.
#
# Everything heavy lives in scratch: home has 26 GB free and one GGUF is seven of them. Nothing
# here reads .env or OPENROUTER_API_KEY, and the sync leaves both on the laptop.
set -euo pipefail

REMOTE=${FQ_REMOTE:-hpi-login}
ROOT=${FQ_ROOT:-/sc/scratch/rahul.singh}
ACCOUNT=${FQ_ACCOUNT:-sci-lippert-intelligent-agents}
PARTITION=${FQ_PARTITION:-gpu-batch}
GPU=${FQ_GPU:-rtx_pro_6000}
REPO=$ROOT/finquery
MODELS=$ROOT/finquery-models
LOGS=$REPO/training/cluster/logs

CUDA_VERSION=12.8.1
CUDA_RUNFILE=cuda_12.8.1_570.124.06_linux.run
CUDA_HOME=$ROOT/cuda-$CUDA_VERSION
# 8.0 is the A100 every benchmark job runs on. 9.0, 10.0 and 12.0 are the GH200, B200 and
# RTX PRO 6000 nodes, so the same build still runs if a job is sent to one of those.
ARCHES=${FQ_CUDA_ARCHES:-80;90;100;120}

step() { printf '\n== %s\n' "$*"; }

sync_repo() {
  step "syncing the repo to $REMOTE:$REPO"
  local here
  here=$(cd "$(dirname "$0")/../.." && pwd)
  ssh "$REMOTE" "mkdir -p '$REPO' '$MODELS' '$LOGS'"
  # The job needs the code, the synthetic year and the two benchmark sets. It never needs the
  # key, the weights, the private fixtures or anything either machine built for itself.
  rsync -az --delete --delete-excluded \
    --exclude '.venv' --exclude 'node_modules' --exclude 'models' --exclude 'data' \
    --exclude 'fixtures/private' --exclude '.env' --exclude '.git' --exclude '__pycache__' \
    --exclude 'frontend/dist' --exclude 'training/cluster/logs' \
    "$here/" "$REMOTE:$REPO/"
}

install_uv() {
  step "uv"
  export PATH="$ROOT/uv/bin:$PATH"
  if [ ! -x "$ROOT/uv/bin/uv" ]; then
    # The standalone installer, into scratch. There is no module system, and /sc/home is
    # mounted noexec, so a copy of uv in the home directory cannot be run at all.
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$ROOT/uv/bin" sh
  fi
  uv --version
}

install_cuda() {
  step "the CUDA toolkit in $CUDA_HOME"
  if [ -x "$CUDA_HOME/bin/nvcc" ]; then
    "$CUDA_HOME/bin/nvcc" --version | tail -2
    return
  fi
  # The nodes carry the driver and nothing else: no nvcc, no headers, no module system. The
  # runfile installs the toolkit alone, which needs no root as long as it stays out of /usr.
  if [ ! -f "$ROOT/$CUDA_RUNFILE" ]; then
    curl -sSL --retry 3 -o "$ROOT/$CUDA_RUNFILE" \
      "https://developer.download.nvidia.com/compute/cuda/$CUDA_VERSION/local_installers/$CUDA_RUNFILE"
  fi
  sh "$ROOT/$CUDA_RUNFILE" --silent --toolkit --toolkitpath="$CUDA_HOME" \
    --defaultroot="$CUDA_HOME" --no-man-page --override
  # Everything the installer writes into this scratch lands as 600, whatever the umask says, so
  # nvcc cannot be run until the execute bit is put back on the programs and the libraries.
  find "$CUDA_HOME" -type d -exec chmod u+rwx {} +
  find "$CUDA_HOME/bin" "$CUDA_HOME/nvvm/bin" -type f -exec chmod u+x {} +
  find "$CUDA_HOME" -type f -name '*.so*' -exec chmod u+x {} +
  # Only once nvcc really runs is the 5 GB installer worth deleting.
  "$CUDA_HOME/bin/nvcc" --version | tail -2
  rm -f "$ROOT/$CUDA_RUNFILE"
}

# The files to have on disk, read out of the app's own catalog so the two never drift: one line
# per file, "<model directory> <repo id> <file name> <size>".
catalog() {
  python3 - "$REPO/src/finquery/local/catalog.py" <<'PY'
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
for block in text.split("ModelSpec(")[1:]:
    name = re.search(r'name="([^"]+)"', block).group(1)
    for repo, filename, size in re.findall(r'repo_id="([^"]+)",\s*filename="([^"]+)",\s*size=(\d+)', block):
        print(name, repo, filename, size)
PY
}

download_models() {
  step "the GGUF files in $MODELS"
  local name repo file size out actual
  while read -r name repo file size; do
    out=$MODELS/$name/$file
    mkdir -p "$MODELS/$name"
    if [ -f "$out" ] && [ "$(stat -c %s "$out")" = "$size" ]; then
      echo "have $name/$file"
      continue
    fi
    echo "downloading $name/$file ($((size / 1000000)) MB)"
    curl -sSL --retry 5 --retry-delay 5 -C - -o "$out" "https://huggingface.co/$repo/resolve/main/$file"
    actual=$(stat -c %s "$out")
    if [ "$actual" != "$size" ]; then
      echo "$name/$file is $actual bytes, the catalog says $size" >&2
      exit 1
    fi
    echo "done $name/$file"
  done < <(catalog)
  du -sh "$MODELS"/*
}

build_environment() {
  step "the environment on $(hostname)"
  nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv
  export PATH="$CUDA_HOME/bin:$ROOT/uv/bin:$PATH"
  export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
  export CUDA_HOME
  # Home has 26 GB free and a wheel cache is gigabytes, so uv keeps everything in scratch.
  export UV_CACHE_DIR="$ROOT/uv-cache"
  export UV_PYTHON_INSTALL_DIR="$ROOT/uv-python"
  # llama-cpp-python ships no CUDA wheel, so `uv sync` builds it here from its sdist. These are
  # the flags that decide whether the GPU is used at all.
  export CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=$ARCHES -DCMAKE_CUDA_COMPILER=$CUDA_HOME/bin/nvcc"
  export FORCE_CMAKE=1
  cd "$REPO"
  time uv sync --group dev
  step "does the build see the GPU"
  uv run python - <<'PY'
import llama_cpp

if not llama_cpp.llama_supports_gpu_offload():
    raise SystemExit("llama-cpp-python was built without CUDA: nothing would run on the GPU")
print("llama-cpp-python", llama_cpp.__version__, "offloads to the GPU")
PY
  echo "setup done"
}

case "${1:-}" in
  --on-cluster)
    install_uv
    install_cuda
    download_models
    ;;
  --build)
    build_environment
    ;;
  "")
    sync_repo
    ssh "$REMOTE" "bash '$REPO/training/cluster/setup.sh' --on-cluster"
    step "the build job"
    job=$(ssh "$REMOTE" "sbatch --parsable --account=$ACCOUNT --partition=$PARTITION --nodes=1 \
      --gres=gpu:$GPU:1 --job-name=fq-setup --cpus-per-task=16 --mem=64G --time=02:00:00 \
      --output='$LOGS/setup-%j.out' --wrap=\"bash '$REPO/training/cluster/setup.sh' --build\"")
    echo "job $job builds the environment; follow it with"
    echo "  ssh $REMOTE tail -f $LOGS/setup-$job.out"
    echo "then: bash training/cluster/run_all.sh --after $job"
    ;;
  *)
    echo "usage: setup.sh [--on-cluster|--build]" >&2
    exit 2
    ;;
esac
