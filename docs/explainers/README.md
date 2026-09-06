# FinQuery explainers

Short documents to read the evening before the presentation. One file per topic. Each one
says what we claim, how it works (a diagram and the same flow as numbered text), the exact
files and functions, where the model is in the loop and where it is not, the guards, the
numbers we measured with their source, three sentences to say out loud, the questions a grader
is likely to ask, and what is not finished.

The topics follow the course task sheet, `docs/course/task-description.md`: one home per
required bullet, one file per claimed elective, and the deeper technical chapters underneath.
`checklist.md` maps every bullet of the sheet, required and elective, to a status, the code
that satisfies it and the evidence.

Every number in these files has a source next to it: a ticket file under
`.scratch/finquery/issues/`, a result file under `bench/results/`, or an ADR. Every "works" is
something a test or a verification session showed. Anything still running or not started is
written as such. State of the code these files describe: `main` on 2026-09-06, with ticket 43
not started and tickets 44 to 47 running in parallel (their code is not on `main` yet).

## The elevator pitch

FinQuery is a local-first personal-finance analyst. You drop bank statements, CSV and Excel
exports, Word documents and receipt photos into a chat, the assistant imports and categorizes them, and you ask questions
in German or English. Every number in an answer comes from a SQL query the assistant really ran
against your own transactions, shown in the transcript next to the answer, and never from the
model's memory. Two models run on the laptop through llama.cpp: a fast Gemma 4 E4B that also
runs every sub-agent, and a Qwen3.5 9B for the quality slot. Charts are generated code, checked
in a sandbox before they are drawn. Nothing about your money leaves the machine unless you
switch on web lookup, and then only a scrubbed merchant name does, logged before it is sent.

## The topics

### Required features of the sheet

| # | File | Sheet bullets | Status |
| --- | --- | --- | --- |
| 01 | [run-ui-chat-and-conversations.md](01-run-ui-chat-and-conversations.md) | runnable with `uv`; a UI; chat with visible, scrollable history; start, stop and resume with switching; create, continue and remove conversations | done |
| 02 | [two-models-and-the-switch.md](02-two-models-and-the-switch.md) | switch the LLM, at least two loadable models | done |
| 03 | [memory-across-chats.md](03-memory-across-chats.md) | a simple memory mechanism across a group of chats (the profile) | done |
| 04 | [fine-tuned-models-training-and-benchmarks.md](04-fine-tuned-models-training-and-benchmarks.md) | at least two fine-tuned models (LoRA), and the benchmark loop they are scored with | not started (infrastructure done) |
| 05 | [video-demo.md](05-video-demo.md) | the video demo and its real-world use case | not started (storyboard done) |

### The technical chapters underneath

| # | File | Claim |
| --- | --- | --- |
| 06 | [numbers-invariant-and-sql-guard.md](06-numbers-invariant-and-sql-guard.md) | Numbers come only from executed, guarded SQL, checked against the question |
| 07 | [charts-as-checked-code.md](07-charts-as-checked-code.md) | A chart is generated code, checked in QuickJS, drawn in a sandboxed frame |
| 08 | [ingestion.md](08-ingestion.md) | CSV, XLSX, PDF, DOCX and photo import with verbatim and reconciliation guards and duplicate cards |
| 09 | [categorization-and-question-cards.md](09-categorization-and-question-cards.md) | Rules, dictionary, model, then a card; answers apply in code |
| 10 | [transactions-and-changesets.md](10-transactions-and-changesets.md) | Every edit is deterministic code; bulk edits are previews the user applies |
| 11 | [dashboard.md](11-dashboard.md) | A dashboard that stores statements, never figures |

### The electives claimed

| # | File | Sheet bullet | Status |
| --- | --- | --- | --- |
| 12 | [elective-context-management.md](12-elective-context-management.md) | intelligent context management: compression, isolation, selection | done |
| 13 | [elective-subagents.md](13-elective-subagents.md) | sub-agent deployment as tool calls (extra credit for a non-waiting controller not claimed) | done |
| 15 | [elective-web-search.md](15-elective-web-search.md) | repeated self-controlled web search that finds and visits pages | done |
| 16 | [elective-multimodal-ingestion.md](16-elective-multimodal-ingestion.md) | multimodal ingestion: images, PDF, text, CSV, XLSX and DOCX through vision-language models | done |

Multimodal ingestion (16) was claimed on 2026-09-06 in place of preference optimisation, and
the deeper chapter under it is 08. Preference optimisation was built and then removed the same
day, not merely unclaimed; [14](14-elective-preference-optimization.md) is the note on what it
was, what it measured and why it went. Built but not claimed as an elective: sandboxed execution
of generated chart code (07, JavaScript rather than Python). Dropped on 2026-09-01 and never
claimed: extensible user-provided tools and secure Python execution
(`git show archive/old-main:DECISIONS.md`). Not built: adaptive RAG, concurrent multi-user,
prompt caching, Tree-of-Thought.

## The order to read in

1. `checklist.md`, to see the whole sheet at once.
2. 06 (the invariant). Everything else hangs off it.
3. 01, 02, 03: the required shell, the models, the memory.
4. 13 (sub-agents): how every model call is made.
5. 07, 08, 09: the three big flows.
6. 10, 11: the pages.
7. 12, 15, 16: the remaining electives; 14 is the note on the one that was removed.
8. 04 and 05 last: what the numbers say and what is not done.

## Conventions in these files

- A code reference is written `path:symbol`, for example `src/finquery/query/guard.py:validate_sql`.
  `check_refs.py` in this folder verifies that every such path exists and defines the symbol
  (`uv run python docs/explainers/check_refs.py`).
- "Fast slot" is Gemma 4 E4B locally (Gemma 4 26B on OpenRouter). "Quality slot" is Qwen3.5 9B
  on both providers. Sub-agents always run on the fast slot.
- A Mermaid block renders on GitHub; the numbered list under it says the same thing in plain
  text for a terminal.
- Background reading: `CONTEXT.md` (vocabulary), `docs/adr/` (decisions), `docs/demo-script.md`
  (the live demo with measured times), `bench/README.md` (the benchmark story),
  `docs/course/task-description.md` (the sheet).
