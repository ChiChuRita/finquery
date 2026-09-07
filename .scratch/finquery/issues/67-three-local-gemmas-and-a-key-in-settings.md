# 67: Three local Gemma 4 entries, one cloud entry, the OpenRouter key in Settings, adapters follow the seat

**What to build:** Qwen3.5 9B was worse than the 12B in every column of the cluster benchmark
(`bench/results/20260906-cluster-compare.md`), so it leaves the catalog and the local provider
(the `qwen` wire format goes with it). The chat picker offers four entries: **Gemma 4 E4B
(local)**, **Gemma 4 12B (local)**, **Gemma 4 26B (local)** and **Gemma 4 26B (cloud)**. The
cloud entry needs an OpenRouter key; when `.env` has none, the Settings models card takes one
and stores it in `.env` for the next start. Query and chart sub-agents ask for their LoRA
adapter on every run; the adapter attaches only when the run is on Gemma 4 E4B (the fast seat,
which the adapters were trained on), so choosing E4B as the chat model gives the fine-tuned
query and chart sub-agents, and choosing the 12B or the 26B runs them on the base weights of
that bigger model, without an audit note, because that is the rule and not a fallback.

**Blocked by:** 61 (merged)

**Status:** done

Decisions:
- E4B is one entry, `local:gemma-4-e4b`, and also the local fast slot: a chat on it holds the
  fast seat, so nothing is loaded twice. The models card shows it once.
- The default entry per provider is explicit (`Catalog.DEFAULT_KEYS`): 12B locally, 26B in the
  cloud. The order in the picker is E4B, 12B, 26B, 26B cloud.
- The 26B is `unsloth/gemma-4-26B-A4B-it-GGUF` at UD-Q3_K_XL (12.9 GB) rather than Q4_K_M
  (16.9 GB): this laptop has 24 GB and E4B stays resident next to it. Q4_K_M is the upgrade on
  a 32 GB machine; `uv run finquery-check` measures the pair on the day.
- The key from Settings is written to the `.env` the process was started with
  (`FINQUERY_KEY_FILE`, default `.env`), applied in-process at once, and never read back to the
  browser beyond its last four characters.
- Sub-agent roles keep their per-role setting; `fast` on a local entry now means the E4B entry.

- [x] Catalog: four entries, Qwen and its wire format removed, E4B a chat entry and the fast slot
- [x] Query and chart runners ask for their adapter; `LlamaCppModel._hold` attaches it on the fast seat only, no note elsewhere
- [x] `PUT` and `DELETE /api/models/openrouter-key`, persisted to the key file; the models card takes the key
- [x] Tests, CONTEXT.md, README, ADR 0013 amendment, `.env.example`, bench aliases

## Comments

Done 2026-09-07. `uv run pytest` is 463 passed (462 before, one new test on the seat rule, one on
the key endpoints, two Qwen wire-format tests gone and the E4B chat-seat test added), `tsc -b` and
`npm run build` clean, oxlint at the 36 baseline. Verified headful on port 8177 against a throwaway
database and a throwaway key file with no key: the Settings models card lists E4B once ("chat model
and sub-agent fast slot"), the 12B, the 26B (not downloaded, 0 % bars) and the cloud entry with
"no API key" and the sentence naming Settings. Saving a key made the cloud entry available, the
hint read `...9876`, the key file kept its comment and got the one line; Forget key emptied the
line and the entry read unavailable again. Screenshots in `/tmp/finquery-67/`.

Left as they were: the course docs, explainers and presentation material that describe the
2026-09-06 four-entry catalog with Qwen (history of the project, not the running app), the
recorded bench results named `local:quality`. `training/cluster/dry_load.py` looked the key up
directly, so its default moved to `local:gemma-4-e4b`.

Measured later the same day (`bench/results/20260907-local-tokens-per-second.md`): the 26B alone
generates at 38.1 tok/s and reads a prompt at 480 tok/s, faster than the 12B on both. But E4B
and the 26B loaded together fail their first decode at 32k and at 16k (`llama_decode returned
-3`), so on this 24 GB laptop the 26B cannot sit beside the resident fast slot. The pair check's
RSS figure (0.1 GB) is wrong for an mmapped model of this size and should not be read as a fit.
Open question for the user: whether a chat on the 26B should evict E4B for its duration, which
is a change to the seat rule, or whether the 26B stays a cloud-only choice on this machine.

The user asked for the cluster benchmark of the 26B and of Qwen3.8 27B (the state of the art of
that size class) before deciding whether the 12B stays. For that the `qwen` wire format is back
(`finquery.local.qwen`, tests driven directly on the model) and benchmark-only models live in
`bench/finquery_bench/candidates.py`, found by `finquery-bench --model` but never by the app.
