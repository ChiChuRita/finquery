# FinQuery, the four electives and the fine-tuned models: a four-minute segment

Speaker: Liudvikas Zekas. Six slides, about forty seconds each, plus one optional closing slide.
Course: Intelligent Agents, HPI Potsdam, 2026-09-07. Product: FinQuery, a local-first
personal-finance analyst.

## Instruction for Claude Design

Make six 16:9 slides from this brief, with the attached "FinQuery Design System". Dark canvas,
one green accent, Geist. Every slide has exactly: one headline of at most eight words, one
diagram, at most three short labels, and at most one large figure. No paragraphs. No bullet
lists. The words under ON SLIDE are the only words allowed on the slide; the words under NOTES are
spoken, never shown. Diagrams use three box colours from the design system: blue where a model
writes, amber where code checks, gray where code executes or stores. Draw the same "fence" picture
on slides 2 to 5 so the audience recognizes one shape.

The fence picture: a blue box in the centre labelled "model"; a thin amber frame around it that
carries the fence's name; gray boxes outside the frame for what is guaranteed.

## The red thread (say it on slide 1, repeat its shape on every slide)

The model never touches the numbers. Four fences make that safe and useful: what the model may
see (context management), what it may do (sub-agents), what it may read (multimodal ingestion),
what may leave the machine (web search). The fine-tuning makes the small model good enough to live
inside those fences.

---

## Slide 1, the thread

HEADLINE: The model never touches the numbers
ON SLIDE: model writes the question | code checks | database answers | context, sub-agents,
ingestion, web
DIAGRAM: three boxes left to right: blue "model: writes the question", amber "guard, check,
sandbox", gray "database: writes the numbers". Under them a row of four empty amber frames
labelled context, sub-agents, ingestion, web. On the following slides one frame at a time is
filled.
FIGURE: none
NOTES: Every number in FinQuery is the result of a SQL query the assistant really ran, shown next
to the answer. The model writes the question, code checks it, the database answers. We built four
fences around the model, one per elective, and fine-tuned the small model to be good inside them.

## Slide 2, fence one: what the model may see

HEADLINE: Context: what the model may see
ON SLIDE: isolation = one profile | selection = per turn | compression at 60 %
DIAGRAM: the fence picture, frame labelled "context". Left of the frame a gray wall "profile" with
the database behind it. Inside the frame three gray tokens flow into the blue model: "memory, two
facts per turn", "summary of older turns", "recent turns and tools". Below the picture a
horizontal bar "32k tokens" with a mark at 60 % labelled "older turns fold into the summary".
FIGURE: 60 %
NOTES: Isolation: a profile is the boundary, enforced by a database view in code, not by a prompt.
Selection: each turn gets the memory, the summary, the recent turns and only the tools that
apply; web lookup is not even declared when it is off. Compression: at 60 percent of the window
the older turns fold into a summary the user can edit in the transcript. Memory is at most two
facts per turn and never a number.

## Slide 3, fence two: what the model may do

HEADLINE: Sub-agents: what the model may do
ON SLIDE: request in words | forced schema, reasoning first | one retry | query, chart,
categorizer, extraction, memory, web
FIGURE: 69 to 79 %
DIAGRAM: the fence picture, frame labelled "sub-agents". The blue chat model hands a small card
"request in words" to a second blue box "sub-agent". Its output passes an amber gate "schema,
reasoning first, check, one retry" into a gray box "result as data". Six small chips under the
sub-agent name the six.
NOTES: A sub-agent is a tool whose handler runs its own model. It gets one prompt built by code,
answers through a forced schema whose first field is its reasoning, and a check that is code
sends a finding back once. Six of them: query, chart, categorizer, extraction, memory, web lookup.
The check pass alone moved one model from 69 to 79 percent, without training anything. We do not
claim the extra credit: the chat agent waits for its tool.

## Slide 4, fence three: what the model may read

HEADLINE: Ingestion: the model points, code verifies
ON SLIDE: PDF, photo, Excel, Word | verbatim | reconciliation | review card or import
FIGURE: 19 of 19
DIAGRAM: left, gray inputs "PDF, receipt photo, Excel, Word". A blue box "vision model reads the
page". Two amber gates in sequence: "verbatim: every digit must occur in the source",
"reconciliation: opening plus bookings equals closing". Two gray outcomes: "review card",
"import".
NOTES: The same local models read scans and receipt photos. A vision model is never trusted with a
number: every amount and date it returns must literally occur in the source, and a statement has
to reconcile to the cent. Anything flagged becomes a review card, nothing is written silently.
Nineteen of nineteen receipt totals were right. Excel and Word take the same paths. Audio is out
of scope.

## Slide 5, fence four: what may leave the machine

HEADLINE: Web search: one token leaves, one page is read
ON SLIDE: scrubbed token | 4 searches, 3 pages | verbatim quote | journal
FIGURE: 0 to 12 pages read
DIAGRAM: the fence picture with the frame drawn as a wall. Inside: an amber "scrubber" turns
booking text into a small gray token "sixt"; the blue model loops "search, fetch, finish" with a
counter "4 searches, 3 pages"; amber floors "at least one search, read the merchant's own page,
quote it verbatim". Outside the wall: a gray "journal" listing requests and a gray "cache".
NOTES: For an unknown merchant the model searches itself, up to four searches and three page
reads, and it must quote the page it read. Only a scrubbed merchant token ever leaves: never an
amount, a date, an IBAN or a person's name. Every request is journaled before it is sent, and the
user can read the journal. After the floors went into code, pages read went from zero to twelve
on twenty merchants.

