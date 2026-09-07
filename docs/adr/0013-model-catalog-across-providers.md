# ADR 0013: A model catalog across both providers, and a slot is a role

Date: 2026-09-06
Amended: 2026-09-06 (ticket 61: the default entry per provider, and the resolution rule for a
sub-agent, which is now one setting per role rather than always the fast slot; see the ticket 61
amendment of ADR 0006); 2026-09-07 (ticket 67: three local Gemma 4 entries and one cloud entry,
Qwen removed, E4B a chat entry, adapters follow the seat, the key from Settings; below);
2026-09-07 (ticket 68: one local model resident at a time, which supersedes the two seats;
below); 2026-09-07 (ticket 73: Gemma 4 26B A4B is the local default and the 12B leaves the
catalog; below)
Status: accepted
Amends: ADR 0002 (the provider switch) and ADR 0006 (the local provider)

The ticket that asked for this called it ADR 0012; that number went to ticket 33 first
(a turn is a task), so this is 0013.

## Context

ADR 0002 gave the app two logical slots, `fast` and `quality`, and one environment variable
deciding which provider fills them. That made the provider a global fact and the slot the
user's only choice, which is two things the product needs to say apart:

- The picker offered two entries, and both moved when `FINQUERY_PROVIDER` moved. There was no
  way to compare the same question on the local Qwen and the hosted one, which is exactly the
  comparison the demo is about.
- `quality` was a position, not a model. A conversation stored `quality` and got whatever was
  in that position at the time, so the label on a stored turn could change under it.
- Sub-agents were pinned to `fast`, which was right, but `fast` also meant "the provider the
  whole process is on". A conversation could not run its chat on one provider without dragging
  every sub-agent behind it onto that provider too.

The user asked for four chat models on 2026-09-06: Qwen3.5 9B and Gemma 4 12B locally, and
their nearest hosted equivalents, Qwen3.5 9B and Gemma 4 26B A4B (OpenRouter has no Gemma 4
12B). Two of those are local and two are cloud, so the four cannot be four slots on one
provider.

## Decision

- **A catalog entry is what a conversation runs on** (`finquery.catalog.Entry`): a stable key,
  a label, the provider it belongs to, and either a local `ModelSpec` or an OpenRouter id. The
  four entries are `local:qwen3.5-9b`, `openrouter:qwen/qwen3.5-9b`, `local:gemma-4-12b` and
  `openrouter:google/gemma-4-26b-a4b-it`. The hosted ids are settings, so another model is a
  config change; the local ones are the GGUFs of `finquery.local.catalog`.
- **A slot is now a role**, `chat` or `fast` (`finquery.providers.ModelRole`). `chat` is the
  conversation's own entry; `fast` is the sub-agent slot. Nothing outside `finquery.catalog`
  and `finquery.providers` knows anything else about a model.
- **The resolution rule is two lines.** The chat runs on the conversation's entry. Every
  sub-agent of that turn runs on the fast slot of that entry's provider: Gemma 4 E4B locally
  (resident, where the adapters attach, ADR 0006), `FINQUERY_OPENROUTER_FAST_MODEL` in the
  cloud. `Catalog.resolver(key)` returns the `role -> Model` callable a turn hands to its tools,
  so a tool still asks for a role and never learns which provider answered. *Ticket 61 kept the
  shape and moved the second line into a setting per sub-agent role, defaulting to the chat
  entry rather than the fast slot; a role is now `chat`, `fast` or a catalog key.*
- **Both providers are live at once.** The local stack is built whatever the provider setting
  says, and nothing about it touches the network or loads weights until a turn needs one.
  `FINQUERY_PROVIDER` decides one thing: which entry a new conversation starts on (since
  ticket 61 the Gemma entry of that provider). On `local` it also starts the downloads at startup, because that is
  the demo machine asking for its weights.
- **An entry that cannot answer is listed with the reason, never hidden.** `GET /api/models`
  returns every entry with `available` and a one sentence `reason` (no API key, weights missing
  or still coming down), plus the download progress for a local one and the fast slot of each
  provider. The picker disables it and shows the reason; a turn on it is a 503 with that
  sentence, which is the path a stack trace used to take.
- **The two local chat models share one seat.** There are two seats in memory: `fast` holds
  Gemma 4 E4B and stays resident, `chat` holds one of the two chat models. Choosing the other
  drains the seat (so the abandoned token pull of a cancelled turn has returned before the
  weights it was reading are freed), unloads it, and loads the new one at the same context.
  This happens under the seat's lock, before the run starts, so nothing reaches llama.cpp
  mid-swap. Qwen 9B plus E4B is 13.5 GB and Gemma 12B plus E4B about 12.9 GB; three together
  do not fit in the 18.2 GB Metal working set of a 24 GB Mac, and a seat is what makes that
  structural rather than a rule somebody has to remember.
