# FinQuery: local-first personal-finance analyst, fresh build

Status: ready-for-agent
Date: 2026-09-04
Deadlines: live demo Monday 2026-09-07 (everything below demoable), hand-in ZIP 2026-09-14

## Problem Statement

I have bank statements from several German banks as PDFs and CSV exports, plus paper bills and
receipts. I want to understand where my money goes, but no tool lets me ask in my own words and
trust the answer. Cloud finance apps want my data on their servers. Spreadsheets need me to
categorize everything by hand, and categories are never quite right: an Edeka receipt is partly
groceries and partly household, a PayPal payment to a friend was dinner, a card payment to a
shop I do not recognize needs a web search before I know what it was.

The previous FinQuery build accumulated features without a shared design. Its UI looked dated,
the code was stale, and the required course features (two chat models, thinking, interruption,
conversation management, memory across chats, two fine-tuned models, sub-agents, context
management, preference optimization, self-directed web search) were only partly wired. It is
gone. This spec describes the product built from zero.

## Solution

A desktop-browser app that runs on my own machine, started with one `uv run` command. I create a
profile, drop statements, CSVs, photos of bills, or pasted text into the chat, and the assistant
imports them, categorizes what it can, and asks me about the rest in the chat with buttons I can
click. I then ask questions in German or English, and every number in the answer comes from a
SQL query the assistant ran against my transactions, shown on request. Charts are drawn to a
house style. I can switch between a fast and a quality model, watch the assistant think, stop it,
and pick up any old conversation. Long chats compress themselves. Things I tell it about my
transactions are remembered across every chat in the profile. I can rate answers and charts, and
those ratings become training data. A transactions page lets me see and fix every row, including
splitting one receipt across categories.

During development the two model slots run on OpenRouter (Gemma 4 26B-A4B and 31B) so the laptop
stays usable. For the demo and the hand-in the same slots run locally on Gemma 4 E4B and 12B
through llama-cpp-python, where the two fine-tuned adapters slot in later.

## User Stories

### Profiles and app shell

1. As a user, I want to start the whole app with one `uv run finquery` command and open it in my browser, so that no other install steps stand between me and my data.
2. As a user, I want to create, rename, switch and delete profiles, so that my own finances and a shared household stay apart.
3. As a user, I want every transaction, category, rule, memory and conversation to belong to exactly one profile, so that nothing leaks between them.
4. As a user, I want the app to look and feel like a modern AI chat product with a dark and a light theme, so that I enjoy using it and my presentation looks good.
5. As a user, I want the UI in English and the assistant to answer in the language I write in, so that German data and English interface coexist.

### Chat basics

6. As a user, I want a conversation list per profile in a sidebar with rename and delete, so that I can find and manage old chats.
7. As a user, I want to open several conversations as tabs at once, each keeping its scroll position and draft, so that I can compare two lines of questioning.
8. As a user, I want to create a new conversation with one click and continue any old one by opening it and sending the next message, so that starting and resuming are both trivial.
9. As a user, I want to pick the fast or the quality model per conversation from the composer and switch mid-conversation, so that I trade speed for quality when I need to.
10. As a user, I want each assistant turn to show which model produced it, so that I can compare them.
11. As a user, I want to see the assistant's thinking stream live in a collapsible panel that folds away when the answer starts and shows how long it thought, so that I trust and understand the answer.
12. As a user, I want to stop generation at any time and keep the partial text, tool calls and thinking as an interrupted turn, so that a wrong direction costs me nothing.
13. As a user, I want to send my next message after a stop and have the assistant continue naturally, so that stopping never breaks the conversation.
14. As a user, I want markdown answers with tables and code blocks rendered nicely, so that numbers are readable.
15. As a user, I want suggested follow-up questions under an answer and starter suggestions in an empty chat, so that I learn what the assistant can do.
16. As a user, I want to see each tool call the assistant made (the SQL it ran, the rows it got back, the sub-agent it called) in a collapsible step, so that every number is auditable.

### Context management

17. As a user, I want long chats to keep working without the model losing the thread, so that a conversation can span a whole evening.
18. As a user, I want a context badge in the conversation header showing how much of the model's context is used, so that compression is not a surprise.
19. As a user, I want to see a divider in the transcript where older turns were replaced by a summary, and to read and edit that summary, so that I control what the assistant still knows.
20. As a user, I want the assistant to remember durable facts across all chats in the profile (what a merchant is, that PayPal to Max is dinner, that I care about subscriptions), so that I never explain things twice.
21. As a user, I want a Memory page listing every remembered fact with edit and delete, so that wrong memories do not haunt me.
22. As a user, I want only the relevant memories injected into a new chat, so that the prompt stays small and the answers stay focused.

