# 61: Ship Gemma 4 12B as the chat model, and give every sub-agent role its own model setting

**What to build:** The benchmark decided (`bench/results/20260906-cluster-compare.md`: 87 against 70 and 66 percent on SQL, 81 against 42 and 45 on charts). Gemma 4 12B becomes the default local chat model and, for the demo, the model every sub-agent runs on. Gemma 4 E4B stays resident as the fast slot and remains the adapter target. Which model a sub-agent role uses becomes one setting per role. Hosted development moves to Gemma 4 26B A4B on both cloud slots. Decided by the user on 2026-09-06.

**Blocked by:** 54, 56 (merged)

**Status:** done

Decisions, settled:
- Catalog defaults (`src/finquery/catalog.py`, `settings.py`): on the local provider the default entry is `local:gemma-4-12b`; Qwen3.5 9B stays a catalog entry. The two local seats stay: E4B resident on the fast seat, the chat seat holding Gemma 4 12B by default (Qwen swaps in if picked). Cloud entries: `openrouter:google/gemma-4-26b-a4b-it` (default when the provider is openrouter) and `openrouter:qwen/qwen3.5-9b`; the hosted fast slot default becomes `google/gemma-4-26b-a4b-it`.
- Sub-agent roles: a setting per role, `FINQUERY_SUBAGENT_MODEL_<ROLE>` with roles query, chart, categorizer, extraction, memory, summary, weblookup (find the exact set by grepping for `resolve("fast")` and `subagent_settings` callers), each taking `fast`, `chat` or a catalog key. Default for every role: `chat`, meaning the conversation's chat entry (Gemma 4 12B locally, Gemma 4 26B in the cloud). `fast` means the provider's fast slot as today. Resolution goes through the catalog's role resolver so the local seats and the cloud entries behave the same. Adapters still attach only on the fast slot (E4B), so a role set to `fast` with an adapter registered gets the adapter; a role on `chat` never does. The models card lists the roles and what each resolves to right now.
- Sub-agent settings: reasoning stays off for sub-agent calls whatever model they run on; `SUBAGENT_MAX_TOKENS` unchanged; the extraction page concurrency stays 4 locally.
- Local memory: Gemma 4 12B plus E4B is about 12.9 GB at 32k context each; `uv run finquery-check` verifies both load together and reports headroom. If the 12B needs a smaller context to fit next to E4B on the 24 GB machine, prefer lowering the 12B's context to 16k over evicting E4B, and say so in the check's output.
- Hosted development: `.env.example`, `CLAUDE.md` ("Models for development and verification") and the agent briefs say Gemma 4 26B A4B on both slots. The coordinator switches the live `.env`.
- Docs: ADR 0006 amended (the Qwen quality slot is superseded; the pair, the per-role setting, the benchmark as the reason, with the numbers), CONTEXT.md (sub-agent role setting), `docs/explainers/02-two-models-and-the-switch.md`, 04 and 13 (which model the sub-agents run on and why), `docs/demo-script.md` (start on Gemma 4 12B, the sample import is slower, say the numbers), README model table.
- Benchmarks: `finquery-bench run --model` and the cluster scripts keep working; add `--subagent-model` only if the run function needs it to reproduce "chat and sub-agent on the same model", otherwise the catalog key already covers it.

- [x] Catalog defaults and cloud entries; `.env.example`; tests updated (default entry per provider, cloud entries listed)
- [x] Per-role sub-agent model setting with `chat` as the default and `fast` as the option; every sub-agent call site goes through it; adapters only on `fast`; models card shows the roles; HTTP-seam tests with scripted models asserting which model each role resolved to for `chat`, `fast` and a catalog key
- [x] `finquery-check` loads both local models together and reports headroom; the 16k fallback rule if needed
- [x] Docs: ADR 0006 amendment, CONTEXT.md, explainers 02, 04 and 13, demo script, README, CLAUDE.md model section
- [x] `uv run pytest` green, `npm run build` clean; headful browser verification on the cloud entries (named session, own port above 8100, throwaway database, Gemma 4 26B on both slots, a handful of turns): the picker's default, the models card with the roles, a chart question end to end; screenshots in `/tmp/finquery-61/`; Comments. The local pair is verified by the coordinator on the laptop when the user frees it.

## Comments

Built on 2026-09-06. Six commits: the catalog and the role settings, the pair check, the models
card, the ADRs and CONTEXT, README and the demo script, plus one for a stale sentence the
browser check found.

### What the rule is now

A conversation still stores a catalog key, and `Catalog.resolver(key)` still hands the turn a
`role -> Model` callable. What changed is the second line of the rule. A tool no longer asks for
`"fast"`; it asks for its own role (`"query"`, `"chart"`, `"categorizer"`, `"extraction"`,
`"memory"`, `"summary"`, `"weblookup"`), and `Catalog.for_role` reads one setting per role:
`chat` (the conversation's own entry, the default), `fast` (the sub-agent slot of that entry's
provider) or a catalog key that pins the role. Thirteen sub-agents share the seven roles,
because the setting picks a model for a kind of work, not for a module. The two groupings worth
naming: the CSV mapping and the typed bookings are `extraction` (both read a file or a paste),
and the follow-up suggestions ride with `summary` (both are a short pass over the finished turn).

