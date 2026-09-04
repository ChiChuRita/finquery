# ADR 0004: Numbers come only from executed queries, never from the model

Date: 2026-09-04
Status: accepted

## Context

A finance assistant that guesses a figure is worse than a spreadsheet. Trust requires every
number in an answer to be reproducible and auditable.

## Decision

- Any figure the assistant states must come from a SQL query it executed against the profile's
  transactions. The system prompt forbids arithmetic in prose and tells the assistant to call the
  query tool for any number. Until the query tool exists (ticket 05) the prompt says so, and the
  assistant answers that it cannot compute numbers yet.
- Executed SQL and its rows are shown in the transcript as a collapsible tool step so the user
  can check any number.
- SQL is validated as read-only before it runs (single SELECT over the profile-scoped view,
  no writes, no attach, auto LIMIT) and the view excludes split parents.
- Ingestion follows the same rule: extracted amounts must be literally present in the source
  text (verbatim guard) and statements must reconcile before they are trusted.

## Consequences

- Answers are deterministic given the data; the model chooses the query, never the number.
- When the data cannot answer a question, the assistant says so instead of estimating.
- Tests for question answering assert the stream contains a tool part with the executed SQL
  before the text that quotes its result.
