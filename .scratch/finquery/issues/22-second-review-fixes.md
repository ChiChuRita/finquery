# 22: Second review fixes

**What to build:** The second headful review (../review-2026-09-04-second.md) confirmed the first review's blockers are fixed and found a sharper set concentrated in the query and chart sub-agents. This ticket fixes them.

**Blocked by:** 20, 21 (merged)

**Status:** done

- [x] The query sub-agent never invents categories in SQL: no CASE WHEN description LIKE ... THEN 'Groceries' classifiers. The guard rejects string-literal category labels derived from description matching, the prompt says category comes only from the category column and that Needs review is shown as its own bucket, and a test covers the refusal
- [x] A chart that fails to render in the browser is reported back to the turn: the card shows the error, the assistant's text says the chart could not be drawn and gives the numbers instead of describing a chart that is not there. The self-check runs against the real rows (duplicate (x, series) pairs for stacked bars and circular or negative sankey links are caught before the browser), and one automatic retry happens when the render fails
- [x] The reasoning stream gets the same template-token and retry-feedback filter as the text stream, and a chart turn ends with text on the first pass (no empty-text retry after a tool)
- [x] Distilled memories are written in the language of the turn they came from, and the answer language rule is verified on a fresh conversation with an English question in a profile whose memories are German
- [x] An absent subcategory renders as a dash, never the string None; a typed transaction never stores the string "null" as counterparty
- [x] Regenerate retries until the second chart differs (up to three attempts server-side) and never offers Pick on a failed side
- [x] Copy: "3 merchants", "1 row matches these filters", "Used 1 source", one number in the delete dialog, one date format in the outbound log, rendered markdown in the import tool step
- [x] Doughnut Rest slice never holds the majority: regroup so the six largest categories are shown when the rest would dominate, or state the share in the title
- [x] Web lookup cache hit shows a step saying it came from the cache
- [x] HTTP-seam tests for the guard, the chart failure path, the reasoning filter and the memory language; suite green; browser verification of a category chart, a stacked bar chart and a sankey on a categorized profile

## Comments

Done 2026-09-05. `uv run pytest` is 144 passed, 3 skipped (the three are environmental: the
private Trade Republic export and the opt-in local smoke suite). `npx tsc --noEmit`,
`npm run build` and `oxlint` are clean. Screenshots: `/tmp/finquery-22/`.

### The blocker, and why it was really three findings

**`chart/runner.py` was asking for the classifier.** The grouped-chart hint said, verbatim,
"When the taxonomy is not filled, build `topic` as a CASE expression over the merchants", and
`query/subagent.py`'s partially-categorized line said to "combine `category` with merchant
matching". So the invented categories were not the model going off script, they were the script.
Three changes, in that order of importance:

1. Both prompts now say the group always comes from the `category` column, with
   `coalesce(category, 'Needs review')` as the honest bucket for what is not categorized. There
   is a worked example for it in `query/subagent.EXAMPLES`.
2. `query/guard.validate_sql` refuses a CASE whose WHEN conditions reach `description` or
   `counterparty` and whose results are string literals (`_invents_a_category`). The refusal
   sentence is the instruction: group by the category column, show NULL as Needs review, and
   match the text columns in a WHERE clause instead. A CASE over `amount_cents` is untouched,
   which is what the shape examples in `tests/test_chart.py` use.
3. The chart hint also asks for one row per (position, series) pair, which is what the UNION of
   real and guessed categories was breaking.

### Charts that fail

- **Two rules moved out of the code check and into the rows.** `selfcheck.data_findings(shape,
  columns, rows)` is judged before a line of code is written, because no repair round can fold
  two rows for 2025-01 / Groceries into one or straighten a circular flow. Stacked and grouped
  bars need unique (position, series) pairs; a sankey needs no self link, no cycle and a
  positive amount on every link. The QuickJS stub grew the same three rules for a graph the
  code assembles itself.
- **`rendered` is on the tool result.** `ChartOutcome.rendered` is `code is not None and error
  is None`, the prompt tells the model to read it before writing a word about the picture, and
  the tool summary of a drawn chart ends with "Write your answer as text now". That last line is
  the cheap half of the empty-text retry fix: the instruction sits where the model reads last.
- **`POST /api/charts/render-failure`** (`src/finquery/api/charts.py`) is new. The frame's error
  reaches the card, the card reports it, and the server does two things: it rewrites the stored
  chart on the turn with `rendered: false`, the reason and no code, in **both** message families;
  and it runs one retry through `run_chart`. A retry that draws replaces the chart on the turn.
  One retry per chart ever, flagged by `render_error` on a failure or `retried` on what a retry
  left behind.
- The card adopts whatever the server recorded, so a failed retry turns the frame into the
  reason and takes Regenerate with it. A pair side whose frame errors loses its Pick
  (`PairSide.unavailable`).

### Everything else

- **Reasoning stream.** `api/chat.ThinkingFilter` is `MarkerFilter` plus a sentence-level filter
  for pydantic AI's "Validation feedback: ..." prompt, which the model quotes back inside its
  thinking. It releases a delta only up to the last sentence end, so a sentence is judged whole;
  `_clean_text` applies the same vocabulary to the stored thinking parts, so a reload does not
  bring either back.
