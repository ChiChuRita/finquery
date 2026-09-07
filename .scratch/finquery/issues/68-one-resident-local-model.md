# 68: One resident local model at a time

**What to build:** The local provider keeps at most one GGUF loaded. Today there are two seats
(`fast` for Gemma 4 E4B, `chat` for the 12B or the 26B) and nothing ever unloads the fast seat,
so a chat that moves from E4B to the 26B tries to load 12.9 GB beside a resident E4B and fails
its first decode on the 24 GB laptop (`bench/results/20260907-local-tokens-per-second.md`,
`llama_decode returned -3` at 32k and at 16k). Since ticket 61 every sub-agent role defaults to
`chat`, so the resident E4B buys nothing for a chat on a bigger model: a turn on the 12B never
touches it. The user asked on 2026-09-07: load only one model, make it efficient.

**Blocked by:** 67 (merged, commit on main of 2026-09-07)

**Status:** ready-for-agent

Decisions:
- `LocalStack` holds one loaded model. Asking for a model that is not the loaded one drains
  the loaded one, unloads it, and loads the new one at the configured context, in that order,
  under one lock (the existing `take_seat` order, applied across seats instead of within one).
  Asking for the model that is loaded costs nothing. Keep `ModelSpec.seat`: it still says which
  model the `fast` role means and which adapters attach where; it no longer means a second
  place in memory. One worker thread and one lock are enough now; the re-entrancy of
  `holding` within one asyncio task (a sub-agent inside an attached adapter) must survive.
- A role set to `fast` on a chat on the 12B or the 26B swaps twice per sub-agent call. That is
  the cost of that setting and is documented on it, not prevented; the default `chat` never
  swaps. A chat on E4B with the adapters attaches and detaches as today, no load.
- `finquery-check`: the pair check (`check_pair`, `PairReport`, the 16k fallback for the chat
  seat) goes; each model is checked alone as before and the report says how much of the Metal
  working set the loaded model took (RSS is not to be trusted for an mmapped 13 GB file; report
  what llama.cpp says it allocated if reachable, else drop the figure rather than print a wrong
  one). `FINQUERY_LOCAL_N_CTX` stays as the one context cap.
- The models endpoint and card: `loaded` is true for at most one local entry; the E4B block's
  note stops saying "resident". `swapping` keeps its meaning.
- Docs: ADR 0013 amendment (the two-seat decision is superseded), CONTEXT.md **Seat** entry
  (now: the one place a local model is loaded, and which model the fast role means), the
  demo script's memory paragraph (one model resident, about 6 GB for E4B, 7 GB for the 12B,
  13 GB for the 26B, plus KV cache), `docs/adr/0006` needs no edit beyond a pointer.
- Tests: `test_the_chat_seat_drains_unloads_and_loads_and_never_holds_three` becomes the
  one-model test (E4B then 26B then 12B then E4B: each step drains and unloads the previous);
  `test_a_chat_on_e4b_holds_the_fast_seat_and_nothing_is_loaded_twice` keeps its point; the
  `local_stack` and `seat_stack` fixtures need no llama.cpp. No smoke run: the weights on the
  laptop are not touched by the agent.

- [ ] `LocalStack` with one loaded model, the swap order and the lock re-entrancy kept, `slot`/`holding`/`take_seat`/`unload` adjusted with their docstrings
- [ ] `finquery.local.check` without the pair check; `finquery-check` output and `/api/models/check` still work; the models card's sanity check section reads correctly
- [ ] Tests updated and green (`uv run pytest`), frontend `tsc -b` clean if the card changes
- [ ] ADR 0013 amendment, CONTEXT.md, demo script, module docstrings; a Comments note here
