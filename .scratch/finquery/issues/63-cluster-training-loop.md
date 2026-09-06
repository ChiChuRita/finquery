# 63: The training loop on the cluster: QLoRA, checkpoint quick eval, conversion, official run

**What to build:** `training/cluster/` grows the fine-tuning half: base weights on the cluster, a QLoRA training job per adapter per base with per-epoch checkpoints, a quick evaluation of every checkpoint with the HF weights on a fixed 100-case set, conversion of the best checkpoint to a GGUF adapter, and the official llama-cpp benchmark of base plus adapter against the vanilla base with the existing scripts. Smoke-tested end to end on a tiny set before any real data exists. Settled with the user on 2026-09-06 (see `.scratch/finquery/training-plan.md`).

**Blocked by:** 56 (merged), 57 (research), 62 (the sample format; use its schema once merged, a tiny hand-written sample file until then)

**Status:** done

Decisions:
- Bases: `google/gemma-4-E4B-it` and `google/gemma-4-12b-it` HF weights downloaded on the cluster into `/sc/scratch/rahul.singh/finquery-hf` (they are gated: use the Hugging Face token found in `~/.cache/huggingface/token` on the laptop or the cluster if present; if none, stop and report, the coordinator asks the user). The Q4_K_M GGUFs already on scratch stay the inference bases.
- Training stack: TRL `SFTTrainer` with PEFT QLoRA (4-bit NF4 base, bf16 compute), completion-only loss on the chat-format samples, rank 16 alpha 32 dropout 0.05 for E4B and rank 32 alpha 64 for the 12B, learning rate 2e-4 with cosine and 3 percent warmup, sequence length 4096 (the prompts are about 3,000 tokens), effective batch 16, 3 epochs, a checkpoint per epoch, gradient checkpointing, no `rank_pattern`, `rslora` or `dora` (the GGUF converter ignores them silently), target modules attention and MLP projections only (never embeddings or the head, which the converter rejects). Everything in `training/cluster/train.py` driven by a small YAML per adapter under `training/cluster/configs/`. `uv` environment on scratch with torch, transformers, peft, trl, bitsandbytes pinned; a separate `pyproject` under `training/cluster/` so the product's lock stays lean.
- Quick eval `training/cluster/quick_eval.py`: loads base plus a checkpoint with transformers, generates for a fixed set of 100 cases (50 SQL, 50 chart, chosen from the held-out set by a fixed seed once the split is frozen; until then from the current held-out), runs the guard and the benchmark's scorers, writes `quick-<adapter>-<epoch>.json` and a curve `curve.md`. Indicative only; the GGUF run is the reported number.
- Conversion `training/cluster/convert.sh`: `convert_lora_to_gguf.py` from the llama.cpp checkout already on scratch, f16, then a dry-run load with llama-cpp-python and a five-case smoke through `finquery-bench run --model local:<base> --adapter <name> --n 5`; the research note's pitfalls checked (no embedding tensors, one global alpha).
- Official run: `bench.sbatch` gains an adapter argument; `run_all.sh` gets a `--adapters` mode that runs base and base plus adapter for both tasks on both bases; `collect.sh` and `compare` produce `bench/results/<date>-adapters-compare.md` with before and after per base per task.
- Slurm: one GPU per training job (A100 80 GB or H100 where the partition allows, RTX PRO 6000 otherwise), four jobs in parallel, `gpu-batch` with a 12 hour limit, logs on scratch. The coordinator submits the real runs; this ticket submits only smoke jobs.
- Smoke: `training/cluster/smoke_train.sh` trains E4B on a 40-sample hand-written file for 20 steps, quick-evals it on 5 cases, converts, loads, runs 5 benchmark cases with the adapter, all on one GPU in under 30 minutes, and reports each step's result. This must pass before ticket 65.
- No OpenRouter key anywhere near the cluster (asserted in every job). No em dashes anywhere.

