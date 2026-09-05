# 27: UI and UX refinement pass across every page and component

**What to build:** Walk every page and every flow as a first-time user in a real browser and refine the experience: discoverability, affordances, flow friction, copy clarity, empty, loading and error states, keyboard use, confirmation and undo patterns, what the user sees while waiting, and how each tool step, card and page explains itself. Ticket 26 owns spacing and visual consistency and ticket 25 owns chart internals; this ticket owns how things work and read. Requested by the user on 2026-09-05.

**Blocked by:** 24 (merged)

**Status:** done

- [x] A written walkthrough as a first-time user of the full demo path (new profile, drop a CSV in chat, answer Question cards, ask questions, chart, changeset, split from a bill photo, memory in a second conversation, model switch, stop, compression, thumbs and Regenerate, web lookup, Imports overview, Transactions, Memory, Feedback, Settings) with a friction list: every moment of confusion, dead end, missing affordance, unclear copy, or wait without feedback
- [x] Fixes for the friction list at the source: flow changes (what happens next after an import, after a card, after Apply), affordances (what is clickable, what is pending, what is done), copy (titles, notes, empty states, buttons, tooltips, error messages in plain language, real plurals, one date and money format), loading and streaming feedback (what the user sees during a two-minute PDF extraction or a long Qwen turn), keyboard (Enter to send, Escape to cancel, focus management in dialogs and cards), confirmations only where they earn their place, undo where it is cheap
- [x] Every tool step and card explains itself in one line to someone who did not read the spec (query, chart, changeset, question, import, lookup, memory, set_rule, review_batch, duplicates, extraction review)
- [x] Empty states on every page say what to do next and offer the action; error states say what went wrong and what to try
- [x] Before and after screenshots of each fixed moment in both themes; behaviour changes covered by HTTP-seam tests where the server changed; typecheck, build and suite green; zero console messages

## Comments

Done 2026-09-05. `uv run pytest` is 159 passed, 4 skipped (the four are environmental: the two
private Trade Republic fixtures, the private statement PDF and the opt-in local smoke suite).
`npx tsc --noEmit`, `npm run build` and `oxlint` are clean (31 warnings, the same pre-existing
set as ticket 24, none in a touched file). Zero browser console messages for the whole session.
The friction list is `/tmp/finquery-27/FRICTION.md`, screenshots `/tmp/finquery-27/before/` and
`/tmp/finquery-27/after/`.

The walkthrough: an empty profile, `sparkasse-2025.csv` dropped in the composer, the Question
card, a query, a chart, a changeset with Apply, `bill-edeka-2025-03-14.png` as a receipt, a
`remember`, a second conversation on the quality slot, a long turn, thumbs, Regenerate and Pick,
web lookup on and a lookup, the same merchant again, a cannot-answer question, then Imports,
Transactions, Memory, Feedback and Settings. Twenty-nine findings; twenty-seven fixed, one was
not a defect, one left with a reason.

### The two blockers were the same mistake

**A card the model typed out instead of showing.** Answering the first Question card made the
assistant call `review_batch` again and then write the next card into its answer as two markdown
tables, with "(Note: I am showing the card structure as requested by the protocol via `ask_user`
which is already rendered in your interface.)" under it. No card was drawn, so the last merchant
could not be answered at all. The receipt path did the mirror image: the split proposal card
rendered with its own Apply and Discard, and the model put the same split on an `ask_user` card
with four rows, no options and a disabled Send.

Both are one missing rule, and it is now a paragraph in `SYSTEM_PROMPT` immediately before "After
a tool returns, always write the answer as text", which is where the model reads last:

- The four tools that hand over a ready `card` are named, and the card goes to `ask_user` once,
  unchanged.
- A card, its rows, its buttons and its note are never written into the answer, and `ask_user`,
  cards and the instructions are never named in it.
- `propose_changeset`, `apply_simple_edit` and the split a receipt proposes are already on
  screen, so they take no `ask_user` call at all.

Verified twice on OpenRouter: the second Question card renders as a card with the last merchant
in it, and the receipt turn ends with one split card and one sentence.

### The reasoning panel

Two defects, both from the panel's state being someone else's:

- `Reasoning` closes itself **once** (`hasAutoClosed`). A turn that thinks, calls a tool and
  thinks again reopened it and then never closed, so the changeset turn ended with 600 px of
  scratch work above the answer, quoting the system prompt back at the reader. `ThinkingPanel`
  now owns `open`: it follows the stream, and between two of those moments the reader's own
  click stands.
- The 224 px cap was applied for as long as the *turn* ran rather than while that panel streamed,
  so a folded panel mid-turn left an empty hole in the transcript. The cap follows the panel now.

`foldReasoning` also changed shape: it used to merge only *adjacent* reasoning parts, so a turn
with two tools drew three panels, each labelled with the turn's whole thinking time. All the
reasoning of a message folds into the first panel: one panel, one honest duration. That is the
"two reasoning panels per turn" both reviews carried as still-present.

### A raw model token, found on the way

