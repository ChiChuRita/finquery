# FinQuery deck brief for Claude Design (or Google Slides)

Paste this whole file into Claude Design with the instruction: "Make a nine-slide 16:9 deck from
this brief. Dark theme, one accent colour (green), Geist or Inter, no stock imagery. Every
diagram is described under DIAGRAM; draw it as boxes and arrows in three colours: blue for
'a model writes', yellow for 'code checks', gray for 'code executes or stores'. Keep every
bullet under twelve words. Speaker notes under NOTES." The talk is 8 minutes plus 2 for
questions; the graders judge thinking and ownership.

Speakers: Rahul Singh and Liudvikas Zekas, Hasso Plattner Institute, Potsdam. Date: 2026-09-07.
Course: Intelligent Agents.

---

## Slide 1, Title

TITLE: FinQuery
SUBTITLE: A local-first personal-finance analyst. Drop your bank statements into a chat, ask in
your own words, get numbers you can audit.
FOOTER: Rahul Singh and Liudvikas Zekas, HPI Potsdam. Runs on the laptop: two Gemma 4 models
through llama.cpp, SQLite, a React app.
IMAGE: docs/presentation/img/dashboard.png (the dashboard after importing the sample year).
NOTES: One sentence on what it is, one on who did what. Straight to slide 2.

## Slide 2, The one rule

TITLE: Numbers come from executed queries, never from the model
DIAGRAM (left to right, six boxes):
1. Chat agent (blue): reads the question, calls the query tool with a request in words.
2. Query sub-agent (blue): writes one SELECT plus a reasoning line: period, filters, sign,
   grouping.
3. SQL guard (yellow): parsed, one SELECT, profile-scoped view, read-only, LIMIT, no invented
   categories, no cents.
4. SQLite (gray): runs it, rows come back. Nothing else ever produces a figure.
5. Check pass (yellow): degenerate or off-question result? One revise with the finding.
6. Answer (gray): the SQL and the rows are shown with the words; a typed figure without a query
   is flagged.
BULLETS:
- The model writes the question. The database writes the numbers.
- Charts take the same path: generated code, self-checked, drawn in a sandbox.
- The check pass alone: 69 to 79 percent figure match on the same model.
NOTES: A wrong number in finance is worse than no number, so every number is auditable in the
transcript.

## Slide 3, Architecture in one picture

TITLE: One chat agent, six sub-agents as tools, a guard, a sandbox
DIAGRAM (three columns of stacked boxes):
Column 1, what the user touches: Chat agent (blue): Gemma 4 12B, thinking on, one model per
conversation; context is memory block, rolling summary, recent turns, the tools that apply.
Composer (gray): text, CSV, XLSX, PDF, DOCX, receipt photos; every import and decision happens
in the chat. Question cards (gray): a deferred tool, the run parks until the user answers by
button or by typing.
Column 2, what the models do: Sub-agents as tools (blue): query, chart, categorizer,
extraction, memory, web lookup; forced schema, reasoning first, one retry, every step narrated.
One model setting per role (gray): default the chat model; fast means Gemma 4 E4B, where
adapters attach. Local runtime (gray): llama.cpp in process, chat seat Gemma 4 12B, fast seat
E4B resident, 12.9 GB together.
Column 3, what the machine guarantees: SQL guard (yellow): the only door to the data,
profile-scoped, read-only, validated. SQLite (gray): transactions, categories, rules, memory,
conversations, one file. Chart frame (yellow): sandboxed iframe, self-check before drawing,
house rules live in the frame, not in the model.
NOTES: The model never touches the database or the screen directly.

## Slide 4, Elective 1: intelligent context management

TITLE: Intelligent context management (isolation, selection, compression)
DIAGRAM (three boxes left to right): Isolation (gray): a profile is a workspace with its own
transactions, chats, memory, categories, rules; every query runs through a view scoped to it.
Selection per turn (gray): memory block + summary + recent turns + only the tools that apply;
web lookup is not even declared when it is off. Compression (blue): at 60 percent of 32k the
older turns fold into a summary by the fast model; the divider is editable.
SECOND DIAGRAM: a horizontal budget bar of one turn's 32k tokens, segments: memory 8, summary
14, recent turns and tool results 38, tools 6, headroom 34 with the label "compression starts
at 60 percent".
BULLETS:
- Memory is distilled after every turn: at most two facts, never figures or dates.
- Selection is by need, not by recency alone.
- Compression is visible and reversible in the transcript.
NOTES: Say the three words of the sheet and point at each box.

## Slide 5, Elective 2: sub-agent deployment