- [x] HF bases on scratch (or a clear stop if the token is missing); training environment built on a GPU node; `train.py` and the four configs
- [x] `quick_eval.py` with the curve output; `convert.sh` with the pitfall checks; `bench.sbatch`, `run_all.sh --adapters`, `collect.sh`, `compare` for before and after
- [x] `smoke_train.sh` passing end to end on the cluster with timings in Comments
- [x] `training/cluster/README.md` updated: the four commands, the checkpoint rule (best quick-eval epoch is converted), the GPU budget, how to add a data round

## Comments

**2026-09-06, implementation agent.** Done on branch `worktree-agent-ab477fdf6a237f45a`. The
OpenRouter key never left the laptop: `train.sbatch`, `bench.sbatch`, `smoke_train.sh`,
`convert.sh`, `train.py`, `quick_eval.py` and `dry_load.py` each refuse to start if
`OPENROUTER_API_KEY` is set, and the two job scripts also refuse a `.env` on the cluster.

### The smoke run, end to end

`smoke_train.sh`, job 2514960, one H100 80 GB on gx13v1 in `aisc-batch`. **9 minutes 11
seconds** wall, COMPLETED, every step passing.

| step | what | elapsed |
| --- | --- | ---: |
| 1 | build the 40 samples with the product's own `query_prompt` | 1.3 s |
| 2 | 20 steps on Gemma 4 E4B, QLoRA r16 | 4:47 (13.1 s per step) |
| 3 | quick eval, 3 questions and 2 chart requests, held out | 2:34 |
| 4a | `convert_lora_to_gguf.py`, f16 | 5.0 s |
| 4b | the config check, the GGUF check, the dry-run load | 12 s |
| 5 | 5 benchmark cases through `finquery-bench` with the adapter | 1:49 |

Training: 34,881,536 trainable parameters, 0.44 percent, over `q_proj, k_proj, v_proj, o_proj,
gate_proj, up_proj, down_proj` in all 42 language-model layers. Loss 0.85 at step 1 and 0.13 at
step 20, token accuracy 0.85 to 0.96, on 40 rows seen seven times, which says the loop learns
and says nothing else. Tokens per sample: p50 3812, p95 3838, p100 3906, against a sequence
length of 4096, so section 1 of the research note holds and nothing is truncated. Seven
checkpoints, one per epoch.

Quick eval of that checkpoint (`smoke/eval/curve.md`): 3 questions, 100 % a well-formed
`run_sql` call, 100 % through the guard, 67 % figure match; 2 chart requests, 100 % a
`chart_plan` call, 100 % shape match, 0 % drawn. Those are five cases after twenty steps on
forty query rows: they say the scorers run, not how good anything is.

Conversion: 516 tensors, one global alpha of 32.0, 69.8 MB. The base GGUF loaded in 10.5 s, the
adapter attached in 0.59 s through the product's own `AdapterRegistry`, generated, detached
cleanly. Then five SQL cases on `local:gemma-4-e4b+query`: **5 of 5 right, 5 of 5 on the first
attempt**, median 9.3 s.

### The cluster

New under `/sc/scratch/rahul.singh/`: `finquery-hf/gemma-4-E4B-it` (15 GB) and
`finquery-hf/gemma-4-12b-it` (23 GB), both bf16 safetensors, no GGUF and no `original/`;
`finquery-training/{data,runs,smoke}`; `triton-cache`; `cache`. The token was read from
`~/.cache/huggingface/token` on the login node and handed to `hf download` through the
environment, never written into the repo or a log.

**`aisc-batch` takes our jobs.** Probed with a ten minute job (2514755, gx08): one H100 80 GB,
compute capability 9.0, COMPLETED. Its nodes are gx07 to gx14 with eight H100s each, plus an
L40 and an A30 node. So training goes there and benchmarks stay on `gpu-batch`, where the
A100s, B200s, GH200s and RTX PRO 6000s are. Four GPUs were used in total across all smoke work,
never more than one at a time.

The training environment builds in **1 minute 45** on a GPU node from `training/cluster/uv.lock`
(torch 2.14.0+cu130, transformers 5.16.1, peft 0.20.0, trl 1.12.0, bitsandbytes 0.50.2). It is
its own `pyproject` with no llama-cpp-python: nothing that trains loads a GGUF.

### Six things the cluster's own stack decided, all now in the scripts

