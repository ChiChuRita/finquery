# 30: End-to-end test fixes

**What to build:** The comprehensive end-to-end test of 2026-09-05 (../e2e-2026-09-05.md, 57 pass, 4 partial, 2 fail, zero console errors) found three blockers and five majors, plus a receipt date miss. Fix them at the root.

**Blocked by:** 17 (merged)

**Status:** ready-for-agent

- [x] B1 Stop during a chart turn must never reach the React error boundary: guard the reads on a half-arrived chart data part (the .length on undefined) and any other part that can arrive partially; the partial turn is kept; a test drives a stop mid chart stream at the HTTP seam and a browser check repeats it three times
- [x] B2 The CSV mapping confirmation card renders with its options and free-text field: the ask_user call must carry the rows and options itself (the stored call had rows: [] while the options sat in the import_file output); a card with nothing to answer is never emitted (server refuses to build it); test with unknown-bank-2025.csv through the chat path
- [x] B3 A changeset never reports Applied unless the database changed: apply verifies its effect (split_count for splits, category for recategorize, existence for delete) inside the same transaction and fails loudly otherwise; the card reflects the real status; find the intermittent cause of the bill split writing no legs (likely the apply running against a stale or different session, or an exception swallowed after the status flip)
- [x] M1 review_batch returning a queue is always followed by an ask_user card: when the model narrates the card instead of calling the tool, the server emits the card itself from the review_batch result (same mechanism as the seeded review conversation), so the next card is never missing
- [x] M2 "Compare a second answer" on a chart turn returns a second answer or a clean 409 with a readable message, never a 500 printed into the transcript; test at the HTTP seam
- [ ] M3 Stacked bars: the chart runner's query hint and the plan must group by both the position and the series column when a tail is folded into Other; the self-check already catches duplicates, so the fix is in the prompt and the fold step; the stacked benchmark prompt passes first attempt
- [ ] M4 The sentence under a chart comes from that chart's rows: the chart tool summary names the chart and its figures, and the prompt says the answer describes the chart that was just drawn, never an earlier one; test with two chart turns in a row
- [ ] M5 Sankey: a self-loop (Income to Income) is folded or refused before the code pass, with a query hint that the source and target columns must differ
- [ ] Receipt date: the bill extraction reads the printed date (the real Edeka receipt prints 04.09.26 20:00 and the model fell back to today); prompt the date field explicitly with German short formats and verify against the text spans; the real receipt at fixtures/private/edeka-bill-real.jpeg is the manual check (never commit it)
- [x] Minors: remember confirms in one line; a deleted memory is not resolved from history; follow-up chips follow the profile's fixed language; the duplicate summary is not a copy of the Applied line; mapping preview uses German dates and decimals; a second Stop keeps the partial tool step; thinking panel order; bulk Recategorize never defaults to Needs review and confirms before applying
- [ ] Suite green, typecheck and build clean; browser verification of every blocker and major in both themes

## Comments

Done 2026-09-05, the B1, B2, B3, M1, M2 and Minors half (the chart items M3 to M5 and the
receipt date are a second agent's). `uv run pytest` is 192 passed, 4 skipped (the four are
environmental: the two private Trade Republic fixtures, the private statement PDF and the
opt-in local smoke suite). `npx tsc --noEmit`, `npm run build` and `oxlint` are clean (34
warnings, the pre-existing set, none in a touched file). Screenshots: `/tmp/finquery-30a/`.

### B1: the tool result of a stopped run is not a tool result

A cancelled run closes the call it was in the middle of with a plain sentence where the tool's
own object belongs, so the browser gets `tool-chart` in state `output-available` and
`output: "The tool call was interrupted before a result was produced."` Every field the chart
card reads off it is then undefined, and `output.notes.length` is the read that replaced the
whole page with the error boundary. `changeset.rows.length` and `output.sources.length` are the
same read one tool over.

The part is judged once, in `chat-view.stoppedTool`, before any card sees it: an output that is
not the object its tool returns, or a call still open on a turn the server marked interrupted,
renders as a step saying it was stopped. So the partial turn keeps the step it lost before (m6)
instead of losing it or crashing. `remember` is the one tool whose result is a sentence and is
named as such. `test_chat.test_stopping_a_running_tool_answers_its_call_with_a_sentence_not_a_result`
pins the shape the guard exists for.

`foldReasoning` also changed: the folded panel goes to the top of the turn rather than to
wherever its first block landed, which is m7 (a model that calls a tool without thinking first
drew its panel under the card).

### B2: a card with nothing to answer is refused, not drawn

The free text field is drawn per row, so the mapping card the e2e saw (`rows: []`, no
`options`) was a title with nothing under it, and it survived a reload. Three changes:

