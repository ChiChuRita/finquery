# 32: Edge cases, conversation and state

**What to build:** Hunt for edge cases in conversation flow, persistence and UI state, fix each at the root with a test, and polish what the user sees. Includes ticket 29 (a Question card answered after a newer message) and the two leftovers of ticket 30 (the import step's counted sentence repeated in prose; the resumed half of a card turn listing the merchants it just applied). Requested 2026-09-05.

**Blocked by:** 30 (merged)

**Status:** done

Cases to cover at least (add what you find):
- Cards: answering a card after a newer message (ticket 29), answering the same card twice, answering with free text only, skipping every row, a card whose merchant was recategorized meanwhile, a duplicate card after the import was deleted, a mapping card after the attachment was deleted
- Turns: Stop during thinking, during a tool call, during the follow-up step; server restart while a turn runs (the turn is marked interrupted on next load, the UI recovers without a stuck spinner); two tabs on the same conversation; reload during streaming; the model returning nothing; a tool raising; the follow-up and distillation steps failing (never visible to the user)
- Compression: cross the threshold twice; edit the summary to empty (422) and to 4000 characters; a conversation whose every turn is a card; compression on a conversation with attachments
- Memory: the same fact in two languages, a contradicting fact (the newer wins or both shown), 200 memories (selection cap and page performance), deleting a memory used in the open conversation
- Conversations and tabs: rename to empty or 500 characters, delete the open conversation, delete a conversation open in another tab, switch profile while streaming, 30 open tabs, a tab pointing at a deleted conversation on reload, browser back and forward through conversations
- Models: switch slot while streaming, the quality slot unavailable (503 shown as a sentence), onboarding default slot honoured on new conversations
- Keyboard: Enter sends and Shift Enter breaks a line; Escape cancels dialogs and inline edits; focus returns to the composer after a card answer
- Polish: the two ticket 30 leftovers; any text that still restates counts twice; any place where a pending state has no spinner or a finished state keeps one

- [x] Each case tried through the real product and recorded in a table with outcome before and after
- [x] Every defect fixed at the root with an HTTP-seam test; ticket 29 closed; suite green; typecheck and build clean; zero console errors during the browser runs

## Comments

Done 2026-09-05. `uv run pytest` is 221 passed, 4 skipped (the four are environmental: the two
private Trade Republic fixtures, the private statement PDF and the opt-in local smoke suite).
`npx tsc --noEmit`, `npm run build` and `oxlint` are clean (34 warnings, the same pre-existing
set as ticket 30, none in a touched file and none new). Zero browser console messages and no 4xx
or 5xx responses for the whole session except the deliberate 404 of the deleted-conversation
case. Screenshots `/tmp/finquery-32/before/` and `/tmp/finquery-32/after/`.

Ticket 29 is closed in its own file, including why resuming the turn beat expiring the card.

### The cases

| Case | Before | After |
| --- | --- | --- |
| **Cards** | | |
| Answered after a newer message (29) | Send disabled the buttons, sent no request at all, and the rows were still Needs review after a reload | The run that card parked resumes, the rules are stored, the turn is rewritten in its own place |
| Answered twice (a second browser tab) | The second request was read as a new prompt, resumed the run again and would have applied everything twice | 409, one sentence in the transcript, the first answer stands |
| Free text only | Stored as the rule for that merchant | unchanged, test kept |
| Every row skipped | Nothing applied, output passed through | unchanged, test kept |
| Merchant recategorized meanwhile | Correct (the applier works against the data as it is) | unchanged, now pinned by a test |
| Duplicate card after its import was deleted | Correct: the candidates went with the import, so nothing is applied | unchanged, now pinned by a test |
| Mapping card after the attachment was deleted | Not reachable: there is no endpoint that deletes one attachment, and deleting the import only clears `Attachment.import_id` (SET NULL), which makes the file importable again. A file the model names that is not there is `no_such_file` with the list of files that are | unchanged |
| **Turns** | | |
| Stop during thinking | Partial thinking and steps kept, Stopped chip, no error boundary | unchanged |
| Stop during a tool call | "The chart step was stopped before it finished, so it has no result." | unchanged |
| Stop during the follow-up step | The turn is already stored when those steps run, so Stop waits for it and returns | unchanged |
| Server restart while a turn runs | The turn vanished: the conversation opened on the transcript it had before the message was typed | The question is there with "This turn was interrupted before an answer was written. Ask again to continue.", and the log says how many turns a restart interrupted |
| Two tabs on the same conversation | Both render; the second tab's card answer was applied a second time | Both render; the second answer is refused as a sentence |
| Reload during streaming | The whole turn vanished, question and all | Kept with the interrupted marker |
| The model returning nothing | "Stream function must return at least one item" in the transcript, and no trace of the question | One sentence the reader can act on, the exception in the server log, the question kept |
| A tool raising | The exception text in the transcript | The same one sentence |
| Follow-up or distillation failing | The exception took the finished answer with it: nothing was persisted at all | Logged; the answer stands, the suggestions are lost |
| **Compression** | | |
| Cross the threshold twice | Correct | unchanged, seen three times in the browser at `FINQUERY_CONTEXT_BUDGET=6000` |
| Summary edited to empty | 422 | unchanged |
| Summary edited to 5000 characters | Cut at `MAX_SUMMARY_CHARS`, untested | unchanged, now pinned by a test |
| A card turn behind the divider | The resumed run was handed a prompt with the pending call summarized away, resumed against the wrong response and answered 200 having applied nothing | The marker is read one turn short of the card for that run, so the card is answerable however long the user took |
| A conversation of nothing but cards | Not reachable as stated: an answered card rewrites its own turn rather than adding one, so a card turn is a turn like any other and the summarizer reads its tool arguments as text | unchanged |
| Compression with attachments | The bytes never enter the model messages (`take_uploads` takes the file parts out before the agent sees them), so the summarizer and the token estimate never see a file | unchanged |
| **Memory** | | |
| The same fact in two languages | Both kept, each in its own language, and the block says a memory's language decides nothing | unchanged |
| A contradicting fact | Both kept, the newer first (recency is the tie-break) | unchanged, now pinned by a test |
| 200 memories | Five in the prompt, all 200 on the page | unchanged, now pinned by a test |
| Deleting a memory used in the open conversation | The next turn does not carry it | unchanged |
| **Conversations and tabs** | | |
| Rename to empty | 422 at the endpoint, and the sidebar sends nothing at all | unchanged |
| Rename to 500 characters | Cut at 200, untested | unchanged, now pinned by a test |
| Delete the open conversation | Leaves the conversation before deleting it, closes its tab | unchanged |
| Delete a conversation open in another tab | "This conversation could not be loaded." and no way out of that tab | "This chat could not be loaded. It may have been deleted." with a New chat button |
| Switch profile while streaming | The turn was dropped without trace | The turn is left interrupted; the new profile opens its own state |
| 30 open tabs | The bar scrolled but showed the oldest tabs: nothing said which chat was open, and New chat was off the right-hand end | The tab in front is scrolled into view and New chat is sticky at the end of the bar |
| A tab pointing at a deleted conversation on reload | It stops showing | unchanged |
| Back and forward | Correct, tabs follow | unchanged |
| **Models** | | |
| Switch slot while streaming | The running turn keeps its slot, the next uses the new one | unchanged, now pinned by a test |
| Quality slot unavailable | `{"detail":"..."}` printed into the transcript | The sentence, through `refusalSentence` |
| Onboarding default slot on a new conversation | Read from the profile's settings by the New chat page | unchanged |
| **Keyboard** | | |
| Enter sends, Shift Enter breaks a line | Correct | unchanged |
| Escape cancels a dialog and an inline edit | Correct | unchanged |
| Focus after a card answer | Left on the button that had just disabled itself | The composer takes the caret |
| **Polish** | | |
| The import step's counted sentence repeated in prose (30, p3) | The model wrote the `summary` out again under the step that already prints it | The result carries a `say` line counted in code, which is what the model writes |
| The resumed card turn listing the merchants it applied (30) | A bullet list of everything the card below already says | The categorization applier carries a `say` line ("2 merchants now have rules and 2 are still to decide.") |
| Thumbs on a turn with nothing in it | Offered on an interrupted turn with no answer | Hidden: there is nothing to rate |

### The root causes

**A turn only existed once its run had finished.** `persist_turn` runs in `on_complete` or
`on_cancel`, and neither of those happens when the request task is cancelled (a browser that
reloads or navigates away) or when the process goes away. So the question disappeared with the
answer, which is four cases in the table above and the one the ticket calls a stuck spinner.

The fix is an end marker. `Turn.finished` is false from the moment a run starts, `open_turn`
writes the turn with the user's message (and the conversation's title, so a first turn that
never finished is not "New chat" for good), and `persist_turn(replaces=...)` rewrites it. Three
ways it can be closed: the run writes it out, the stream's `finally` closes it as interrupted
when nothing was persisted, and `close_open_turns` at startup closes whatever a dead process
left. The registry of running turns is a fresh dictionary in the same lifespan, so the two
agree by construction. The transcript hangs its marker on an assistant message with no parts,
and the sentence under it is the browser's (`chat-view.InterruptedTurn`), the way a stopped
tool step's sentence is.

