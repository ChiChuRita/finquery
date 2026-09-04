# 20: Review fixes, agent and stream side

**What to build:** The headful review of 2026-09-04 (see ../review-2026-09-04.md) found leaks between model and screen that would show on stage. This ticket fixes the agent, prompt and stream side; ticket 21 takes the frontend side.

**Blocked by:** 06, 07, 09 (all merged)

**Status:** done

- [x] Question card answers are applied deterministically in code: when the answered `ask_user` output arrives, the server turns each answer into a category rule and recategorizes that merchant before the model is asked to continue, and the model only summarizes and asks the next card. The fast model must never be asked to sequence N `set_rule` calls itself (it looped for 145 seconds and created nothing)
- [x] The Gemma end-of-turn marker `<turn|>` (and any other chat-template token) never reaches answer text on either provider: stripped in the stream path in one place, with a test
- [x] The answer language follows the latest user message, not the conversation so far, and money in prose uses German formatting (comma decimals, dot thousands, EUR after the number); one prompt paragraph, verified on a German then English then German exchange
- [x] "Recategorize all X rows" and any other bulk change goes through `propose_changeset` with a preview card; `set_rule` is reserved for teaching statements ("PayPal to Anna is always Dining") and Question card answers. Prompt wording plus a guard: `set_rule` refuses when the user's request was a bulk edit phrase is not feasible, so the prompt has to carry it and a test asserts the tool choice on a scripted turn
- [x] Every assistant fragment carries `model_slot` in metadata so a model switch never relabels an earlier turn; the context badge never shows NaN (older conversations without a data-context part show a dash)
- [x] The "cannot answer" reply gives one sentence of why and an alternative, and still gets follow-ups
- [x] Every tool gets a visible step: `remember`, `set_rule`, `review_batch`, `propose_changeset`, `apply_simple_edit` render as collapsible steps like `query`
- [x] Thinking duration persisted per turn matches the live value after reload
- [x] HTTP-seam tests for each item; full suite green; browser verification of the Question card flow end to end on the real fast model

## Comments

Done 2026-09-04. 96 passed, 2 skipped (both environmental: the private Trade Republic export and
the opt-in local smoke suite). Screenshots: /tmp/finquery-20/.

**What a Question card answer means is now the server's job, not the model's.** This is the one
contract change tickets 08 and 10 depend on:

- `AskUser` gained `apply: {"kind": "category_rule"} | None`, and the output gained
  `applied: str | null`. Wire contract and reasoning are in `src/finquery/ask_user.py` and
  ADR 0008, which was amended (the old text said the assistant calls `set_rule` once per
  answer).
- `src/finquery/answers.py` is the dispatcher: `resolve_answers(session_factory, profile_id,
  calls, outputs)` runs between the two halves of the run and returns the tool results the
  resumed run is given. `APPLIERS: dict[ApplyKind, Applier]` is where ticket 08 (mapping
  confirmation) and ticket 10 (duplicate decisions) add their kind. A card that declares no
  kind is a categorization card, which is what the seeded review conversation and every
  `review_batch` card are; a kind nobody handles is passed to the model untouched.
- `categorize.apply_answers(session, profile_id, rows, answers)` is the categorization
  applier: one `set_rule` per answered row, patterns from the row `ref`, labels from the card.
  It returns the line that becomes `applied`, for example "Applied: Anna Weber (via PayPal) ->
  Dining (6 bookings recategorized), Jonas Keller (via PayPal) -> Dining (7 bookings
  recategorized). Left for later: Max Schulz (via PayPal)." `None` when every row was skipped,
  and then the output stays exactly what the browser sent.
- `History.open_tool_calls` returns the `ToolCallPart`s now, not just their names: the apply
  hint lives in the call's own arguments.
- `review_batch` returns `apply` alongside its questions and the `ask_user` description tells
  the model to copy it onto the card, so a model-built card behaves like the seeded one.
- The prompt no longer asks for `set_rule` per answer. It says the card is already applied when
  the model sees it and to say the `applied` line back.
- The card renders `applied` under the rows, so the transcript shows what happened even before
  the model speaks.

**The resumed half of a card turn runs with reasoning off** (`state.subagent_settings`, the same
override sub-agents get). It has nothing to work out, and with reasoning on the fast model
collapsed into a 23 000 character "based-based-based" repetition loop at exactly that boundary,
which is the same failure the review saw as "Wait, I'll do all three." for 145 seconds. With it
off the same step takes about four seconds. A test asserts the settings of that request.

Everything else:

- **Chat-template tokens.** `local/gemma.py` owns the vocabulary (`TEMPLATE_MARKERS`),
  `strip_markers` for finished text and `MarkerFilter` for a stream, which holds back a tail
  that could still become a marker (`<tur` then `n|>`). `api/chat.py` filters text deltas on
  the way out and `persist_turn` cleans the stored text with the same function, so a reload
  does not bring the marker back. The test feeds a marker split across two deltas and a whole
  one.
- **Language and money.** One paragraph before the answer-as-text line, plus the closing line
  now names the language too. Money in prose is `1.234,56 EUR`, dates `04.09.2026`. The
  "Quote the figures ... as EUR with two decimals" line became "never rounded or rescaled",
  because it was the line that produced `843.60 EUR`.