### Ingestion

23. As a user, I want to drop CSV, PDF and image files into the chat composer and have the assistant import them as a tool call with visible progress, so that import is part of the conversation.
24. As a user, I want a dedicated Import page with drag and drop and a mapping preview, so that a large first import does not have to happen in a chat.
25. As a user, I want the assistant to propose the CSV column mapping (date, amount, description, counterparty, debit and credit columns, German decimal commas, DD.MM.YYYY) and let me correct it before anything is committed, so that any bank's export works.
26. As a user, I want exports from Sparkasse, DKB, ING, N26, comdirect and Trade Republic recognized by their headers without asking the model, so that the common cases are instant.
27. As a user, I want text PDFs of bank statements read from their text layer with every amount and date literally present in the source text, so that the model can point at numbers but never invent them.
28. As a user, I want a statement to reconcile (opening balance plus all bookings equals closing balance) before it is trusted, and flagged rows shown to me when it does not, so that extraction errors are caught by arithmetic, not by luck.
29. As a user, I want scanned PDFs and photos read by the vision model, with the same guards wherever a total exists, so that paper statements and receipts are usable.
30. As a user, I want to paste a statement snippet or type "I paid 12 EUR cash for lunch today" and get a preview card of the transaction to confirm, so that cash spending is tracked too.
31. As a user, I want a photo of a bill to become a new transaction, or, when it matches an existing card payment by amount and date, a proposed split of that transaction into the bill's line items, so that one Edeka receipt yields groceries and household separately.
32. As a user, I want every duplicate candidate (same account, amount, date and similar description, or same amount within two days) listed after import and asked about in chat with Keep both or Remove, so that I never lose a real repeated payment and never double count.
33. As a user, I want a shipped synthetic German household dataset (one year, CSV, a Sparkasse-layout text PDF, a few bill images) so that the demo, the tests and the video have realistic data without exposing mine.

### Categorization

34. As a user, I want transactions categorized at import time by, in order, my own rules, merchant enrichment, and the model with a confidence score, so that most rows are right without my help.
35. As a user, I want every transaction to get an enriched friendly title and short description (Edeka Filiale 1234 becomes Edeka, supermarket), so that the table and the charts read well.
36. As a user, I want the uncertain rows batched into a Question card in the chat right after import, showing the transaction, the top guesses as buttons and a free text field, so that I answer ten questions in a minute.
37. As a user, I want each answer I give to become a rule in memory, so that the same merchant never asks again.
38. As a user, I want to tell the assistant things like "PayPal to Anna is always Dining" in plain language and have that stored as a rule, so that teaching is conversational.
39. As a user, I want about fifteen default categories with subcategories one level deep, so that I start with something sensible.
40. As a user, I want to add, rename, merge and delete categories and subcategories in Settings or by asking the assistant, so that the taxonomy is mine.
41. As a user, I want Needs review to be the state of an unclassified transaction and Unknown a real category for things a human decided fit nothing, so that the two are never confused.
42. As a user, I want the assistant to search the web for a merchant it does not recognize when I have allowed it, deciding by itself how many searches it needs, so that "what is an Xbox subscription" is answered without me.
43. As a user, I want only a scrubbed merchant token (never amounts, dates, IBANs, card numbers or personal names) to leave the machine, so that my privacy holds.
44. As a user, I want web lookup off by default with one switch in Settings and an outbound log of every request that ever left, so that "nothing left my machine" is checkable.

### Asking questions

45. As a user, I want to ask "how much did I spend on groceries in May" and get a number that came from a SQL query I can expand, so that I trust the answer.
46. As a user, I want the SQL written by a dedicated query sub-agent and validated as read-only before it runs, so that the main assistant stays focused and my data cannot be changed by a query.
47. As a user, I want the assistant to say clearly when the profile has no data or the question cannot be answered from the data, so that it never guesses a number.
48. As a user, I want charts for trends and breakdowns drawn in a consistent house style (line, area, vertical and horizontal bars including grouped and stacked, doughnut with at most six slices, sankey), so that every chart looks like it belongs to the app.
49. As a user, I want the chart sub-agent to plan the chart, write it, check it in-process and repair it up to twice before I see it, with the plan and repairs visible in the thinking panel, so that broken charts never reach me and I can see the work.
50. As a user, I want charts to respect dark and light theme, format money as EUR, use short month labels, show a legend only with more than one series and animate subtly, so that they are readable and pretty.
51. As a user, I want the assistant to answer a follow-up like "and compared to April" with the previous question in mind, so that analysis flows.

