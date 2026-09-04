# ADR 0003: One automated test seam, the FastAPI app over HTTP with scripted models

Date: 2026-09-04
Status: accepted

## Context

Tests that import internal modules and assert on their state break on every refactor and still
miss wiring bugs. Tests that call real models are slow, flaky and cost money.

## Decision

- Every automated test drives the FastAPI application in-process through
  `httpx.AsyncClient(transport=ASGITransport(app))`, with the app's lifespan run explicitly.
- Both model slots are replaced by `pydantic_ai.models.function.FunctionModel` with a stream
  function scripted per test (thinking deltas, tool calls, text). Sub-agents are scripted the same
  way. No test loads a real model or calls OpenRouter.
- Tests assert external behaviour: the SSE chunks of the chat stream (order, headers, content),
  REST responses, and what a later GET returns after a turn. They do not reach into the database
  or application state.
- The harness lives in `tests/conftest.py`: `client`, `scripts` (per-slot stream functions),
  `chat` (post a user message, parse the SSE) and `make_settings` (in-memory SQLite).
- The frontend has no unit tests. Each ticket is verified by a browser agent against the running
  app on OpenRouter, with screenshots in the report.

## Consequences

- Refactors inside the backend do not touch tests as long as the HTTP contract holds.
- Timing-dependent behaviour (Stop mid-turn) is tested by a scripted model that parks on an
  `asyncio.Event`, and the stop endpoint waits for persistence before answering.
