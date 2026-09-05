# ADR 0004: Numbers come only from executed queries, never from the model

Date: 2026-09-04
Status: accepted

## Context

A finance assistant that guesses a figure is worse than a spreadsheet. Trust requires every
number in an answer to be reproducible and auditable.

## Decision

- Any figure the assistant states must come from a SQL query it executed against the profile's
  transactions. The system prompt forbids arithmetic in prose and tells the assistant to call the
  `query` tool for any number, so a question it cannot query is answered without a figure.
- Executed SQL and its rows are shown in the transcript as a collapsible tool step so the user
  can check any number.
- SQL is validated as read-only before it runs (`finquery.query.guard`): sqlglot parses it, one
  SELECT over `transaction_view` is admitted, a schema prefix, another relation, a write, an
  attach, a pragma and a file-system function are refused, and a LIMIT of at most 200 is
  applied. The view excludes split parents.
- Profile scoping is not a predicate the generated SQL could widen. The executing connection
  gets a temp view named `transaction_view` that is already filtered to the profile: SQLite
  resolves the unqualified name in the temp schema first, the guard refuses a qualified one, and
  `PRAGMA query_only` makes the connection reject writes whatever the guard let through.
- A guard or SQLite error goes back to the query sub-agent once, with the refused statement and
  the reason. A second failure is reported to the chat agent as an error instead of a number.
- Two rules judge what the SQL means, not only what it touches. A `CASE` over the booking text
  that returns a label of its own invents a categorization and is refused (ticket 22). A
  statement with more than eight `LIKE` terms over the booking text is refused too (ticket 17):
  asked about a person it could not find, the local fast model matched every merchant it had
  been shown and returned the household's whole spending as the answer. The reason it gets
  back says to match the one name the question carries and to return no rows when nothing
  carries it.
- The tool result carries the rows numeric for the transcript's table and, next to them,
  `figures`: the same rows as lines with every euro column written the German way, so the
  figure the answer quotes is copied, never reformatted by the model.
- Ingestion follows the same rule: extracted amounts must be literally present in the source
  text (verbatim guard) and statements must reconcile before they are trusted.

## Consequences

- Answers are deterministic given the data; the model chooses the query, never the number.
- When the data cannot answer a question, the assistant says so instead of estimating.
- Tests for question answering assert the stream contains a tool part with the executed SQL
  before the text that quotes its result.
