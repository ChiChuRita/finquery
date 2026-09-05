# 42: Prompt engineering for the sub-agents and the chat agent

**What to build:** Give every model-facing prompt three things a small model needs: few-shot examples drawn from validated data, a short reasoning step before the answer, and a retry framing that shows the mistake and asks for a correction instead of a fresh start. Measured before and after on the benchmarks and the existing measurement scripts. Requested by the user on 2026-09-05. The query sub-agent's prompt is done inside ticket 40 (same file); this ticket covers the rest.

**Blocked by:** 37 (merged); coordinate with 40 (query prompt) and 41 (benchmark files)

**Status:** done

Prompts in scope: chart sub-agent (plan and code passes, chart/subagent.py), categorizer (categorize/subagent.py), extraction (statement pages and receipts, extract/subagent.py), memory distillation (memory.py), the follow-up step (followups.py), the web lookup decision loop (weblookup/loop.py), and the chat agent's system prompt (agent.py) for how it uses tool results and hands mistakes back.

- [x] Few-shot: every prompt carries one worked example per hard pattern it is known to get wrong, taken from validated sources (the chart benchmark's train split once ticket 41 lands, else the hand-written ones judged correct; the twenty public receipts and the real Edeka receipt for extraction, described without personal data; the categorization measure script's misses; the review reports), never a heldout benchmark item
- [x] Reasoning before the answer: each forced tool gets a short `reasoning` field filled first (three to five one-line steps specific to that job: for charts the shape choice and the columns, for the categorizer the merchant reading and the category versus subcategory choice, for extraction the layout and where the date and total sit, for memory whether the fact is durable), so the model commits to an interpretation before producing the structured answer; the reasoning is kept in the narration or the tool result where a step already renders it, never in prose
- [x] Retry framing everywhere a retry exists (chart self-check repairs, categorizer confidence resubmits, extraction guard rejections, memory dedup refusals, tool validation errors): the message shows the previous reasoning and answer, the exact finding, and asks for the corrected reasoning and answer with a diff of what changed
- [x] Chat agent prompt: how to read a tool result (figures, rendered flag, applied lines), when to call a tool again with a sharper request, and how to say what could not be done; kept within a few hundred tokens of growth with the context BUDGET re-measured
- [x] Measured: chart benchmark on qwen/qwen3.5-9b and google/gemini-3.8-flash before and after (figure match, first attempt, drawn); categorization on the shipped year with scripts/measure_categorization.py before and after (share categorized, spot check of twenty); extraction on the twenty public receipts and the synthetic PDF before and after (items add up, dates read); tables in the ticket and the bench README's own section
- [x] Prompt example tests still cover every worked example; suite green; build clean

## Comments

Done 2026-09-05. `uv run pytest` is 313 passed, 4 skipped (the four are the usual environmental
ones: the two private Trade Republic fixtures, the private statement PDF and the opt-in local
smoke suite), five of the tests new. `npx tsc --noEmit` is clean and no frontend file is
touched. The query sub-agent's prompt is ticket 40's: nothing here touches `src/finquery/query`
or either benchmark set.

### What changed, per prompt

**Chart, plan pass** (`chart/subagent.py`). `ChartPlan` opens with `reasoning`, three to five
one-line steps (the language of the request, what it compares, the shape that reads that
comparison, the columns, the period), and `reason` is gone: the steps are the reason, and
`as_text` renders them into the thinking panel, which is where the narration already showed the
plan. Two worked plans from the training half of the benchmark (13-doughnut-categories-en and
10-quarter-groups-de), chosen for the two decisions this pass gets wrong: an English request
about German data coming back `de`, and a request naming quarters that asks for months.

**Chart, code pass.** `ChartCode` opens with the same field (the shape and its mark, the column
names of *these* rows and which one holds the numbers, what each axis is), and the runner
narrates it per attempt. Two more worked examples, both from the train split: an area over a
`quarter` column (a name axis, no `monthShort`, no label dropped) and a doughnut over a `label`
column. Both teach the failure the qwen run repeated most: the code copies a column name out of
the example instead of reading the rows brief, and `radialArc` reads `merchant` where the rows
carry `topic`. Two contract lines say it in words, and one more says the answer is the body
itself, never wrapped in a function and never inside a markdown fence, which four datapoints
came back as. The repair round is now a correction: the model's own reasoning, its own code, the
findings, and "answer again with the corrected reasoning and code, what changed on the first
line".

