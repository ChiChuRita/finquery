# The benchmark on the HPI cluster

Three local candidates, scored on the same sets with the same runtime the product ships:
Gemma 4 E4B, Qwen3.5 9B and Gemma 4 12B, Q4_K_M through llama-cpp with CUDA, one model per job,
all layers on the GPU, 32k context. No vLLM, no hosted model, no OpenRouter key: the jobs refuse
to start if `OPENROUTER_API_KEY` is set or if a `.env` reached the cluster.

## The three commands

```bash
bash training/cluster/setup.sh                  # sync, uv, CUDA, the GGUFs, the build job
bash training/cluster/run_all.sh --after <job>  # the nine jobs, waiting on the setup job
bash training/cluster/collect.sh                # the results home and the comparison
```

`run_all.sh --smoke` is the fourth: five SQL cases on E4B, which is what says the environment
works before nine jobs queue behind it.

Collect before you sync again: `setup.sh` rsyncs with `--delete`, so a result file that is only
on the cluster does not survive the next sync.

## What runs where

Nothing runs on the laptop but ssh, rsync and `finquery-bench compare`.

| | where | what |
| --- | --- | --- |
| `setup.sh` | laptop, then the login node, then one GPU job | rsync, uv into scratch, the CUDA toolkit into scratch, the GGUFs from Hugging Face, `uv sync` with `GGML_CUDA=on` |
| `bench.sbatch` | one GPU job | one model, one set, one A100 |
| `run_all.sh` | laptop | submits three models times three sets |
| `collect.sh` | laptop | rsyncs the results back, writes `bench/results/<date>-cluster-compare.md` |

Paths on the cluster, all in scratch because home has 26 GB free and one GGUF is seven of them:

```
/sc/scratch/rahul.singh/finquery            the repo (no .env, no weights, no node_modules)
/sc/scratch/rahul.singh/finquery-models     the GGUFs, laid out as FINQUERY_MODELS_DIR expects
/sc/scratch/rahul.singh/cuda-12.8.1         the CUDA toolkit (the nodes carry only the driver)
/sc/scratch/rahul.singh/uv, uv-cache        uv and its cache
.../finquery/training/cluster/logs          the job logs, which stay here
```

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
- The nodes reach PyPI and Hugging Face, but the benchmark jobs run `uv run --offline`: a
  benchmark has no business resolving packages.

## The sets

`--set sql` is 152 questions and `--set chart` 63 chart requests, both through the sub-agent
path the app uses. `--set e2e` is 30 cases (15 and 15) drawn from the training half of those two
sets and run through the whole chat turn, with the candidate as the chat model and as the
sub-agent model. The sub-agent tables are the primary numbers; the end-to-end table is the
routing and phrasing loss on top of them.

## The decision rule

Accuracy first, on the SQL set and then the chart set. Speed breaks a tie only inside about five
points. The pair the product ships is the fast slot (Gemma 4 E4B) plus one chat model, and it
has to fit in about 13.5 GB, which is what the 24 GB Mac has left for both models at 32k.
