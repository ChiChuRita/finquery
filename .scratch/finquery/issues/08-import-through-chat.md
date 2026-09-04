# 08: Import through chat attachments and text

**What to build:** A user drops a CSV, PDF or image into the chat composer and sends it. The assistant runs the import as a tool with progress streamed into the tool step, then continues in the same conversation with the categorization questions. A pasted statement snippet or a typed sentence like "I paid 12 EUR cash for lunch today" produces a preview card of the extracted transaction with Confirm and Discard.

**Blocked by:** 07 Categorization at import with Question card

**Status:** done

- [x] Composer accepts CSV, PDF and image attachments; file parts reach the server and are stored per conversation
- [x] `import_file` tool runs the ingestion pipeline for CSV now and delegates PDF and images to the extraction path (which lands in ticket 11); progress as transient data parts
- [x] Mapping confirmation for unknown CSV layouts happens through the Question card
- [x] Pasted or typed transactions are extracted by the fast slot and shown as a preview card; Confirm creates the transaction and categorizes it
- [x] HTTP-seam tests: CSV attachment import end to end, typed transaction preview and confirm
- [x] Browser verification of drop, progress, questions, and a typed transaction

## Comments

Done 2026-09-04. 6 new tests (`tests/test_chat_import.py`), 75 passed and 2 skipped in total.
Screenshots of the verification: /tmp/finquery-08/.

Structure, for tickets 10 and 11:

- **`src/finquery/attachments.py` is the store.** A file dropped into the composer arrives as a
  file part with a data URL. `api/attachments.py` takes it out of the message before the agent
  is given it and stores the bytes in the new `attachment` table (per conversation, identified
  by content hash, 20 MB and 5 files per message). The prompt therefore never carries a file:
  a 75 KB CSV would be twenty thousand tokens and the model has no use for it. What the
  assistant is told instead is `attachments.brief`, an `@chat_agent.instructions` block naming
  each file, its kind, its size and whether it was already imported. `GET /api/attachments/{id}`
  serves the bytes back, which is what the chip in the transcript links to.
- **The chip after a reload.** `persist_turn` gained `attachments=`, symmetric to `data_parts=`:
  the file parts are appended to the turn's user message when it is stored. The attachment row
  remembers `turn_position` (the number of turns the conversation had when it arrived), and a
  rewritten turn keeps its position, so answering a Question card does not lose the chip.
- **`import_file(file_name, account_name=None, confirmed=False)`** is `ingest/chat_import.py`.
  It is the Import page's pipeline, same functions: `sniff`, `detect_preset` or the mapping
  sub-agent, `commit_rows`, `categorize_import`, then `pending_questions` for the card. Its
  return is a status: `imported` (counts, the `summary` sentence counted in code, and
  `questions` in exactly `review_batch`'s shape), `confirm_mapping` (a ready-made `card` for
  `ask_user`, plus the proposal stored on the attachment; the confirmed second call commits the
  stored mapping, so the model never rewrites it), `extraction_not_ready` (PDF and image: a
  sentence naming ticket 11, not an error), `already_imported`, `no_such_file`, `unreadable`,
  `mapping_failed`. Ticket 10's per-candidate duplicate question belongs between `commit_rows`
  and `categorize_import` there; ticket 11 replaces the `extraction_not_ready` branch and reads
  `record.data` (bytes, media type and kind are on the row).
- **`import_summary` moved to `ingest/commit.py`**, so the seeded review conversation and the
  chat import state the same sentence about the same import. `mapping_agent.propose` is the
  shared mapping call (`api/imports.py` is now only its HTTP shape, raising `MappingUnusable`
  as a 502).
- **Progress is a transient data part**, `finquery/progress.py`: an async tool emits
  `ImportProgress` through `RunContext.emit` and the Vercel adapter turns it into
  `data-import_progress` with `transient: true`, attributed to the tool call. It needed no
  change in `api/chat.py` at all, and because transient parts never reach `messages`, a
  reloaded transcript shows the tool's result rather than the counting. `chat-view.tsx` keeps
  the lines from `onData` keyed by tool call id and `import-tool.tsx` renders them inside the
  running step.
