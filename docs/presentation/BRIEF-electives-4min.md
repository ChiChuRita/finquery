# Brief for Claude Design: the electives and the fine-tuned models in four minutes

Speaker: Liudvikas Zekas. Six slides, about forty seconds each. Paste this file into Claude
Design with the instruction: "Six 16:9 slides from this brief, attached design system FinQuery.
Dark canvas, one green accent, Geist. Every slide is one headline of at most eight words, one
diagram, and at most three short labels; no paragraphs, no bullet lists longer than three items.
Diagrams use the design system's three box colours: blue where a model writes, amber where code
checks, gray where code executes or stores. Numbers appear as one large figure per slide, never in
prose." The speaker notes under NOTES are what is said; they are not on the slide.

## The red thread

One sentence carries the whole segment: **the model never touches the numbers, and four fences
make that both safe and useful.** Each elective is one fence around the model: what it may see
(context), what it may do (sub-agents), what it may read (multimodal ingestion), what may leave
the machine (web search). The fine-tuning makes the small model good enough to live inside those
fences. Every slide repeats the fence picture, so the audience sees the same shape five times.

The fence picture, used on slides 2 to 5: a blue box in the middle labelled "model", a thin amber
frame around it labelled with the fence's name, and on the outside gray boxes for what is
guaranteed. Slide 1 introduces the picture; slide 6 shows the model inside all four fences with
the adapter attached.

---

## Slide 1, the thread

HEADLINE: The model never touches the numbers
DIAGRAM: left, a blue box "model writes the question"; middle, an amber frame "guard, check,
sandbox"; right, a gray box "database writes the numbers". Under it, four small amber frames in a
row, empty, labelled context, sub-agents, ingestion, web. They light up one by one on the next
slides.
LABELS: model writes, code checks, data answers
FIGURE: none
NOTES: "Every number you see in FinQuery is the result of a SQL query the assistant really ran.
The model writes the question, code checks it, the database answers. We built four fences around
the model, one per elective, and then fine-tuned the small model to be good inside them. Here are
the four."

## Slide 2, fence 1: what the model may see

HEADLINE: Context management: what the model may see
DIAGRAM: the fence picture. Inside the amber frame three gray tokens flow into the blue model box:
"memory (2 facts per turn)", "summary of old turns", "recent turns". Left of the frame a gray wall
labelled "profile" with the query view behind it. Below, a horizontal budget bar of 32k tokens with
a mark at 60 percent labelled "fold into summary".
LABELS: isolation = profile, selection = per turn, compression = 60 percent
FIGURE: 60 %
NOTES: "Isolation: a profile is the boundary, enforced by a database view, not by a prompt.
Selection: each turn gets the memory, the summary, the recent turns and only the tools that
apply. Compression: at 60 percent of the window the old turns fold into a summary the user can
edit. Memory is two facts per turn, never a number."

## Slide 3, fence 2: what the model may do

HEADLINE: Sub-agents: what the model may do
DIAGRAM: the fence picture. The blue chat model hands a small card "request in words" to a second
blue box "sub-agent". The sub-agent's output goes through an amber gate "schema, reasoning first,
check, one retry" into a gray box "result as data". Six small chips under the sub-agent: query,
chart, categorizer, extraction, memory, web.
LABELS: forced schema, reasoning first, one retry
FIGURE: 69 to 79 % (the check pass alone, same model)
NOTES: "A sub-agent is a tool whose handler runs its own model. It gets one prompt built by code,
answers through a forced schema with a reasoning field first, and a check that is code sends a
finding back once. Six of them. The check pass alone moved one model from 69 to 79 percent
without any training. We do not claim the extra credit: the chat agent waits for its tool."

## Slide 4, fence 3: what the model may read

HEADLINE: Multimodal ingestion: the model points, code verifies
DIAGRAM: left, gray inputs "PDF, photo, Excel, Word"; a blue box "vision model reads the page";
then two amber gates in sequence: "verbatim: every digit must occur in the source" and
"reconciliation: opening plus bookings equals closing"; then two gray outcomes "review card" and
"import".
LABELS: verbatim, reconciliation, review card
FIGURE: 19 of 19 receipt totals
NOTES: "The same local models read scans and receipt photos. But a vision model is never trusted
with a number: every amount and date it returns must literally occur in the source, and a
statement must reconcile to the cent. Anything flagged becomes a review card; nothing is written
silently. Excel and Word take the same paths. Audio is out of scope."

## Slide 5, fence 4: what may leave the machine

HEADLINE: Web search: one token leaves, one page is read
DIAGRAM: the fence picture with the frame drawn as a wall. Inside: amber "scrubber" turns booking
text into a small gray token "sixt"; the blue model loops "search, fetch, finish" with a small
counter "4 searches, 3 pages"; amber floors "at least one search, read the merchant's page, quote
it verbatim". Outside the wall: a gray "journal" listing the requests, and a gray "cache".
LABELS: scrubbed token, verbatim quote, journal
FIGURE: 0 to 12 pages read (before and after the floors)
NOTES: "For an unknown merchant the model searches itself, up to four searches and three page
reads, and it has to quote the page it read. Only a scrubbed merchant token ever leaves: never an
amount, a date, an IBAN or a person's name. Every request is journaled before it is sent. After we
put the floors in code, pages read went from zero to twelve on twenty merchants."

## Slide 6, the fine-tuned models

HEADLINE: Fine-tuned inside the fences: 62 to 78 percent
DIAGRAM: top, a compact three-step loop in gray and blue: "1,977 samples kept only by execution"
to "QLoRA on the cluster" to "scored on a frozen benchmark the training never saw". Bottom, a
two-bar chart per adapter in the chart palette: E4B query 62 to 78 (tall, green, "ships"); E4B
chart 38 to 36 ("no"); 12B query 78 to 82 ("noise"); 12B chart, vanilla 62, adapter bar with a
question mark ("running").
LABELS: ships, no, noise
FIGURE: 62 to 78 %
NOTES: "Four QLoRA adapters, trained overnight on data written by sixty agents and kept only when
the SQL ran and an independent statement agreed. Scored with the product's own runtime against
the vanilla base on a benchmark household the training never saw. The small model's query adapter
gains sixteen points and ships. Its chart adapter does not help, and on the big model the gain is
inside the noise, which is what you expect from a model already at 78 percent. We say so."

## If there is a seventh slide

HEADLINE: What we reversed, on evidence
DIAGRAM: three arrows, each from a crossed-out word to a word: Qwen to Gemma 12B (benchmark),
preference to multimodal (measured, removed), no dashboard to guarded dashboard (research).
NOTES: one sentence each.
