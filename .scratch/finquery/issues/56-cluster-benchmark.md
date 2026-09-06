# 56: The benchmark on the HPI cluster, for the three local candidates

**What to build:** One command that benchmarks Gemma 4 E4B, Qwen3.5 9B and Gemma 4 12B on the SQL set and the chart set on the HPI cluster, with the product's own runtime (llama-cpp, the same Q4_K_M GGUFs and wire formats as the laptop), plus a small end-to-end subset that runs the chat agent's turn in front of the sub-agent. Results come back into `bench/results/` as a comparison table that decides which pair the product ships. Grilled with the user on 2026-09-06; decisions below are settled.

**Blocked by:** 38, 40, 41, 42 (merged); 54 (catalog keys for `--model`, merge main when it lands)

**Status:** ready-for-agent

Decisions, settled:
- Runtime: llama-cpp-python with CUDA on the cluster, the same GGUF files and `local/` wire formats as the laptop, one model per job, all layers on the GPU, the same context size as the product. No vLLM. Hosted models are not run; the OpenRouter key is never used by anything under `training/cluster/` (assert it is unset in the job environment).
- Where: `training/cluster/` holds `setup.sh` (clone or rsync the repo to `/sc/scratch/rahul.singh/finquery`, `uv sync`, build llama-cpp-python with CUDA for the node's GPU, download the three GGUFs and projectors from Hugging Face into `/sc/scratch/rahul.singh/finquery-models` using the same repo ids and file names as `local/downloads.py`, verify sizes), `bench.sbatch` (one job per model and set, `gpu-shortrun` partition with one A100 or RTX PRO 6000, a time limit that fits, logs under `training/cluster/logs/`), `run_all.sh` (submits the six sub-agent jobs and the three end-to-end jobs with `sbatch --dependency` on setup, then `collect.sh`), `collect.sh` (rsyncs the result JSON and markdown back into `bench/results/` and runs `finquery-bench compare` across the three models into `bench/results/<date>-cluster-compare.md`), and a `README.md` with the three commands and the decision rule. Home is nearly full (26 GB left); everything heavy goes to scratch.
- Model selection: `finquery-bench run --model` takes the catalog keys from ticket 54 (`local:gemma-4-e4b`, `local:qwen3.5-9b`, `local:gemma-4-12b`); until 54 is on main, run with the env overrides the local stack already reads and note it. `FINQUERY_MODELS_DIR` points at the scratch models dir.
- End-to-end subset: `--set e2e`, about 30 cases (15 SQL, 15 chart) picked with a fixed seed from the training split of each set, run through the chat agent (`chat_agent` with the scripted-free real model on both roles: the candidate as chat model and as sub-agent model) so the request the chat agent writes and the sub-agent's answer are both scored; scored with the same figure match and shape match, reported as a second table. This measures routing and phrasing loss; the sub-agent tables stay the primary numbers.
- Comparison table: per model, per set: figure match, first attempt, drawn (charts), median seconds on the cluster GPU, and the laptop tokens per second from `bench/results/20260906-local-tokens-per-second.md` as a column, plus the memory of each pair. The decision rule under the table: accuracy first, speed as a tie-breaker within about five points, the pair must fit in about 13.5 GB.
- Kept simple: no new dependency on the cluster beyond what `pyproject.toml` already has; the job scripts are plain bash; nothing runs on the laptop except ssh, rsync and the compare command.

- [ ] `training/cluster/setup.sh`, `bench.sbatch`, `run_all.sh`, `collect.sh`, `README.md`; the OpenRouter key asserted absent in jobs
- [ ] `--set e2e` in the bench with its scorer and its table; unit tests for the subset selection and the scoring, no model needed
- [ ] `--model` accepting the three catalog keys (after merging main with ticket 54), `FINQUERY_MODELS_DIR` honoured
- [ ] Setup run on the cluster over ssh (`hpi-login`, VPN is up): repo synced, environment built, three GGUFs downloaded to scratch, a smoke run of five SQL cases on E4B passing
- [ ] The nine jobs submitted and finished; results collected into `bench/results/`; the comparison table written with the decision rule; Comments with the numbers, the job times and anything that failed
