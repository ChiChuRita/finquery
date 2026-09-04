# 18: Retry feedback must not appear in the transcript

**What to build:** When the model ends a step with thinking only (or otherwise triggers a Pydantic AI retry such as "Please return text or call a tool"), the retry request is currently persisted with the turn and renders as a user bubble after reload. The user never wrote it. Retry prompts and other framework-generated request parts must be filtered out of the persisted UI messages and never shown, while the model history keeps them so the run itself is unchanged.

**Blocked by:** 13 Memory across chats (merged)

**Status:** ready-for-agent

- [ ] Persisted UI messages contain only what the user wrote and what the assistant produced; retry prompts are dropped in one place in the persistence path
- [ ] Live stream does not render a retry prompt as a user message either
- [ ] HTTP-seam test: a scripted model that answers with thinking only on the first step and text on the retry yields one user message and one assistant message after reload
- [ ] Browser verification of the reload case
