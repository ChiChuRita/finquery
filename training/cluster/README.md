# The benchmark and the training loop on the HPI cluster

Two halves that share one repository on scratch, one environment and one set of facts about the
cluster. The **benchmark** half scores local candidates on the same sets with the same runtime
the product ships: Q4_K_M through llama-cpp with CUDA, one model per job, all layers on the GPU,
32k context. The **training** half turns samples into a LoRA adapter, scores every checkpoint,
converts the best one to GGUF and benchmarks it against the vanilla base with the first half.

No vLLM, no hosted model, no OpenRouter key: every job refuses to start if `OPENROUTER_API_KEY`
is set or if a `.env` reached the cluster.

## The four commands of the training half

```bash
bash training/cluster/setup.sh --training        # the HF bases and the training environment
bash training/cluster/smoke_train.sh             # the whole loop on 40 rows, half an hour
ssh hpi-login sbatch --export=ALL,FQ_CONFIG=configs/query-e4b.yaml \
  /sc/scratch/rahul.singh/finquery/training/cluster/train.sbatch   # one real adapter
bash training/cluster/run_all.sh --adapters      # before and after, per base, per task
bash training/cluster/collect.sh --adapters      # bench/results/<date>-adapters-compare.md
```

Between the third and the fourth come two steps that run on the cluster, on a GPU node:

```bash
uv run --project training/cluster python training/cluster/quick_eval.py \
  --base /sc/scratch/rahul.singh/finquery-hf/gemma-4-E4B-it \
  --checkpoint <run>/checkpoint-N --label query-e4b-e2 --out <run>/eval
bash training/cluster/convert.sh <run>/checkpoint-N query
```

## The three commands of the benchmark half

```bash
bash training/cluster/setup.sh                  # sync, uv, CUDA, the GGUFs, the build job
bash training/cluster/run_all.sh --after <job>  # the nine jobs, waiting on the setup job
bash training/cluster/collect.sh                # the results home and the comparison
```

`run_all.sh --smoke` is the fourth: five SQL cases on E4B, which is what says the environment
works before nine jobs queue behind it.

`setup.sh --sync` is the fifth: the code again and nothing else, which is what a rerun after a
fix to the benchmark needs. Collect first either way: the sync rsyncs with `--delete`, so a
result file that is only on the cluster does not survive it.

## The checkpoint rule

`train.py` writes one checkpoint per epoch. `quick_eval.py` scores each of them on a fixed set
of held-out cases cut with seed 63, and appends a row to `curve.md` beside them. **The epoch
that gets converted is the best row of that table**: the highest figure match for a query
adapter, the highest shape match and then drawn for a chart adapter. Nothing else is converted,
because a GGUF adapter per epoch is four benchmark runs per epoch and the quick evaluation
already separates them.

The quick evaluation is indicative and never the reported number. It runs on the HF weights
with transformers, and there is no GBNF grammar there: in the app llama.cpp constrains the
forced tool call into a well-formed one, and here a malformed answer is simply a miss. So a
checkpoint scores at most as well in `curve.md` as it will in the app, never better. The
reported number is `bench/results/<date>-adapters-compare.md`, which is the product's own
runtime on the converted adapter.

## The GPU budget

One GPU per training job. QLoRA at these sizes is a lunch break on one card, not an overnight
job on four: the research note puts an adapter at 25 to 50 minutes on an A100 and 12 to 25 on
an H100, and the smoke run measured E4B at 22 seconds a step on one H100 at an effective batch
of 16. Four jobs in parallel, one per adapter, is the whole budget of a training round.

`train.sbatch` asks for `aisc-batch` and one H100 80 GB. That partition takes this account's
jobs (probed on 2026-09-06 with a ten minute job, 2514755 on gx08) and it is where the H100s
are. `FQ_TRAIN_PARTITION=gpu-batch FQ_TRAIN_GPU=a100` is the fallback; the RTX PRO 6000 nodes
of `gpu-batch` work too and are slower. The benchmark jobs stay on `gpu-batch` with one
RTX PRO 6000, because every job of one comparison has to be on one GPU type.

## How to add a data round

1. Ticket 62's `training/data/assemble.py` writes a new `query.jsonl` and `chart.jsonl`.
2. rsync them to `/sc/scratch/rahul.singh/finquery-training/data/`, which is where the four
   configs point. Nothing else changes: the config names the file, not the round.
3. Resubmit `train.sbatch` per config. The output directory is per adapter, so a second round
   overwrites the first; rename it in the config if both are wanted side by side.
4. Quick-evaluate every checkpoint, read `curve.md`, convert the best one, run
   `run_all.sh --adapters` and `collect.sh --adapters`.

The learning curve of section 7 of the research note is the same loop with `--samples` pointed
at nested subsets of the same file and `--output` per subset: five runs per adapter, one table.

## What runs where

Nothing runs on the laptop but ssh, rsync, the unit tests and `finquery-bench compare`.

| | where | what |
| --- | --- | --- |
| `setup.sh` | laptop, then the login node, then one GPU job | rsync, uv into scratch, the CUDA toolkit into scratch, the GGUFs from Hugging Face, `uv sync` with `GGML_CUDA=on` |
| `setup.sh --training` | laptop, then the login node, then one GPU job | the two gated Gemma 4 bases in bf16, then `uv sync` of `training/cluster/pyproject.toml` |
| `bench.sbatch` | one GPU job | one model, one set, optionally one adapter |
| `train.sbatch` | one GPU job | one adapter from one YAML, one checkpoint per epoch |
| `quick_eval.py`, `convert.sh` | one GPU job | the curve, then the conversion and its checks |
| `run_all.sh`, `collect.sh`, `smoke_train.sh` | laptop | submit and bring the results home |