- **Bulk changes.** A prompt bullet in "Changing the data" ("use `propose_changeset` and never
  `set_rule`"), and a guard in `categorize.rules.set_rule`: a pattern of several words one of
  which is a bulk word ("all Netflix rows") is refused with the tool to use instead. A single
  word is never refused, so a merchant that happens to be one of those still works.
- **Model slot per fragment.** `persist_turn` stamps `model_slot` on every assistant UI message
  of the turn and the full metadata on the last one. The badge shows a dash when no turn
  reported usable stats (a seeded review conversation, or a conversation stored before the part
  carried token counts), which is where the NaN came from.
- **Cannot answer.** One more `query` bullet: no tool call, one sentence why it is not in the
  data, one question that is. `followups.py` now tells the follow-up step that a question the
  data cannot answer is exactly when to offer something it can, instead of "No follow-ups."
- **Tool steps.** `remember` is in `ChatTools` and renders through the new
  `components/memory-tool.tsx`; `set_rule` and `review_batch` became collapsible `Tool` steps
  with a body (the rule, its effect, the bookings it matched; the queue and the merchants being
  asked about). Deviation worth knowing: `propose_changeset` and `apply_simple_edit` stay full
  cards rather than collapsible steps, because their body is the row-by-row preview the user
  has to read before pressing Apply. Every tool the agent has is visible as its own step now.
- **Thinking duration.** `close_thinking` sums the blocks of a turn instead of letting the last
  one win, and `on_complete` closes an open block. A turn that thinks before and after a tool
  call reported one second before; the test sleeps inside the first block and asserts the total.
- **The test context budget went from 2600 to 3200 tokens.** The system prompt is about 1300
  tokens now, so the floor a compressed prompt cannot go below (system prompt plus summary plus
  six turns) is about 2600. Nothing changed in the code; the real default is 32768. Third time
  this constant has had to move for a longer prompt (tickets 12 and 09 before this).
- Requests per turn are unchanged, except that an answered Question card now costs one chat
  request instead of two or more (no `set_rule` round trip).

Verified on OpenRouter on port 8083 with a throwaway database, the Sparkasse preset imported by
REST (433 rows, categorization placed 408 and left 25, the same figures as tickets 07 and 09):

- The seeded review conversation opened with the four-merchant card and a dash in the header
  badge (no NaN). Three answers (two buttons, one free text "Leisure") and one row skipped:
  Jonas Keller -> Dining (7), Anna Weber -> Dining (6), Lea Hoffmann -> Leisure (5) were all in
  the database within seconds of pressing Send, before the model had said anything, and Max
  Schulz stayed Needs review. "Ask me about the merchants that are still left" produced the next
  card in 13 s; answering it took 4 s and ended with "Max Schulz (via PayPal) has been
  categorized as Transfers > Friends and family (7 bookings). All merchants have been
  reviewed.", with the `applied` line on the card. 0 rows Needs review afterwards.
- German, then English, then German in one conversation: "4.474,95 EUR für Lebensmittel"
  (German), "In 2025, the merchants you spent the most at were: Hausverwaltung Bergmann GmbH:
  13.800,00 EUR ..." (English answer to an English question after a German turn, German money
  format), then "Deine größte einzelne Ausgabe im Jahr 2025 war am 01.01.2025 ... über
  1.150,00 EUR." No `<turn|>` anywhere in either conversation (checked over the whole API
  payload).
- "Recategorize all Netflix rows as Leisure." went through `query` then `propose_changeset`: a
  card titled "Netflix-Buchungen als Leisure umkategorisieren", 12 rows previewed as
  `Subscriptions -> Leisure`, status Waiting for you, Apply and Discard, and an answer that says
  it proposed the change. "PayPal to Lea Hoffmann is always Dining." went through `set_rule`
  (5 matched, 5 updated) and renders as a collapsible Rule step with its effect and sample rows.
- Switching the conversation to Quality left the earlier turns' chips reading "Fast model" and
  labelled only the new turn "Quality model". A reload reproduced every thinking duration
  exactly (identical set of "Thought for N seconds" labels before and after, no "Thought for a
  moment"), including a 100 second one from a stopped turn.
- "What is my credit score?" answered "I cannot provide your credit score as it is not part of
  your bank transaction data. I can, however, tell you about your spending trends or your total
  income for a specific period." with no query call, and three follow-ups under it.
- Zero browser console messages and no server-side errors for the whole session.

Left for other tickets, seen in passing:

- The fast model still answers in German when the conversation has been German and the newest
  message is an English *command* ("Recategorize all Netflix rows as Leisure." got a German
  answer). The review's actual case (a German turn, then an English question) is fixed; this
  residue is a fast-model limitation, not a missing instruction.
- The model's thinking still occasionally quotes pydantic AI's "Validation feedback: Please
  return text or call a tool" retry prompt inside the reasoning panel. The prompt asks it not
  to; the UI messages never carry it (ticket 18's filter).
- The reasoning panel with no height cap and the two panels per turn are ticket 21.

Harness notes for the next browser verification, both cost me time:

- `agent-browser fill` on a React controlled input writes the DOM value without React noticing,
  and the field then stays desynced (later real keystrokes do not update state either). Use
  `click` then `type`.
- The click-below-the-fold quirk from ticket 09 also applies *above* the fold: clicking a
  Question card row that has scrolled off the top reports success and does nothing.
  `scrollintoview` first, and check the "Send N answer(s)" count before pressing it.