### Editing and the transactions page

52. As a user, I want a Transactions page with a virtualized table (date, description, enriched title, amount, category, subcategory, account, source), so that I can see everything.
53. As a user, I want to filter by text, date range, category, account and Needs review, so that I find things fast.
54. As a user, I want to click a cell and edit it inline, so that fixing one row takes one click.
55. As a user, I want to expand a row to see its splits and edit them, with the children always summing to the parent amount, so that a split never breaks the bank total.
56. As a user, I want to select many rows and recategorize or delete them at once, so that bulk fixes are quick.
57. As a user, I want to add a transaction manually or from a bill photo on the Transactions page, so that the chat is not the only way in.
58. As a user, I want to ask the assistant to split, recategorize, edit or delete transactions and see a preview card with the exact affected rows and Apply and Discard buttons, so that bulk mutations are never a surprise.
59. As a user, I want a single obvious edit I literally asked for ("set this one to Dining") to apply directly with an Undo, so that small fixes have no ceremony.
60. As a user, I want queries and charts to count split children and never the parent, so that splits do not double count.

### Preference optimization

61. As a user, I want thumbs up and down on every assistant answer ("Was this response useful?"), so that I can give feedback in one click.
62. As a user, I want thumbs on every chart ("Was this chart useful?") and a Regenerate that draws a second chart so I can pick the better one, so that chart quality improves.
63. As a user, I want every rating and every pick stored as a preference record with the prompt, the chosen and the rejected output, the SQL and the chart code, so that training data accumulates while I use the app.
64. As a user, I want a Feedback page that shows what has been collected and an export to a training set, so that I can see and use the data.
65. As a developer, I want a training folder with a DPO export and a train script for the adapters, so that the preference data becomes better sub-agents.

### Models and sub-agents

66. As a user, I want two selectable chat models, a fast one and a quality one, so that I choose the trade-off.
67. As a developer, I want a provider switch between OpenRouter and local llama-cpp-python via one environment variable, with the same two logical slots, so that development runs remote and the demo runs local without code changes.
68. As a developer, I want the sub-agents (query, chart, categorizer, extraction, memory distillation) pinned to the fast slot regardless of the chat model, so that the fine-tuned adapters slot in later without touching the chat model.
69. As a developer, I want local inference to keep both models resident with a context cap that fits 24 GB, thinking enabled through the chat template, and vision through the multimodal projector, so that the local path matches the remote one feature for feature.
70. As a developer, I want an adapter registry where a LoRA adapter can be attached to the fast slot per sub-agent (query, chart), so that the two fine-tuned models load on the same base weights and a comparison measures weights only.
71. As a developer, I want a sanity check command that proves both models answer, think and call tools, so that a broken model setup is found before the demo.

### Video and hand-in

72. As a presenter, I want the app to run through a full demo script (import, questions, chart, split, memory across chats, model switch, stop, compression, preference, web lookup) without a reload or a crash, so that Monday goes well.
73. As a grader, I want to unzip, run `uv run finquery`, and have models download on first run with progress, so that evaluation takes minutes.

## Implementation Decisions

### Architecture

- One Python process (FastAPI, uvicorn) serves the API and the built frontend as static files. Python 3.12, managed by uv. Node is used only on development machines to build the frontend.
- SQLite is the store, one database file per installation, every table carries a profile foreign key. SQLAlchemy 2 for models and migrations by simple create-all plus versioned upgrade functions.
- Pydantic AI is the agent framework. The course rule that no library may implement an entire elective is respected because the sub-agents, the context compression, the memory selection, the preference pipeline and the self-directed web search loop are our code; Pydantic AI supplies the model abstraction, tool dispatch and the stream adapter.
- The chat wire protocol is the Vercel AI SDK UI message stream, produced by Pydantic AI's Vercel adapter with sdk_version 7. The frontend uses useChat from the AI SDK React package with the default HTTP transport. Thinking maps to reasoning parts, tool calls to tool parts, everything custom (charts, question cards, changesets, import progress, context stats) travels as named data parts. Chunk shapes and required headers are those documented for AI SDK 7.
- Stop is a dedicated endpoint per conversation that sets a cancel flag checked by the model stream, in addition to the client disconnect. The partial turn is persisted as interrupted.
- Frontend: Vite, React 19, TypeScript, Tailwind 4, shadcn (CSS variables mode), AI Elements components from the official registry, TanStack Router and Query, TanStack Table with virtualization for the Transactions page, TanStack Charts pinned to the exact installed version. The AI Elements `message` component provides the markdown response renderer; `shimmer` replaces the removed loader.
- Every AI Elements component that fits is used rather than re-implemented: conversation, message, reasoning, tool, prompt-input with attachments and stop, model-selector, suggestion, context, confirmation, sources, inline-citation, code-block, chain-of-thought, task, plan, artifact, image, checkpoint, queue.

