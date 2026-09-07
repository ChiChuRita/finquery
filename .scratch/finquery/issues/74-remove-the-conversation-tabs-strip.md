# 74: Remove the conversation tabs strip, the sidebar is the one list

**What to build:** The user finds the tabs strip above the pages and the Recent list in the
sidebar redundant (2026-09-07): both list conversations, both navigate to the same routes, both
mark the active one the same way since ticket 49. Decision: one view, the sidebar. Remove
`ConversationTabs` from the shell and the "open tabs" concept behind it; keep what is worth
keeping, the unsent draft and the scroll position per conversation, and the memory of which
conversation a profile was last in.

**Blocked by:** 49 (done)

**Status:** done

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

- [x] Before and after screenshots at 1440x900 and 1024x800, both themes, of a chat page with
      two conversations in Recent and of the Dashboard, in `/tmp/finquery-74/before/` and `/after/`
- [x] A draft typed in chat A survives switching to chat B and back through the sidebar; the
      scroll position of a long chat survives the same round trip
- [x] Reload lands on the conversation that was open; after deleting that conversation from the
      sidebar a reload lands on the new chat page without an error
- [x] Importing a file from the Imports page still opens its conversation
- [x] Sidebar header and page bar alignment measured and stated in Comments
- [x] `npm run build`, `npx tsc -b` clean, lint at or below 36 warnings, no unused export left
      in `workspace.tsx`

## Comments

Done 2026-09-07. Verified on port 8099 with a throwaway database (`/tmp/finquery-74/verify.db`),
the sample year and the welcome chat seeded through the API (no model call), browser session
`ticket74`. `npm run build` clean, `npx tsc -b` clean, oxlint 35 warnings (36 before: the deleted
component held one).

### What changed, per file

- `routes.tsx`: `<ConversationTabs />` and its import are gone, so every page starts at the top
  of the inset. `ConversationPage` calls `rememberLastConversation` where it called `openTab`,
  and a conversation the server does not have now sends the user to the new chat page
  (`navigate({ to: '/', replace: true })`) instead of the "This chat could not be loaded" card,
  which was the dead end the removed tab list used to prevent. The card's `Link`, `Button` and
  `PlusIcon` imports went with it.
- `components/conversation-tabs.tsx`: deleted.
- `lib/workspace.tsx`: `tabsKey`, `readIds`, `edited`, `tabIds`, `tabs`, `openTab` and
  `closeTab` are gone. What is left is the active profile, `readDraft`/`writeDraft`,
  `readScrollTop`/`writeScrollTop`, `forgetConversation`, and the last conversation per profile:
  `rememberLastConversation` on the context and the exported `readLastConversation`, no longer
  filtered by anything. The storage key stays `finquery-tab:<profile>` (a comment says why) so
  browsers keep the memory they have; `finquery-tabs:<profile>` is left where it is, nothing
  reads it.
- `components/imports-list.tsx`: `openTab` after an import becomes `rememberLastConversation`.
- `components/app-sidebar.tsx`: deleting a conversation only calls `forgetConversation` now.
  Header re-tuned, see the measurement below.
- `components/profile-switcher.tsx`: `readActiveTab` becomes `readLastConversation`, and the
  comment says the profile remembers the conversation it was last in.
- `components/composer.tsx` (`DraftKeeper`) and `components/chat-view.tsx` (the `min-h-0` note,
  `useRememberedScroll`, the detached-node note): comments say chat where they said tab.
- `index.css`: the canvas comment no longer names the tabs strip, the `focus-ring` comment no
  longer names tabs.
- Outside the ticket's list, two docs pointed at the deleted file:
  `docs/explainers/01-run-ui-chat-and-conversations.md` line 82 and
  `docs/explainers/checklist.md` line 19 dropped the `ConversationTabs` reference (the first one
  also says workspace keeps the last conversation, not open tabs).

### Sidebar header against the page bar

Measured with `getBoundingClientRect` at 1440x900 on a chat page.

Before: page bar 40 to 88 under a 40px tabs strip; sidebar header 0 to 96, brand row 12 to 44,
New chat 56 to 88. So the brand row ended 4px below the strip's hairline and the header was 96,
not the 88 ticket 66's comment claims (`pt-3` and `gap-3` are 12, not 8).

After: page bar 0 to 48; sidebar header 0 to 100, brand row 16 to 48 (`pt-4`), New chat 60 to 92.
The brand row's bottom is the page bar's bottom hairline, 48 on both sides, which is ticket 66's
rule; New chat sits under that line where the page's content starts. It cannot also be centred on
the page title any more (that centre is 24 now, above the brand row), so that half of ticket 66's
tuning is gone with the strip. The rail measures the same: the brand square is 16 to 48.

### Acceptance checks in the browser

- Screenshots at 1440x900 and 1024x800, both themes, of the sample-year chat (two conversations
  in Recent) and of the Dashboard: `/tmp/finquery-74/before/` and `/tmp/finquery-74/after/`,
  `chat-<width>-<theme>.png` and `dashboard-<width>-<theme>.png`, eight files each side, plus
  `/tmp/finquery-74/after/chat-1440-light-rail.png` for the collapsed rail.
- Draft and scroll: typed "half-written question about groceries" into the sample year (never
  sent), scrolled its transcript to 266 (its maximum at that height), followed Welcome in the
  sidebar and came back: the textarea holds the draft and the scroller is back at 266.
- Reload: a reload of `/c/<sample year>` lands on the same chat, and `finquery-tab:<profile>`
  holds its id. After deleting it from the sidebar, opening `/c/<that id>` again lands on `/`
  with no `role="alert"` and no "could not be loaded" text, and the draft and scroll keys for it
  are gone. Note this profile's `onboarding_state` was still `not_started`, so `/` first bounced
  to `/onboarding?step=1` (existing behaviour, nothing to do with the strip); with the state set
  to `done` the same URL lands on the new chat page with its composer.
- Imports: "Continue in chat" on the Imports page opens the import's conversation and writes it
  as the profile's last one.
- Last conversation across profiles: with Default in Welcome, switching to a second profile and
  back lands on Welcome again, now with no tab list in the way.
- The chat page still fits the viewport without the strip: `documentElement.scrollHeight` is 900
  at 1440x900, and the composer is on screen at 1024x800.
