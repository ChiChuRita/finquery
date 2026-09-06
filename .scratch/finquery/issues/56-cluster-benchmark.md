# 56: The benchmark on the HPI cluster, for the three local candidates

**What to build:** One command that benchmarks Gemma 4 E4B, Qwen3.5 9B and Gemma 4 12B on the SQL set and the chart set on the HPI cluster, with the product's own runtime (llama-cpp, the same Q4_K_M GGUFs and wire formats as the laptop), plus a small end-to-end subset that runs the chat agent's turn in front of the sub-agent. Results come back into `bench/results/` as a comparison table that decides which pair the product ships. Grilled with the user on 2026-09-06; decisions below are settled.

**Blocked by:** 38, 40, 41, 42 (merged); 54 (catalog keys for `--model`, merge main when it lands)

**Status:** done

Decisions, settled:
- Runtime: llama-cpp-python with CUDA on the cluster, the same GGUF files and `local/` wire formats as the laptop, one model per job, all layers on the GPU, the same context size as the product. No vLLM. Hosted models are not run; the OpenRouter key is never used by anything under `training/cluster/` (assert it is unset in the job environment).
- Where: `training/cluster/` holds `setup.sh` (clone or rsync the repo to `/sc/scratch/rahul.singh/finquery`, `uv sync`, build llama-cpp-python with CUDA for the node's GPU, download the three GGUFs and projectors from Hugging Face into `/sc/scratch/rahul.singh/finquery-models` using the same repo ids and file names as `local/downloads.py`, verify sizes), `bench.sbatch` (one job per model and set, `gpu-shortrun` partition with one A100 or RTX PRO 6000, a time limit that fits, logs under `training/cluster/logs/`), `run_all.sh` (submits the six sub-agent jobs and the three end-to-end jobs with `sbatch --dependency` on setup, then `collect.sh`), `collect.sh` (rsyncs the result JSON and markdown back into `bench/results/` and runs `finquery-bench compare` across the three models into `bench/results/<date>-cluster-compare.md`), and a `README.md` with the three commands and the decision rule. Home is nearly full (26 GB left); everything heavy goes to scratch.
- Model selection: `finquery-bench run --model` takes the catalog keys from ticket 54 (`local:gemma-4-e4b`, `local:qwen3.5-9b`, `local:gemma-4-12b`); until 54 is on main, run with the env overrides the local stack already reads and note it. `FINQUERY_MODELS_DIR` points at the scratch models dir.
- End-to-end subset: `--set e2e`, about 30 cases (15 SQL, 15 chart) picked with a fixed seed from the training split of each set, run through the chat agent (`chat_agent` with the scripted-free real model on both roles: the candidate as chat model and as sub-agent model) so the request the chat agent writes and the sub-agent's answer are both scored; scored with the same figure match and shape match, reported as a second table. This measures routing and phrasing loss; the sub-agent tables stay the primary numbers.
- Comparison table: per model, per set: figure match, first attempt, drawn (charts), median seconds on the cluster GPU, and the laptop tokens per second from `bench/results/20260906-local-tokens-per-second.md` as a column, plus the memory of each pair. The decision rule under the table: accuracy first, speed as a tie-breaker within about five points, the pair must fit in about 13.5 GB.
- Kept simple: no new dependency on the cluster beyond what `pyproject.toml` already has; the job scripts are plain bash; nothing runs on the laptop except ssh, rsync and the compare command.

- [x] `training/cluster/setup.sh`, `bench.sbatch`, `run_all.sh`, `collect.sh`, `README.md`; the OpenRouter key asserted absent in jobs
- [x] `--set e2e` in the bench with its scorer and its table; unit tests for the subset selection and the scoring, no model needed
- [x] `--model` accepting the three catalog keys (after merging main with ticket 54), `FINQUERY_MODELS_DIR` honoured
- [x] Setup run on the cluster over ssh (`hpi-login`, VPN is up): repo synced, environment built, three GGUFs downloaded to scratch, a smoke run of five SQL cases on E4B passing
- [x] The nine jobs submitted and finished; results collected into `bench/results/`; the comparison table written with the decision rule; Comments with the numbers, the job times and anything that failed

## Comments

**2026-09-06, implementation agent.** Done on branch `worktree-agent-a3a122a6b8be1309d`. Main was
merged first for ticket 54, so `--model` reads the catalog keys rather than env overrides. The
key never left the laptop: every job asserts `OPENROUTER_API_KEY` is unset and that no `.env`
reached the cluster, and both assertions are in `bench.sbatch` before anything else runs.

### The comparison

`bench/results/20260906-cluster-compare.md`, written by `collect.sh`. All nine runs on one
RTX PRO 6000 on gx32, Q4_K_M, 32k context, one model per job.

| model | sql figure match | chart figure match | chart drawn | e2e figure match | median s (sql / chart / e2e) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemma 4 E4B | 66 % | 45 % | 90 % | 53 % | 8.2 / 34.9 / 34.3 |
| Qwen3.5 9B | 70 % | 42 % | 78 % | 73 % | 25.4 / 45.1 / 50.8 |
| **Gemma 4 12B** | **87 %** | **81 %** | **94 %** | **77 %** | 10.0 / 46.7 / 46.9 |

152 questions, 73 charts, 30 end-to-end cases per model. First attempt on the SQL set: E4B 75 %,
Qwen 30 %, the 12B 82 %. Qwen writes a statement that runs and then rewrites it: 97 % valid SQL
and 30 % first attempt is the check pass of ticket 40 sending it back, which is also why its SQL
run took 87 minutes against the 12B's 31.

**The decision the rule gives: Gemma 4 E4B as the fast slot and Gemma 4 12B as the chat model.**
Accuracy first, and the 12B is 17 points ahead of Qwen on the SQL set and 39 on the chart set,
which is nowhere near the five point band where speed breaks a tie. The pair is about 12.9 GB
against the 13.5 GB ceiling, so it fits, and it is the cheaper pair on the laptop as well
(22.4 tok/s generation against Qwen's 29.5, but 12.9 GB against 13.5 GB).

This contradicts ticket 23, which made Qwen3.5 9B the quality slot on memory alone: Gemma 4 12B
at 32k did not fit at the time, and the ADR 0006 table says so. It fits now, and on the numbers
it should be the entry the demo runs. That is a product decision, not this ticket's, so it is
written down here rather than acted on.

### The end-to-end subset

`--set e2e`, 30 cases (15 questions, 15 chart requests) from the training half of each set, cut
with a fixed seed and stratified over the eight kinds and the shapes. The whole chat turn runs
in front of the sub-agent, the candidate answering both roles.

It measures what it was built to measure. E4B loses 13 points against its own SQL number and
gains 8 on charts, and the miss list says why in words: "the turn never called query, it called
chart" (`s22-account-months-de`), and a follow-up it never routed. Qwen gains 3 points over its
sub-agent SQL number and 31 over its chart number, because the chat agent writes the sub-agent a
sharper request than the benchmark's raw question. The 12B is level with itself, 77 % against
87 % and 81 %.

One correction during the run: a follow-up datapoint ("Und wie oft war ich dort einkaufen?") is
not a turn that stands on its own, and the first e2e run scored every follow-up as a miss for a
reason that had nothing to do with the model. The earlier questions now ride in on the user's
own message, the way a conversation would have them, which is the same information
`run.PREFIX_HINT` gives the sub-agent. All three e2e runs are from after that fix.

### The cluster

Paths, all in scratch: `/sc/scratch/rahul.singh/finquery` (the repo, no `.env`, no weights),
`finquery-models` (18.6 GB of GGUFs, laid out as `FINQUERY_MODELS_DIR` expects),
`cuda-12.8.1`, `uv`, `uv-cache`. Home was never touched beyond reading: it has 26 GB free.

Four things about this cluster are worth keeping, and all four are in
`training/cluster/README.md`:

- `/sc/home` is mounted **noexec**. There is a `uv` in `~/.local/bin` that cannot be run at all,
  so uv, its Python and the virtual environment all live in scratch.
- There is no module system and no CUDA toolkit on the nodes, only the driver (590.48, CUDA
  13.1). The toolkit is installed from NVIDIA's 12.8.1 runfile into scratch, which needs no root.
- Everything the installer writes into this scratch lands as mode 600 whatever the umask says.
  nvcc is not one program: the first build failed after four minutes because `cicc`, `cudafe++`
  and `bin2c` had no execute bit, and CMake reported it as "Compiling the CUDA compiler
  identification source file failed". Setup now puts the bit back on every run.
- `gpu-shortrun` takes no batch jobs (it is interactive only) and caps a job at an hour, which
  the SQL set on a 9B does not fit into. The jobs go to `gpu-batch`. Every A100 in that
  partition was allocated all afternoon, so all nine jobs asked for one RTX PRO 6000 instead:
  one GPU type for the whole comparison is what the speed column needs, and which type matters
  less than that.

The build is compiled for 8.0, 9.0, 10.0 and 12.0, so a rerun on the A100, B200 or GH200 nodes
needs no rebuild.

### Job times

Setup: 11 minutes for the CUDA build of llama-cpp-python, 16 seconds for a rebuild from the uv
cache. Smoke run: five SQL cases on E4B, 5 of 5 right, 58 seconds.

| job | model, set | elapsed |
| --- | --- | ---: |
| 2513738 | E4B sql | 23:54 |
| 2513739 | E4B chart | 49:54 |
| 2513766 | E4B e2e | 15:29 |
| 2513741 | Qwen sql | 1:26:59 |
| 2513763 | Qwen chart | 1:08:24 |
| 2513767 | Qwen e2e | 34:48 |
| 2513764 | 12B sql | 31:13 |
| 2513765 | 12B chart | 1:00:48 |
| 2513768 | 12B e2e | 22:41 |

All nine COMPLETED. About seven hours of GPU time in total, most of it queued behind one card.

### What went wrong on the way

Three of my own mistakes, all fixed in the scripts:

1. `rsync --delete-excluded` deletes the excluded paths **at the destination**, which is exactly
   the virtual environment and the job logs the cluster built for itself. One sync destroyed
   both mid-run. The running jobs survived (their files were unlinked, not closed) but six
   queued jobs had to be cancelled, the environment rebuilt (16 seconds, from the cache) and the
   six resubmitted. `--delete` alone is what a code sync wants. The console logs of the three
   jobs that were running at that moment are gone; their result JSON is not, because the
   benchmark writes that itself.
2. The laptop's bash is 3.2: no associative arrays, and `set -euo pipefail` turns a glob that
   matches nothing into a dead script. Both bit `run_all.sh` and `collect.sh` once each.
3. The first CUDA build was submitted asking for an A100 and sat in the queue; the permission
   problem above cost a second build. Neither is a code problem, but both are why `setup.sh`
   prints its job id and `run_all.sh` takes `--after`.

### Numbers that are not in the table

The two files under `bench/results/` with `n` of 5 and `n` of 2 are the smoke run and a
two-case end-to-end probe, kept because they are what said the environment worked before nine
jobs queued behind it. `collect.sh` takes the newest run per model and set, so they are not in
the comparison.
