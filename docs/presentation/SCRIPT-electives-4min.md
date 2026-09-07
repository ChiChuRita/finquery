# The four-minute transcript: electives and the fine-tuned models

Speaker: Liudvikas Zekas. The five story slides of the deck: Reading files, Web search, Context,
Sub-agents, Fine-tuned. About 600 spoken words at a calm pace is four minutes. The words in
brackets say where to point. Learn the bold sentences first: they are the ones to keep if you run
short.

The slides tell one story about one household: files come in, an unknown merchant is looked up,
a question is asked, the models are measured. Present them in story order (files, web, context,
sub-agents, fine-tuned). If the deck stays in fence order (context, sub-agents, files, web), say
after the sub-agents slide: "Two slides back in the story: how did that data get in?"

Hand-over line from Rahul (slide 7, Memory): "Liudvikas takes you through the four electives and
the fine-tuning, with one household as the example."

---

## Reading files: the model points, code checks (0:00 to 0:50)

One rule runs through everything you saw: **the model never touches the numbers.** We built four
fences around the model, one per elective, and I will show each one on one household.

Step one of the story: the user drops a statement PDF and a receipt photo into the chat.

[extraction card] A vision model reads the page and returns spans, never numbers: the text
"01.01.2025", the text "minus 1.150,00", the word "Miete". [verbatim card] Code then asks: does
this span occur on the page? "1.150,00" does. A misread "1150,00" does not, and that row is
refused with the sentence you see. [reconciliation card] Then arithmetic: opening balance plus 433
bookings equals the closing balance, to the cent. **Anything flagged becomes a review card, and
nothing is written silently.**

[bottom row] The receipt has no text layer, so the printed total is the only proof: seven items
sum to 20,73, and the booking is matched and split into groceries and household. Nineteen of
nineteen receipt totals were right.

## Web search: one token leaves, one page is read (0:50 to 1:40)

Step two: one merchant on the statement is unknown, Vogtlandbahn.

[scrubber] Fence four is what may leave the laptop. Three rules in order: a legal form anywhere
means business, a list of two hundred German given names refuses persons, then the two-word
rule. GmbH fires, so the token "vogtlandbahn" may leave. **No amount, date, IBAN or name is in
it.**

[loop] Now the model searches itself, within a budget of four searches and three page reads. The
floors are code, not prompt, because a strong model answered from memory and never searched. It
must search at least once. When a hit is the merchant's own page or its Wikipedia article, the
fetch is forced. And the finish has to quote a sentence that occurs verbatim on the page it read,
here the German Wikipedia line, or its confidence is capped.

[journal] Every request is written to the journal before it is sent, and cached, so this token
leaves once. [bottom bar] "PayPal Anna Weber" is a person: rule two fires and nothing leaves.

## Context: one turn, assembled by code (1:40 to 2:25)

Step three: the user asks "How much did I spend on groceries in May?". Fence one is what the
model gets to see.

[isolation] A profile is the boundary, enforced in code: a temporary view with this profile's id
inlined, on a read-only connection. **No WHERE clause the model writes can widen it.**

[selection] Each turn is assembled fresh: at most five memories chosen by keyword overlap, the
rolling summary of the older turns, the last six turns in full, and only the tools that apply.
Web lookup is off here, so that tool is not even declared. The chat model sees nothing else.

[bar] Compression: at 60 percent of the 32k window, the small model folds the older turns into a
summary the user can edit in the transcript. A pending question card is never summarized away.

## Sub-agents: one question through the query tool (2:25 to 3:10)

Fence two is what the model gets to do. **The chat model never runs SQL itself. It asks a
sub-agent.**

[request, then the blue card] The request arrives in plain words. The query sub-agent must answer
in a forced schema, and the first field is its reasoning: period May 2025, category Groceries,
spending is negative and reported positive, no grouping. Then the SQL. [guard] Code parses that
SQL into a tree and walks it: exactly one SELECT, only the profile view, no CASE that invents a
label, no cents column, LIMIT 200 added. [run] It runs read-only and returns one row, 440,72.
The answer may say that figure and nothing else.