**Categorizer** (`categorize/subagent.py`). `Categorization` opens with `reasoning`, one line per
merchant: what the merchant reads as, and whether a subcategory of that category really fits. The
worked example is a batch of four now, covering the patterns the single pair did not: money in
that is a salary and not a spending category, a person paid through PayPal at 0.4, and a receipt
line item, which is the other caller of this sub-agent (`extract/bill.py`). A batch naming a
category the household does not have, or leaving a merchant out, is resubmitted once with its own
entries and the exact finding: both cost the merchant its category silently today, and the
pipeline reads that silence as Needs review.

**Extraction** (`extract/subagent.py`, `extract/statement.py`, `extract/bill.py`). Both readers
open with `reasoning` (the layout, where the first booking starts, where the date, the amount and
the balance stand, which lines are not bookings; for a receipt what it is, where the total and
the date stand, which lines are not articles). Each carries one worked example in that shape, the
receipt one written from the public set of twenty and holding a subtotal, a quantity line and a
discount. A guard rejection is handed back once, framed as a correction: a statement page whose
figure is not printed on it is read again with the refused rows and the finding, and the second
reading is kept only when the same guard refuses less of it; a receipt whose items do not add up,
which came back with no items, or whose currency refuses it is looked at once more the same way,
and the better of the two readings wins. Both retries are judged by code. `no_date` deliberately
triggers no retry: nothing could check an invented date, and the card asks the user for it.

**Memory distillation** (`memory.py`). `DistilledFacts` opens with `reasoning`, one line per
candidate: what the turn established and whether it is still true next month. Three worked
exchanges whose right answer is twice "store nothing" (a figure, an order for this turn) and once
a standing rule. A pass whose every fact was refused (a figure, a date, a name this turn proved
absent, something the profile already knows word for word) is handed the refusals once with its
own sentence in front of them, and told that an empty list is the right answer and the usual one.

**Follow-ups** (`followups.py`). Not a forced tool, so no reasoning field. Two worked exchanges,
one of them a question the transactions cannot answer, which is the case its own copy singles out
and the one the reviews saw handled worst.

**Web lookup** (`weblookup/loop.py`). `Decision` opens with `reasoning`, two to four lines, and
the rules carry one worked lookup with both of its steps (a search, then a finish citing the page
it read). Every refused step now carries the decision it refused, the model's own reasoning and
what to send instead, rather than one line the model reads as a new question and starts over on.

**Chat agent** (`agent.py`). One paragraph, in the fixed order between the cards rule and the
`tool_failed` rule: which fields an answer may be written from (`figures`, `rows`, `row_count`,
`rendered`, `applied`, `say`, `error`) and that a field a result does not carry says nothing at
all; when to call a tool once more with a sharper request and never the same one twice; and how
to say what could not be done without closing the gap with a figure nothing returned. Tool
validation errors were already framed this way in code (`AMOUNT_NOT_ASKED_FOR` and the
`ModelRetry` sentences name the finding and the corrected call, with the refused call still in
the history), so nothing there needed changing.

### Prompt growth, in the app's own estimator

| prompt | before | after | growth |
| --- | ---: | ---: | ---: |
| chart plan | 967 | 1286 | +319 |
| chart code (the contract plus the examples one call carries) | 1339 | 1853 | +514 |
| categorizer | 606 | 857 | +251 |
| extraction, statement page | 422 | 747 | +325 |
| extraction, receipt | 858 | 1292 | +434 |
| memory distillation | 532 | 769 | +237 |
| follow-ups | 155 | 324 | +169 |
| web lookup | 519 | 819 | +300 |
| chat agent | 3592 | 3919 | +327 |

The chat prompt is the only one with a budget on it. `tests/test_context.py` re-measured the
floor a compressed prompt cannot go below the way its own comment describes, twelve turns at the
budget: 4838 tokens, up from 4500. `BUDGET = 5700` keeps the same 18 percent of headroom. Tenth
ticket to move it.

### Measured: the chart benchmark

`--set chart`, 63 datapoints, OpenRouter, 2026-09-05. Before is the committed baseline of
`bench/README.md` (the `--set all` run of the same day), after is this ticket's run. The same
table is appended to that README as its own section.

| google/gemini-3.8-flash | figure match | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| before | 92 % | 98 % | 95 % | 100 % | 98 % | 97 % | 6.3 |
| **after** | **97 %** | 98 % | 97 % | 100 % | 98 % | 97 % | 7.2 |

Per shape, the area chart is the whole move: 67 % to 100 % (both cumulative charts were drawn as
plain monthly series before), the line 90 % to 100 %, the bar 87 % to 93 %, the doughnut 100 % to
88 %, whose one loss is a query that came back with no rows at all.