**The framework's exception text was the transcript's error text.** Anything that went wrong
inside a run (a model that returned nothing, a tool that raised, a provider that refused)
reached the user as `{"type":"error","errorText":"Stream function must return at least one
item"}`. It is replaced by one sentence and the detail goes to the log. A refused request
(409, 503) reaches the same box through `lib/api.refusalSentence`, because
`DefaultChatTransport` throws the whole JSON body as the error message.

**The post-turn pair could take the answer down with it.** `_followups` and `_distill` each
resolve the fast slot themselves, which raises on the local provider while the models are still
downloading, and `asyncio.gather` propagated that out of `on_complete` before the turn was
stored. Both are extras and are now caught as such.

**One counted sentence, written once.** Both ticket 30 leftovers are the shape m4 fixed: a model
handed a finished line writes it back word for word. `import_attachment` and
`categorize.apply_answers` each carry a `say` line counted in code, the prompt names it, and
`categorize.apply_answers` returns `Applied` rather than a bare string so both halves travel
together.

### The budget

Re-measured rather than assumed: the system prompt is 3166 tokens (ticket 30 measured 3145) and
the floor a compressed prompt cannot go below is 4084 (was 4063). `BUDGET = 4800` still leaves
about 15 percent of headroom, so the constant did not have to move this time; both numbers are
in the comment in `tests/test_context.py`.