- **Typed and pasted transactions** are `ingest/typed.py`: the fast slot reads them through one
  forced tool (`propose_transactions`, unsigned `amount` plus a `direction`, so no sign can be
  lost), each booking becomes a `transaction_draft` row with a short ref (`t1`, `t2`), and the
  preview card is `ask_user` with Confirm and Discard per row. `add_transaction(ref)` writes the
  booking from the stored draft (source `manual`), categorizes that one row and is idempotent.
  The draft table is what keeps the model out of the arithmetic: the amount that lands is the
  amount that was shown. Ticket 11's "otherwise a new transaction preview" for a bill photo is
  the same table and the same card.
- **The composer** takes CSV, PDF and images (`accept`, `maxFiles=5`, 20 MB, chips with a remove
  button, a paperclip button, the error line under the chips). A file sent with no text still
  sends: `take_uploads` gives that turn the one sentence the gesture meant. Files attached on
  the empty New chat page survive the navigation through `lib/pending.ts`, now a message rather
  than a string.
- **Two existing tests changed.** `test_local_provider.py`'s vision test drove an image through
  the chat endpoint; no route sends bytes to the chat model any more, so it now drives the same
  rendering contract directly (`Agent(stack.resolve("fast")).run([text, BinaryContent(...)])`),
  which is also the shape ticket 11's extraction sub-agent will use. `test_context.py`'s budget
  went from 2000 to 3000 tokens: the system prompt grew by the two paragraphs this ticket adds
  (about 800 tokens now), and ADR 0007's floor is system prompt plus summary plus six turns.
- Requests per turn for an import: the chat model twice (the call, then the answer), and on the
  fast slot the mapping proposal when no preset matches, the categorizer for the import, the
  categorizer again for the card, then the follow-up and distillation steps. A typed transaction
  is the chat model three times across the card round trip, plus the extraction and one
  categorizer call.
- **`allow_uploaded_files` is not passed.** In pydantic-ai 2.39 that flag only gates
  `UploadedFile` references (a provider-side file id the client asks the server to fetch); a
  data URL becomes `BinaryContent` regardless, which is what the composer sends. Setting it
  would widen what a client may ask for and buy nothing, so it stays off, and the file parts are
  taken out of the message before the run either way.
- Verified on OpenRouter on port 8080 with a throwaway database: `sparkasse-2025.csv` dropped on
  the composer with "import this" imported 433 of 433 bookings into Sparkasse Girokonto (384 by
  the merchant list, 24 by the categorizer, 25 Needs review), the progress lines ticked past
  inside the tool step, the four PayPal merchants came as a Question card in the same
  conversation, answering Anna Weber with Dining stored the rule ("6 bookings recategorized")
  and the next card arrived. "I paid 12 EUR cash for lunch today" previewed Lunch, -12,00 EUR,
  04.09.2026, Cash, and Confirm wrote it (the Transactions page shows it as source Manual,
  Needs review). `unknown-bank-2025.csv` asked for its mapping on a card showing the columns and
  the first three bookings; confirming it imported 420 of 433 into Volksbank with 13 unreadable
  rows and 6 placed by the rule from the first conversation. The synthetic PDF answered with the
  ticket 11 sentence and was stored anyway. A reload of all three conversations showed the same
  transcripts including the attachment chips.
- Two things seen in passing. The fast model usually goes straight from the import tool step to
  the Question card without repeating the summary in prose, because `ask_user`'s own description
  says "say nothing else in the same turn"; the summary is in the tool step, so nothing is lost.
  And the mapping the sub-agent proposed for the renamed-header file mapped `Soll` but not
  `Haben`, which is why 13 incoming rows were unreadable: the card shows exactly that, and the
  reject path points at the Import page, where the mapping is editable.

Merged into main on 2026-09-04 on top of 01 to 07, 09, 12, 13, 14, 16, 18 and 19. What changed
in the merge:

