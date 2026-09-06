# 54: A model catalog: Qwen3.5 9B local and cloud, Gemma 4 12B local, Gemma 4 26B cloud

**What to build:** The model picker offers four chat models across both providers: Qwen3.5 9B (local), Qwen3.5 9B (cloud), Gemma 4 12B (local), Gemma 4 26B (cloud). Decided by the user on 2026-09-06 ("both" for the third entry, since OpenRouter has no Gemma 4 12B and the closest hosted Gemma 4 is 26B A4B). Today the provider is a global switch and the picker lists the two slots of that provider; this ticket replaces "slot as chat choice" with a catalog entry that names its provider, while sub-agents keep running on a fast slot.

**Blocked by:** 23 (Qwen quality slot), 33 (background turns), 42 (merged)

**Status:** done

Decisions, settled:
- Catalog entries, keyed by a stable string and labelled for the UI: `local:qwen3.5-9b` "Qwen3.5 9B (local)", `openrouter:qwen/qwen3.5-9b` "Qwen3.5 9B (cloud)", `local:gemma-4-12b` "Gemma 4 12B (local)", `openrouter:google/gemma-4-26b-a4b-it` "Gemma 4 26B (cloud)". Hosted ids are settings with these defaults (the existing `openrouter_quality_model` and `openrouter_fast_model` settings keep working for the sub-agent fast slot; add what is needed for the second hosted chat entry). A catalog entry carries: key, label, provider, the local `ModelSpec` or the hosted id, and availability with a reason (weights missing or downloading, no API key, provider disabled).
- Sub-agents stay on a fast slot, and the slot follows the chat entry's provider: a local chat entry runs its sub-agents on the local fast slot (Gemma 4 E4B, resident, adapters attach there, as ADR 0006 says); a cloud chat entry runs them on the hosted fast model (`openrouter_fast_model`, Qwen3.5 9B per CLAUDE.md). `ChatDeps.resolve_model` therefore resolves by role (chat entry, fast) for the conversation's entry, not by a global provider.
- Both providers can be live at once. `FINQUERY_PROVIDER` decides the default entry for a new conversation (local: Qwen3.5 9B local; openrouter: Qwen3.5 9B cloud) and nothing else; a hosted entry without `OPENROUTER_API_KEY` is listed as unavailable with that reason and a turn on it fails with a readable sentence, never a stack trace; a local entry with weights missing shows the download state the Settings models card shows today and can be downloaded from there.
- Local memory: E4B stays resident as the fast slot. The two local chat models (Qwen3.5 9B, Gemma 4 12B) share one seat: choosing the other drains the running one (existing `LocalStack.drain`), unloads it, loads the new one at the same context size, and the models card shows which is loaded and the swap in progress. Qwen 9B plus E4B is 13.5 GB and Gemma 12B plus E4B is about 12.9 GB; the three together do not fit and are never loaded together. `uv run finquery-check` checks both local chat models when both are on disk.
- Storage: conversations and turns record the catalog key. `conversation.model_slot`, `turn.model_slot`, `profile.default_model_slot` (and the fourth `model_slot` column in db.py) are widened or joined by a `model_key` column through `db.NEW_COLUMNS`; existing values `fast` and `quality` are read as the Qwen entry of the configured provider (`fast` was never a chat choice the user meant to keep). The per-conversation switch, the turn chips, the History and the models card use the catalog label. The onboarding step that picks a default model offers the four entries with availability.
- `GET /api/models` returns the catalog (key, label, provider, available, reason, loaded, download progress for local ones) plus the sub-agent fast slot per provider, so the frontend never names a model that is not listed. `frontend/src/lib/slots.ts` becomes the catalog hook; `MODEL_SLOTS` goes.
- Benchmarks: `finquery-bench run --model` keeps accepting hosted ids and `local:fast|local:quality`; add the catalog keys as accepted values, nothing more.
- Docs: ADR 0012 "Model catalog across providers" amending 0002 and 0006 (what a slot means now: sub-agent fast slot per provider, chat entry from the catalog), CONTEXT.md terms (catalog entry, seat), `docs/explainers/02-two-models-and-the-switch.md` updated (the required feature "at least two models to switch between" now reads as four entries), demo script step for the switch.
- Constraints: no regression of the numbers invariant or of the background turn machinery; a running turn keeps its entry when the user switches; the picker is the existing model selector component; no new dependency; no em dashes.

