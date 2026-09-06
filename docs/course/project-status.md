# FinQuery: project status against the course sheet

Intelligent Agents project, 40 percent of the overall grade. Working as a **pair** (Rahul Singh,
Liudvikas Zekas), so **4 electives** are required instead of 2.

Presentation **Mon 2026-09-07**. Hand-in **Mon 2026-09-14**, as a ZIP archive.

The product invariant, for context: numbers always come from executed queries, never from the
model. State of this file: main on the evening of 2026-09-06.

## Required features

- [x] **Runnable with `uv`**: `uv run finquery` starts the FastAPI server, which serves the
  prebuilt Vite `dist/`; no Node at runtime. `uv run finquery-check` verifies the local models.
- [x] **A user interface, cross-platform**: React 19, Vite, TanStack Router and Query, shadcn
  and the vendored AI Elements, served as static files, one dark canvas with a collapsible
  shadcn sidebar. Pages: Chat, Dashboard, Transactions, Imports, Memory, Settings, onboarding.
- [x] **A chat interface**: text input, attachments in the composer, the full transcript
  scrollable, a thinking panel, the sub-agents' steps as a chain of thought, Question cards
  answered by button or by typing anything into the composer.
- [x] **Start, stop and resume chats**: tabs, sidebar with rename and delete, Stop keeps the
  partial turn, background turns survive a closed tab, History per conversation.
- [x] **Switch the generation model, at least two loadable**: a catalog of four entries,
  Gemma 4 12B (local, default), Gemma 4 26B (cloud), Qwen3.5 9B (local), Qwen3.5 9B (cloud),
  switchable per conversation mid-chat. Locally the chat seat swaps between the 12B and Qwen;
  Gemma 4 E4B stays resident on the fast seat. 12.9 GB for the pair.
- [x] **Memory across a group of chats**: the profile is the folder. Distilled facts (at most
  two per turn, never figures or dates unless a rule), category rules from Question cards,
  answer language and default model, all profile-scoped, injected per turn, visible and editable
  on the Memory page.
- [ ] **At least two fine-tuned models for special purposes**: four QLoRA adapters in training
  on the HPI cluster tonight, query and chart, on Gemma 4 E4B and on the 12B. Training data:
  1,977 query and 1,791 chart samples over five synthetic households, kept only by execution and
  judged; the benchmark household is unseen in training. Attached on the fast seat through the
  adapter registry, one model setting per sub-agent role. Numbers pending; the transaction
  classifier adapter of the old plan is dropped.
- [ ] **A video demo**: not recorded. `docs/demo-script.md` is the 32-step storyboard on the local
  pair, the real-world elective use case is an unknown merchant resolved by web lookup and a
  receipt photo resolved through vision plus the guards.

## Elective features

Four claimed. Changed twice: on 2026-09-01 secure code execution and user tools left for
preference optimisation and web search; on 2026-09-06 preference optimisation left (built,
measured, removed) for multimodal ingestion.

### 1. Intelligent context management (claimed)

- **Isolation**: the profile is the boundary. Every query runs through a temp view scoped to the
  profile in code; conversations, memory, taxonomy, rules, lookup cache and dashboard are
  profile-scoped; profile switcher and create dialog exist.
- **Selection**: per-turn assembly of the memory block, the rolling summary, the recent turns and
  only the tools that apply (web lookup is not declared when off); the header badge shows the
  budget used.
- **Compression**: at 60 percent of the 32k window the older turns fold into a summary by the fast
  model, with an editable divider; the pending Question card is never summarized away.

### 2. Sub-agent deployment (claimed)

Six sub-agents as tools: query (guard, execution, check pass with one revise), chart (plan, code,
self-check on real rows, repairs, sandboxed frame), categorizer (batches, threshold, Question
cards), extraction (verbatim and reconciliation guards), memory, web lookup. Forced tool schema
with a reasoning field first, one retry with the finding, every step narrated. One model setting
per role: `chat` by default, `fast` for E4B where adapters attach. Extra credit (controller
continues without waiting) not claimed.

### 3. Multimodal ingestion (claimed, since 2026-09-06)

PDF text layer first, vision for scans and receipt photos through the local Gemma 4 models with
their projectors, pasted text, CSV, XLSX (openpyxl into the mapping engine) and DOCX
(python-docx into the text path). Two guards on every extracted figure: verbatim and
reconciliation; flagged rows go to a review card. Duplicates asked about one by one. Receipts
become drafts with item legs and the store resolved. Audio out of scope.

### 4. Web search (claimed)

The lookup loop decides search, fetch or finish with a budget of four searches and three page
reads; floors in code: at least one search, a page read when a hit is the merchant's own site or
Wikipedia, a failed backend retried free; the finish carries a verbatim quote and a confidence
cap. Only a scrubbed merchant token leaves (legal form first, a given-name list, the two-word
rule); off by default; every request journaled before sending and shown in Settings; cached per
profile. Three callers: the chat tool, the categorizer at import, receipt headers.

### Built but not claimed

Preference optimisation (removed 2026-09-06), sandboxed execution of generated chart code
(JavaScript, not Python), the dashboard as a product feature.

## Product, as shipped

1. Local, no accounts; profiles as workspaces with onboarding (categories with delete, answer
   language, first data, default model).
2. UI reworked on AI Elements and shadcn: one dark canvas, collapsible sidebar, equal tiles,
   square charts, date range pickers.
3. Chat: thinking always on, model per conversation, Stop, tabs, history, compression, memory,
   Question cards with typed answers, changesets with Apply and Undo, long-term charts kept by
   the agent's own decision, dashboard charts listed, shown, edited and removed from chat.
4. Categorization: dictionary and rules, categorizer sub-agent, Question cards whose answers
   become rules, about fifteen default categories with subcategories, splits as child rows, web
   lookup for unknown merchants.
5. Transactions page: virtualized table, filters with a shadcn date range picker, inline edit,
   splits, bulk actions. Imports page: overview only.
6. Dashboard: four tiles with deltas and seven default cards from guarded SQL, a date range in
   the URL, cards made and edited in chat.
7. Ingestion: everything through the chat composer; CSV, XLSX, PDF, DOCX, images, pasted text;
   duplicates asked; guards on extraction.
8. Edit transactions: split, delete, add (also from a receipt photo), edit, all as changesets.

## Measured

| what | number | source |
| --- | --- | --- |
| SQL figure match, cluster, same runtime as the laptop | E4B 66, Qwen3.5 9B 70, Gemma 4 12B 87 percent | `bench/results/20260906-cluster-compare.md` |
| Chart figure match | 45, 42, 81 percent | same |
| End to end, 30 cases through the chat agent | 53, 73, 77 percent | same |
| Check pass effect on one model | 69 to 79 percent | `bench/results/20260905T182106Z-*`, `20260906T115540Z-*` |
| Tokens per second on the laptop | 47, 30, 22 | `bench/results/20260906-local-tokens-per-second.md` |
| Receipts | 19 of 19 totals | `.scratch/finquery/reviews/receipts-web-2026-09-05.md` |
| Web lookup after the floors | no-search lookups 9 to 0, pages read 0 to 12 | ticket 53 |
| Benchmark | 459 SQL and 302 chart cases, 141 and 94 held out, frozen | `bench/SPLIT_FROZEN.md` |
| Tests | 460 passed | `uv run pytest` |

## Open until the hand-in

- Adapter numbers against vanilla (training running; quick evals per epoch, best checkpoint
  converted, official runs).
- The video demo.
- Verify the local pair on the laptop once (both models resident).
- A second data round only if the learning curve asks for it.