- `AskUserToolset` validates the arguments of the deferred call, which `ExternalToolset` does
  not do by default (`args_validator_func`, `max_retries=2`). A card with no rows and no
  options comes back as a `ModelRetry` whose sentence is the instruction. Seen working on
  OpenRouter: the model's first card was exactly the e2e's, the refusal reached its thinking
  ("Wait, looking at the `import_file` result again: ... options: [...]. I will call `ask_user`
  again with all these fields") and the second card carried both buttons.
- A refused card leaves nothing behind: `api/chat._renderable` drops the call with its retry,
  or a dead question would sit above the card the model then got right. Whatever the model said
  around it stays.
- The `confirm_mapping` payload stopped carrying a second copy of the note under the card's own
  field name; what is left for the tool step is `mapping_note`.

Two card-rendering fixes came out of the browser check: the mapping preview writes its dates
and amounts through `formats.py` (`01.01.2025`, `-39,90 EUR`, which is m5), and `question-card`
reads a note's newlines back, because a model retyping a multi-line note escapes them twice and
the card printed a wall of literal `\n`.

### B3: apply reads its own effect back before the status flips

The intermittent trigger was not reproducible on demand, so the fix is the one that makes the
class of it impossible rather than a guess at the trigger. `changesets._not_written` flushes and
re-reads, in the same transaction and before `applied` is written: the legs of a split and their
sum, the category, description, amount or date of a recategorize or an edit, and that a delete
left nothing behind, through column selects that go to the connection rather than to the
identity map. A refusal is a `ChangesetError`, so the request answers 400 with the sentence, the
write rolls back with it, and the changeset stays `proposed` with Apply still on the card.
`is_distinct_from` rather than `!=`, because a row left at Needs review compares NULL against
the target and would drop out of a `!=` count. A taxonomy change is not checked and says why.

Three bill splits applied in the browser (Edeka, Rossmann, OBI), 3, 2 and 4 legs, every one of
them on the Transactions page afterwards.

### M1: the server shows the card the model only wrote about

`api/chat.card_the_model_did_not_ask`: when a turn produced a `card` from one of the four tools
that hand one over and made no `ask_user` call, the server appends the call itself and streams
it. The run then parks on it exactly as if the model had made it, which is what the test proves
by answering it. All four tools, not only `review_batch`, because the same silence kills the
same step. Follow-ups are held back on such a turn, the way they are for any pending card.

### M2: one list decides what a second answer may call

Two lists had drifted apart. The rerun declared only `query`; the refusal was a separate list of
writing tools that `chart` was not in. So a chart turn was allowed through, ran without the tool
its own prompt tells the model to use, and died when the model called it anyway.
`preferences.RERUN_TOOLS` is now the only list: the endpoint declares exactly those tools on the
rerun and refuses a turn that used anything else, with the tool named, and the frontend offers
the button on the same allowlist. `lookup_merchant` stays out on purpose: a rerun of it would
send a merchant token out of the machine because someone pressed a thumbs down.

### The minors

- **m1**, the `remember` confirmation. The cannot-answer rule read every message as a question.
  It now says a message that is not a question is never that case, and the `remember` paragraph
  says what the one line contains. "Merke dir: Mein Mitbewohner ist Max Schulz." now answers
  "I've noted that Max Schulz is your flatmate, and this will be remembered in all our
  conversations."
- **m2**, the deleted memory, was not the category-rule digest the e2e guessed. The thinking
  panel said it outright: "According to the instructions, 'my flatmate' is 'Max Schulz'". The
  system prompt's own worked example named a real person of the sample year, so deleting the
  memory changed nothing. The example now uses a name no fixture has, says outright that it is
  the shape and not a fact about this user, and names the instructions themselves among the
  places a name may not come from. Asking again after the delete answers "I don't know who your
  flatmate is."
- **m3**, the chips. `followups.language_line` names the profile's fixed language and says
  nothing on `follow`, where the exchange still decides. Verified with the profile fixed to
  English and a German question: English answer, English chips.
- **m4**, the duplicate summary. Telling the model not to repeat the Applied line did not stop
  it, because that was the only sentence the result carried. So the result carries two:
  `AskAnswers` gained `say` next to `applied`, and an applier answers with `Applied(line, say)`.
  Only the duplicate applier fills it, with ticket 10's own counted sentence. The prose now
  reads "Of 433 bookings that looked like duplicates, 0 were kept and 433 removed."
- **m5** is in B2 above, **m6** and **m7** are in B1.
- **p2**, the bulk bar. It starts on nothing chosen (the select shows "Move them to..."),
  Recategorize is disabled until something is, and it confirms with what it is about to do.

### The budget

Re-measured on the grown prompt rather than guessed: the system prompt is 3145 tokens (main
carried 2884) and the floor a compressed prompt cannot go below is 4063 (was 3710). `BUDGET =
4800` leaves about 18 percent of headroom; both numbers are in the comment in
`tests/test_context.py`. Eighth ticket to move it.

### Verified on OpenRouter, port 8101, throwaway database, session `fq30a`

The sample year through onboarding (433 rows, 408 categorized, 25 Needs review).

- **Stop mid chart, four times** (three dark, one light): no error boundary, the thinking panel
  and the stopped chart step both kept, the Stopped chip on the turn. `02`, `16`
- **unknown-bank-2025.csv**: the model built the e2e's empty card, the server refused it, the
  second card carried "Yes, import it" and "No, the mapping is wrong" with German dates and
  amounts in its preview, and confirming imported 433 of 433. `03`, `04`, `15`
- **Three bill splits applied**, legs on the Transactions page each time (the OBI parent shows
  4 legs adding to -41,76 €). `05`, `bill-1..3`
- **The second Question card** after three of four merchants were answered. `06`, `07`
- **Compare a second answer on a chart turn**: a real second answer at temperature 1.2 and a
  stored pair with both sides, no 500 anywhere. `08`
- **The bulk bar**: no default, disabled Recategorize, the confirmation, then the row moved.
  `09`, `10`, `11`
- **The minors**: the remember confirmation with English chips under a German question (`12`),
  the deleted memory answered "I don't know who your flatmate is" (`13`), the duplicate
  summary in its own words (`14`), the thinking panel above the chart (`01`).
- Zero browser console messages and zero 4xx or 5xx responses for the whole session.

### Left, seen in passing

- The import step's counted sentence is still repeated in prose right under the step (p3 of the
  e2e). It is the same shape m4 fixed and it would take the same treatment: a `say` on the
  import result. Not in this ticket's list.
- The resumed half of a card turn lists the merchants it just applied as a bullet list before
  the next card. The figures are the applied line's own, so nothing is invented, but it is one
  more thing the card below already says.
