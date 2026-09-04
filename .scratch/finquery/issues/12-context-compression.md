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