TITLE: Sub-agent deployment (an LLM calls another LLM for one task)
DIAGRAM (five boxes left to right): Chat agent (blue) decides a tool is needed and writes the
request in words. Tool call (gray): one prompt built by code with rules, worked examples and the
household's facts. Sub-agent (blue): forced tool schema, reasoning field first, then the answer.
Check (yellow): guard, execution, self-check or judge; a finding goes back once. Result (gray):
returned as data, every step streams into the transcript.
TABLE (four columns: sub-agent, gets, returns, checked by):
query | request, schema, rules, examples | reasoning + SQL | guard, execution, check pass
chart | request, rows brief | plan, then chart code | self-check on real rows, frame
categorizer | batch of unknown bookings | category + confidence per booking | threshold, Question cards, rules
extraction | a page as text or image | bookings | verbatim and reconciliation guards
memory | the finished turn | at most two facts | no figures, no dates
web lookup | a scrubbed merchant token | search, fetch or finish | floors, verbatim quote, cap
FOOTNOTE: Not claimed: the extra credit for a controller that continues without waiting.
NOTES: The loop is the same for all six; the table is what differs.

## Slide 6, Elective 3: multimodal ingestion

TITLE: Multimodal ingestion (PDF, images, text, CSV, XLSX, DOCX)
DIAGRAM (six boxes left to right): File (gray). Route (gray): text layer or table present?
read as text; none? render the page. Extraction sub-agent (blue): Gemma 4 with its vision
projector reads the page and returns bookings. Verbatim guard (yellow): every amount and date
must occur in the source. Reconciliation (yellow): opening balance plus bookings equals closing
balance, to the cent. Review or import (gray): flagged rows become a review card; nothing is
written silently.
BULLETS (two columns):
- Inherently multimodal: the same local models read images and text.
- The model points, code verifies. It may not invent a digit.
- Every duplicate is asked about before anything lands.
- 19 of 19 receipt totals right on real and web receipts.
- Excel feeds the CSV mapping engine; Word feeds the text path.
- Audio is out of scope, and we say so.
NOTES: Lead with the two guards.

## Slide 7, Elective 4: self-controlled web search

TITLE: Self-controlled web search (find a page, read it, quote it)
DIAGRAM (vertical loop, four boxes): Scrubber (yellow): booking text becomes a merchant token;
a person's name is refused; nothing else ever leaves. Decide (blue): search, fetch or finish,
with reasoning, up to 4 searches and 3 page reads. Floors in code (yellow): at least one search;
a page read when a hit is the merchant's own site or Wikipedia; a failed backend is retried
free. Finish (yellow): a verbatim quote that must occur in what was read; confidence capped when
no source names the merchant. Draw an arrow from Floors back to Decide to show the loop.
BULLETS:
- Every request is journaled before it is sent and shown in Settings.
- Three callers, one loop: chat tool, categorizer at import, receipt headers.
- Cached per profile: the second question about a merchant leaves nothing.
- Measured: lookups without a search 9 to 0, pages read 0 to 12.
IMAGE (small): docs/presentation/img/web-lookup.png
NOTES: "Further than direct results": it visits the page and quotes it; the log proves what left.

## Slide 8, Models and the training loop

TITLE: Which local models, and how the adapters are trained
TABLE (Model, SQL, Charts, End to end, laptop tok/s):
Gemma 4 E4B | 66 % | 45 % | 53 % | 47
Qwen3.5 9B | 70 % | 42 % | 73 % | 30
Gemma 4 12B (highlight) | 87 % | 81 % | 77 % | 22
CAPTION: Figure match on 152 SQL and 73 chart cases, held-out third never trained on; same
GGUFs and wire formats as the laptop; HPI cluster.
BULLETS:
- Rule written before the numbers: accuracy first, speed within five points, fits in 13.5 GB.
- Result: Gemma 4 12B for chat and sub-agents, E4B resident as fast seat and adapter target.
DIAGRAM (vertical, four boxes, label "in progress"): Data (gray): six synthetic households,
60 writer agents, 60 judges, kept only by execution (guard, database, independent second
statement, chart self-check, rendered picture). Frozen benchmark (yellow): the shipped household
is benchmark-only and unseen in training; split hashed and frozen before any training row.
QLoRA, four adapters (blue): query and chart on E4B and on the 12B; samples are byte for byte
the production prompts; a checkpoint per epoch, quick eval, the best converted to GGUF.
Official run (gray): base against base plus adapter, same benchmark and runtime; smoke-tested
end to end on an H100.
NOTES: The ownership moment: Qwen chosen on memory in week one, reversed on evidence. State the
training status as it is on Monday morning; never a number that is not in bench/results.

## Slide 9, What we own

TITLE: Decisions we made, and the ones we reversed on evidence
FOUR BLOCKS:
Kept: numbers only from executed SQL; sub-agents as forced tool calls, reasoning first; every
import and decision in the chat; training equals production.
Reversed: Qwen3.5 9B chosen on memory, replaced by Gemma 4 12B after the cluster benchmark;
preference optimisation built, measured and removed for multimodal ingestion; "no dashboard"
became a dashboard of guarded queries.
Not claimed, on purpose: sub-agent extra credit; Python code execution (our sandbox runs
JavaScript charts); audio ingestion.
Next: adapter numbers against vanilla; the video; a second data round if the learning curve
asks for it.
FOOTER: Questions. Hand-in as a ZIP archive on 2026-09-14.
NOTES: Close on the three reversals and the evidence that forced each. Then stop.