1. **PEFT refuses `Gemma4ClippableLinear`.** The research note said an explicit `target_modules`
   list fails on Gemma 4; it is right, and the reason is that the vision and audio towers wrap
   their projections in that class and a bare `q_proj` matches those too. But `auto` is not the
   answer either: PEFT's own default is `q_proj` and `v_proj` alone, 4.5 M parameters, 0.06
   percent, and QLoRA's finding is that rank stops mattering once every layer is adapted. The
   configs now name a regular expression anchored on `language_model.layers`, which picks the
   seven projections and nothing else, and `train.py` reads back which modules really got a
   LoRA and refuses an embedding or the head from the model rather than from the YAML.
2. **TRL 1.12 has no `warmup_ratio`,** only `warmup_steps`. The three percent the config names
   is turned into steps rather than silently dropped.
3. **Gemma 4 is multimodal,** so TRL reaches for `AutoProcessor` and `Gemma4Processor` needs
   Pillow and torchvision to import at all. The tokenizer is handed over instead, because a
   sample is two strings; both packages are in the lock anyway so a stray `AutoProcessor` is a
   mistake and not a dead job.
4. **Triton compiles a CUDA shim at the first backward pass** and needs `Python.h` for it. The
   node's `/usr/bin/python3.12` has no development headers, so the environment is pinned to
   uv's managed Python 3.12, whose headers are in scratch. Its cache goes to scratch too: the
   home directory is noexec and a cached shared object there cannot be loaded.
5. **My own GGUF check was wrong.** `attn_output.weight` ends in `output.weight`, so the first
   converted adapter failed the embedding check on all 42 attention output projections. The
   three tensors llama.cpp names the embeddings and the head are matched whole now.
6. **`setup.sh --sync` copies the code and never the environment.** Ticket 58 added
   `python-docx` to the product after the ticket 56 setup, so the cluster's environment was a
   ticket behind and `uv run --offline` failed on a missing wheel in step 4 of the conversion.
   Resubmitting `setup.sh --build` fixes it in 1.5 seconds from the uv cache. This is in the
   README.

### One product change, and one thing the coordinator should look at

`LocalStack.with_adapter` held the **fast** seat whatever model it was asked for. That is right
in the app, where every sub-agent runs on the fast slot, and wrong in the benchmark:
`--model local:gemma-4-12b --adapter query` was scoring E4B while the run claimed to be scoring
the 12B. It now holds the seat of the model it was given. One line, plus the existing tests.

The other half of "on both bases" is that `adapter_path` keys an adapter by sub-agent and not by
base, so there is one `adapters/query.gguf`. Rather than change the product's Adapter (ADR 0013
and `CONTEXT.md` both say the fast seat, and that is a product decision, not this ticket's), a
base other than E4B gets its own models directory on scratch whose weights are symlinks and
whose `adapters/` is its own. `convert.sh` lays it out and `run_all.sh --adapters` points each
job at the right one. If the 12B adapters are ever shipped rather than measured, that keying is
the thing to revisit.

### What is not proven

`run_all.sh --adapters` and `collect.sh --adapters` are written and syntax-checked but have not
been run against eight finished jobs, because there are no trained adapters to compare yet. The
half of that path that matters, `finquery-bench run --adapter` through `bench.sbatch`, ran in
step 5 of the smoke and wrote `20260906T191153Z-local-gemma-4-e4b+query-sql.json`, so the file
naming `collect.sh` looks up is the naming the runner produces. `quick_eval.py` has run on 5
cases, not on 100; the per-case cost measured there (15 s a question, 44 s a chart request on
one H100 with no grammar) puts a real 100-case quick evaluation at about 50 minutes, which is
worth knowing before ticket 65 schedules one per epoch per adapter.

The forty smoke samples are a fixture, not training data: `samples/smoke-query.json` names
forty generated datapoints in the train half of the SQL benchmark and carries the one thing the
benchmark does not, the reasoning line. `smoke_samples.py` builds the JSONL from them with the
product's own prompts, and `tests/test_training_cluster.py` fails if one of those ids ever moves
into the held-out half. Ticket 62's `assemble.py` writes the same shape and `train.py` cannot
tell the two apart.
