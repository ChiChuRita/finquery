# 18: Retry feedback must not appear in the transcript

**What to build:** When the model ends a step with thinking only (or otherwise triggers a Pydantic AI retry such as "Please return text or call a tool"), the retry request is currently persisted with the turn and renders as a user bubble after reload. The user never wrote it. Retry prompts and other framework-generated request parts must be filtered out of the persisted UI messages and never shown, while the model history keeps them so the run itself is unchanged.

**Blocked by:** 13 Memory across chats (merged)

**Status:** done

- [x] Persisted UI messages contain only what the user wrote and what the assistant produced; retry prompts are dropped in one place in the persistence path
- [x] Live stream does not render a retry prompt as a user message either
- [x] HTTP-seam test: a scripted model that answers with thinking only on the first step and text on the retry yields one user message and one assistant message after reload
- [x] Browser verification of the reload case

## Comments

Done 2026-09-04, by the merge of ticket 07 rather than by its own change. `api/chat.py` gained
`_renderable`, which drops a request whose parts are all retry prompts with no `tool_name`, and
`persist_turn` runs every turn's messages through it before the dump. A retry that belongs to a
tool call keeps its `tool_name` and stays, because that one is the tool step's error line, not a
user bubble.

- One place: `_renderable` sits inside `persist_turn`, so the seeded review turn, a streamed turn
  and a rewritten one are all filtered by the same call.
- The live stream never carried it: the Vercel adapter streams the assistant's parts, and a
  mid-run `ModelRequest` is not one of them. Only the dump for storage ever turned it into a user
  text part.
- HTTP-seam test: `test_a_thinking_only_response_is_retried_without_a_user_bubble` in
  `tests/test_chat.py` scripts thinking only on the first step and text on the retry, then asserts
  the reloaded transcript is one user and one assistant message with no "Validation feedback"
  text anywhere in it.
- Browser verification: during the merge-07 verification the fast model really did earn a retry
  ("Please return text or call a tool.") on the groceries turn. The stored model messages of that
  turn hold the `retry-prompt` part, its stored UI messages hold only the user's own text plus the
  assistant's reasoning, tool step and answer, and the transcript rendered the same live and after
  a reload. Screenshots: /tmp/finquery-merge07/05-groceries-answer.png and 06-query-sql.png.
