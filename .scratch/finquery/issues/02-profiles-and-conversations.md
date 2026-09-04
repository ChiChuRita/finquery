# 02: Profiles and conversation management

**What to build:** A user creates, renames, switches and deletes profiles from a switcher in the sidebar. Within a profile the sidebar lists conversations with rename and delete, several conversations open as tabs across the top and each tab keeps its scroll position and draft. New conversation is one click; opening an old one and sending a message continues it. The model is chosen per conversation in the composer and can be switched mid-chat; every assistant turn shows which model wrote it. An interrupted turn stays visible as interrupted and the next message continues naturally. Suggested follow-ups appear under answers.

**Blocked by:** 01 Walking skeleton

**Status:** ready-for-agent

- [ ] Profile CRUD over REST and a profile switcher; all conversations are profile-scoped and switching profiles changes the sidebar
- [ ] Sidebar conversation list ordered by last activity with inline rename and delete with confirmation
- [ ] Tabs for open conversations, persisted in local storage with scroll position and draft text per tab
- [ ] Per-conversation model slot stored server-side; switching applies to the next turn; each assistant message carries and displays the model label
- [ ] Interrupted turns render with a marker and the conversation continues on the next message
- [ ] Follow-up suggestions rendered from a data part the agent emits at the end of a turn
- [ ] HTTP-seam tests for profile isolation, conversation CRUD, model switch mid-conversation, continuation after interruption
- [ ] Browser verification covering create, rename, switch, tabs, delete
