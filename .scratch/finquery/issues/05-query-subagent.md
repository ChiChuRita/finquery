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
