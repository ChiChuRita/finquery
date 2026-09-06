# Checklist against the course task sheet

Every bullet of `docs/course/task-description.md` (the sheet of 2026-07-06), with its status on
`main` as of 2026-09-06, where the code satisfies it, and the evidence. Status words: **done**,
**partial**, **not started**, **not claimed**.

Tickets 44 to 47 are running in parallel and their code is not on `main`; ticket 43 has not
started.

## Required features

| Bullet | Status | Where | Evidence | Explainer |
| --- | --- | --- | --- | --- |
| Runnable with `uv` | done | `pyproject.toml` `[project.scripts]` (`finquery`, `finquery-check`, `finquery-bench`); `src/finquery/main.py:main` | ticket 17 clean checkout (`uv sync` 0.2 s cached, server up); `README.md` Run section | 01 |
| A user interface, cross-platform | done | React SPA served by `src/finquery/app.py:create_app` from `frontend/dist`; routes in `frontend/src/routes.tsx:router` | browser verifications in every ticket, both themes at 1024 and 1440 (tickets 26, 27) | 01 |
| Chat: text input | done | `frontend/src/components/composer.tsx:Composer`; `src/finquery/api/chat.py:chat` | `tests/test_chat.py`; an empty message is 422 (ticket 31) | 01 |
| Chat: history visible | done | the full transcript from `src/finquery/api/conversations.py:get_conversation`, rendered by `frontend/src/components/chat-view.tsx:ChatView` | reload assertions in `tests/test_categorization.py`, `tests/test_query.py`; ticket 01 | 01 |
| Chat: view any part of the prior history | done | the whole conversation is loaded and scrollable; tabs keep scroll position (`frontend/src/lib/workspace.tsx:readScrollTop`); the reasoning panel is capped and scrolls internally (ticket 21) | tickets 02, 21, 32 (30 tabs, back and forward) | 01 |
| Start, stop and resume: switching between conversations | done | `frontend/src/components/conversation-tabs.tsx:ConversationTabs`, `frontend/src/components/app-sidebar.tsx:AppSidebar`; a running turn survives a switch (`src/finquery/api/running.py:RunningTurn`, `src/finquery/api/chat.py:reattach`) | `tests/test_background_turns.py` (8 tests); ticket 33 | 01 |
| Start, stop and resume: stop | done | `src/finquery/api/chat.py:stop`, cancellation token checked between tokens locally | `tests/test_chat.py` stop tests; demo: under a second | 01, 02 |
| Create new, continue old, remove old conversations | done | `src/finquery/api/conversations.py:create_conversation`, `patch_conversation`, `delete_conversation`; the server owns the history | `tests/test_conversations.py`; ticket 02 | 01 |
| Switch the LLM: at least two loadable models | done | Four catalog entries across both providers: `src/finquery/catalog.py:Catalog`, `finquery.providers.ModelRole`; `src/finquery/local/runtime.py:LocalStack` (two seats, the chat one swapped); `frontend/src/components/model-picker.tsx:ModelPicker`; the entry per conversation and per turn | `tests/test_model_catalog.py` (four entries, the resolution rule, the seat swap); `tests/test_conversations.py` (switch mid-conversation, every turn carries its entry); `tests/test_local_provider.py`; `finquery-check` all eight checks (ticket 23) | 02 |
| Simple memory across a group of chats (the profile) | done | `src/finquery/memory.py:add_memory`, `select_memories`, `build_memory_block`, `distill_memories`; `src/finquery/agent.py:remember`; `frontend/src/components/memory-page.tsx:MemoryPage` | `tests/test_memory.py` (a fact reaches a new conversation and stays in its profile, five of two hundred); demo steps 17 and 18 | 03 |
| At least two fine-tuned models (LoRA or QLoRA) | **not started** (infrastructure done, training not run) | attach path `src/finquery/local/adapters.py:AdapterRegistry`, `src/finquery/local/runtime.py:LocalStack` (`with_adapter`), settings key `src/finquery/local/model.py:LocalModelSettings`; bench `--adapter` in `bench/finquery_bench/models.py:local_target`; DPO `training/preference/train_dpo.py:train`; data generation ticket 43 | `tests/test_local_provider.py` (`test_adapter_falls_back_to_base_weights_with_a_note`); no `models/adapters/*.gguf` exists; no sub-agent sets `finquery_adapter` yet | 04 |
| Video demo: required and elective features | **not started** | storyboard `docs/demo-script.md` | ticket 17 (the script ran end to end on the local provider on 2026-09-05) | 05 |
| Video demo: at least one real-world use case that benefited from the electives | **not started** (use case identified) | unknown merchant: web lookup, categorizer, memory; demo steps 25 to 27 and 17 to 18 | tickets 14, 17 | 05 |

## Elective features