- **Memory language.** The distillation prompt now has its own paragraph ("Write every fact in
  the language of the user's own message ... never translate"), and the memory block tells the
  model that a memory's language says nothing about this turn's.
- **`src/finquery/nullish.py` is new and is the root-cause fix for two findings.** A model that
  writes `"null"` or `"None"` into an optional field had that string stored: as a counterparty
  on a typed booking and as a subcategory on a bulk recategorize. `ask_user.py` already had a
  private copy of that guard; it is now one module, used by `ChangesetIntent`,
  `ProposedTransaction` and the card models.
- **The subcategory dash was a second, separate bug.** `PickerCell`'s `placeholder` was the
  literal "None" *and* the label of the item that clears the cell, and a `Select` whose value is
  the clear item prints that item's words. The trigger now renders the placeholder itself when
  the value is null, so the cell shows the same em dash the rest of the table uses, and the
  dropdown item reads "No subcategory".
- **`review_batch` returns a ready `card`** built by `categorize.review_card`, the way
  `review_duplicates` and `import_file` already do, so its note is written once with real
  plurals instead of being invented per turn ("3 merchant(s)"). `import_file` returns one too.
- **Regenerate** loops up to `ALTERNATIVE_ATTEMPTS = 3` inside the one press, comparing against
  the code already on the turn.
- **The doughnut rest slice** puts its share into the caption when it holds more than half
  (`runner._rest_share`), and the plan prompt asks for the largest six instead of five plus a
  rest row when a handful of buckets carry the spending.
- **Web lookup cache.** The card already rendered the "from the lookup cache of this profile"
  note; what was missing was the model calling the tool a second time at all. One prompt bullet.
- Copy: "1 row matches these filters", "Used 1 source" (`ai-elements/sources.tsx`), "Keep it" /
  "Delete it" in the delete dialog, the outbound log through `lib/format.formatDateTime`
  (04.09.2026, 21:57), and the import tool step through `MessageResponse` so its counted
  sentence renders as markdown.

### Numbers and requests

- Requests per turn are unchanged. A chart that the rows make impossible now costs **less**: the
  code pass never runs. A render failure costs one plan, one statement and one code on the fast
  slot, once.
- **The test context budget stayed at 3600.** Re-measured rather than assumed: the system prompt
  is 2374 tokens (was 2110) and the floor a compressed prompt cannot go below is 3282 (was
  3018), so there is about 9 percent of headroom left. The comment in `tests/test_context.py`
  carries both numbers. The next ticket that adds a prompt block will have to move it.
- `tests/conftest.py` gained `turn_of(chunks)` and `tool_call_of(chunks, tool)`, moved out of
  `test_preferences.py` so `test_chart.py` can name a turn and its chart call without importing
  from another test module.

### Verified on OpenRouter, port 8087, throwaway database

`fixtures/synthetic/sparkasse-2025.csv` imported through the Sparkasse preset by curl (433 rows)
and categorized (384 by the dictionary, 24 by the model, 25 Needs review).

- **Spending per category as a doughnut**: `COALESCE(category, 'Needs review') AS topic`, six
  real categories in the legend (Housing, Groceries, Cash, Transport, Shopping, Dining), text on
  the first pass, "Housing mit 14.736,00 EUR" matching the row. `01`
- **Stacked bars per month and category**: 132 rows, twelve months, eleven series including
  Needs review as its own bucket. This is the chart that crashed the browser last time. `03`,
  `04`
- **Sankey from income into the categories**: 11 links, Einkommen into Housing, Insurance, Needs
  review, Shopping, Subscriptions and Transport. This is the other one that crashed. `05`, `06`
- All three: `rendered: true`, no repairs, no `<turn|>` and no "Validation feedback" anywhere in
  the conversation payload, and every turn ended with text on the first pass (5, 11 and 18
  seconds of thinking, no second round).
- **The failure path**, driven through the endpoint the card calls: the first report retried and
  the card swapped to the chart that drew; the second report recorded the failure, and a reload
  shows "The chart could not be drawn in the browser: TypeError: A stack requires at most one
  value for each position and series" with the SQL and the 12 rows still under it and no
  Regenerate. `07`
- **Language**: a brand-new conversation, an English question, two German memories in the prompt
  ("2 memories used") and an English answer with German money. The fact the same turn stored is
  English ("I want to keep my transport costs under 150 EUR a month."), and the fact distilled
  from the earlier German turn stayed German. `08`
- **Typed transaction**: "I paid 12 EUR cash for lunch today" previewed as `lunch · Cash` (not
  "null · Cash") and stored `counterparty: null`. `09`
- **Bulk recategorize**: 12 Netflix rows to Leisure through a changeset, and every Subcategory
  cell shows the em dash. `11`, `12`
- **Copy**: "1 row matches these filters", "Delete this transaction? / Keep it / Delete it",
  "04.09.2026, 21:57" in the outbound log, and the import step's "**0 of 2 bookings** from
  `sparkasse-mini.csv`" rendered rather than printed. `13`, `14`, `17`, `19`
- **Web lookup**: one search left the machine for the token `cafe milchbart`; asking again in
  another conversation rendered the step reading "from the lookup cache of this profile, nothing
  left the machine" and added no log entry. `15`, `16`, `17`
- **Regenerate**: one press produced a different chart and a pair with a Pick under each, where
  the review needed three. `20`
- Zero browser console messages for the whole session.

### Left for another ticket, seen in passing

- The answer text of a turn whose chart failed *after* the answer was written still describes the
  chart: the model read `rendered: true` because it was true when the tool returned. The card is
  honest, the sentence above it is stale. Fixing that means re-running the turn, which is a
  bigger change than this ticket.
- The chart Y axis still starts above zero on a line chart, chart titles and month labels still
  come back German for English questions, and a split parent still loses its enriched title.
  All three are carried findings from the first review and are untouched here.