- **Storage records the catalog key.** `conversation.model_key`, `turn.model_key` and
  `profile.default_model_key`, all added through `db.NEW_COLUMNS`. `preference_record.model_key`
  was a fourth until 2026-09-06, when the preference feature was removed (ticket 59): the table
  is left alone in databases that have it, and nothing creates or reads it any more. The pre-catalog `model_slot` columns stay because an existing database
  declares them NOT NULL, and their old values are read through `Catalog.key_of`: both `fast`
  and `quality` become the default entry of the configured provider. `fast` was the sub-agent
  slot, never a chat choice a user meant to keep, and `quality` was a position rather than a
  model, which is why the model in it moved again in ticket 61.
- **The browser is told, never told twice.** `GET /api/models` is the only place a model name
  comes from (`frontend/src/lib/catalog.ts`), so the picker, the turn chips, the context badge,
  the models card and the onboarding default cannot name a model the server
  does not offer. There is no list of models in the frontend any more.

## Consequences

- The demo can ask the same question on the local Qwen and the hosted Qwen in two tabs, which
  is the comparison ADR 0002 made impossible.
- A stored turn keeps the model that produced it, by name, forever. Switching a conversation
  changes the next turn and relabels nothing.
- Sub-agent behaviour follows the chat's provider, so a local conversation stays local: no
  merchant, no statement page and no SQL question leaves the machine because a sub-agent was
  resolved somewhere else.
- Swapping a local chat model costs a load (about 20 seconds for the 12B), paid by the turn
  that asked for it. The models card says which model is in the seat and when one is loading.
- The two fast slots are models the app runs that nobody picks. They are in `fast_slots` on the
  models endpoint and on the Settings card, and never in the chooser.
- `finquery-bench --model` takes a catalog key now, and still takes `fast`, `quality`, an
  OpenRouter id and `local:fast`, so every recorded run stays reproducible.

## Amendment, 2026-09-07 (ticket 67): four Gemma 4 entries, and the adapters follow the seat

The cluster benchmark of 2026-09-06 placed Qwen3.5 9B behind Gemma 4 12B in every column
(`bench/results/20260906-cluster-compare.md`), so the comparison this ADR was written for, the
same question on the local Qwen and the hosted Qwen, is no longer one worth a picker entry.

- **The four entries are `local:gemma-4-e4b`, `local:gemma-4-12b`, `local:gemma-4-26b` and
  `openrouter:google/gemma-4-26b-a4b-it`**, listed in that order. Qwen3.5 9B leaves the catalog
  on both providers, and its `qwen` wire format leaves `finquery.local`; a second family is
  still one wire module and one `WIRE_FORMATS` entry. The local 26B is Gemma 4 26B A4B at
  UD-Q3_K_XL (12.9 GB), not the Q4_K_M the other two use (16.9 GB), because it shares 24 GB
  with a resident E4B; the cloud entry is the same model hosted, so a question can be compared
  on the two.
- **Gemma 4 E4B is a chat entry and still the local fast slot.** A chat on it holds the fast
  seat, so nothing is loaded twice and the chat seat stays free for the 12B or the 26B. The key
  `local:fast` is gone; the models endpoint lists the E4B entry in both `entries` and
  `fast_slots`, and the models card draws it once with both jobs named.
- **The default entry per provider is explicit** (`Catalog.DEFAULT_KEYS`): the 12B locally,
  the 26B in the cloud. "First entry of the provider" would now name E4B.
- **The query and chart sub-agents ask for their adapter on every run**
  (`finquery.providers.with_adapter`), and `LlamaCppModel._hold` attaches it exactly when the
  run is on E4B. So the rule the user asked for is one rule: a chat on E4B runs the fine-tuned
  query and chart sub-agents; a chat on the 12B or the 26B runs them on that model's own
  weights, with no audit note, because that is the choice and not a fallback. The one fallback
  still noted is an adapter file missing on E4B. The per-role settings are unchanged; `fast` on
  a local entry now means the E4B entry.
- **The OpenRouter key can come from Settings.** `PUT` and `DELETE /api/models/openrouter-key`
  apply it in-process (`Catalog.set_openrouter_key` drops the hosted models built with the old
  one) and write the `OPENROUTER_API_KEY` line of the key file (`FINQUERY_KEY_FILE`, default
  `.env`) so the next start has it. The browser gets the last four characters back and nothing
  more. A machine without a key still lists the cloud entry, unavailable, with the sentence
  saying where to enter one.