- `agent.py` is the union of eleven tools on one `ChatDeps`: `query`, `chart`,
  `propose_changeset`, `apply_simple_edit`, `remember`, `set_rule`, `review_batch`,
  `lookup_merchant`, `import_file`, `extract_transaction` and `add_transaction`, plus the
  `ask_user` toolset. Four `@chat_agent.instructions` blocks now: `data_brief`, `attached_files`,
  `web_lookup_brief` and the memories the context assembly adds. Prompt order is the query
  rules, `chart`, "Changing the data", the `remember` rule, the categories and rules block, the
  two blocks this ticket adds (attached files, then typed transactions), then the two paragraphs
  that stay last.
- `data_brief`'s empty-profile line is the union of both: it names `chart` as well as `query` as
  something not to call, and it says a statement can be dropped into the chat *or* imported on
  the Import page.
- `api/chat.py`: the attachment interception runs first (it takes the file parts out of the
  message, which is what `_latest_user_text` then reads), then the narration queue is built.
  `persist_turn` needed nothing: `attachments=` and `narration=` sit next to `data_parts=` and
  `replaces=` in one signature, and they touch different messages of the turn (the chips go on
  the user message, the narration and data parts on the assistant one).
- `db.py`: `Attachment` and `TransactionDraft` next to ticket 14's `OutboundRequest` and
  `WebLookup`. Both sides had inserted a class at the same spot and the shared `created_at` line
  under the conflict belonged to a different class on each side, so each class got its own.
- `app.py` includes `attachments.router` next to `imports`, `changesets` and `settings`.
- `lib/api.ts` is the union of the tool map (eleven tools) and its part types;
  `chat-view.tsx` renders `tool-import_file`, `tool-extract_transaction` and
  `tool-add_transaction` alongside the changeset, chart and lookup branches, and keeps 08's
  `onData` handler for the transient `data-import_progress`.
- **The test context budget went from 2600 to 3000 tokens** and its comment was rewritten,
  because the reason it has to move is not the one either branch wrote. Compression needs two
  things: something older than the last six turns (so never before the eighth) and a prompt over
  60 percent of the budget. The system prompt alone is 1856 tokens now, so the token half is
  already true on turn one and the turn count is what decides. What the budget really has to
  clear is the floor a compressed prompt cannot go below, measured at 2764 tokens here. 3000
  leaves 236, which is why ticket 20 has to raise it again.
- `uv run pytest` is 109 passed, 1 skipped (`tests/test_chat_import.py` adds 6 to the 103 after
  ticket 14). `npx tsc --noEmit`, `npm run build` and `oxlint` are clean.
- Verified on OpenRouter on port 8077 with a throwaway database. `agent-browser upload` is off
  limits and a 100 kB base64 literal broke `eval`, so the drop was done by **copying the fixture
  into `frontend/dist/` (the SPA route serves any file that exists there), then fetching it
  same-origin in `eval` and dispatching a synthetic `change` on the composer's file input**. The
  chip appeared, "import this" ran `import_file` with the progress lines ticking inside the
  running step, and the completed step read 433 of 433 into Sparkasse Girokonto, 384 by the
  merchant list, 24 by the categorizer, 25 Needs review, the same figures as the REST path.
  The four PayPal merchants came as a Question card in the same conversation; answering Anna
  Weber with Dining stored the rule and the next card arrived, and Skip these closed it. "I paid
  12 EUR cash for lunch today" previewed `lunch, -12,00 €, Cash` with Confirm and Discard, and
  Confirm wrote it (`GET /api/transactions?q=lunch` returns one row, -1200 cents, account Cash,
  source manual, 2026-09-04, Needs review). Screenshots: /tmp/finquery-merge08/.
- Harness notes for the next verification: the file must be reachable over http for the
  synthetic drop, and `input.files` is empty right after the `change` event because the
  component clears the input, so read the chip rather than the input to check it worked. The
  `agent-browser` daemon also stopped answering for a few minutes after a long streamed turn and
  swallowed one click; the click has to be repeated once it answers again.
