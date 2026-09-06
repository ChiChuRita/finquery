# 13: Elective, sub-agent deployment

**Claim:** The chat agent never does specialist work itself. Every job that needs a model of its
own (writing SQL, judging a result, planning and coding a chart, categorizing merchants, reading
a statement page or a receipt, distilling memories, deciding the next web search step, proposing
a CSV mapping, extracting typed bookings, summarizing, suggesting follow-ups) is a separate
Pydantic AI agent on the fast slot with one forced tool, called from inside a tool of the chat
agent, narrating its steps into the thinking panel. The sheet's extra credit (a controlling LLM
that continues without waiting) we do not claim: the chat agent waits for its tool result; what
runs on without anyone waiting is the turn itself, on the server, and the user.

## How it works

```mermaid
sequenceDiagram
  participant U as User (browser)
  participant S as Server task (RunningTurn)
  participant A as Chat agent (chosen slot)
  participant T as Tool (our code)
  participant B as Sub-agent (fast slot, forced tool)
  U->>S: message
  S->>A: run
  A->>T: query(request) / chart(request) / import_file(...) / lookup_merchant(...)
  T->>B: agent.run(prompt) with reasoning off and a 3072 token ceiling
  B-->>T: one structured answer (reasoning field first)
  T->>T: guard, check, fold, apply; narrate each step
  T-->>S: narration lines as reasoning chunks, live
  T-->>A: tool result (rows, figures, rendered, applied, error)
  A-->>S: answer text
  Note over U,S: the browser may leave and come back; the task keeps running
```

In words:

1. The chat agent has tools. A tool that needs a model resolves the fast slot through
   `ctx.deps.resolve_model("fast")` whatever slot the conversation runs on, and runs a dedicated
   agent with `subagent_settings` (reasoning off on OpenRouter, a 3072 token output ceiling on
   both providers).
2. Each sub-agent has exactly one tool and no text output, so its answer is a schema. On the
   local provider that makes llama.cpp build a grammar and turns thinking off; instead every
   schema opens with a `reasoning` field the model fills first (ticket 42).
3. The sub-agent sees a compact prompt of its own, never the conversation: the chat agent writes a
   standalone request.
4. Our code around the sub-agent does the deterministic work (guard, execute, check, fold,
   self-check, apply) and narrates each step through `ChatDeps.narrate`; the chat endpoint turns
   those lines into reasoning chunks on the same stream, so the user watches the sub-agent work
   live and after a reload.
5. The tool result goes back to the chat agent, which writes the answer from the fields the
   result carries (`figures`, `rendered`, `applied`, `say`, `error`), and nothing else.
6. Retries are framed as corrections: the model is shown its own reasoning and answer, the
   finding, and asked for the corrected reasoning and answer.

## The sub-agents

| Sub-agent | Forced tool | Called from | Module |
| --- | --- | --- | --- |
| query | `run_sql` | `query`, `chart`, the bench | `src/finquery/query/subagent.py:query_agent` |
| result check | `judge_result` | `run_query` | `src/finquery/query/check.py:check_agent` |
| chart plan | `chart_plan` | `chart`, dashboard preview, the render-failure retry | `src/finquery/chart/subagent.py:plan_agent` |
| chart code | `chart_code` | same | `src/finquery/chart/subagent.py:code_agent` |
| categorizer | `categorize` | imports, cards, receipt legs | `src/finquery/categorize/subagent.py:categorizer_agent` |
| statement reader | `read_statement` | `import_file` for a PDF or a scanned page | `src/finquery/extract/subagent.py:statement_agent` |
| receipt reader | `read_bill` | `import_file` for a photo | `src/finquery/extract/subagent.py:bill_agent` |
| memory distillation | `remember_facts` | after every turn | `src/finquery/memory.py:distill_agent` |
| web lookup decision | `decide` | `lookup_merchant`, categorizer stage | `src/finquery/weblookup/loop.py:lookup_agent` |
| CSV mapping | `propose_mapping` | `import_file` for an unknown header | `src/finquery/ingest/mapping_agent.py:mapping_agent` |
| typed bookings | `propose_transactions` | `extract_transaction` | `src/finquery/ingest/typed.py:extraction_agent` |
| rolling summary | text | the turn that crosses 60 percent | `src/finquery/context.py:summary_agent` |
| follow-ups | text | after every turn | `src/finquery/followups.py:followup_agent` |

## The code path

1. `src/finquery/agent.py:chat_agent` and its tools: `query`, `chart`, `import_file`,
   `extract_transaction`, `add_transaction`, `lookup_merchant`, `propose_changeset`,
   `apply_simple_edit`, `remember`, `set_rule`, `review_batch`, `review_duplicates`, plus the
   `ask_user` toolset. `ChatDeps` carries `resolve_model`, `subagent_settings` and `narrate`.
2. `src/finquery/providers.py:subagent_settings` and `SUBAGENT_MAX_TOKENS`.
3. `src/finquery/agent.py:guarded`: an unexpected exception inside any tool is one sentence in
   its step.
4. `src/finquery/api/chat.py:Narration` and `_pump`: narration lines and agent chunks travel
   through one queue; `_insert_narration` puts them back after the tool part when the turn is
   persisted.
5. `src/finquery/local/model.py:LlamaCppModel`: a request with one forced tool becomes a grammar
   with thinking off; a free request declares tools with `tool_choice: auto`.