[bottom lane] A wrong first attempt, "SELECT star FROM transactions", gets the guard's sentence
back word for word, and the sub-agent rewrites once. [chips] Six sub-agents work this way: query,
chart, categorizer, extraction, memory, web lookup. The chat agent waits for its tool, so we do
not claim the extra credit.

## Fine-tuned inside the fences (3:10 to 3:55)

Step four: is the small model good enough to live inside those fences? We fine-tuned it.

[sample] This is one training sample, from a student household in Leipzig: the exact production
prompt, and the answer as the tool call, reasoning first. **A sample was kept only when its SQL
ran and an independent check agreed to the cent.** Sixty agents wrote them over five synthetic
households.

[middle] QLoRA, one night on the HPI cluster: two adapters for the small model, one for queries
and one for charts, 70 megabytes each, attached to the frozen base at inference.

[bars] Scored in the real app, with the product's own runtime, on the Berlin household the
training never saw. **The query adapter goes from 62 to 78 percent on 459 questions and ships.**
The chart adapter stays flat, and we know why: the misses are in the plan's data question, where
our data had no failure examples. We say so.

Four fences, one rule, one adapter that ships. Thank you. [3:55]

---

## If you run long

Cut in this order: the receipt sentence on the files slide, the "PayPal Anna Weber" line, the
"sixty agents" sentence. Never cut a bold sentence.

## Numbers you say, with the source

| number | slide | source |
| --- | --- | --- |
| 433 bookings, opening 4.210,55, closing 9.909,56 | files | `tests/test_extraction.py` (the synthetic statement PDF) |
| 20,73 total, 7 items, 11,75 + 8,98 | files | `tests/test_extraction.py`, `fixtures/synthetic/bill-edeka-2025-03-14.png` |
| 19 of 19 receipt totals | files | `.scratch/finquery/reviews/receipts-web-2026-09-05.md` |
| 4 searches, 3 page reads, 200 given names | web | `src/finquery/weblookup/loop.py`, `scrub.py` |
| Vogtlandbahn: 1 search, Wikipedia read, 0.95 | web | ticket 53 Comments, `.scratch/finquery/reviews/weblookup-2026-09-06.md` |
| 5 memories, last 6 turns, 60 % of 32k = 19,661 | context | `src/finquery/context.py`, `memory.py` |
| 440,72 EUR groceries May 2025 | sub-agents | `docs/demo-script.md` |
| 62 to 78 % on 459 questions, 38 to 36 on 302 charts | fine-tuned | `bench/results/20260907-adapters-compare.md` |

## The two-minute questions, one line each

- Where is isolation enforced? In the SQL guard, a temp view with the profile id inlined,
  read-only. A prompt cannot cross it.
- Why 60 percent and not the limit? The summarizing model needs room, and a tool result can be
  large; the turn that crosses the threshold already runs small.
- Why reasoning first in the schema? The model commits to period, filters, sign and grouping
  before it writes SQL; the check pass judges that line as strictly as the SQL.
- What is a sub-agent technically? A tool whose handler runs a second Pydantic AI agent with its
  own instructions and a forced output schema, checks the answer with code, returns data.
- What is sqlglot? A SQL parser. The guard reads the statement as a tree, so a comment or odd
  casing cannot hide anything, and it can repair `/ 100` to `/ 100.0`.
- Why not trust the vision model? Under blur it invents digits; the verbatim guard makes it a
  pointer into the source, not a source.
- What leaves on a web lookup? A scrubbed merchant token and the model's own short search query,
  checked by the same scrubber. Journaled before sending.
- What is QLoRA? Frozen base weights in 4-bit, a small low-rank correction trained next to each
  weight matrix. Our adapters are 70 MB, attached at inference by llama.cpp.
- Why did the chart adapter not gain? The misses are the plan's data question returning nothing,
  and every training sample was a success; a second round needs plan-repair rows. We also found
  and fixed a runtime bug in multi-line tool-call JSON on the way.
- Why only the small model? We trained the 12B too: four points on 459 cases, inside the set's
  resolution, at half again the time per question. Dropped.
- Why is the benchmark household unseen? The shipped household's cases went into the benchmark,
  the five synthetic households into training; the split is hashed and frozen.
