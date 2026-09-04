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
  See ADR 0007 for the whole mechanism, including why an answered turn is rewritten instead of
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
