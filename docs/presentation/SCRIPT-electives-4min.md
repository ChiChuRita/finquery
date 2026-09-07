# The four-minute script: electives and the fine-tuned models

Speaker: Liudvikas Zekas. Slides 8 to 12 of the deck (Context, Sub-agents, Reading files,
Web search, Fine-tuned). About 540 spoken words at a calm pace is four minutes. Each slide gets
about 45 seconds. The words in brackets say where to point. Learn the bold sentences first: they
are the ones to keep if you run short.

Hand-over line from Rahul (slide 7, Memory): "Liudvikas takes you through the four electives and
the fine-tuning."

---

## Slide 8, Context: what the model gets to see (0:00 to 0:45)

You have heard the rule: **the model never touches the numbers.** We built four fences around
the model, one per elective. The first fence is what the model may see.

[profile box] Isolation. A profile is the boundary. Every query runs through a temporary view
scoped to that profile, in code, read-only. Not a prompt rule. Even a perfect injection can only
read this profile's rows.

[four blocks] Selection. Each turn is assembled fresh: memory block, rolling summary, recent
turns, and only the tools that apply. When web lookup is off, the model does not even see it.

[bar] Compression. At 60 percent of the window the small model folds older turns into a summary
the user can edit in the transcript. A pending question card is never summarized away.

## Slide 9, Sub-agents: what the model gets to do (0:45 to 1:35)

Fence two: what the model may do. **The chat model never runs SQL or code itself. It asks a
sub-agent.**

[the row] A sub-agent is a tool whose handler runs its own model with its own prompt, built by
code. It answers in a forced schema, and the first field is always its reasoning: period,
filters, sign, grouping. Then code checks the answer: for SQL the guard and the real execution,
for charts a self-check on the real rows. A failed check goes back once, word for word, and the
sub-agent gets one retry.

[six chips] Six of them: query, chart, categorizer, extraction, memory, web lookup. Every step is a
card in the chat, so the user can audit it.

One honest line: the chat agent waits for its tool. We do not claim the extra credit.

## Slide 10, Reading files: the model points, code checks (1:35 to 2:20)

Fence three: what the model may read. The same local models read statements and receipts. PDF
text layer first, vision for scans and photos, Excel into the mapping engine, Word into the text
path.

[amber boxes] A vision model under blur invents digits, so it is never trusted with a number.
**Every amount and date it returns must literally occur in the source.** And a statement must
reconcile: opening plus bookings equals closing, to the cent.

Anything flagged becomes a review card. Nothing is written silently. Duplicates are asked about
one by one. On the real receipt and 18 from the web, 19 of 19 totals were right.

## Slide 11, Web search: one word leaves, one page is read (2:20 to 3:05)

Fence four: what may leave the machine. For an unknown merchant the model searches the web
itself: search, fetch or finish, with a budget of four searches and three page reads.

[floor row] The floors are code, not prompt, because a strong model answered from memory and
never searched. At least one search. If a hit is the merchant's own site or Wikipedia, read that
page. The finish must quote a page it read, verbatim, or its confidence is capped.

["sixt"] **Only a scrubbed merchant token ever leaves.** Legal form decides business first, a
list of German given names refuses persons, then the two-word rule. Never an amount, a date, an
IBAN or a name. Off by default, and every request is journaled before it is sent.

## Slide 12, Fine-tuned inside the fences (3:05 to 3:55)

The fine-tuning makes the small model good enough to live inside those fences.

[three steps] Sixty agents wrote training data over five synthetic households. A sample was kept
only when the SQL actually ran and a second, independent statement agreed to the cent. Every
sample is byte for byte the prompt the sub-agent sends in production. Four QLoRA adapters, query
and chart, on the small and the big model, one night on the HPI cluster.

[bars] Scored in the real app, with the product's own runtime, on a household the training never
saw. **The small model's query adapter goes from 62 to 78 percent and ships.** Its chart adapter
did not gain. On the big model the gain is inside the noise, which is what you expect from a model
already at 78 percent. We say so.

Four fences, one rule, one adapter that ships. Thank you. [3:55]

---

## If you run long

Cut in this order: the "19 of 19" sentence on slide 10, the given-name detail on slide 11, the
"sixty agents" sentence on slide 12. Never cut a bold sentence.

## Numbers you say, with the source

| number | slide | source |
| --- | --- | --- |
| 60 percent of 32k | 8 | `src/finquery/context.py`, ADR 0007 |
| six sub-agents, one retry | 9 | `src/finquery/agent.py`, explainer 13 |
| 19 of 19 receipt totals | 10 | `.scratch/finquery/reviews/receipts-web-2026-09-05.md` |
| 4 searches, 3 page reads, 200 given names | 11 | `src/finquery/weblookup/loop.py`, `scrub.py` |
| 1,977 samples, 62 to 78, 38 to 36, 78 to 82 | 12 | `bench/results/20260907-adapters-compare.md` |

## The two-minute questions, one line each

- Where is isolation enforced? In the SQL guard, a temp view with the profile id inlined,
  read-only. A prompt cannot cross it.
- Why 60 percent and not the limit? The summarizing model needs room, and a tool result can be
  large; the turn that crosses the threshold already runs small.
- Why reasoning first in the schema? The model commits to period, filters, sign and grouping
  before it writes SQL; the check pass judges that line as strictly as the SQL.
- What is a sub-agent technically? A tool whose handler runs a second Pydantic AI agent with its
  own instructions and a forced output schema, checks the answer with code, returns data.
- Why not trust the vision model? Under blur it invents digits; the verbatim guard makes it a
  pointer into the source, not a source.
- What leaves on a web lookup? A scrubbed merchant token and the model's own short search query,
  checked by the same scrubber. Journaled before sending.
- What is QLoRA? Frozen base weights in 4-bit, a small low-rank correction trained next to each
  weight matrix. Our adapters are 70 MB on the small model, attached at inference by llama.cpp.
- Why did the chart adapter not gain? Too few repair rows (72 for 959 code rows) and, we found, a
  runtime bug that broke multi-line JSON from fine-tuned models; a rerun on the fixed code is in
  progress.
- Why is the big model's gain noise? Four points on 459 cases is inside the set's resolution, and
  a model at 78 percent has little left to learn from data written for a 4B model's mistakes.
- Why is the benchmark household unseen? The shipped household's cases went into the benchmark,
  the five synthetic households into training; the split is hashed and frozen.