### Providers and models

- Two logical model slots: fast and quality. A provider setting (environment variable, default openrouter during development, local for hand-in) resolves each slot to a Pydantic AI model.
- OpenRouter mapping: fast is google/gemma-4-26b-a4b-it, quality is google/gemma-4-31b-it, reasoning enabled through the request options. The key lives in a gitignored env file.
- Local mapping: fast is gemma-4-E4B-it Q4_K_M, quality is gemma-4-12b-it Q4_K_M, both with their multimodal projector, downloaded from Hugging Face on first run to a models folder with progress reporting, reusing a parked copy if the hash matches. Both stay resident, context capped at 32k tokens per model.
- The local model is a custom Pydantic AI Model over llama-cpp-python 0.3.35 with the Gemma 4 multimodal chat handler wrapped so thinking is enabled through the chat template. The raw text stream is split on the Gemma 4 thought channel markers into thinking parts and text parts. Tool calls are parsed from the Gemma 4 tool-call syntax. Schema-constrained output and free tool calling are never combined in one request; sub-agent calls that need a schema use a forced single tool.
- LoRA adapters attach and detach through the low-level llama.cpp adapter API on the fast slot, one adapter at a time, guarded by a lock. Adapter specs are a registry keyed by sub-agent (query, chart). A missing adapter file falls back to base weights with an audit note in the turn. Training itself is out of scope for this spec.
- Sub-agents always use the fast slot. The chat agent uses the slot chosen in the conversation.

### Domain model

- Profile: the isolation boundary. Owns accounts, transactions, categories, rules, memories, conversations, preference records, outbound log.
- Account: a bank account or card, derived from imports or created manually.
- Transaction: one booking with exactly one amount, description, date, account, optional category and subcategory, an enrichment (title and short description), a source (import id, manual, bill photo) and a fingerprint for duplicate detection. A transaction may be a parent with split children; children reference the parent, must sum to its amount, and only children of a split parent are counted by queries and charts.
- Category and Subcategory: profile-scoped taxonomy, subcategory one level deep. Needs review is the absence of a category. Unknown is a real category never produced by automation.
- Category rule: a profile-owned pattern to category mapping created from Question card answers, chat statements, or manual edits. Highest-priority categorization stage.
- Memory: a durable fact with text, kind (rule, preference, fact), source (explicit or distilled), created from a turn. Selected into a chat by keyword and recency.
- Conversation: profile-scoped, has a title, a model slot, messages stored as Pydantic AI message history JSON plus the UI messages, a summary and a summary-through marker for compression.
- Import: a record of one ingestion (file name, kind, mapping used, row counts, duplicates found, reconciliation result).
- Changeset: an agent-proposed bulk mutation with an exact preview of affected rows, inert until applied through the UI. Applying is deterministic code.
- Preference record: prompt, chosen output, rejected output, kind (answer or chart), the SQL and chart code involved, the rating.
- Outbound log and Web lookup cache: every request that left the machine, and the cached result per merchant token.

### Chat agent and tools

- The chat agent has these tools: query (delegates to the query sub-agent and executes the returned SQL), chart (delegates to the chart sub-agent), import_file, propose_changeset, apply_simple_edit, ask_user, remember, lookup_merchant (only when web lookup is on), and read-only helpers for taxonomy and account listing.
- Numbers come only from executed queries. The system prompt forbids arithmetic in prose and the assistant is told to call query for any figure.
- SQL guard: the query sub-agent's SQL is parsed with sqlglot, must be a single SELECT over the profile-scoped transaction view, no writes, no attach, auto-LIMIT. The view excludes split parents.
- ask_user is a client-side tool: the assistant emits it with a structured question (title, transaction refs, options, allow free text), the frontend renders a Question card, and the user's answer is returned as the tool output, after which the run continues. Categorization questions, duplicate decisions and CSV mapping confirmation all use it.
- propose_changeset returns a changeset id and preview; the card in chat offers Apply and Discard which call REST endpoints. apply_simple_edit is for single-row edits the user literally requested and returns an undo token.
- Import inside chat: attached files arrive as file parts; import_file runs the ingestion pipeline and streams progress as transient data parts, then the assistant asks about uncertain rows and duplicates via ask_user.

