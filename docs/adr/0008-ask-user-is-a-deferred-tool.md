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
- The browser renders the Question card and **answers it explicitly**: `chat-view.answerCard`
  puts the output on the message the card is on and sends that one message. The SDK's own pair
  is not used, and the reason is in ticket 29: `addToolOutput` writes to the newest assistant
  message whatever call id it is given, and `sendAutomaticallyWhen` only ever looks at the
  newest message, so a card the user came back to after typing something else swallowed its own
  answer and sent nothing at all.
- The chat endpoint matches the outputs it receives against the tool calls its own persisted
  history left open, **in any turn**, and passes them as `deferred_tool_results`, so the same
  run resumes. A request whose outputs match no open call is refused with 409 rather than read
  as a new prompt: it is a second browser tab answering a card that is already applied.
- A turn that ended on a pending call is **rewritten in place**, not followed by a second turn
  (`persist_turn(..., replaces=...)`): the messages of both halves are dumped together, so the
  tool part carries its output and a reload renders what the stream rendered. It keeps its
  position, so a card answered after a newer message stays where the user saw it. This is also
  why the Import page can seed a first turn nobody streamed (summary plus a pending `ask_user`
  call) and have answering it resume that run.
- **The prompt for a resumed run ends where that turn ended.** pydantic AI looks for the
  pending call on the last response of the history it is given, so the turns the user added in
  between are left out of that one run: they stay in the transcript and in every later prompt.
  For the same reason the rolling summary is read one turn short of the card, or a long enough
  detour would summarize the pending call out of its own run (ADR 0007), and nothing is
  compressed on that run: it is not the resumed run's business to move a marker the rest of the
  conversation is assembled from.
- What the answers mean is not the wire format's business, and it is not the model's either.
  The card carries an `apply` hint (`{"kind": "category_rule"}` today) and
  `finquery.answers` acts on the answers in code between the two halves of the run: for
  categorization that is one `set_rule` per answer. What it did goes back as the `applied`
  line of the tool result, so the model summarizes rather than sequences. Asking the fast
  model to make those calls itself is what looped for 145 seconds and stored nothing in the
  review of 2026-09-04. Tickets 08 and 10 add a kind and an applier, not a wire change.

## Consequences

- Tickets 08, 10 and 11 add no wire protocol: they build an `AskUser` and read `AskAnswers`.
- The frontend has exactly one Question card component, which is also what makes the card look
  the same whether the server seeded it or the model asked for it.
- A retry prompt from the agent (a response with nothing but thinking) is dropped from the UI
  messages, because it would otherwise render as a user message inside the rewritten turn.
- The one-assistant-message fold now spans several model round trips per turn: a review
  conversation is one user message and one assistant message holding every card and rule step.