## Amendment, 2026-09-07 (ticket 68): one resident local model at a time

The two-seat decision above is superseded. The laptop measurement of the same day
(`bench/results/20260907-local-tokens-per-second.md`) settled it: with Gemma 4 E4B resident and
the 26B A4B in the chat seat, the first decode failed with `llama_decode returned -3` at 32k and
again at 16k, and `finquery-check`'s pair report had called that same pair "ok" because it read
the process RSS, which comes back as 0.1 GB with a 13 GB GGUF mmapped. Two seats also bought
nothing: since ticket 61 every sub-agent role defaults to `chat`, so a turn on the 12B or the
26B never touches a resident E4B.

- **`LocalStack` keeps one GGUF loaded.** Asking for a model that is not the loaded one drains
  the loaded one, unloads it, and loads the new one at the configured context, in that order
  and under one lock, which is the old `take_seat` order applied across seats instead of within
  one. Asking for the model that is loaded costs nothing. One worker thread and one lock;
  `holding` stays re-entrant within one asyncio task, so a sub-agent run inside an attached
  adapter does not deadlock on itself. A nested hold cannot swap: the run around it is holding
  the model it asked for.
- **A seat is a role, not a place in memory.** `ModelSpec.seat` still says which model a
  sub-agent role set to `fast` means (Gemma 4 E4B) and which base the adapters attach to.
  `loaded_spec(seat)` answers "the loaded model, if it is the one for this seat", and
  `GET /api/models` reports `loaded` for at most one entry.
- **A role set to `fast` on a chat on the 12B or the 26B swaps twice per sub-agent call.** That
  is the cost of that setting, documented on it (`.env.example`, `finquery.catalog`) rather than
  prevented; the default `chat` never swaps, and a chat on E4B runs its fine-tuned sub-agents
  with no swap at all.
- **The pair check is gone** (`check_pair`, `PairReport`, the 16k fallback for the chat seat).
  `finquery-check` runs each model alone, as it already did, and prints no memory figure: RSS is
  not to be trusted for an mmapped 13 GB file, and a wrong number is worse than none.
  `FINQUERY_LOCAL_N_CTX` stays as the one context cap, and at 32k every catalog model fits on
  its own.

## Amendment, 2026-09-07 (ticket 73): the local default is Gemma 4 26B A4B, and three entries

The entry list of the ticket 67 amendment above is superseded. Gemma 4 12B leaves the catalog.
The user decided this on the cluster and laptop numbers of the same day: on the 459 question SQL
set the 26B A4B ties the 12B, 79 against 78 percent figure match, and on the laptop it generates
at 38.1 tok/s against 22.3 and reads a prompt at 480 tok/s against 205
(`bench/results/20260907-local-tokens-per-second.md`, and the 26B SQL run of 2026-09-07). Its
end-to-end result is 67 against the 12B's 77 on 30 turns; the user took the speed, because a
demo turn is four to six requests and almost all of that time is prompt evaluation.

- **The three entries are `local:gemma-4-e4b`, `local:gemma-4-26b` and
  `openrouter:google/gemma-4-26b-a4b-it`**, listed in that order, and
  `Catalog.DEFAULT_KEYS["local"]` is `local:gemma-4-26b`. The local default and the cloud entry
  are now the same weights, so the pair a verification run compares is one model on two
  providers. E4B keeps the fast seat, the adapters and its own chat entry.
- **Gemma 4 12B is a benchmark candidate under its unchanged key.** The spec moved as it stood,
  files and hashes included, from `finquery.local.catalog` to `finquery_bench.candidates`, so
  `finquery-bench --model local:gemma-4-12b` and the cluster scripts keep working and every
  recorded run still resolves to the model it was scored on. Nothing in `src/` imports from
  `bench/`: the app cannot list, download or start a conversation on it.
- **A conversation stored on `local:gemma-4-12b` reads as the default entry.** `Catalog.key_of`
  already did that for any key the catalog no longer offers, which is the same path the
  pre-catalog `fast` and `quality` take; a test says so for the 12B on the local provider.
- **The weights on the laptop are the user's to delete.** `models/gemma-4-12b-it` (7.1 GB) and
  `models/Qwen3.5-9B` are no longer wanted by anything the app or the benchmark runs on this
  machine, but a benchmark run of the 12B candidate would download them again, so nothing
  removes them automatically.