6. Retry framing: `src/finquery/query/subagent.py:_correction`,
   `src/finquery/chart/subagent.py:repair_prompt`,
   `src/finquery/categorize/subagent.py:resubmit_prompt`,
   `src/finquery/extract/subagent.py:statement_retry` and `bill_retry`,
   `src/finquery/memory.py:refusal_prompt`, `src/finquery/weblookup/loop.py:refused`.
7. Background turns (what continues without waiting): `src/finquery/api/running.py:RunningTurn`
   and `src/finquery/api/chat.py:reattach` (01, ADR 0012).
8. Tests: `tests/test_query.py`, `tests/test_query_check.py`, `tests/test_chart.py`,
   `tests/test_categorization.py`, `tests/test_extraction.py`, `tests/test_web_lookup.py`,
   `tests/test_memory.py`, all with the fast slot scripted per forced tool.

## Where the model is in the loop, and where it is not

- Model: the chat agent decides which tool to call and writes the request; the sub-agent writes
  its one structured answer; the check judges.
- Not the model: dispatch (a tool call is a Python function), which slot a sub-agent runs on,
  its settings and ceiling, the deterministic work around it, the narration, the retry framing
  and its limits (one resubmit, two repairs, one reread, one refusal round), the tool result's
  shape.

## Guards and failure handling

- Every sub-agent call is bounded: `SUBAGENT_MAX_TOKENS`, a fixed number of rounds, and a result
  that is an `error` field rather than an exception.
- A sub-agent that cannot be resolved (models still downloading) answers with a sentence in the
  tool result.
- The post-turn sub-agents (follow-ups, distillation) run under a 30 s timeout and never cost the
  answer.
- `QUERY_BUDGET = 5` stops a chat agent from spending fifteen sub-agent calls on one question
  (ticket 37).
- Tool validation errors name the finding and the corrected call, with the refused call still in
  the history.

## What we measured

| Figure | Value | Source |
| --- | --- | --- |
| Reasoning off for sub-agents | the follow-up step from 11 s to 3 s on OpenRouter | ticket 02 |
| Requests per fast turn with one query, local | four to six model requests: chat, query, check, chat again, follow-ups, distillation | `docs/demo-script.md` |
| Prompt growth from the ticket 42 pass (worked examples, reasoning field, corrections) | chart plan 967 to 1286 tokens; chart code 1339 to 1853; categorizer 606 to 857; statement page 422 to 747; receipt 858 to 1292; distillation 532 to 769; follow-ups 155 to 324; web lookup 519 to 819; chat agent 3592 to 3919 | ticket 42 |
| What the pass bought on charts | Gemini 92 % to 97 % figure match; area 67 % to 100 % | ticket 42, `bench/README.md` |
| What it bought on SQL (ticket 40's part) | Qwen 57 % to 69 %, held out 48 % to 64 % | ticket 40 |
| The categorizer | one call for 39 merchants of 433 bookings | ticket 07 |
| Extraction | one call per page, four in flight locally and twelve hosted; 15 pages in 131 s hosted | ticket 11 |
| The web lookup loop | two to three model calls per lookup; typical searches per lookup one | ticket 14 |
| Sub-agent output ceiling | a three-page extraction ran until `n_ctx` was full (6 minutes) before it; the 15-page PDF finishes locally after it | tickets 11, 17 |

## Three sentences for the talk

1. "The chat model is a coordinator: for SQL, charts, categories, statement pages, receipts,
   memories and web search it calls a tool, and behind the tool a second agent on the small model
   answers one structured question with one forced tool."
2. "Each sub-agent writes a short reasoning first and then its answer, and everything around it,
   the guard, the check, the fold, the self-check, is code that narrates what it did into the
   thinking panel, so you watch the sub-agent work."
3. "We do not claim the extra credit for a controlling model that continues without waiting: the
   chat agent waits for its tool. What does continue without anyone waiting is the turn itself,
   which is a server task the browser only subscribes to."

## Likely grader questions

- **Is a sub-agent just a prompt?** It is a Pydantic AI `Agent` with its own instructions, its
  own output schema (a forced tool), its own settings and its own retry framing, called from a
  tool of the chat agent. Thirteen of them, in the table.
- **Does the controlling LLM continue without waiting?** No. The tool call blocks the run until
  the sub-agent answers. Ticket 33 made the turn a server task, so the user and the browser
  continue without waiting, and a turn survives a reload; that is a different thing and we say
  so.
- **Why always the fast slot?** So the adapters slot into one base, so a Qwen turn does not pay
  Qwen's thinking on every sub-call, and so a sub-agent's behaviour is the same whichever model
  the user picked for the chat.
- **How do you test them without a model?** Every test scripts the fast slot per forced tool name
  (`run_sql`, `chart_plan`, `chart_code`, `categorize`, ...) and asserts the stream and the
  database (ADR 0003).
- **Is Pydantic AI implementing the elective?** It dispatches a tool call to a Python function.
  Which sub-agents exist, what they see, how they are bounded, retried and narrated is ours.

## What is not finished

- The extra credit (a non-blocking controlling agent) is not built and not claimed.
- The query and chart adapters that would make the two main sub-agents better are not trained
  (04).
- The check sub-agent's own before and after is unmeasured (06).
