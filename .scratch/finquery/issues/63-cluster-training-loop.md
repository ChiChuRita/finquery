# 63: The training loop on the cluster: QLoRA, checkpoint quick eval, conversion, official run

**What to build:** `training/cluster/` grows the fine-tuning half: base weights on the cluster, a QLoRA training job per adapter per base with per-epoch checkpoints, a quick evaluation of every checkpoint with the HF weights on a fixed 100-case set, conversion of the best checkpoint to a GGUF adapter, and the official llama-cpp benchmark of base plus adapter against the vanilla base with the existing scripts. Smoke-tested end to end on a tiny set before any real data exists. Settled with the user on 2026-09-06 (see `.scratch/finquery/training-plan.md`).

**Blocked by:** 56 (merged), 57 (research), 62 (the sample format; use its schema once merged, a tiny hand-written sample file until then)

**Status:** ready-for-agent

Decisions:
- Bases: `google/gemma-4-E4B-it` and `google/gemma-4-12b-it` HF weights downloaded on the cluster into `/sc/scratch/rahul.singh/finquery-hf` (they are gated: use the Hugging Face token found in `~/.cache/huggingface/token` on the laptop or the cluster if present; if none, stop and report, the coordinator asks the user). The Q4_K_M GGUFs already on scratch stay the inference bases.
- Training stack: TRL `SFTTrainer` with PEFT QLoRA (4-bit NF4 base, bf16 compute), completion-only loss on the chat-format samples, rank 16 alpha 32 dropout 0.05 for E4B and rank 32 alpha 64 for the 12B, learning rate 2e-4 with cosine and 3 percent warmup, sequence length 4096 (the prompts are about 3,000 tokens), effective batch 16, 3 epochs, a checkpoint per epoch, gradient checkpointing, no `rank_pattern`, `rslora` or `dora` (the GGUF converter ignores them silently), target modules attention and MLP projections only (never embeddings or the head, which the converter rejects). Everything in `training/cluster/train.py` driven by a small YAML per adapter under `training/cluster/configs/`. `uv` environment on scratch with torch, transformers, peft, trl, bitsandbytes pinned; a separate `pyproject` under `training/cluster/` so the product's lock stays lean.
- Quick eval `training/cluster/quick_eval.py`: loads base plus a checkpoint with transformers, generates for a fixed set of 100 cases (50 SQL, 50 chart, chosen from the held-out set by a fixed seed once the split is frozen; until then from the current held-out), runs the guard and the benchmark's scorers, writes `quick-<adapter>-<epoch>.json` and a curve `curve.md`. Indicative only; the GGUF run is the reported number.
- Conversion `training/cluster/convert.sh`: `convert_lora_to_gguf.py` from the llama.cpp checkout already on scratch, f16, then a dry-run load with llama-cpp-python and a five-case smoke through `finquery-bench run --model local:<base> --adapter <name> --n 5`; the research note's pitfalls checked (no embedding tensors, one global alpha).
- Official run: `bench.sbatch` gains an adapter argument; `run_all.sh` gets a `--adapters` mode that runs base and base plus adapter for both tasks on both bases; `collect.sh` and `compare` produce `bench/results/<date>-adapters-compare.md` with before and after per base per task.
- Slurm: one GPU per training job (A100 80 GB or H100 where the partition allows, RTX PRO 6000 otherwise), four jobs in parallel, `gpu-batch` with a 12 hour limit, logs on scratch. The coordinator submits the real runs; this ticket submits only smoke jobs.
- Smoke: `training/cluster/smoke_train.sh` trains E4B on a 40-sample hand-written file for 20 steps, quick-evals it on 5 cases, converts, loads, runs 5 benchmark cases with the adapter, all on one GPU in under 30 minutes, and reports each step's result. This must pass before ticket 65.
- No OpenRouter key anywhere near the cluster (asserted in every job). No em dashes anywhere.

- [ ] HF bases on scratch (or a clear stop if the token is missing); training environment built on a GPU node; `train.py` and the four configs
- [ ] `quick_eval.py` with the curve output; `convert.sh` with the pitfall checks; `bench.sbatch`, `run_all.sh --adapters`, `collect.sh`, `compare` for before and after
- [ ] `smoke_train.sh` passing end to end on the cluster with timings in Comments
- [ ] `training/cluster/README.md` updated: the four commands, the checkpoint rule (best quick-eval epoch is converted), the GPU budget, how to add a data round
