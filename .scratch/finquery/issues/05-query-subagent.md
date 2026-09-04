# 05: Query sub-agent and the numbers invariant

**What to build:** A user asks "how much did I spend on groceries in May" and gets a figure that came from a SQL query. The chat agent calls the query tool, a dedicated query sub-agent on the fast slot writes the SQL through a forced single tool, a guard validates it as a single read-only SELECT over the profile-scoped split-aware view with an automatic LIMIT, the rows come back, and the tool step in the transcript shows the SQL and the rows on expand. Follow-ups like "and compared to April" work. A profile without data gets a clear answer without any number. The system prompt forbids arithmetic in prose.

**Blocked by:** 01 Walking skeleton, 03 Data model, synthetic dataset and CSV import page

**Status:** done

- [x] Query sub-agent prompt with schema, taxonomy, data date range and examples; same framing later reused for training
- [x] SQL guard with sqlglot: single SELECT, allowlisted view, no writes or attach, auto LIMIT, clear error back to the agent for a retry
- [x] Tool step UI shows the question the sub-agent received, the SQL, row count and a table of rows
- [x] No-data path answers without calling the model for numbers
- [x] HTTP-seam tests: scripted sub-agent SQL executes and its rows appear in the tool part; a write attempt is refused; empty profile answer
- [x] Browser verification of three questions on the synthetic dataset including a follow-up

## Comments

Done 2026-09-04. Structure for the next tickets:

- `src/finquery/query/`: `subagent.py` (the `query_agent`, forced single tool `run_sql`, the
  pure prompt builder `query_prompt(request, context, hints=, rejected=)` and
  `load_query_context`), `guard.py` (`validate_sql`, `execute_read_only`, `MAX_ROWS = 200`),
  `runner.py` (`run_query(resolve_model=, session_factory=, profile_id=, request=, hints=)`
  returning a `QueryOutcome` whose `.payload()` is the tool result).
- `agent.py` gained `ChatDeps` (session factory, profile id, model resolver), dynamic
  instructions (`data_brief`) and the `query` tool. `api/chat.py` passes the deps into
  `run_stream`. Another tool is one `@chat_agent.tool` plus, if it needs a model, a
  `ctx.deps.resolve_model(...)` call inside it; another sub-agent is one module next to
  `query/subagent.py` with its own forced tool and pure prompt builder.
- Profile scoping is a per-connection temp view that shadows `transaction_view`, plus
  `PRAGMA query_only`; the guard refuses schema prefixes so the main view is unreachable. See
  ADR 0004, which now records the guard and the scoping.
- A guard or SQLite error goes back to the sub-agent once with the refused statement and the
  reason (`Rejection`); a second failure returns `error` in the tool payload, and the chat
  prompt tells the agent to report it without a figure.
- `api/chat.py` now folds a turn's model responses into one assistant UI message
  (`_one_assistant_message`), because a tool call ends a model response and the reload has to
  look like the live stream (thinking, tool step, answer in one message).
- Frontend: `components/query-tool.tsx` renders the AI Elements `tool` component (request, SQL
  through the existing streamdown code renderer, row count, scrollable rows table).
  `lib/api.ts` types the tool as `ChatTools`, so `part.type === 'tool-query'` is typed.
  The registry's `code-block.tsx` was dropped and `tool.tsx` uses a plain `<pre>` for its
  generic dumps: the app already ships one highlighter and a second shiki copy is not worth it.
- Tests: 22 total (`tests/test_query.py` adds 7). The chat model is scripted to call `query`
  and then to answer from the tool result it finds in the history, so any figure in the
  asserted answer provably came from the executed SQL.
- Screenshots of the verification: /tmp/finquery-05/.

Merged into main on 2026-09-04 on top of 01, 02, 03 and 16. What changed in the merge:

- `ChatDeps.profile_id` comes from the conversation row (`Conversation.profile_id`), because
  explicit profile scoping won in 02 and `app.state.profile_id` no longer exists.
- `ChatDeps` gained `subagent_settings`, filled from `app.state.subagent_settings`. It reaches
  the query sub-agent as `run_query(model_settings=...)` -> `write_sql(model_settings=...)` ->
  `query_agent.run(model_settings=...)`, so the sub-agent runs with reasoning off on OpenRouter
  the same way the follow-up step does. Any later tool that starts a sub-agent reads it off the
  deps instead of knowing provider specifics.
- `api/chat.py` is the union: deps into `run_stream`, `_one_assistant_message`, the follow-up
  step on the fast slot (`data-followups` live and appended to the persisted message),
  `model_slot` in the assistant metadata and the local provider's `audit_notes`. The follow-up
  part is appended after the fold, so it lands on the one folded assistant message.
- `chat-view.tsx` is the union: per-turn model chip, Stopped marker, follow-up suggestions and
  per-tab scroll restore from 02, plus `tool-query` rendering and `foldReasoning` from here.
  Reasoning only folds when two reasoning parts are adjacent, so a turn that queries still shows
  two panels (before and after the tool step), which is what the live stream shows.
- `tests/test_query.py` moved to the merged conventions: `profile_id` on the import commit and
  on `GET /api/transactions`, `new_conversation(client, profile_id, slot)` from conftest, and
  `scripted_sql(..., followups=[...])` answers the post-turn follow-up request that shares the
  fast slot instead of failing its forced-tool assertions. Request counts per turn are now one
  chat request plus one follow-up request plus the sub-agent's requests.
- `uv run pytest` is 43 passed, 1 skipped (the local smoke suite skips by design).
- Verified on OpenRouter with the synthetic dataset: "How much did I spend on groceries in May
  2025?" answered 403.60 EUR from an executed SELECT, the tool step shows the request, the SQL
  and the row, the follow-ups appear, and a reload renders the same transcript. Screenshots:
  /tmp/finquery-merge05/.