### Tests

Fifteen new tests, all at the HTTP seam: the late card answer and its three neighbours
(answered twice, merchant moved, behind the compression divider), the restart, the browser
hanging up mid-answer, a model that says nothing, a tool that raises, a failing post-turn step,
a slot the provider cannot give, a duplicate card whose import is gone, a summary past its
ceiling, a slot switched mid-turn, 200 memories, and two contradicting facts. Three existing
tests changed shape: the chat import now asserts the prose is the `say` line and *not* the
summary, the answered card asserts its `say`, and the rename test asserts a title past its
ceiling is cut. 206 passed before, 221 after.

### Verified on OpenRouter, port 8105, throwaway database, session `fq32`

The sample year imported and categorized by REST (433 rows, 25 Needs review), then the cases in
the table. Worth naming: **the late card answer** (`05`), **a card answered twice from a second
browser tab** (`08`, the first answer stands in the database), **Stop during thinking and during
a chart tool** (`09`, `10`), **the server killed mid-turn and restarted** (`11`, one interrupted
turn logged), **a reload mid-answer** (`06`), **deleting the open conversation** (`17`) and one
open in another browser tab (`18`), **thirty tabs** (`19`), **back and forward** (`21`),
**switching profile mid-answer** (`22`), **the divider crossed three times** at
`FINQUERY_CONTEXT_BUDGET=6000` (`23`), and **both themes** (`24`, `25`, `26`).

### Left, seen in passing

- The resumed half of a card turn no longer lists what it applied, but the fast model still
  sometimes names the merchant of the *next* card in its sentence ("There is one more merchant
  to categorize: Lea Hoffmann"), which the card below also names. The `say` line is the fix for
  the counts; a fifth prompt line about not naming rows is not.
- Answering an older card leaves the resumed answer at the bottom of the screen while it
  streams, because the SDK appends a stream to the newest assistant message, and it hops up to
  its own turn when the turn ends and the transcript is taken back from the server. One
  transient, on a path the user reaches by leaving a card unanswered.
- Harness note for the next browser run: `agent-browser type @ref "..."` reaches the React
  composer where `fill` and a bare `type` after a `click` do not, and `press Control+a` in this
  session twice left the tab on `about:blank` with no console output, which is the harness and
  not the app (the same flows are correct when driven with Backspace).