**The qwen run is 26 of 63.** The OpenRouter key hit its total limit mid-run and the remaining 37
datapoints are 403s, which is also why the extraction and categorization runs below are the last
ones this key could pay for. On the 26 that ran, all hand-written, against the same 26 of the
baseline:

| qwen/qwen3.5-9b, 26 of 63 | figure match | columns map | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: |
| before | 46 % | 73 % | 73 % | 38 % | 7.9 |
| after | 50 % | 85 % | 69 % | 46 % | 12.8 |

Twenty-six datapoints is well under the error bar the bench README already names for Qwen, so the
honest reading is "no regression signal, and the columns-map move is the one the two new examples
were written for". Re-run it when the key has credit.

### Measured: categorization

`scripts/measure_categorization.py` against the shipped year on a throwaway database, before and
after, same fast slot.

| the shipped year, 433 bookings | before | after |
| --- | ---: | ---: |
| by the profile's rules | 0 | 0 |
| by the merchant dictionary | 384 (88.7 %) | 384 (88.7 %) |
| by the categorizer | 24 (5.5 %) | 24 (5.5 %) |
| Needs review | 25 (5.8 %) | 25 (5.8 %) |
| categorized | 408 (94.2 %) | 408 (94.2 %) |
| model calls | 1 | 1 |

The two runs are identical line for line, spot check included: all 39 enriched titles land in the
same category and the same four PayPal people come back at 0.4 for the Question card, which is
the right answer for them. That is what this dataset can say. Only seven of its 39 merchants ever
reach the categorizer, the dictionary knows the rest, and the model already placed those seven
correctly, so no resubmit fired because there was nothing to resubmit. What this prompt work is
really measured by is the receipts below, where the same sub-agent categorizes line items, and by
the next import of a profile whose merchants the dictionary does not know.

### Measured: extraction

`scripts/measure_extraction.py`, the twenty public receipts of `fixtures/private/receipts-web/`
scored against the merchant, date, total and item count their own `SOURCES.md` records, plus the
shipped 15 page statement PDF.

| twenty public receipts | before | after |
| --- | ---: | ---: |
| printed total read to the cent | 19 of 19 | 19 of 19 |
| date right (17 printed, 3 correctly unread) | 20 of 20 | 19 of 20 |
| line items add up to the printed total | 15 of 20 | 16 of 20 |
| a euro receipt refused as foreign money | 1 (Schlecker) | 0 |
| the photo of three receipts says so | no | yes |

| the shipped statement PDF | before | after |
| --- | ---: | ---: |
| rows read | 433 of 433 | 432 of 433 |
| flagged | 0 | 1 |
| reconciliation | ok | failed, naming the row and the 66,30 EUR gap |

What moved the right way on the receipts: the Lidl 2007 receipt reads all ten of its items and
adds up (the second subtotal used to stop it at nine), the Combi and ALDI Hesel receipts recover
an item each, the Polish receipt loses its `does_not_add_up` and keeps only the currency refusal
it deserves, and the photo of three receipts says so on the card. What moved the wrong way: the
dot-matrix Schlecker date was not read at all this time (a flag and a question to the user, not a
wrong booking), and the US receipt came back with an empty currency, which would have booked
$2.18 as 2,18 EUR. That last one is the single failure on this path that nothing later catches,
so the currency line was rewritten to say "copy the sign printed in front of the figure, leave it
empty only when nothing is printed at all" (commit "Copy the currency sign when a receipt prints
one"). It landed after the run and the key was empty by then, so it is the one prompt line in
this ticket that is not inside the measured numbers.

The PDF lost one booking of 433, on page 13. The reconciliation guard caught it, named the row
and the gap, and the review card is what the user would see, which is the designed behaviour for
exactly this. It is one sample against one sample of the same file on the same slot, so it is
either variance or the reasoning field costing output tokens on a 30 row page. The page-level
retry cannot help there: it fires on the verbatim guard, and reconciliation is judged over the
whole statement, where no single page can see the hole.

### What is left

- The Qwen chart number, and a second and a third sample of the statement PDF. Both need credit
  on the OpenRouter key.
- A page whose own balance chain breaks could be read again the way a verbatim rejection is,
  which is the retry that would have caught the lost booking. It needs the reconciliation to run
  per page before the pages are gathered, so it is a change to `extract_statement`'s shape rather
  than to a prompt, and it wants a measurement to justify it.
- The categorizer is measured on a dataset that barely exercises it. A profile of real merchants
  (the private Trade Republic export) would say much more, but its rows carry a real name and an
  IBAN, so nothing from it belongs in a ticket comment.