### Sub-agents

- Query sub-agent: fast slot, receives the question, the taxonomy, the date range of the data and the schema, returns SQL through a forced single tool. Same prompt framing in production and later in training.
- Chart sub-agent: fast slot. Plan pass (shape, columns, title) visible as thinking; SQL via the query sub-agent; then a TanStack Charts definition in plain JavaScript (no JSX) using an allowlisted set of globals: defineChart, lineY, areaY, barY, barX, polar, pie, radialArc, sankeyDiagram, scaleLinear, scaleBand, scalePoint, scaleOrdinal, tooltip, theme palette, EUR formatters. In-process self-check with quickjs against a stub that records the definition: compiles, runs, exactly one chart, referenced columns exist, requested shape honoured, data mapped not inlined, house rules (six slices max, legend only when more than one series, height 280). Up to two repair rounds streamed as thinking. Result travels as a data part (title, SQL, rows, code) and renders in a sandboxed iframe that hosts React and TanStack Charts with theme and formatters. Month axes use band scales with short labels; there is no time scale in TanStack Charts.
- Categorizer sub-agent: fast slot, batches of transactions, returns category, subcategory, confidence, enrichment per row through a forced single tool. Below a confidence threshold the row goes to the Question card batch.
- Extraction sub-agent: fast slot, text-layer path points at literal amounts and dates in the source text (verbatim guard) and the statement must reconcile; vision path receives page images and applies the same guards where a total exists. Flagged rows are shown in a review step before commit.
- Memory distillation: fast slot, after each assistant turn, extracts durable facts as structured output; deduplicated against existing memories.
- Web lookup loop: our own loop over a keyless multi-backend search library with explicit backend fallback; the agent decides how many searches to run up to a budget; scrubbing produces the merchant token; every request is written to the outbound log before it is sent; results cached per merchant token.

### Context management

- Token counting per model through the provider's tokenizer or an approximation. When history exceeds 60 percent of the slot's context, turns older than the last six are summarized by the fast slot into a rolling summary that replaces them in the prompt. The summary and its boundary are stored on the conversation, shown as a divider in the transcript and editable.
- Per-turn context assembly: system prompt, selected memories (max five, by keyword and recency), taxonomy digest, data date range, rolling summary, recent turns. A context data part reports token usage for the badge.

### Ingestion pipeline

- One pipeline with pluggable readers: CSV (preset headers for the six named banks, otherwise model-proposed mapping confirmed via ask_user or the Import page preview), text PDF (pdfplumber text and tables), scanned PDF and images (pypdfium2 rendering, vision through the fast slot), pasted text and typed statements (model extraction with a preview card).
- Guards: verbatim guard for text sources, reconciliation guard for statements with balances, mandatory preview for anything flagged.
- Duplicate detection at commit: exact fingerprint (account, date, amount, normalized description) and near match (same amount within two days and similar description). Every candidate is asked about; nothing is dropped silently.
- Bill photos: line items, total, date and merchant are extracted; a match against an existing transaction by amount and date within three days proposes a split changeset, otherwise a new transaction preview.
- Synthetic dataset generator: one canonical year of a German household, emitting CSV, a Sparkasse-layout text PDF and a few bill images, shipped in fixtures and used by tests.

### Preference optimization

- Thumbs on answers and charts write preference records. Chart Regenerate produces a second chart for the same prompt; the pick stores chosen and rejected. Answer thumbs down offers an optional A/B: a second answer at higher temperature, the pick stores the pair.
- Feedback page lists records and exports a JSONL training set. A training folder contains the DPO export and train script targeting the fast slot's adapters (script exists; running it is a later phase).

### Settings

- Profile management, taxonomy editor, web lookup switch with outbound log, memory page, feedback page, provider and model status, model download progress, sanity check button.

## Testing Decisions

