# 13: Memory across chats

**What to build:** Facts the user establishes in one conversation are known in every other conversation of the profile. After each assistant turn a background pass on the fast slot extracts durable facts (what a merchant is, preferences, goals). Explicit statements to remember are stored through a tool immediately. A Memory page lists all facts with edit and delete. New turns receive only the relevant memories, selected by keyword and recency, capped at five.

**Blocked by:** 02 Profiles and conversation management

**Status:** ready-for-agent

- [ ] Memory entity with text, kind, source (explicit or distilled), created-from reference
- [ ] Distillation pass after each turn with deduplication against existing memories
- [ ] `remember` tool for explicit statements
- [ ] Selection into the prompt with a visible "using N memories" hint in the context badge
- [ ] Memory page with edit and delete
- [ ] HTTP-seam tests: a fact stated in one conversation is present in the prompt of a new one, deleted memories are not, cap of five holds
- [ ] Browser verification across two conversations
