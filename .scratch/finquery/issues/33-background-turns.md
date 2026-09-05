# 33: Turns run in the background and survive a closed chat

**What to build:** A turn (and so an import) keeps running when the user switches conversation, closes the tab or reloads, and the user can come back and watch it. Today the run is tied to the HTTP stream: dropping the connection four seconds into a turn left nothing behind, not even the user's message (measured 2026-09-05 on the OpenRouter build). For a two-minute CSV import or a twenty-minute PDF that is a real loss.

**Blocked by:** 32 (conversation and state edge cases, touches the same file)

**Status:** done

- [x] The user's message and a pending assistant turn are persisted before the model is called, so a dropped connection never loses the question
- [x] The run is a server-side task detached from the response: the HTTP stream is one subscriber; a disconnect unsubscribes and never cancels; Stop is the only cancel
- [x] Progress and parts are persisted as they arrive (at least at every tool boundary and every few seconds of text), so a reload mid-turn shows the turn so far with a running marker
- [x] Reattach: useChat's resume (GET .../stream) replays what was missed and continues live; the composer stays disabled for that conversation while it runs
- [x] A running indicator on the conversation's tab and its sidebar row (a small spinner or dot) wherever the user is; the Imports overview shows a running import too
- [x] Server restart marks running turns interrupted (ticket 32's recovery) and the indicator clears
- [x] HTTP-seam tests: message persisted before the model answers; a dropped stream leaves the turn to finish and the full result is in the conversation afterwards; reattach replays; Stop cancels; browser verification: start a sample-year import, switch conversation, come back, see progress and the cards; reload mid-turn; close the tab entirely and reopen

## Comments

Done 2026-09-05. `uv run pytest` is 254 passed, 4 skipped (the four are environmental: the two
private Trade Republic fixtures, the private statement PDF and the opt-in local smoke suite);
247 before. `npx tsc --noEmit`, `npm run build` and `oxlint` are clean (34 warnings, the same
pre-existing set as tickets 30 and 32, none in a touched file and none new). Zero browser
console messages and no 4xx or 5xx for the whole session except one deliberate 409 driven with
curl. Screenshots `/tmp/finquery-33/`.

### As built

**The run is a task the app owns; the response is a subscriber.** `api/running.RunningTurn` is
the turn being produced: its cancellation token, its task, and the chunks it has produced.
`push` appends and wakes; `follow()` replays the buffer and then follows it live, so a reader
that arrives late is given the stream rather than the rest of the stream. The chat endpoint
starts the task and returns `stream_response(turn.follow())`; the `finally` of the task takes
the turn out of the registry, closes an unwritten turn as interrupted and closes the buffer, in
that order (out of the registry first, so a client whose stream just ended and asks to reattach
is told 204 rather than handed a finished turn). A client that hangs up stops reading. Only
Stop cancels, through the token it always went through.

**Endpoints.** `POST /api/conversations/{id}/chat` is unchanged on the wire, and answers 409
with `chat.ALREADY_RUNNING` when a turn of that conversation is already running. `GET
/api/conversations/{id}/stream` is new: the same chunks encoded the same way, or 204 when
nothing runs. `POST .../stop` is unchanged and still waits for the partial turn to be stored.
`running` is new on `ConversationOut` (so on the list and the detail) and on `ImportOut`.

**Persistence cadence.** Every tool boundary (`tool-input-available`, `tool-output-available`)
and otherwise at most every `PARTIAL_SECONDS = 3` of text, the open turn's UI messages are
rewritten with what has been streamed so far (`chat.persist_partial`, built by
`running.partial_parts` out of the chunk buffer). One row, one column, so it is cheap. Only the
UI messages: half a run is not something to assemble a later prompt from, and `persist_turn`
writes both families once at the end, replacing the partial.

**The message id is the hinge.** The partial assistant message is stored under the id the stream
names in its `start` chunk (`server_message_id`), because the AI SDK replaces the message it
already has when a resumed stream names it and pushes a second one when it does not. That is
what makes "reload mid-turn" show one turn rather than two. The one turn that writes no partial
is a card being answered from further up the transcript: its resumed half lands on the newest
message live, so a partial in the middle of the transcript would be drawn twice.

**The browser.** `resume` is passed to `useChat` only when the conversation is running and this
view is not the one streaming it (`sentHere`), because a resume on top of the request that
started the turn would run the same stream into the transcript twice.
`prepareReconnectToStreamRequest` points the SDK's own reconnect at `/stream`; its default would
have been the chat endpoint with the conversation id twice. The spinner on the tab and on the
sidebar row, and "Still importing" on the Imports page, come from the `running` flag; both lists
poll every two seconds while something is running and not at all otherwise, and the transcript
asks for the list again as soon as its own turn really is running (the first chunk is the
proof). The composer is closed while the chat answers, wherever it is open, its button is the
Stop button, and the line under it reads "This chat is answering. It keeps going if you switch
chats or close the tab."

**Restart.** Unchanged from ticket 32 and now worth more: the registry starts empty,
`close_open_turns` marks whatever a dead process left, and what it leaves is no longer only the
question but the thinking, the tool steps and the paragraph the run had written.

ADR 0012 is new and ADR 0001 is amended (the response no longer comes from the adapter, because
a reattaching client sends no request to build one from). CONTEXT.md gained **running turn**.

### Tests

Eight new tests in `tests/test_background_turns.py`, all at the HTTP seam with a model that
parks in the middle of its answer: the question and the running flags before the model answers,
a dropped stream that leaves the run to finish (the full turn lands, nothing is marked
interrupted), the reattach replaying what was missed and following to the end, 204 with nothing
running, the 409 on a second message and the same message accepted once the turn is over, the
text so far stored mid-run, a tool step stored the moment it returns, and Stop with no reader
attached.

One test of ticket 32 was replaced by the second of those:
`test_a_browser_that_hangs_up_mid_answer_leaves_the_turn_marked_not_missing` asserted the
opposite behaviour on purpose, and this ticket is what inverts it.

The context budget was not re-measured: no prompt changed.

### Verified on OpenRouter, port 8106, throwaway database, session `fq33`

The file was attached to a conversation by the harness (`/tmp/finquery-33/setup.py`, one
attachment row, the same one `store_uploads` writes), because the browser harness cannot drive a
file input; everything after that is the product.

- **A chat import of `sparkasse-2025.csv`, 433 rows**, started from the composer. Switching to
  the other conversation four seconds in kept a spinner on its tab and on its sidebar row
  (`02`), `/import` showed the row with **Still importing** and a Continue in chat button
  (`03`), and coming back joined the same stream mid-answer and watched the counted summary and
  the four-merchant Question card arrive (`01`, `04`). One `GET .../stream` in the log per
  reattach.
- **A reload mid-turn** on a chart turn: the transcript came back with the question, the
  thinking and the running chart step, and carried on to the finished chart and answer in one
  message, no duplicate (`06`, `07`).
- **The browser tab closed entirely** eight seconds into a turn: the run finished with nobody
  attached (`running` went false on its own), and reopening the conversation showed the whole
  turn (`08`).
- **Stop** still stops: partial thinking kept, the Stopped chip, `running` false (`09`).
- **The server killed mid-turn** (`kill -9`) and restarted: "1 turn(s) were interrupted by a
  restart", and the transcript kept the query step and the five months of the table the model
  had written, chipped Stopped, with no stuck spinner (`13`). That table is the progressive
  write: before this ticket the whole turn would have been the question alone.
- **A second message while a turn runs** is not reachable from the UI any more: the second
  browser tab on the same conversation had its composer closed and its Stop button showing
  within a second of the turn starting, and the typed text stayed in the box as its draft. The
  server's own refusal was driven with curl and is one sentence ("This chat is still answering.
  Wait for that turn to finish, or press Stop first."), which reaches the transcript through
  `lib/api.refusalSentence`.
- **Both themes** (`10`, `11`, `12`), and the onboarding sample year still opens its seeded turn
  with the Question card on a fresh profile (`14`).

### For the demo script

`docs/demo-script.md` step 9 now switches chat while Qwen thinks and comes back before pressing
Stop, and the troubleshooting list has "reload the page" as a real recovery. The stale first
bullet of that list (a Question card answered after a newer message does nothing) was removed:
ticket 29 fixed it and the script had not caught up.

### Left, seen in passing

- The buffer of a finished turn goes with the turn, so a client that asks to reattach a second
  after the run ended is told 204 and reads the stored transcript instead. That is the right
  answer and it is why the transcript is refetched when a turn ends.
- `memory distillation failed` was logged on every OpenRouter turn of this session: the fast
  model answers the distillation prompt in prose instead of calling its tool, and ticket 32's
  guard catches it (logged, never visible, the answer stands). Not this ticket's, but it means
  no memories were stored on the hosted provider today.