### Deviations, all small

- **The two hosted chat ids are constants, not settings.** `FINQUERY_OPENROUTER_QUALITY_MODEL`
  and `FINQUERY_OPENROUTER_SECOND_CHAT_MODEL` are gone: they were the reason the picker showed
  one cloud entry when `.env` pointed both at the Gemma id, which is exactly what hosted
  development does now. `catalog.HOSTED_CHAT_MODELS` holds the two ids;
  `FINQUERY_OPENROUTER_FAST_MODEL` stays a setting because the fast slot is a slot.
- **`subagent_settings()` lost its argument.** It branched on `FINQUERY_PROVIDER`, which was
  already wrong once both providers were live and is plainly wrong now that a role can run on
  the chat entry. It returns reasoning off plus `SUBAGENT_MAX_TOKENS` for every model; the local
  model ignores the OpenRouter key in the dict.
- **An adapter asked for on a chat model is now an audit note, not a silent attach.**
  `LlamaCppModel._hold` honours `finquery_adapter` only when the model in hand is the fast seat.
  Before this ticket it would have taken the fast seat and run the chat model's request against
  it, which nothing exercised because no sub-agent sets the flag yet (the adapters are ticket
  43). The note says the adapter is trained on the fast slot's weights and the run used the base
  weights, which is what the existing audit-note path already carried.
- **A role setting is validated at startup**, so a typo in `.env` is a pydantic error naming the
  variable instead of a 503 the first time that one sub-agent runs.
- **The demo script's timings were not re-measured.** They were taken with E4B answering and E4B
  behind every tool. The script now says to read them as a floor and roughly double them, with
  the tokens per second of both pairs next to it. The sample import is called out as the step to
  talk over.

### The pair check

`finquery-check` ends with `check_pair`: it holds E4B and Gemma 4 12B at the same time and
prints what is resident (through `ps`, because the stdlib only offers the peak and a peak would
follow the retry) against `SC_PHYS_PAGES * SC_PAGE_SIZE * 0.75`, which is the 18.2 GB of 24 GB
this Mac was measured at in ADR 0006. Under a gigabyte of headroom, or a load that raises, and
it unloads the chat seat, loads it again at 16384 and says to set `FINQUERY_LOCAL_N_CTX=16384`.
The fast seat is never the one that is given up. Two unit tests over the fake loader cover both
paths, including that the fast slot loads once and is never closed.

### Tests

405 passed and 4 skipped before, 410 and 4 after. `tests/test_model_catalog.py` gained the role
tests (every role on the conversation's entry by default, every role on `fast`, one role pinned
to a catalog key, and the endpoint's role list) and lost nothing. `tests/conftest.py`: the
scripted resolver now dispatches on the entry key for every role, so a test that scripts one
entry answers its sub-agents too. Ten assertions across `test_chart`, `test_query`,
`test_changesets`, `test_context`, `test_conversations` and `test_local_provider` changed from
`"fast"` to the role that asked, which is the readable half of this ticket.

### Browser check

Own port 8137, throwaway database, `FINQUERY_MODELS_DIR` pointed read-only at the real weights,
`.env` with both cloud slots on Gemma 4 26B A4B. Two turns on OpenRouter in total (the sample
import's categorizer pass, then one chart question).

- Onboarding and the composer picker both list the four entries in the new order with **Gemma 4
  26B (cloud)** ticked as the default (`01`, `05`).
- The models card lists the four entries, then both fast slots, then the seven sub-agent roles
  with their setting and what it resolves to, then the adapters (`02`, `03` dark, `04` light).
- The sample year imported 433 bookings, 408 categorized: the categorizer sub-agent ran on the
  chat entry, which is the default this ticket ships.
- "Show my spending per month in 2025 as a line chart" drew end to end, chart and query
  sub-agents on the same cloud model as the chat, 12 rows, chip "Gemma 4 26B (cloud)",
  follow-ups after it (`06` light, `07` dark).
- A second server with `FINQUERY_SUBAGENT_MODEL_QUERY=fast` and
  `FINQUERY_SUBAGENT_MODEL_CHART=local:gemma-4-12b` reported those two roles resolving to
  `openrouter:fast` and `local:gemma-4-12b` while the rest stayed on the chat entry
  (`08-roles-from-env.txt`).

Screenshots in `/tmp/finquery-61/`.

### Found and fixed in the browser

The onboarding model step still said "Tools always run on the fast model of whichever provider
the chat is on", which this ticket made false. It now says tools run on the same model unless a
role was set to the fast one.

### Left, seen in passing

- The local pair is unverified on real weights: nothing was loaded on this machine. The
  coordinator runs `uv run finquery-check` when the user frees the laptop, and that is also the
  first real reading of the headroom line.
- The Settings "Run sanity check" button still runs the per-model checks only. The pair check is
  the CLI's, because it holds both seats for a minute and the page has no place to say that yet.
- No `--subagent-model` for the bench: `--model local:gemma-4-12b` already pins every role to one
  model, which is the "chat and sub-agents on the same model" shape the demo runs.
