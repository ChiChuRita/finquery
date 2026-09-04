# 12: Context compression

**What to build:** A long conversation keeps working. A context badge in the conversation header shows tokens used against the model's context. When history passes 60 percent, turns older than the last six are distilled by the fast slot into a rolling summary that replaces them in the prompt. A divider in the transcript marks where the summary took over; the summary is readable and editable there.

**Blocked by:** 02 Profiles and conversation management

**Status:** done

- [x] Token counting per slot; context stats emitted as a data part every turn
- [x] Summarization at the threshold, stored with a summary-through marker on the conversation; per-turn prompt assembly uses summary plus recent turns
- [x] Divider and editable summary in the transcript; edits are used on the next turn
- [x] HTTP-seam tests with a small fake context size: summary created at the threshold, older turns no longer sent to the model, edited summary reaches the model
- [x] Browser verification of a long chat crossing the threshold

## Comments

Done 2026-09-04. 5 new tests (40 passed, 2 skipped in total). Screenshots of the verification:
/tmp/finquery-12/. Design recorded in
`docs/adr/0007-rolling-summary-compression-before-the-turn.md`.

`src/finquery/context.py` is the whole feature: the budget, one token estimate, the per-turn
assembly and the summarizer on the fast slot. `api/chat.py` calls `_prompt_for` before the run.

What the next tickets need from this:

- **Per-turn assembly is `context.assemble`.** It returns the history, the system-level note, the
  token count and where the transcript divider goes. Ticket 13 adds its selected memories there
  (and reports the count in `memories`, which the badge already shows), not in `api/chat.py`, or
  the badge and the compression decision stop matching the prompt.
- The rolling summary reaches the model as run-level instructions
  (`adapter.run_stream(instructions=...)`), which Pydantic AI appends to the agent's own system
  prompt. Anything else that wants to be system-level should join that string rather than
  fabricate a system message in the history.
- `data-context` per turn: `{used, budget, slot, memories, summarized_turns}`. Streamed from
  `on_complete` (and `on_cancel`) and appended to the persisted assistant message, so the badge
  is identical live and after a reload. `_persist_turn` now takes a list of `DataUIPart`s, which
  is where a new custom part goes.
- `Conversation` gained `summary` and `summary_through` (position of the last covered turn).
  `GET /api/conversations/{id}` returns `summary`, `summarized_turns` and `summarized_messages`
  (the divider's index into `messages`); `PATCH /api/conversations/{id}` accepts `summary` and
  rejects an empty one with 422.
- `FINQUERY_CONTEXT_BUDGET` (default 32768) caps the working budget; the local provider's
  `n_ctx` caps it further. Tests set it through the new `settings_overrides` fixture in
  `conftest.py`, and `conftest.is_summary_request` tells the compression step apart from a chat
  turn and a follow-up step (so a scripted fast slot now answers three kinds of request).
- Adding a column to a table that already shipped needs an entry in `db.NEW_COLUMNS`;
  `create_all` never alters a table and an existing database would otherwise lose its rows.
- Two things fixed in passing: `ChatView`'s root was `h-full` under the tabs bar, which pushed
  the page 40 px past the viewport, and `.env.example` still suggested a 32k local context.

Deviation worth knowing: past the threshold the prompt holds at six turns plus the summary, so
every further turn folds exactly one more turn in and asks the fast slot for one small summary.
That is what the spec asks for ("turns older than the last six"), and it is cheap with reasoning
off, but it means the badge plateaus rather than falling. No manual Compress action was built
(YAGNI, the ticket does not ask for one).

Merged into main on 2026-09-04 on top of 01, 02, 03, 04, 05, 13, 16 and the two bug tickets
18 and 19. What changed in the merge:

- **Memories go through `context.assemble`.** It takes a fourth argument, the `MemoryBlock`
  ticket 13 selects for this turn, and joins the memory text to the summary note into one
  `Assembly.instructions` string. `Assembly` gained `memories`. So one string is the whole
  system-level part of the prompt, one `estimate_tokens` call covers all of it, and the badge,
  the compression decision and what the model was sent are the same number. `api/chat.py`
  builds the block (it needs the session and the newest user message) and hands it to
  `_prompt_for`, which passes it to both of its `assemble` calls.
- **One `data-context` part, merged shape:** `{used, budget, slot, memories, summarized_turns}`.
  Ticket 13's `memories_used` key is gone: it was the same number under a second name, and the
  three assertions that read it had to change anyway because the dict grew. `chat-view.tsx`
  (the chip) and `test_memory.py` now read `memories`, which is also what `ContextBadge`
  already showed.
- Post-turn steps are 13's pair (follow-ups and distillation gathered under
  `POST_TURN_TIMEOUT`); compression stays where this ticket put it, before the answer. So a
  compressing turn is one chat request plus a fast-slot summary, follow-up and distillation
  request, four in total, and three otherwise (plus one per query sub-agent call).
  `test_context.py` asserts that count.
- `tests/conftest.py` is the union: `script(answer, thought, followups, memories)`,
  `distilled`, `is_followup_request`, `is_distillation_request`, `is_summary_request`,
  `settings_overrides`, the scripted sub-agent side (`_collected` answers a distillation
  request with an empty `distilled()` whatever the test scripted), and the `profile_id`
  fixture. `test_context.py`'s `Recorder` had to learn the distillation request: without it
  every post-turn pass fell into its chat branch and corrupted its own bookkeeping.
- **The test budget went from 1200 to 2000 tokens.** The merged system prompt is 557 tokens
  (05's query rules, 13's remember rule and the answer-as-text line), where it was under 200
  when this ticket was written. A compressed prompt can never go below system prompt plus
  summary plus the last six turns, which is about 1465 tokens here, so a 1200-token budget was
  under the floor and `used < budget` could not hold after compression. Nothing changed in the
  code: the real default is 32768 and the local cap is 16384, both far above the floor.
- `uv run pytest` is 61 passed, 1 skipped. `npx tsc --noEmit` and `npm run build` are clean.
- Verified on OpenRouter with the synthetic Sparkasse dataset on port 8074 with
  `FINQUERY_CONTEXT_BUDGET=6000`: the `remember` tool stored the PayPal-to-Anna rule, the
  groceries question answered 403.60 EUR from an executed SELECT with the tool step showing
  it, the header badge read "20.6%, 1.2K / 6K, Fast slot, Memories in prompt 1", eight turns
  took it to 65.3% and the eighth compressed one turn into the summary, the divider appeared
  above the first turn and opens onto the editable summary, and a reload showed the same
  transcript, badge and chips. Screenshots: /tmp/finquery-merge12/.
- Seen again in the reloaded transcript: the "Please return text or call a tool" retry request
  rendered as a user bubble. That is ticket 18, still open, and not caused by this merge.
