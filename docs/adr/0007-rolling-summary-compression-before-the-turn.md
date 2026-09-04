# ADR 0007: One rolling summary, compressed before the turn, counted by approximation

Date: 2026-09-04
Status: accepted

## Context

A conversation grows without limit and a context window does not: 16k per resident model on the
local provider (ADR 0006), 262k on OpenRouter. The spec asks for a badge showing how full the
context is, a summary that replaces the older turns once history passes 60 percent of the slot's
context, and a divider in the transcript where that happened, with the summary editable.

Three questions had to be answered: what a token count is, when compression runs, and how the
summary reaches the model.

## Decision

- **One budget per slot, capped by configuration.** `FINQUERY_CONTEXT_BUDGET` (default 32768) is
  the working budget for a turn, and the local provider's `n_ctx` caps it further. Both slots have
  the same context on both providers today, so the budget does not depend on the slot. The cap
  keeps prompts small on OpenRouter, where the real window is eight times bigger than any
  finance conversation needs, and makes compression demonstrable.
- **One token count, an approximation, ours.** `finquery.context.estimate_tokens` is four
  characters per token plus a fixed overhead per message. The compression decision is made before
  the request is sent, so a provider-reported count (OpenRouter returns one, the local model
  reports one) cannot inform it; using the reported count for the badge as well would put a
  second, disagreeing number on the screen. The badge therefore shows the number the decision
  used. The upgrade path is a `tokenize` call on the local stack's `Slot`, behind the same
  function.
- **Compression runs before the answer, not after it.** The turn that would cross the threshold
  is already the turn that runs small. It costs one fast-slot call (reasoning off) on that turn.
- **The summary travels as run-level instructions**, appended to the agent's system prompt by
  Pydantic AI (`Agent.run_stream(instructions=...)`), not as a fabricated system message in the
  history. On the local provider the chat template folds instructions and system prompts into one
  leading system message, so both providers see the same shape.
- **Nothing is deleted.** Turns stay in the database and in the transcript. `conversation.summary`
  and `conversation.summary_through` (the position of the last turn the summary covers) are the
  whole state. The transcript renders every message and puts a divider after the summarized ones,
  which is why the summary can be edited (`PATCH /api/conversations/{id}` with `summary`) and why
  the next turn simply sends the edited text.
- **Per-turn assembly is one function**, `finquery.context.assemble`, returning the history, the
  note, the token count and where the divider goes. Its stats reach the client as a `data-context`
  part, streamed at the end of the turn and stored on the assistant message, so the badge is the
  same live and after a reload.

## Consequences

- Past the threshold the window holds at six turns plus the summary: each further turn folds
  exactly one more turn in and asks the fast slot for one small summary. The badge climbs while
  the whole history is sent and then holds.
- Ticket 13 adds selected memories to `assemble` and reports their count in the same data part,
  where the badge already has a slot for it.
- Anything that adds to the prompt (memories, taxonomy digest, data date range) has to go through
  `assemble` or the badge and the compression decision stop agreeing with the prompt.