## Slide 6, the fine-tuned models

HEADLINE: Fine-tuned inside the fences: 62 to 78 percent
ON SLIDE: kept only by execution | QLoRA on the cluster | frozen benchmark, unseen household |
ships, no, noise
FIGURE: 62 to 78 %
DIAGRAM: top, three gray and blue steps left to right: "1,977 samples, kept only when the SQL ran
and a second statement agreed", "QLoRA, four adapters, one night on the cluster", "scored with
the product's own runtime on a frozen benchmark the training never saw". Bottom, a before-and-
after bar pair per adapter in the chart palette: E4B query 62 to 78 (tall, green, "ships"); E4B
chart 38 to 36 ("no"). The 12B adapters were trained and dropped (query 78 to 82, noise; chart
62 to 50): no bars for them, one line of text at most.
NOTES: Four QLoRA adapters, query and chart on the small and on the big model, trained overnight
on data written by sixty agents and kept only when the SQL executed and an independent statement
agreed to the cent. Scored against the vanilla base with the product's own runtime, on a
benchmark household the training never saw. The small model's query adapter gains sixteen points
and ships. Its chart adapter does not help, and on the big model the gain is inside the noise,
which is what you expect from a model already at 78 percent. We say so.

## Optional slide 7, what we reversed

HEADLINE: Three reversals, on evidence
ON SLIDE: Qwen to Gemma 12B | preference to multimodal | no dashboard to guarded dashboard
DIAGRAM: three arrows from a struck-through word to a word, each with a one-word cause under it:
benchmark, measured, research.
NOTES: We chose Qwen on memory and replaced it after the benchmark. We built preference
optimisation, measured it and removed it for multimodal ingestion. We wrote "no dashboard" into
the spec and reversed it after studying what finance apps show.

---

## Appendix A: every number on the slides, with its source

| number | meaning | source |
| --- | --- | --- |
| 60 % | context compression threshold of the 32k window | `src/finquery/context.py`, ADR 0007 |
| 2 facts | memory distilled per turn, never figures or dates | `src/finquery/memory.py` |
| 69 to 79 % | the query check pass alone, same model (Qwen3.5 9B), SQL figure match | `bench/results/20260905T182106Z-*-nocheck-sql.md`, `20260906T115540Z-*-sql.md` |
| 6 | sub-agents: query, chart, categorizer, extraction, memory, web lookup | `src/finquery/agent.py`, explainer 13 |
| 19 of 19 | receipt totals right, real Edeka receipt and 18 web receipts | `.scratch/finquery/reviews/receipts-web-2026-09-05.md` |
| 4 and 3 | web lookup budget: searches and page reads per lookup | `src/finquery/weblookup/loop.py`, ADR 0010 |
| 0 to 12 | pages read on 20 merchants before and after the floors | ticket 53 Comments |
| 1,977 | query training samples (plus 1,791 chart samples) | `training/data/out/samples/stats.md` |
| 62 to 78 % | E4B query adapter, SQL figure match on 459 questions | `bench/results/20260907-adapters-compare.md` |
| 38 to 36 % | E4B chart adapter, figure match on 302 charts; drawn 85 to 72 | same |
| 78 to 82 % | 12B query adapter; inside the set's resolution of about five points | same |
| 62 % | vanilla 12B on the chart set; adapter run pending | same |

## Appendix B: the answers behind each slide, in one line each

- Isolation is enforced where? In the SQL guard: every query runs through a temporary view with
  the profile id inlined, connection read-only. A prompt cannot cross it.
- Why 60 percent and not the limit? The summarizing model needs room, and a tool result can be
  large; the turn that crosses the threshold already runs small.
- What makes a sub-agent a sub-agent? A tool whose handler runs a second model call with its own
  prompt, schema and check; the chat agent cannot tell it from a plain tool.
- Why reasoning first in the schema? The model commits to period, filters, sign and grouping
  before it writes SQL; the check pass judges that line as strictly as the SQL.
- Why is a vision model not enough? Under blur it invents digits; the verbatim guard makes it a
  pointer into the source, not a source.
- What leaves the machine on a web lookup? A scrubbed merchant token only; legal forms decide
  business first, a given-name list refuses persons, and the journal records every request before
  it is sent.
- Why did the chart adapter fail? Too few repair rows in its training set (72 for 959 code rows
  against the 25 to 30 percent the research asked for); a second data round is the fix.
- Why is the 12B gain noise? Four points on 459 cases is inside the resolution of the set, and a
  model at 78 percent has little left to learn from data written for a 4B model's mistakes.
- Why the benchmark household is unseen: the shipped household's candidates went into the
  benchmark, the five new households into training; the split is hashed and frozen.

Longer explanations: `docs/presentation/how-it-works/` (one note per slide) and
`docs/explainers/` (one chapter per topic with file and function references).
