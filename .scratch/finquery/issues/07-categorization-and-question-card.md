# 07: Categorization at import with Question card

**What to build:** After an import, transactions are categorized in order by the profile's rules, merchant enrichment, and the categorizer sub-agent on the fast slot with a confidence score per row. Every row gets an enriched title and short description. Confident rows are set. The Import page hands off to a new conversation where the assistant asks about the uncertain rows in Question cards: the transaction, the top guesses as buttons and a free text field, several rows per card. Each answer becomes a category rule so the same merchant never asks again. Telling the assistant "PayPal to Anna is always Dining" in plain language stores a rule too. Needs review remains the state of unanswered rows; Unknown is a real category never produced by automation.

**Blocked by:** 03 Data model, synthetic dataset and CSV import page, 05 Query sub-agent and the numbers invariant

**Status:** done

- [x] Categorization pipeline with the three stages and a confidence threshold; batch calls to the categorizer sub-agent through a forced single tool returning category, subcategory, confidence and enrichment
- [x] `ask_user` client-side tool: the agent emits a structured question, the frontend renders the Question card, the answer returns as tool output and the run continues
- [x] Import page finishes by opening a conversation that summarizes the import and asks the questions
- [x] Answers create category rules and apply to all matching rows in the profile; a rules stage runs before any model call
- [x] Plain-language rule statements in chat create rules through a tool with a confirmation line
- [x] HTTP-seam tests: rules beat the model, low confidence triggers a question, an answer becomes a rule that recategorizes matching rows
- [x] Browser verification of import, questions, answers and the resulting table

## Comments

Done 2026-09-04. Structure for the next tickets:

- `src/finquery/categorize/`: `merchants.py` (`fold`, the one normalization every stage matches
  through, `merchant_of` stripping processors, branch numbers, legal forms and city, and
  `DICTIONARY`, about sixty German merchants), `rules.py` (`set_rule`, which stores a
  `CategoryRule` and applies it to every matching booking in the profile, plus `resolve`,
  `split_choice` and the row writers), `subagent.py` (the categorizer, forced single tool
  `categorize`, pure `categorize_prompt`, `CONFIDENCE_THRESHOLD = 0.75`), `pipeline.py` (the
  three stages, `categorize_import`, `pending_questions`, `review_card`).
- The categorizer is asked **per merchant, not per booking**: the 433 bookings of the shipped
  year are 39 merchants, so one batch of 25 entries answers all of them (`BATCH_SIZE = 25`
  merchants). Per-row output is unchanged, the confidence lands on the merchant, and that is
  also what a Question card asks about and what a rule matches on. Per-booking batching would
  have been 18 model calls and minutes per import.
- `src/finquery/ask_user.py` is the generic Question card tool for tickets 08, 10 and 11:
  `AskUser` in, `AskAnswers` out, registered as an `ExternalToolset` so the run ends with the
  call pending. `chat_agent` therefore has `output_type=[str, DeferredToolRequests]`.
  See ADR 0008 for the whole mechanism, including why an answered turn is rewritten instead of
  appended.
- `api/chat.py`: `_load_history` now returns a `History` (messages plus which turn was last and
  how long it was), `History.open_tool_calls` finds the calls the server left open,
  `_tool_outputs` matches the browser's outputs against them, and `persist_turn` is a module
  function with `replaces=` so the pending turn is rewritten. `_renderable` drops the agent's
  own retry prompts from the UI messages (they would render as a user bubble saying
  "Validation feedback: ...").
- Endpoints: `POST /api/imports/{id}/categorize` (body `profile_id`) returns the stage counts
  and the uncertain merchants; `POST /api/imports/{id}/review-conversation` creates the
  conversation and seeds its first turn (the user's request, the assistant's summary counted in
  code, and a pending `ask_user` call), returning `conversation_id`. 409 when nothing is left
  to review. The Import page calls both after a commit and navigates into the conversation.
- Chat tools: `set_rule(pattern, category, subcategory)` (sequential, because SQLite serializes
  writers and a card usually answers several rows at once) and `review_batch(limit)` which
  returns the next merchants with a guess and ready-made buttons.
- Frontend: `components/question-card.tsx` (buttons per row, free text per row, Skip these,
  Send answers; renders `input-available` and the reloaded `approval-requested` as answerable
  and `output-available` as the answers), `components/rule-tool.tsx` (one-line rule and queue
  steps), `chat-view.tsx` wires `addToolOutput` and
  `sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls`.
- Tests: 51 passed, 2 skipped (`tests/test_categorization.py` adds 8, `tests/test_chat.py` one
  for the retry prompt). `tests/test_local_provider.py` expects `ask_user` next to `query` in
  the declared tools now.
