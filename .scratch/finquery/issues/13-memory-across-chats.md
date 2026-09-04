# 13: Memory across chats

**What to build:** Facts the user establishes in one conversation are known in every other conversation of the profile. After each assistant turn a background pass on the fast slot extracts durable facts (what a merchant is, preferences, goals). Explicit statements to remember are stored through a tool immediately. A Memory page lists all facts with edit and delete. New turns receive only the relevant memories, selected by keyword and recency, capped at five.

**Blocked by:** 02 Profiles and conversation management

**Status:** done

- [x] Memory entity with text, kind, source (explicit or distilled), created-from reference
- [x] Distillation pass after each turn with deduplication against existing memories
- [x] `remember` tool for explicit statements
- [x] Selection into the prompt with a visible "using N memories" hint in the context badge
- [x] Memory page with edit and delete
- [x] HTTP-seam tests: a fact stated in one conversation is present in the prompt of a new one, deleted memories are not, cap of five holds
- [x] Browser verification across two conversations

## Comments

Done 2026-09-04. 42 tests pass, 2 skipped. Screenshots: /tmp/finquery-13/.

Layout:

- `src/finquery/memory.py` is the whole feature: `add_memory` (writes and refuses a
  duplicate), `list_memories`, `select_memories`, `build_memory_block`, and the distillation
  sub-agent (`distill_memories`, one forced tool `remember_facts`, empty list allowed,
  `retries={"output": 0}` because nothing waits on it).
- `db.Memory`: profile_id, text, kind (rule, preference, fact), source (explicit, distilled),
  `created_from` (conversation id, `SET NULL` when that conversation is deleted), timestamps.
- `agent.py` gained `ChatDeps` (session factory, profile id, conversation id) and the first
  chat tool, `remember`. The chat agent is now `Agent[ChatDeps, str]`, so `chat.py` passes
  `deps=` to `run_stream`.
- `api/memories.py`: `GET /api/memories?profile_id=...` (required, newest first),
  `PATCH /api/memories/{id}` (`text` and/or `kind`, blank text is 422),
  `DELETE /api/memories/{id}`. No POST: memories are created by the assistant, not by hand.
- Frontend: `components/memory-page.tsx` on `/memory` with a sidebar link, inline edit
  (click the text, Enter saves, Escape cancels) and delete behind the shared `ConfirmDialog`.
  A "N memories used" chip sits next to the model chip on each answer and links to the page.

Prompt injection is one function called from one place: `build_memory_block(session,
profile_id, message)` returns `MemoryBlock(text, used)` and `chat.py` passes `text` as
`instructions=` to `run_stream`, so it lands at system level above the conversation. Selection
is keyword overlap with the user's message, recency as the tie-break, capped at five
(`MAX_MEMORIES`). A profile with fewer than five memories sends all of them, which is what
makes a fact land when the wording moved on.

New data part: `data-context` with `{"memories_used": N}`, streamed once per turn and appended
to the persisted assistant message (same code path as `data-followups`). Ticket 12 adds the
token counts to this part and can render both in the header badge; the chip in the transcript
reads the same part.

Requests per turn is now three: the chat model on the conversation's slot, then the follow-up
step and the distillation pass, both on fast, run side by side with `asyncio.gather`. Count
assertions updated in `test_conversations.py` (`scripts.resolved`) and
`test_local_provider.py` (3 -> 5 fast requests for two turns). Both post-turn steps now share
a `POST_TURN_TIMEOUT` of 30 s: during verification Gemma looped on a post-turn request and held
a finished answer open forever, so on timeout the answer persists and the suggestions are lost.
The system prompt also gained a line telling the model to answer as text after a tool returns,
because once it replied with thinking only and pydantic AI's "return text or call a tool"
feedback leaked into the visible answer.

Deduplication is a normalized text match (words only, lowercased) in `add_memory`, so a
repeated sentence never lands twice but a paraphrase does. Seen in verification: the `remember`
tool stored "PayPal payments to Anna are categorized as dinner" and the distillation pass
added "PayPal payments to Anna are always for dinner and the bill is split" from the same turn.
The Memory page is the escape hatch; the upgrade path (noted in `memory.py`) is embedding the
text and comparing by similarity.

Test harness: `conftest.script(...)` takes `memories=[...]` (what the distillation pass finds),
`distilled(*facts)` builds the forced tool call and `is_distillation_request` recognises the
step. A script that says nothing about distillation remembers nothing, so existing tests did
not have to care. `tests/test_memory.py` records the instructions each chat request received,
which is literally the prompt the model got.

For ticket 07: category rules and memories stay separate tables, and a rule statement in chat
is worth both. `CategoryRule` (pattern to category) is what recategorizes rows;
`memory.add_memory(session, profile_id, text, kind="rule", source="explicit",
created_from=conversation_id)` is what makes the assistant still know it next month in prose.
The `remember` tool is already on the chat agent with `ChatDeps`, so a `create_rule` tool can
sit next to it and call both, and its confirmation line follows the same prompt rule. Watch the
duplication: if the rule tool also remembers, the distillation pass will usually find nothing
to add, which is the intent.
