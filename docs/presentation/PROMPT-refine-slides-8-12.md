# Prompt: refine slides 8 to 12 of the FinQuery deck

Paste everything below the line into Claude Code (in the FinQuery repo) or into Claude Design
with the current deck PDF attached. If you use Claude Design, also attach
`docs/presentation/SCRIPT-electives-4min.md` and `docs/guide/finquery-guide.html`.

---

I am presenting slides 8 to 12 of this deck (Context, Sub-agents, Reading files, Web search,
Fine-tuned) in four minutes, then answering questions from a professor. The current slides state
conclusions but do not show how anything works, and I have to be able to explain each slide
from memory. Rebuild these five slides. Keep the rest of the deck as it is.

## What I want on every slide

One worked example per slide, with real values, instead of a list of claims. The audience should
see the mechanism run once: an input on the left, the step that decides in the middle, the
output on the right. Numbers and strings in the example must be real ones from the repo, not
placeholders.

Read these before you start, they hold the material and the exact wording:

- `docs/presentation/SCRIPT-electives-4min.md`: what I will say, slide by slide, with the
  order I point at things. The slide must read left to right in the same order as the script.
- `docs/guide/finquery-guide.html`: the technical guide with the diagrams and the quoted
  prompts. The level of detail in there is the level I want on the slides, compressed.
- `docs/explainers/12` to `16` and `bench/results/20260907-adapters-compare.md` for numbers.
- The code, when the guide points at it: `src/finquery/query/guard.py`, `context.py`,
  `memory.py`, `extract/guards.py`, `weblookup/scrub.py`, `weblookup/loop.py`,
  `training/data/samples/`.

## One running example, carried through all five slides

Explain everything with one story, so the audience follows a single household instead of five
unrelated cases. The household is the shipped demo profile (Berlin, the year 2025). The story:

1. The user drops the Edeka receipt photo and a statement PDF into the chat (slide 10 is this
   step: the receipt line and the statement page go through the two guards and get imported).
2. One merchant on the statement is unknown, the supermarket "Combi" (slide 11 is this step: the
   scrubbed token `combi` is looked up, the page is read, the category Groceries comes back with
   its quote).
3. The user asks: "How much did I spend on groceries in May?" (slide 8 shows this turn being
   assembled, with the memory fact from the receipt import and the summary of the earlier import
   conversation; slide 9 shows the question going through the query sub-agent and the guard,
   ending in the rows and the figure).
4. The same question is one case in the benchmark, and a grocery question from another household
   is the training sample (slide 12: the sample, the LoRA, the before-and-after bars; say on the
   slide that the benchmark household is this one and the training households are five others).

Present the slides in the deck order (8, 9, 10, 11, 12) but put a small step marker on each slide
("step 3 of the story: the question") so I can say "remember the receipt from two slides ago".
Use the same figure for groceries in May everywhere it appears: take it from running the query
against the shipped fixture, do not make one up. Use the merchant Combi for the web lookup only if
the repo's lookup fixtures or the ticket 53 review contain it; otherwise use Vogtlandbahn, which
they do, and adjust the story sentence.

## The example each slide must show (all from the story above)

Slide 8, Context. One real turn being assembled. Show the four blocks as they actually look:
a memory block with two real facts from the story ("the Edeka receipt of 12.05.2025 was split into groceries and household", and one rule from the profile, taken from the fixtures),
a one-line summary excerpt, the recent turns as a count, the tool list with web lookup greyed
out because it is off. Under it the token bar with the real numbers: the window is 32k,
compression starts at 60 percent, and mark where this turn sits. On the left the isolation step
as the actual SQL: `CREATE TEMP VIEW transaction_view AS SELECT * FROM main.transaction_view
WHERE profile_id = '<this profile>'` with `PRAGMA query_only`.

Slide 9, Sub-agents. The query sub-agent running once on "How much did I spend on groceries in
May?". Show: the request in words, the forced schema with reasoning first as it comes back
(`reasoning: period May 2025; filters category Groceries; sign amount < 0; grouping none`, then
the SQL), the guard as a tree walk with three checks and their verdicts (one SELECT: yes; only
transaction_view: yes; CASE that invents a label: none; LIMIT 200 added), then the rows. Add a
small second lane showing one refusal and the retry: the model writes `SELECT * FROM
transactions`, the guard answers "The only relation you may name is transaction_view", the
sub-agent rewrites. The six sub-agents stay as small chips at the bottom.

Slide 10, Reading files. One receipt line going through both guards. Left: the printed line from
the real Edeka receipt as an image crop or as monospace text. Middle: the vision model's row
(`date, amount, merchant`) and the verbatim check as a lookup: `"12,49" occurs in source: yes`,
and a second, wrong row `"12,94" occurs: no, refused`. Right: reconciliation as one line of
arithmetic, opening plus bookings equals closing, with the tick or the flag, and the two
outcomes: review card or import. Keep the file-type list small on the far left.

Slide 11, Web search. The story's unknown merchant end to end. The raw booking text on the left,
the scrubber's three rules in order with the one that fired, the token, then the loop as three
numbered steps with their budgets (search 1 of 4, fetch 1 of 3 of the merchant's own page, finish), the quoted
evidence sentence from the page, and the journal entry on the right with what was sent and when.
State the person case in one line: `"PayPal Anna Weber"` is refused, nothing leaves.

Slide 12, Fine-tuned. Left: one real grocery training sample from another household, from
`training/data/samples/` or `training/data/batches/`, shortened:
the user prompt as a stack of labelled bands (schema, rules, 9 examples, household facts,
question) with the real question text, and the completion as the wire tool call with the real
reasoning line and SQL. Middle: what a LoRA is in one picture, frozen W plus a thin B times A,
with our numbers (rank 16, 70 MB, E4B). Right: the before-and-after bars as they are now, and
mark "measured with the product's own runtime on a household the training never saw". Take the
current numbers from `bench/results/20260907-adapters-compare.md` and leave the two cells that
are still running as dashed bars.

## Rules for the slides

- One headline of at most eight words, then the example. No bullet lists of claims, no
  paragraphs. Every word on the slide is either a label, a real value, or a verdict.
- Keep the fence red thread: a blue box where a model writes, amber where code checks, gray
  where code executes or stores. Same legend on every slide as in the current deck.
- Use the FinQuery design system already attached to the deck: dark canvas, one green accent,
  Geist, square chart corners.
- Verdicts are written as the code writes them, in monospace, so I can read them out. Refusal
  sentences must be the real ones from `guard.py`.
- Every number on a slide has a source in the speaker notes. Notes hold my script text from
  `SCRIPT-electives-4min.md` for that slide, verbatim, so I can rehearse from the notes view.
- Nothing invented: if a value is not in the repo, ask me or leave it off.

## Two corrections to the rest of the deck

- Slide 6 says the small model runs the sub-agents. In the demo every sub-agent runs on the 12B
  by default. The E4B runs summaries, memory distillation and any role pointed at it, and carries
  the adapters. Fix the two lines under "Gemma 4 E4B" to say that.
- Slide 12's "small chart 38 to 36" was measured before a runtime fix and is being rerun. Read
  the compare file for the current value.

Deliver the five slides in the same format as the deck, plus a short list of every value you
placed on a slide with the file it came from.
