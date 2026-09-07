# 74: Remove the conversation tabs strip, the sidebar is the one list

**What to build:** The user finds the tabs strip above the pages and the Recent list in the
sidebar redundant (2026-09-07): both list conversations, both navigate to the same routes, both
mark the active one the same way since ticket 49. Decision: one view, the sidebar. Remove
`ConversationTabs` from the shell and the "open tabs" concept behind it; keep what is worth
keeping, the unsent draft and the scroll position per conversation, and the memory of which
conversation a profile was last in.

**Blocked by:** 49 (done)

**Status:** open

Decisions:
- `frontend/src/routes.tsx` drops `<ConversationTabs />`; `conversation-tabs.tsx` is deleted.
  Every page gains the strip's 40px.
- `frontend/src/lib/workspace.tsx` loses the tab list (`tabsKey`, `readIds`, `edited`, `tabIds`,
  `tabs`, `openTab`, `closeTab`). It keeps: the active profile, `readDraft` and `writeDraft`,
  the scroll position helpers, `forget` (drafts and scroll of a deleted conversation), and the
  last conversation per profile (`rememberActiveTab` and `readActiveTab` renamed to
  `rememberLastConversation` and `readLastConversation`, no longer filtered by the tab list: a
  conversation that still exists on the server is worth going back to, one that does not falls
  through to the new chat page, which `routes.tsx` must handle when the query 404s).
- Callers: `routes.tsx` (`openTab` on a new conversation becomes `rememberLastConversation`),
  `imports-list.tsx` (`openTab` after an import opens a conversation: same), `app-sidebar.tsx`
  (`closeTab` on delete becomes `forget`), `profile-switcher.tsx` comment ("Each profile keeps
  its own tabs" becomes the last conversation). `composer.tsx` line 234 and `chat-view.tsx`
  lines 254 and 255 update their comments; `chat-view.tsx` keeps `min-h-0`, check the page still
  fits the viewport without the strip. `index.css` lines 94 and 148 lose the words "the tabs
  strip" and "tabs". `app-sidebar.tsx` line 114: the brand row height was tuned so it ends on
  the hairline under tabs strip plus page bar (h-10 plus h-12); with the strip gone the page bar
  alone is h-12, so re-tune per ticket 66's rule (the brand row ends on the page bar's bottom
  hairline) or state in a comment why the sidebar header keeps its height. Measure it.
- Old local storage keys `finquery-tabs:<profile>` are left alone (harmless, nothing reads them).
- No new dependency, no server change, no em dashes.

- [ ] Before and after screenshots at 1440x900 and 1024x800, both themes, of a chat page with
      two conversations in Recent and of the Dashboard, in `/tmp/finquery-74/before/` and `/after/`
- [ ] A draft typed in chat A survives switching to chat B and back through the sidebar; the
      scroll position of a long chat survives the same round trip
- [ ] Reload lands on the conversation that was open; after deleting that conversation from the
      sidebar a reload lands on the new chat page without an error
- [ ] Importing a file from the Imports page still opens its conversation
- [ ] Sidebar header and page bar alignment measured and stated in Comments
- [ ] `npm run build`, `npx tsc -b` clean, lint at or below 36 warnings, no unused export left
      in `workspace.tsx`
