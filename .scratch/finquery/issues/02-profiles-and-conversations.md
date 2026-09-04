# 02: Profiles and conversation management

**What to build:** A user creates, renames, switches and deletes profiles from a switcher in the sidebar. Within a profile the sidebar lists conversations with rename and delete, several conversations open as tabs across the top and each tab keeps its scroll position and draft. New conversation is one click; opening an old one and sending a message continues it. The model is chosen per conversation in the composer and can be switched mid-chat; every assistant turn shows which model wrote it. An interrupted turn stays visible as interrupted and the next message continues naturally. Suggested follow-ups appear under answers.

**Blocked by:** 01 Walking skeleton

**Status:** done

- [x] Profile CRUD over REST and a profile switcher; all conversations are profile-scoped and switching profiles changes the sidebar
- [x] Sidebar conversation list ordered by last activity with inline rename and delete with confirmation
- [x] Tabs for open conversations, persisted in local storage with scroll position and draft text per tab
- [x] Per-conversation model slot stored server-side; switching applies to the next turn; each assistant message carries and displays the model label
- [x] Interrupted turns render with a marker and the conversation continues on the next message
- [x] Follow-up suggestions rendered from a data part the agent emits at the end of a turn
- [x] HTTP-seam tests for profile isolation, conversation CRUD, model switch mid-conversation, continuation after interruption
- [x] Browser verification covering create, rename, switch, tabs, delete

## Comments

Done 2026-09-04. 16 tests, screenshots in /tmp/finquery-02/.

Endpoints added or changed:

- `GET/POST /api/profiles`, `PATCH/DELETE /api/profiles/{id}`. Duplicate name is 409, deleting
  the last profile is 409, deleting a profile takes its conversations with it.
- `GET /api/conversations?profile_id=...` (required) and `POST /api/conversations` with
  `profile_id` in the body. `PATCH /api/conversations/{id}` now takes `title` and/or
  `model_slot`. `DELETE /api/conversations/{id}` is new. `ConversationOut` carries `profile_id`.

For the next tickets:

- Assistant UI message metadata is `{model_slot, interrupted?, thinking_seconds?}`. The client
  merges every `message-metadata` chunk of a turn, so more keys can be added freely.
- Custom data parts: the turn emits `data-followups` (`{suggestions: [...]}`) from `on_complete`
  and the same part is appended to the persisted assistant message, so live and reloaded
  transcripts render from one code path. Frontend types live in `ChatDataParts` in
  `frontend/src/lib/api.ts`.
- `finquery.followups` is the first sub-agent: fast slot, plain text out, parsed to at most three
  short questions (only lines ending in a question mark survive), failures are logged and
  swallowed. `providers.subagent_settings` turns reasoning off for sub-agent runs, which took the
  post-turn step from 11 s to 3 s on OpenRouter; it is on `app.state.subagent_settings`.
- Tests: `conftest.script(answer, thought=..., followups=[...])` scripts one slot for both the
  turn and its follow-up step, and `is_followup_request` tells the two apart. The scripted model
  now answers non-streamed requests too, which is what sub-agents use.
- Browser state per profile and conversation lives in `frontend/src/lib/workspace.tsx`
  (`WorkspaceProvider`): active profile, open tabs, per-conversation draft and scroll position.
  Two traps found there: a detached scroll node reports `scrollTop` 0 (never write it on
  unmount), and anything a route effect reads from the workspace has to be identity stable or
  the effect fights the user (it re-added closed tabs and undid profile switches).

Merged into main on 2026-09-04 alongside 03 (data model, CSV import) and 16 (local provider).
Explicit profile scoping won, so `app.state.profile_id` is gone. Ticket 03's endpoints were
adapted to the same convention as conversations: `profile_id` is a required query parameter on
`GET /api/imports`, `GET /api/transactions`, `GET /api/accounts` and `GET /api/categories`, and
a required form field on `POST /api/imports`. An unknown id is 404 everywhere.
`POST /api/imports/preview` stays unscoped: it sniffs and parses without touching the database.
`POST /api/profiles` now goes through `db.create_profile`, so a profile created over REST gets
the default taxonomy too, not only the seeded one.

On the frontend everything profile-scoped reads the active profile from
`useWorkspace()` (`lib/workspace.tsx`): `importsQuery(profile?.id)` and
`commitImport(profile.id, ...)`. Tickets 04 (transactions page) and 05 (query sub-agent) must
do the same, and the query sub-agent needs the profile id passed down from the conversation
rather than read off `app.state`.
