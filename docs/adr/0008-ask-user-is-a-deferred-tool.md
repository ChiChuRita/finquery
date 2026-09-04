# ADR 0008: `ask_user` is a deferred tool, and its turn is rewritten when the answer arrives

Date: 2026-09-04
Status: accepted

## Context

Categorization asks the user about the merchants it could not place, and later tickets ask
about duplicates (10), a CSV mapping (08) and flagged extractions (11). All of them are the
same shape: the assistant needs one decision from a human in the middle of a run, the answer
is a click, and a human may take a minute or an hour to give it.

Holding the run open would hold a model slot, a streaming HTTP response and a cancellation
token for that whole time, and a reload would lose the question.

## Decision

- `ask_user` (`finquery.ask_user`) is one generic client-side tool: a title, an optional note,
  the rows being asked about with their own buttons, question-level buttons, and a free text
  flag. The answer comes back as `{"answers": [{"ref", "value", "text"}]}`. Every ticket that
  needs a decision uses this tool rather than adding its own.
- On the server it is a deferred tool: an `ExternalToolset` with no function, and the chat
  agent's `output_type` is `[str, DeferredToolRequests]`. A run that calls it ends with the
  call pending, so no model slot is held while the user thinks. The Vercel adapter streams the
  call as a tool part in state `input-available`.
- The browser renders the Question card, answers with `addToolOutput`, and `useChat` sends the
  next request by itself (`sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls`).
  That request carries the assistant message with the tool output instead of a new prompt.
- The chat endpoint matches the outputs it receives against the tool calls its own persisted
  history left open and passes them as `deferred_tool_results`, so the same run resumes. An
  output that matches no open call of this conversation is ignored.
- A turn that ended on a pending call is **rewritten**, not followed by a second turn
  (`persist_turn(..., replaces=...)`): the messages of both halves are dumped together, so the
  tool part carries its output and a reload renders what the stream rendered. This is also why
  the Import page can seed a first turn nobody streamed (summary plus a pending `ask_user`
  call) and have answering it resume that run.
- What the answers mean is not the tool's business. For categorization the assistant reads them
  and calls `set_rule` once per answer, which is deterministic code, so the rule and the rows
  it moves never depend on the model's arithmetic.

## Consequences

- Tickets 08, 10 and 11 add no wire protocol: they build an `AskUser` and read `AskAnswers`.
- The frontend has exactly one Question card component, which is also what makes the card look
  the same whether the server seeded it or the model asked for it.
- A retry prompt from the agent (a response with nothing but thinking) is dropped from the UI
  messages, because it would otherwise render as a user message inside the rewritten turn.
- The one-assistant-message fold now spans several model round trips per turn: a review
  conversation is one user message and one assistant message holding every card and rule step.
