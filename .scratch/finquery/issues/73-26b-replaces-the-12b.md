# 73: Gemma 4 26B A4B replaces the 12B as the smart model

**What to build:** The catalog offers two local entries, Gemma 4 E4B (fast, the adapter target) and
Gemma 4 26B A4B (smart, the new local default), plus the cloud 26B for hosted development. Gemma 4
12B leaves the catalog. The user decided this on 2026-09-07 on the cluster numbers: on the 459
question SQL set the 26B ties the 12B (79 against 78 percent), and on the laptop it generates at
38 tok/s against 22 and reads a prompt at 480 tok/s against 205
(`bench/results/20260907-local-tokens-per-second.md`, the 26B SQL run of 2026-09-07). Its
end-to-end result is 67 against the 12B's 77 on 30 turns; the user took the speed. The 12B stays
benchmarkable as a candidate, because its recorded runs are the baseline every number is read
against.

**Blocked by:** 67, 68 (merged)

**Status:** ready-for-agent

Decisions:
- `LOCAL_GEMMA_12B` moves from `src/finquery/local/catalog.py` to `bench/finquery_bench/candidates.py`,
  keeping its key `local:gemma-4-12b`, so `finquery-bench --model local:gemma-4-12b` and the
  cluster scripts keep working and the app never lists, downloads or offers it. `LOCAL_CHAT_MODELS`
  is `(LOCAL_GEMMA_26B,)`; `Catalog.DEFAULT_KEYS["local"]` is `local:gemma-4-26b`. A conversation
  or profile default stored on `local:gemma-4-12b` reads as the default entry through `key_of`,
  which already does that for any key the catalog no longer offers; one test says so.
- `run_all.sh`'s default model list and `bench.sbatch`'s docstrings name the 12B as a candidate
  where they name it; `collect.sh` unchanged. `training/cluster/dry_load.py` unchanged.
- Docstrings and docs that call the 12B the shipped or default model move to the 26B:
  `finquery/catalog.py`, `local/catalog.py`, `settings.py` (`local_n_ctx`, the validator example),
  `local/check.py`, `CLAUDE.md` "Models for development and verification" (two local entries, the
  26B is the local default and the same model the cloud runs, E4B carries the adapters), `README.md`
  catalog table and its numbers (26B: 79 percent SQL on 459, 67 end-to-end; E4B with the query
  adapter 80), `CONTEXT.md` catalog entry list, `docs/demo-script.md` (the demo starts on the 26B;
  its timings are the laptop numbers above; the seat swap sentences), `.env.example`, ADR 0013
  amendment dated 2026-09-07 (ticket 73) with the decision and the numbers, and a pointer in ADR
  0006's ticket 61 amendment saying the pair changed again.
- Frontend: nothing names the 12B in code; check `models-card.tsx` and `catalog.ts` comments.
- Tests: `tests/test_model_catalog.py` entries list becomes E4B, 26B, cloud 26B in that order
  with local default `local:gemma-4-26b`; the one-model test keeps three swaps using the 12B spec
  from the candidates module (a stack over any specs is fine, the test builds its own model map);
  `tests/test_local_provider.py` stand-ins: `GEMMA` becomes the 26B key as the chat stand-in, the
  extra `BIG` stand-in goes, and the assertions on entries lists and `loaded` lists shrink to two
  local entries; `tests/test_chat.py` health keys; `tests/test_bench.py` candidate test also
  asserts the 12B resolves as a candidate.
- Weights on the laptop (`models/gemma-4-12b-it`, `models/Qwen3.5-9B`) are not deleted by the
  agent; the ticket comment names them for the user to remove.

- [ ] Catalog and candidates moved; `key_of` test for a stored 12B key; suite green
- [ ] Cluster scripts and docstrings updated; `bash -n` on the shell scripts
- [ ] CLAUDE.md, README, CONTEXT.md, demo script, .env.example, ADR 0013 amendment, ADR 0006 pointer
- [ ] Comments note here, with the files the user may delete