Paths on the cluster, all in scratch because home has 26 GB free and one GGUF is seven of them:

```
/sc/scratch/rahul.singh/finquery            the repo (no .env, no weights, no node_modules)
/sc/scratch/rahul.singh/finquery-models     the GGUFs, laid out as FINQUERY_MODELS_DIR expects
/sc/scratch/rahul.singh/finquery-models-*   one per base whose adapters are being scored
/sc/scratch/rahul.singh/finquery-hf         the bf16 bases: gemma-4-E4B-it 15 GB, 12b-it 23 GB
/sc/scratch/rahul.singh/finquery-training   data/, runs/ and smoke/: the samples and the runs
/sc/scratch/rahul.singh/hf-cache            HF_HOME, so nothing is written into the home dir
/sc/scratch/rahul.singh/llama.cpp           the checkout convert_lora_to_gguf.py comes from
/sc/scratch/rahul.singh/cuda-12.8.1         the CUDA toolkit (the nodes carry only the driver)
/sc/scratch/rahul.singh/uv, uv-cache        uv and its cache
.../finquery/training/cluster/logs          the job logs, which stay here
```

The Gemma 4 repositories are gated. `setup.sh --hf-bases` reads the token from
`~/.cache/huggingface/token` on the cluster and hands it to the downloader through the
environment. It is never written into the repository, into a job script or into a log.

`adapters/query.gguf` is keyed by sub-agent and not by base, because in the app there is one
base for adapters: the fast slot. Scoring two bases needs two files, so a base other than E4B
gets its own models directory whose weights are symlinks to the one copy on scratch and whose
`adapters/` is its own. `convert.sh` lays it out and `run_all.sh --adapters` points each job at
the right one.

## The facts the scripts are built on

- Slurm needs `--account=sci-lippert-intelligent-agents` and `--nodes=1` beside a `--gres`.
- `gpu-shortrun` takes no batch jobs (interactive only) and caps a job at one hour, so the jobs
  go to `gpu-batch`, which is the same nodes with a seven day limit.
- Every job asks for the same GPU, so the median seconds of two models are seconds on one GPU.
  It is one RTX PRO 6000 (`--gres=gpu:rtx_pro_6000:1`): the partition's twenty A100s were all
  allocated when this ran, and there were free Blackwell cards. The build is compiled for 8.0,
  9.0, 10.0 and 12.0, so a rerun on the A100, B200 or GH200 nodes needs no rebuild, but every
  job of one comparison has to be on one type.
- The nodes have the driver and nothing else: no `module`, no `nvcc`, no CUDA headers. The
  toolkit is installed from NVIDIA's runfile into scratch, which needs no root.
- `/sc/home` is mounted `noexec`, so uv, its Python and the virtual environment all live in
  scratch. A binary in the home directory cannot be run at all, whatever its mode bits say.
- The nodes reach PyPI and Hugging Face, but the benchmark and training jobs run
  `uv run --offline` with `HF_HUB_OFFLINE=1`: a run whose weights are not the ones that were
  checked is not a run, and neither is one that resolves packages while it trains.
- `aisc-batch` takes this account's jobs. Probed on 2026-09-06 with a ten minute job (2514755,
  gx08): one H100 80 GB, compute capability 9.0, COMPLETED. Its nodes are `gx07` to `gx14` with
  eight H100s each, plus an L40 and an A30 node. `gpu-batch` has the A100s, the B200s, the
  GH200s and the RTX PRO 6000s. Training goes to `aisc-batch`, benchmarks stay on `gpu-batch`.
- The training environment is built on a GPU node and not on the login node, because
  bitsandbytes loads its CUDA kernels on import and a login node has no GPU to load them for.
  It took 1 minute 45 on an H100, including the torch download.
- `hf download` takes one `--exclude` per pattern. A second pattern after the first is read as
  a file name to download, and the command then fails looking for a file called `original/*`.
- `setup.sh --sync` copies the code and never the environment. A ticket that adds a dependency
  to the product (ticket 58 added `python-docx`) leaves the cluster's environment behind, and
  the next `uv run --offline` fails on a missing wheel rather than resolving it. Resubmit
  `setup.sh --build`, which is 1.5 seconds from the uv cache in scratch, and
  `setup.sh --build-training` for the other environment.

## The sets

`--set sql` is 152 questions and `--set chart` 73 chart requests, both through the sub-agent
path the app uses. `--set e2e` is 30 cases (15 and 15) drawn from the training half of those two
sets and run through the whole chat turn, with the candidate as the chat model and as the
sub-agent model. The sub-agent tables are the primary numbers; the end-to-end table is the
routing and phrasing loss on top of them.

## The decision rule

Accuracy first, on the SQL set and then the chart set. Speed breaks a tie only inside about five
points. The pair the product ships is the fast slot (Gemma 4 E4B) plus one chat model, and it
has to fit in about 13.5 GB, which is what the 24 GB Mac has left for both models at 32k.