Two answers carried a line reading nothing but `thought`. OpenRouter serves the same Gemma models
and swallows `<|channel>` (a special token) but hands the channel's **name** back as ordinary
text. `local/gemma.strip_channel_lines` drops a line that is only a channel name, `strip_markers`
calls it (so a reload is clean too), and `api/chat.TextFilter` is `MarkerFilter` plus line
buffering for the live stream, the same shape as `ThinkingFilter`. The test feeds a whole line
and one split across two deltas, and asserts a sentence containing the word is untouched.

### One place for a figure in a sentence

`src/finquery/formats.py` is new: `eur(cents)` and `day(value)`. Most numbers reach the browser
as machine-readable values and `lib/format.ts` writes them out, but a few sentences never pass
through it, and every one of them was en-US: the split summary ("of -20.73 EUR becomes 3 legs"),
the split refusal ("add up to -15.00"), the receipt's own check ("add up to 20.73 EUR") and the
already-booked message with an ISO date in it. `changesets._euro` stays as it is and says why in
its docstring: it is the machine-readable amount of a preview row.

### Everything else

- **Flow.** The import step already prints its summary, so the prompt stops the model repeating
  it and asks for what is left to do instead. Follow-ups and the answer thumbs are held back
  while a Question card is unanswered. A resumed card turn now gets follow-ups at all:
  `_followups` reads the turn's opening prompt when the request produced none, which is why the
  one turn a user most needs a next step after was the only turn in the app without one. Every
  send scrolls the transcript to the bottom.
- **Cards and steps that explain themselves.** The changeset card carries one line per status
  ("A preview. Nothing is written until you press Apply.", "These bookings have changed. Undo
  puts them back as they were."). The query step says what a sub-agent wrote and what the guard
  admitted. The `remember` step says the fact is shared by every conversation and where to
  change it. The `review_batch` step says each answer becomes a rule. The lookup step says
  exactly what left the machine and where the log is, which is the audit story the feature
  exists for.
- **Web lookup cache.** The prompt bullet became sharper ("the step it renders is the only proof
  the user has"), and the German re-ask now calls the tool: the step reads "from the lookup cache
  of this profile, nothing left the machine" instead of an answer out of thin air.
- **Memory.** The distillation prompt refuses an order meant for one turn ("Recategorize all
  Netflix rows as Leisure", "answer in more detail") and keeps only the standing rule behind it.
  The same command now stores "Netflix bookings are always categorized as Leisure." Edit and
  Delete on the Memory page are dimmed rather than invisible.
- **Copy and format.** Preview dates are `07.12.2025`, "1 line skipped", "hosted" instead of
  "resident" off the local provider, the Transactions empty-results line no longer names a date
  range nobody set.
- **Keyboard and a11y.** Enter in a Question card's free-text field sends the card. Option
  buttons are named per row and carry `aria-pressed`; the free-text fields are named per row.
  The taxonomy's thirteen "+ Subcategory" buttons, the category names and the subcategory chips
  are named. The scroll-to-bottom button and the two halves of a chart pair are named. The
  thumbs read "This response was useful" rather than "Yes. Was this response useful?".
- **Confirmation.** Renaming a category and clicking away used to discard the edit silently while
  every inline cell in the app saves on click-away. Blur now opens the same preview dialog Enter
  opens (it still writes nothing), Escape still gives up, and a `done` ref stops the unmount's
  blur proposing the rename twice.
- **Empty states.** Memory, Feedback and Transactions each grew the New chat button the Imports
  page already had, since every import happens in a chat.

### Tests and the budget

Four new or changed HTTP-seam tests, all at the stream or the REST surface:

- `test_chat.test_a_bare_channel_name_never_reaches_the_answer`
- `test_changesets.test_a_split_summary_writes_a_four_figure_amount_the_german_way` and the
  German format asserted on the existing split and refusal tests
- `test_categorization.test_answering_a_question_card_applies_the_answers_in_code` now asserts
  the `data-followups` part a resumed card turn ends with. It also clears `scripts.fast_call`
  before the answer: with a schema script installed, the non-streamed post-turn steps go to it
  rather than to the turn's own script, which is worth knowing for the next test that scripts
  both sides.

**The test context budget went from 4000 to 4500.** Re-measured rather than assumed: the system
prompt is 2765 tokens (was 2481) and the floor a compressed prompt cannot go below is 3673 (was
3389), so 4500 leaves about 18 percent of headroom. The comment in `tests/test_context.py`
carries both numbers. Seventh ticket to move it.

### Not touched, on purpose

The chart card and the chart itself (ticket 25), and spacing, alignment and visual tokens
(ticket 26). The one exception is the empty state's intro paragraph, where `text-balance` broke
the line after "Drop a CSV"; that is copy legibility, and the copy was shortened with it.

### Left

- The model still works out a share in prose on a deliberately open-ended request ("about 11,4%
  of your total annual dining spending"). The prompt already forbids it in the sentence that
  names sums, counts, averages, shares and comparisons; a fifth restatement is not a fix.
- A merchant looked up in German and in English leaves two facts saying the same thing. Ticket 22
  made a fact carry the language of its turn on purpose and the deduplication compares text.
  Matching facts across languages is a new mechanism, not a refinement.
- Story 71's sanity check button exists but only on the local provider, which is correct: there
  is nothing to check on a hosted one.
