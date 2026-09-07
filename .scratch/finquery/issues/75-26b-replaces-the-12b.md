# 75: Gemma 4 26B A4B replaces the 12B as the smart model

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

**Status:** done

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
  amendment dated 2026-09-07 (ticket 75) with the decision and the numbers, and a pointer in ADR
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

- [x] Catalog and candidates moved; `key_of` test for a stored 12B key; suite green
- [x] Cluster scripts and docstrings updated; `bash -n` on the shell scripts
- [x] CLAUDE.md, README, CONTEXT.md, demo script, .env.example, ADR 0013 amendment, ADR 0006 pointer
- [x] Comments note here, with the files the user may delete

## Comments

Done 2026-09-07. `LOCAL_CHAT_MODELS` is `(LOCAL_GEMMA_26B,)` and `Catalog.DEFAULT_KEYS["local"]`
is `local:gemma-4-26b`, so the catalog is three entries: E4B, the local 26B A4B and the cloud
26B. The `LOCAL_GEMMA_12B` spec moved to `bench/finquery_bench/candidates.py` unchanged, key,
name, files and hashes, and joined `CANDIDATES`, so `finquery-bench --model local:gemma-4-12b`
and `run_all.sh` still resolve and every recorded run still names the model it was scored on.
Nothing in `src/` imports from `bench/`.

What changed:
- `src/finquery/local/catalog.py`: the 12B spec is gone, `LOCAL_CHAT_MODELS` is the 26B alone,
  docstrings say why.
- `src/finquery/catalog.py`: the local default key, and the docstrings that named the 12B as
  shipped. `key_of` needed no change; it already maps any key the catalog dropped.
- `bench/finquery_bench/candidates.py`, `models.py`, `cli.py`, `bench/README.md`: the 12B as a
  candidate, in the docstrings and the `--model` help.
- `src/finquery/settings.py`, `providers.py`, `context.py`, `local/__init__.py`, `local/model.py`,
  `local/runtime.py`: docstring and comment wording only.
- Tests: the entries and `loaded` lists shrink to two local entries (`test_model_catalog.py`,
  `test_local_provider.py`, `test_chat.py` health), `GEMMA` in `test_local_provider.py` is now
  the 26B key and the `BIG` stand-in is gone, the one-model swap test keeps three specs by
  importing the 12B from the candidates module, and one new test says a conversation and a
  profile default stored on `local:gemma-4-12b` read as `local:gemma-4-26b` on the local
  provider. `test_bench.py` also asserts the 12B resolves as a candidate and is not a catalog
  entry. Three tests in `test_chat.py` and `test_conversations.py` indexed the entries list at
  `keys[3]`; they take `keys[-1]` now.
- Docs: `CLAUDE.md` (two local entries, the 26B as the local default and the same model the
  cloud runs), `README.md` catalog table (three rows) and the local-run paragraphs, `CONTEXT.md`
  (catalog entry and seat), `.env.example`, `docs/demo-script.md` (the demo starts on the 26B,
  the laptop tok/s numbers, "to time" where a step was only ever measured on the 12B), a ticket
  73 amendment on ADR 0013 and a pointer line in ADR 0006's ticket 61 amendment.
- Cluster: `run_all.sh`'s default `MODELS` is now `local:gemma-4-e4b local:gemma-4-26b
  local:gemma-4-12b` (it still named `local:qwen3.5-9b`, which has resolved to nothing since
  ticket 67), and the comments in `run_all.sh` and `bench.sbatch` that called the 12B a shipped
  model. `bash -n` clean on both.
- Frontend, comments and one line of card text: `models-card.tsx` said "a chat on the 12B or
  the 26B runs them on that model's own weights", `api.ts`, `catalog.ts` and `onboarding.tsx`
  had counts and an example key in comments. `npx oxlint` exits 0 with the usual 36 warnings;
  `tsc -b` was not run, this worktree has no `node_modules`.

Tests: 464 passed, 3 skipped (`uv run pytest -q --ignore=tests/test_local_smoke.py`). The
baseline at 40b1b2b was 463; the new `key_of` test is the difference.

Weights you may delete on the laptop: `models/gemma-4-12b-it` (7.1 GB plus its projector) and
`models/Qwen3.5-9B`. Nothing the app runs wants either one. A benchmark run of the 12B candidate
would download it again, which is why nothing here removes it.

Two things the ticket asked for that I could not do as written:
- There is no recorded 26B result file in `bench/results/`. The 79 percent SQL, the 67
  end-to-end and the 12B's 78 percent baseline are the ticket's own numbers; the tok/s figures
  are in `20260907-local-tokens-per-second.md` and the 12B's 78 percent is in
  `20260907-adapters-compare.md`. Where I needed a citation for the 26B accuracy I wrote "the
  26B SQL run of 2026-09-07 (ticket 75)" rather than pointing at a file that is not there. Drop
  the run's md and json into `bench/results/` and those references can name it.
- The course documents were left alone: `docs/explainers/`, `docs/course/project-status.md`,
  `docs/presentation/`, `docs/guide/finquery-guide.html` and
  `docs/research/finetuning-data-2026-09-06.md` still describe the 12B as the shipped model.
  They are dated records of what was decided and measured when, the ticket does not list them,
  and rewriting them is a bigger job than this one. `docs/explainers/16` also names the
  `LOCAL_GEMMA_12B` symbol, which now lives in the candidates module.