- [x] Catalog module with the four entries, availability and reasons; `GET /api/models` returns it; settings for the hosted ids
- [x] Resolution by (entry, role): chat on the entry, sub-agents on the entry's provider fast slot; both providers live at once; a hosted entry without a key fails readably
- [x] Local seat swap with drain, unload, load; models card shows loaded and swapping; `finquery-check` covers both local chat models
- [x] Storage: `model_key` through `NEW_COLUMNS`, old `fast`/`quality` values mapped; per-conversation switch, turn chips, History, onboarding default, profile default all on the catalog
- [x] Frontend: picker with four entries and disabled unavailable ones with the reason; `slots.ts` replaced; build clean
- [x] Tests at the HTTP seam with scripted models per provider: four entries listed with availability; a conversation switched to each entry records the key and its turns carry it; sub-agents resolve on the fast slot of the entry's provider (the scripted resolver asserts which provider was asked); a hosted entry without a key returns the readable error; old `fast` and `quality` rows map; local swap logic unit-tested with a fake stack (drain order, never three loaded)
- [x] ADR 0012, CONTEXT.md, explainer 02, demo script; `uv run pytest` green; headful browser verification (named session, own port above 8100, throwaway database, `.env` with the key so the two cloud entries are live; the local entries show their availability honestly without loading anything on this machine unless the user is not using it): the picker with four entries, a switch mid-conversation, chips and History showing the labels, the models card, onboarding; screenshots in `/tmp/finquery-54/`; Comments in the earlier tickets' style

## Comments

Built on 2026-09-06. Four commits: the catalog and the local seat, its tests, the picker, the
docs, plus one for a wrapping fix the browser check found.

### What the rule is now

A conversation stores a catalog key, and `Catalog.resolver(key)` hands the turn a
`role -> Model` callable: `chat` is that entry, `fast` is the sub-agent slot of that entry's
provider. Every one of the ~50 sub-agent call sites still says `resolve_model("fast")` and none
of them learned anything about providers, which is why this touched so little outside the seam.

`ModelSlot` became `ModelRole` (`chat`, `fast`), because a slot was doing two jobs: naming a
role and naming a chat choice. On the local provider a role is also a seat.

### Deviations, all small

- **ADR 0013, not 0012.** Ticket 33's "a turn is a task" took 0012 while this ticket was
  waiting. Everything else in the ticket is as written.
- **Storage widened rather than joined where it was free.** `model_key` columns went in through
  `NEW_COLUMNS` on `conversation`, `turn`, `profile` and `preference_record` as the ticket says;
  the old `model_slot` columns stay, empty on new rows, because an existing database declares
  `turn.model_slot` NOT NULL and SQLite cannot take that back. `Catalog.key_of` reads a stored
  `fast` or `quality` (or an unknown key) as the Qwen entry of the configured provider, so an
  old row opens and answers, which `test_model_catalog.py` holds to.
- **The local stack is now built on both providers**, since a local entry has to report its
  availability honestly while the process runs hosted. It downloads at startup only when
  `FINQUERY_PROVIDER=local`, so an OpenRouter run does not start 13 GB nobody asked for.
  `context_budget` had to learn the same distinction: the local `n_ctx` ceiling is only applied
  when the demo is actually on the local provider.
- **The fast slots are in `fast_slots`, not `entries`.** They are models the app runs that
  nobody picks, so they are on the Settings card and never in the chooser.

### Tests

352 before, 356 after (4 skipped, unchanged). `tests/test_model_catalog.py` is new: the four
entries with availability, a conversation on each entry recording its key, the resolution rule
asserted on the scripted resolver by `(entry key, role)` on both providers, the readable error
with no API key, the legacy `fast`/`quality` mapping, and the seat swap as a unit test over a
fake loader (drain, unload, load in that order, never three loaded, and no swap when the model
asked for is already in the seat). `tests/test_local_provider.py` grew a third stand-in model
and its swap test. `Scripts.resolve` takes `(key, role)` now and records both.

### Browser check

Own port 8154, throwaway database, `FINQUERY_MODELS_DIR` pointed read-only at the real weights
so the local entries could report `on disk` without loading anything. Four turns on OpenRouter
in total (two of them the pair below), both cloud entries.

- The picker lists all four with their provider icon and a line saying where each runs
  (`03-picker-dark`). Onboarding offers the same four (`01`, `02`).
- One chat, two entries: asked on Qwen3.5 9B (cloud), switched mid-conversation to Gemma 4 26B
  (cloud), asked again. Each turn kept its own chip, the switch relabelled nothing, and the
  sidebar and composer followed (`04` dark, `07` light).
- The models card lists the four entries with their files and sizes, then both fast slots with
  `sub-agent fast slot` under them, and the two adapters missing as before (`05`, `06`). The
  local entries read `on disk`, not `loaded`: nothing local was loaded on this machine.
- Both themes at 1280 wide.

Screenshots in `/tmp/finquery-54/`.

### Found and fixed in the browser

Four labels do not fit on one line of the onboarding card: "Gemma 4 26B (cloud)" was cut off at
the right edge. The choices group wraps now.

### Left, seen in passing

- Swapping the local seat is untested against real weights: this machine was in use, so the
  swap is only covered by the unit test with a fake loader. Worth one run before the demo, and
  the demo script now says the swap costs about 20 seconds.
- `finquery-bench --model` takes catalog keys, plus everything it took before. Nothing else in
  the bench changed, as the ticket asked.