- One automated seam: the FastAPI application driven in-process over HTTP with an async test client. The chat endpoint is exercised by posting AI SDK UI messages and reading the SSE stream; REST endpoints (profiles, transactions, imports, changesets, memories, settings, preferences) are exercised directly.
- Both model slots are replaced in tests by Pydantic AI's scripted FunctionModel, which returns predetermined thinking, tool calls and text for a given step. Sub-agents are scripted the same way. No test loads a real model or calls OpenRouter.
- A good test asserts external behaviour: the stream contains a reasoning part then a tool part with the executed SQL then text; the transactions table shows the applied changeset; a duplicate import asks a question instead of inserting; a chart data part passed the self-check. Tests never import internal modules to assert on their state.
- Each ticket ships its tests at this seam. The synthetic dataset is the test fixture.
- The frontend has no unit tests. Every ticket is verified by a browser agent against the running app (OpenRouter provider), iterating until the flow works and looks right, and the verification is reported back with screenshots.
- A small opt-in smoke suite, skipped by default, runs the sanity check against the configured real provider.
- Prior art: none in this repo, it is empty.

## Out of Scope

- Training the two LoRA adapters, the data generation and labeling page for the chart adapter, and the held-out evaluation. The adapter registry and the training scripts are in scope; running them is the phase after this spec.
- Accounts, authentication, multi-user, sync.
- Audio input. Gemma 4 audio is not supported by llama.cpp.
- OFX, MT940, CAMT and XLSX importers.
- A dashboard page. Charts live in chat.
- Mobile layout beyond not breaking at tablet width.
- The hand-in ZIP packaging and the video recording. They follow the demo.

## Further Notes

- OpenRouter is a development convenience. Only synthetic data goes through it. The privacy story of the product is the local path, and the demo and hand-in run local.
- Laptop load: at most two implementation or verification agents run real models at once while the provider is local. On OpenRouter this limit does not apply.
- The old repository is archived at ~/Dev/finquery-old.tar.gz and on the branch archive/old-main. It is reference material only, never a source of truth.
- Vocabulary to carry into CONTEXT.md: Profile, Account, Transaction, Split, Category, Subcategory, Needs review, Unknown, Category rule, Enrichment, Memory, Conversation, Rolling summary, Import, Changeset, Preference record, Merchant token, Outbound log, Model slot (fast, quality), Provider, Sub-agent, Adapter.

## Amendments

- 2026-09-05: The Import page is an overview only. It lists past imports (file, kind, account, when, rows read, imported, duplicates found and undecided, reconciliation, needs review) with a Delete action and a "Continue in chat" link for anything undecided. It has no drop zone, no mapping preview and no review table. Every import happens in the chat composer (attachments, pasted text), and every decision (mapping confirmation, duplicates, extraction review, Needs review questions) happens in chat through Question cards. User stories 24 and 25 are read accordingly; story 57's "from a bill photo on the Transactions page" is dropped, bill photos go through chat too.
- 2026-09-04: The quality slot is Qwen3.5 9B instead of Gemma 4 12B (ticket 23). OpenRouter runs the same model as the local path for it.
- 2026-09-05: A Dashboard page exists after all (ticket 35): four default charts and four summary tiles per profile, charts pinned from chat or added on the page through the chart sub-agent, persisted as title, SQL, code and plan with the SQL re-run through the guard on every load. The "no dashboard" line under Out of Scope is superseded.
- 2026-09-06: Long-term charts are made in chat, and the Dashboard page is an overview with a date range (tickets 44 and 45). Two kinds of chart: a one-time chart that lives in its transcript, and a long-term chart that also lives on the dashboard. The chat agent decides itself, through a flag on its chart tool, whether a chart it draws is long-term (asked to be tracked, per month over time, a recurring overview) and stores it directly; the card then says "On the dashboard" with a Remove action, and the manual "Add to dashboard" stays for the rest. Long-term charts are listed, shown, edited, renamed and removed from chat as well; an edit or removal applies directly and the card carries Undo. The dashboard's own "Add chart" line is removed, like the Import page's drop zone was: the page shows, filters, renames, reorders, refreshes and removes, and points to chat for anything new. The page has a date range (from, to, presets This month, Last 3 months, This year, All) kept in the URL search params; the range narrows the profile-scoped view every stored statement and the tiles run over, with no model call, so the four defaults' "newest booking" becomes the end of the range. Inside a chart nothing is rounded: slices, bars and swatches are square, enforced by the frame; rounding stays on cards, buttons, inputs and the tooltip.
