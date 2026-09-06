# 61: Ship Gemma 4 12B as the chat model, and give every sub-agent role its own model setting

**What to build:** The benchmark decided (`bench/results/20260906-cluster-compare.md`: 87 against 70 and 66 percent on SQL, 81 against 42 and 45 on charts). Gemma 4 12B becomes the default local chat model and, for the demo, the model every sub-agent runs on. Gemma 4 E4B stays resident as the fast slot and remains the adapter target. Which model a sub-agent role uses becomes one setting per role. Hosted development moves to Gemma 4 26B A4B on both cloud slots. Decided by the user on 2026-09-06.

**Blocked by:** 54, 56 (merged)

**Status:** ready-for-agent

Decisions, settled:
- Catalog defaults (`src/finquery/catalog.py`, `settings.py`): on the local provider the default entry is `local:gemma-4-12b`; Qwen3.5 9B stays a catalog entry. The two local seats stay: E4B resident on the fast seat, the chat seat holding Gemma 4 12B by default (Qwen swaps in if picked). Cloud entries: `openrouter:google/gemma-4-26b-a4b-it` (default when the provider is openrouter) and `openrouter:qwen/qwen3.5-9b`; the hosted fast slot default becomes `google/gemma-4-26b-a4b-it`.
- Sub-agent roles: a setting per role, `FINQUERY_SUBAGENT_MODEL_<ROLE>` with roles query, chart, categorizer, extraction, memory, summary, weblookup (find the exact set by grepping for `resolve("fast")` and `subagent_settings` callers), each taking `fast`, `chat` or a catalog key. Default for every role: `chat`, meaning the conversation's chat entry (Gemma 4 12B locally, Gemma 4 26B in the cloud). `fast` means the provider's fast slot as today. Resolution goes through the catalog's role resolver so the local seats and the cloud entries behave the same. Adapters still attach only on the fast slot (E4B), so a role set to `fast` with an adapter registered gets the adapter; a role on `chat` never does. The models card lists the roles and what each resolves to right now.
- Sub-agent settings: reasoning stays off for sub-agent calls whatever model they run on; `SUBAGENT_MAX_TOKENS` unchanged; the extraction page concurrency stays 4 locally.
- Local memory: Gemma 4 12B plus E4B is about 12.9 GB at 32k context each; `uv run finquery-check` verifies both load together and reports headroom. If the 12B needs a smaller context to fit next to E4B on the 24 GB machine, prefer lowering the 12B's context to 16k over evicting E4B, and say so in the check's output.
- Hosted development: `.env.example`, `CLAUDE.md` ("Models for development and verification") and the agent briefs say Gemma 4 26B A4B on both slots. The coordinator switches the live `.env`.
- Docs: ADR 0006 amended (the Qwen quality slot is superseded; the pair, the per-role setting, the benchmark as the reason, with the numbers), CONTEXT.md (sub-agent role setting), `docs/explainers/02-two-models-and-the-switch.md`, 04 and 13 (which model the sub-agents run on and why), `docs/demo-script.md` (start on Gemma 4 12B, the sample import is slower, say the numbers), README model table.
- Benchmarks: `finquery-bench run --model` and the cluster scripts keep working; add `--subagent-model` only if the run function needs it to reproduce "chat and sub-agent on the same model", otherwise the catalog key already covers it.

- [ ] Catalog defaults and cloud entries; `.env.example`; tests updated (default entry per provider, cloud entries listed)
- [ ] Per-role sub-agent model setting with `chat` as the default and `fast` as the option; every sub-agent call site goes through it; adapters only on `fast`; models card shows the roles; HTTP-seam tests with scripted models asserting which model each role resolved to for `chat`, `fast` and a catalog key
- [ ] `finquery-check` loads both local models together and reports headroom; the 16k fallback rule if needed
- [ ] Docs: ADR 0006 amendment, CONTEXT.md, explainers 02, 04 and 13, demo script, README, CLAUDE.md model section
- [ ] `uv run pytest` green, `npm run build` clean; headful browser verification on the cloud entries (named session, own port above 8100, throwaway database, Gemma 4 26B on both slots, a handful of turns): the picker's default, the models card with the roles, a chart question end to end; screenshots in `/tmp/finquery-61/`; Comments. The local pair is verified by the coordinator on the laptop when the user frees it.
