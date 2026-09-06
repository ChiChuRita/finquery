# ADR 0001: Pydantic AI plus the Vercel AI SDK adapter as the chat wire

Date: 2026-09-04
Status: accepted

## Context

The chat needs streamed thinking, text, tool calls and custom cards (charts, question cards,
changesets, import progress) between one Python process and a React frontend. Writing our own
event protocol and React rendering for all of these would be the biggest single chunk of work in
the project and none of it is a course elective.

## Decision

- Pydantic AI is the agent framework: model abstraction, tool dispatch, message history types
  (`ModelMessagesTypeAdapter` for persistence) and cancellation tokens.
- The wire protocol is the Vercel AI SDK UI message stream, produced by
  `pydantic_ai.ui.vercel_ai.VercelAIAdapter` with `sdk_version=7`. The frontend uses `useChat`
  from `@ai-sdk/react` with `DefaultChatTransport`.
- The server owns the history. `useChat` sends only the newest message
  (`prepareSendMessagesRequest`), and the chat endpoint trims the request to the last message
  anyway before appending it to the persisted history.
- Thinking maps to reasoning parts, tool calls to tool parts, everything custom travels as named
  data parts (`data-*`). Turn-level facts (interrupted, thinking duration) travel as message
  metadata and are stored on the assistant UI message.
- The endpoint uses `VercelAIAdapter.from_request` plus `run_stream` rather than
  `dispatch_request`, so the request messages can be trimmed and a per-conversation cancellation
  token registered. Since ticket 33 that stream is consumed by a task rather than by the
  response, and both the chat endpoint and the reattach endpoint encode the chunks themselves
  (one line, the adapter's own `encode_event`) because a reattaching client sends no request for
  an adapter to be built from. See ADR 0012.

## Consequences

- AI Elements components render the stream with no glue code of our own.
- Each turn is persisted twice: Pydantic AI messages (what the model sees) and UI messages (what
  the transcript renders). They are derived from the same run, UI messages through
  `VercelAIAdapter.dump_messages`.
- The course rule that no library may implement an elective holds: sub-agents, compression,
  memory and web search are our code; Pydantic AI only carries the stream. Preference
  optimisation was in that list until 2026-09-06, when the feature was removed (ticket 59,
  `docs/explainers/14-elective-preference-optimization.md`).
