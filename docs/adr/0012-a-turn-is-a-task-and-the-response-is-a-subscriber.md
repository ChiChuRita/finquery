# ADR 0012: A turn is a task the app owns, and the HTTP stream is one subscriber

Date: 2026-09-05
Status: accepted

## Context

Until ticket 33 a turn was its request. The agent run lived inside the streaming response, so
anything that closed the connection ended the run: a reload, a switch to another conversation,
a closed tab. Measured on 2026-09-05, dropping the stream four seconds into a turn left nothing
behind at all, not even the user's question (ticket 32 kept the question; the work was still
lost). For a two minute CSV import or a twenty minute statement PDF, which are the two flows the
product exists for, that is the wrong shape.

Ticket 32 had already made the turn a row that exists before the model is asked (`Turn.finished`
as an end marker, `close_open_turns` at startup). What was left was the run itself.

## Decision

- **The run is an `asyncio` task the app owns**, in a registry keyed by conversation id, one per
  conversation (`app.state.running_turns`, `api/running.RunningTurn`). A second POST for a
  conversation that is running is 409, which is also what keeps one transcript from being
  written by two runs.
- **The response is a subscriber.** The task appends every chunk it produces to the turn's
  buffer; a reader replays what is in the buffer and then follows it live (`RunningTurn.follow`).
  A client that hangs up stops reading. **Only `POST .../stop` cancels**, through the
  cancellation token it always went through.
- **`GET /api/conversations/{id}/stream` is the reattach**: the same stream from its first
  chunk, or **204** when nothing is running. It is the URL `useChat`'s own `resume` asks for
  (through the transport's `prepareReconnectToStreamRequest`), so the browser half is the SDK's
  and not ours. The wire protocol is unchanged: both endpoints encode the same chunks the same
  way, which is why the reattach needs no adapter and no request body.
- **The turn is written as it is produced**, not only when it ends: at every tool boundary and
  at most every few seconds of text, the open turn's UI messages are rewritten with the parts
  streamed so far (`chat.persist_partial`, `running.partial_parts`). Only the UI messages: half
  a run is not something to assemble a later prompt from, so the model messages are written once,
  at the end, by `persist_turn`.
- **The partial assistant message carries the id the stream names** in its `start` chunk
  (`server_message_id`). The AI SDK replaces the message it already has when a resumed stream
  names it and pushes a new one when it does not, so this is what stops a reload mid-turn from
  drawing the turn twice. The one case where no partial is written is a turn being rewritten
  from a Question card further up the transcript: its resumed half belongs to the newest message
  live, and to its own turn once it is stored.
- **`running` is a fact about the server**, reported on the conversation, the conversation list
  and the import row. The browser draws its spinners and closes its composer from that flag, so
  "this chat is busy" is true in every tab and on every page, not only in the one that pressed
  Send.

## Consequences

- A closed tab, a reload and a switch of conversation all cost nothing. Stop is the only way to
  end a turn, which is the one thing a user asked for and never got by accident.
- A process that dies mid-turn leaves the thinking, the tool steps and the paragraph it had
  written, and the next startup marks that turn interrupted (ADR 0008's neighbour, ticket 32).
- The buffer lives as long as the turn and goes with it. It is a few hundred chunks; there is
  no eviction policy and no cross-process story, because the app is one local process (ADR 0002)
  and a turn that outlives it is interrupted by definition.
- The composer is closed while a chat is answering, so the 409 is reached only by a tab that has
  not noticed yet, and it reads as one sentence (`chat.ALREADY_RUNNING`).