| Bullet | Status | Where | Evidence | Explainer |
| --- | --- | --- | --- | --- |
| Adaptive RAG over user documents | not claimed, not built | | | |
| Extensible user-provided tool calling | not claimed, not built (dropped 2026-09-01) | | `git show archive/old-main:DECISIONS.md` | |
| Sub-agent deployment: a sub-agent fulfils an LLM-defined task as a tool call | **done** (claimed) | thirteen agents on the fast slot: `src/finquery/query/subagent.py:query_agent`, `src/finquery/query/check.py:check_agent`, `src/finquery/chart/subagent.py:plan_agent` and `code_agent`, `src/finquery/categorize/subagent.py:categorizer_agent`, `src/finquery/extract/subagent.py:statement_agent` and `bill_agent`, `src/finquery/memory.py:distill_agent`, `src/finquery/weblookup/loop.py:lookup_agent`, `src/finquery/ingest/mapping_agent.py:mapping_agent`, `src/finquery/ingest/typed.py:extraction_agent`, `src/finquery/context.py:summary_agent`, `src/finquery/followups.py:followup_agent`; dispatched from tools of `src/finquery/agent.py:chat_agent`; narration via `src/finquery/api/chat.py:Narration` | `tests/test_query.py`, `tests/test_chart.py`, `tests/test_categorization.py`, `tests/test_extraction.py`, `tests/test_web_lookup.py`; `bench/results/` | 13 |
| Sub-agent extra credit: the controlling LLM continues without waiting | not claimed | the chat agent waits for its tool; the turn is a server task the browser does not wait on (`src/finquery/api/running.py:RunningTurn`) | ADR 0012, ticket 33 | 13 |
| Secure execution of generated code (Python) | not claimed (dropped 2026-09-01); built for JavaScript charts, not Python | `src/finquery/chart/selfcheck.py:check_chart_code` (QuickJS, 2 s, 64 MB), `frontend/src/components/chart-tool.tsx:ChartFrame` (`sandbox="allow-scripts"`) | `tests/test_chart.py`; ADR 0009 | 07 |
| Repeated self-controlled web search: finds and visits pages | **done** (claimed) | `src/finquery/weblookup/loop.py:run_loop` (search, fetch, finish; 4 searches, 3 page reads), `src/finquery/weblookup/client.py:HttpWebClient` (fetch and HTML to text), `src/finquery/weblookup/scrub.py:scrub`, `src/finquery/weblookup/store.py:OutboundJournal`, `src/finquery/agent.py:lookup_merchant`, `src/finquery/categorize/pipeline.py:_look_up` | `tests/test_web_lookup.py` (12 plus 2); ticket 14 (Nordsee two searches; ten log rows, tokens only); demo step 26 (one search, one page read, 53 s) | 15 |
| Preference optimisation: a choice of generated texts, picked by the user | **done** (claimed) | `src/finquery/api/preferences.py:chart_alternative`, `answer_alternative`, `store_pair`, `rate`; `src/finquery/preferences.py:store`; `frontend/src/components/feedback.tsx:PairSide`, `AnswerCompare`; `frontend/src/components/feedback-page.tsx:FeedbackPage` | `tests/test_preferences.py` (8); tickets 15, 22, 30 | 14 |
| Preference optimisation: code to train a LoRA or QLoRA on the choice data | **partial** (claimed; script exists and validates, training not run) | `training/preference/export_pairs.py:chart_pairs`, `query_pairs`; `training/preference/train_dpo.py:train` (`--dry-run` without a GPU) | `training/preference/README.md`; ticket 15 export produced one query pair on a verification database | 14 |
| Multimodal ingestion (images, PDF and more; a vision-language model) | **done** (claimed 2026-09-06) | `src/finquery/extract/statement.py:extract_statement` (PDF text layer, rendered pages and DOCX text), `src/finquery/extract/subagent.py:read_statement_image`, `read_bill` (vision on the fast slot), `src/finquery/extract/bill.py:bill_outcome`; CSV in `src/finquery/ingest/csv_reader.py:parse`, XLSX in `src/finquery/ingest/xlsx.py:read_xlsx`, DOCX in `src/finquery/extract/docx.py:read_docx`; every local model ships a vision projector (`src/finquery/local/catalog.py:LOCAL_FAST`) | `tests/test_extraction.py`, `tests/test_xlsx_and_docx_import.py` (5); ticket 11 (15 pages, 433 of 433, reconciled); ticket 42 (twenty receipts); ticket 58 (433 rows off the cells of a workbook, 15 out of a Word document reconciled). Not covered: audio | 16, 08 |
| Concurrent multi-user | not claimed, not built (profiles isolate data, not users; one local process) | | ADR 0012 | |
| Intelligent context management: compression, isolation, selection | **done** (claimed) | compression `src/finquery/context.py:needs_compression`, `summarize`, `src/finquery/memory.py:distill_memories`; isolation `src/finquery/db.py:Profile` foreign keys, `src/finquery/query/guard.py:execute_read_only` (profile temp view), `src/finquery/agent.py:ChatDeps`; selection `src/finquery/context.py:assemble`, `src/finquery/memory.py:select_memories`, the `@chat_agent.instructions` blocks `src/finquery/agent.py:data_brief`, `answer_language`, `attached_files`, `web_lookup_brief` | `tests/test_context.py`, `tests/test_memory.py`, `tests/test_profiles.py`; ticket 12 (divider at `FINQUERY_CONTEXT_BUDGET=6000`), ticket 32 (crossed three times) | 12 |
| Advanced prompt caching (a method like H2O implemented yourself) | not claimed, not built | | | |
| Tree-of-Thought reasoning as a user-enabled thinking mode | not claimed, not built (both models think natively and the panel shows it; that is not ToT) | | | |

## Counting

- Required: 10 bullets done, 3 not started (two fine-tuned models, and the two halves of the
  video demo).
- Electives claimed (pair, four required): context management done; sub-agent deployment done
  (extra credit not claimed); web search done; multimodal ingestion done (claimed 2026-09-06,
  ticket 58). Preference optimisation was the fourth until 2026-09-06; ticket 59 owns its rows
  here and what becomes of them.
- Built but not claimed: sandboxed execution of generated chart code (JavaScript, not Python).