- Measured on OpenRouter with the shipped year (`uv run python scripts/measure_categorization.py
  http://127.0.0.1:8058 fixtures/synthetic/sparkasse-2025.csv`, reproducible over three runs):
  39 merchants, one model call, **94.2 percent of rows categorized** (0 by rule, 384 by the
  dictionary, 24 by the model), 5.8 percent Needs review, and 0 rows without enrichment. The 25
  Needs review rows are the four PayPal payments to friends, each guessed
  `Transfers > Friends and family` at confidence 0.4, which is the honest answer. Spot check of
  all 39 enriched titles and categories: all 39 correct, including the two the model placed
  (landlord to `Housing > Rent`, employer to `Income > Salary`).
- Rough edge worth knowing: the fast model sometimes emits a malformed first tool call
  (trailing characters after the JSON object) when it makes several `set_rule` calls in a row.
  Pydantic AI retries it and the second call succeeds; the transcript shows one red line
  ("That rule call could not be read, so it was made again").
- Screenshots of the verification: /tmp/finquery-07/.

Merged into main on 2026-09-04 on top of 01, 02, 03, 04, 05, 12, 13 and 16. What changed in the
merge:

- **The ADR is now 0008** (`docs/adr/0008-ask-user-is-a-deferred-tool.md`): ticket 12 had taken
  0007 for the rolling summary. References updated in `CONTEXT.md`, `agent.py` and above.
- `agent.py` is the union: one `ChatDeps` (`session_factory`, `profile_id`, `conversation_id`,
  `resolve_model`, `subagent_settings`), four tools (`query`, `remember`, `set_rule`,
  `review_batch`) plus the `ask_user` toolset, and `output_type=[str, DeferredToolRequests]`.
  The prompt order is query rules, the `remember` rule, the categories and rules block, then the
  two paragraphs that have to stay last (answer as text after a tool, keep answers short).
- **`History` now carries the turns, not a flat message list.** `_load_history` returns
  `History(turns=[TurnMessages], last_turn_id, last_turn_length)`, with `messages` as a property.
  One object therefore feeds both features: `history.turns` goes to `_prompt_for` (which assembles
  summary plus memories plus the recent turns) and `history.open_tool_calls` finds the call the
  server left open. A deferred answer goes through the same `_prompt_for`, so a Question card is
  answered with the same prompt shape as a typed message.
- `persist_turn` is the union signature: module-level with `session_factory` (the Import page seeds
  a turn with it), `data_parts` from ticket 12 (`data-context`, then `data-followups`) instead of
  `followups=`, and `replaces=` from here. `_renderable` still runs inside it, in one place.
- **Two indices, not one.** `turn_start` is where the turn being written starts in the run's
  messages (the start of the pending turn when a card is being answered, otherwise the end of the
  prompt); `produced` is everything after the prompt, which is what the follow-up step, the
  distillation pass and the badge are given. Without the second index the rewritten turn's tokens
  would be counted twice, because the pending half is already inside `prompt.tokens`.
- A resumed turn brings no new user message, so memory selection falls back to the pending turn's
  own prompt: the second half of a turn is given the memories the first half was given.
- `data-context` lands on the rewritten turn, so the two reload assertions in
  `test_categorization.py` gained `"data-context"`. The seeded turn has none (nobody streamed it),
  which is why the header badge in a review conversation appears with the first answer.
- `test_memory.py`'s deleted-memory test asserts the whole sentence now: the merged system prompt
  names Rewe itself in the plain-language rule example, so a bare `"Rewe" not in prompt` could not
  hold.
- Scripted fast slots answer the distillation request: `scripted_categorizer` and the retry test
  here would otherwise have counted it as a categorizer or chat call. Requests per turn are the
  chat model on the conversation's slot plus the follow-up and distillation steps on fast, one more
  per `query` call, and one more when the turn compresses. A Question card round trip is a full
  turn of its own by that count.
- `uv run pytest` is 70 passed, 1 skipped. `npx tsc --noEmit`, `npm run build` and `oxlint` are
  clean.
- Verified on OpenRouter on port 8075 with a throwaway database: the Sparkasse preset was
  recognized, 433 rows committed, categorization placed 408 and left 25, the review conversation
  opened by itself with a four-merchant card, answering Anna Weber with Dining stored the rule
  ("6 bookings recategorized"), `review_batch` ran and the next card arrived with three merchants,
  the header badge read 7.7 percent, a second conversation stored the PayPal memory through
  `remember` and the distillation pass, "how much did I spend on groceries in 2025" answered
  4474.95 EUR from an executed SELECT with the tool step showing the statement, the "2 memories
  used" chip and the follow-ups rendered, and a reload of both conversations showed the same
  transcripts, including the answered card and the pending one. Screenshots:
  /tmp/finquery-merge07/.
- Seen in passing, not caused by the merge: the fast model confirmed "6 transactions were updated"
  in prose for a `set_rule` call whose tool step said 0 (the rows had already moved). The tool step
  is the truth; the prompt line asking it to quote the figures the tool returned is what it
  ignored.
