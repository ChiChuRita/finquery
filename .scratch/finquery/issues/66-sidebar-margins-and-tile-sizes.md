# 66: Sidebar margins and equal dashboard tiles (micro-ticket)

**What to build:** Two visual fixes the user saw on 2026-09-06: some margins in the new sidebar are off (uneven gaps between header, groups, footer and the rail edge, and between rows), and the dashboard tiles are no longer the same size since ticket 51 gave the three money tiles two delta lines while Needs review has one. The tiles should read as one row of equal cards, Apple style: same height, same padding, same type scale, aligned baselines; when the content differs, the shorter card keeps its height and its text sits on the same lines.

**Blocked by:** 49, 51 (merged)

**Status:** done

Decisions:
- Sidebar: use the shadcn Sidebar's own spacing tokens (group padding, menu item height, header and footer padding) consistently; no ad hoc margins on rows; the brand row, the New chat button, the pages group, the Recent group and the footer share one horizontal inset; the collapsed rail keeps icons centred. Check the tabs strip and the page bar align with the sidebar header height.
- Tiles: one grid with `items-stretch`, cards as flex columns with the value line and the notes area at fixed positions, Needs review getting a second line of equal height (for example "of 433 bookings" or the month) so all four cards carry label, value, two notes. Numbers keep tabular alignment where they are compared. Both themes, 1024 and 1440. No new dependency, no restructuring beyond the two areas.

- [x] Before and after screenshots of the sidebar (expanded and rail) and the dashboard tiles, both themes, 1024 and 1440, in `/tmp/finquery-66/`
- [x] Sidebar spacing on the component's tokens; tiles equal; `npm run build` clean; oxlint at or below 36; a short Comments note

## Comments

Done 2026-09-06. `npm run build` is clean, `oxlint` is 36 warnings (the baseline named on this
ticket), no suite run because nothing under `src/` moved. Verified headful on port 8166 with a
throwaway database and the sample year loaded through onboarding (no model call), session
`ticket66`. Screenshots in `/tmp/finquery-66/before/` and `/tmp/finquery-66/after/`: chat (the
sidebar expanded, with a conversation in Recent) and dashboard, expanded and as the rail, both
themes, 1440x900 and 1024x768, sixteen files each side, same names.

### What was off, and what changed

1. **The sidebar header was 104px against 88px of tabs strip and page bar.** The brand row was
   `size="lg"` (h-12) over an h-8 New chat, so nothing on the two sides of the hairline lined up.
   The brand row is now `h-8 p-0` on the `lg` variant (which keeps the rail's unpadded square for
   the 32px mark): header padding 8, row 32, gap 8, row 32, padding 8 is 88. The brand row ends
   on the tabs strip's bottom hairline and New chat is centred on the page title. `page.tsx` and
   `conversation-tabs.tsx` needed nothing.
2. **The footer had its own layout.** Settings was a menu row; under it a plain `div` held the
   profile switcher (`flex-1`) and the theme toggle, a 28px ghost `Button`, with the footer's
   `gap-2` between them and `gap-1` inside. In the rail that was a 32, 8, 32, 4, 28 stack next to
   the pages' 32, 0, 32. The footer is one `SidebarMenu` of three `SidebarMenuButton` rows,
   Settings, the theme ("Light theme" or "Dark theme", the one it switches to, with the tooltip
   in the rail) and the profile: the same height, inset and gap as the pages, three equal squares
   in the rail. `theme-toggle.tsx` had no other caller and is deleted; the profile switcher lost
   its `flex-1`.
3. **The empty Recent text was centred with `py-6`.** It is a row now: `h-8`, `px-2`, left, on
   the inset the first conversation will take.
4. **Tiles: three had five lines, one had three, and the corners differed from the cards.** The
   `Tile` is a flex column with four slots at fixed positions, label, value, period and a block of
   two caption lines (`children`), on the app's `text-2xs` token instead of `text-[11px]
   leading-tight`, and `rounded-lg` like `ChartCard`; the grid says `items-stretch`. Needs review
   carries the range's days as its period (`01.01.2025 to 28.12.2025` through `formatDate`,
   because the count is over the range and not the newest month), then "Bookings without a
   category" and the "Answer them in a chat" link; "Set them in Transactions" when the bookings
   came without an import, "Every booking has a category" at zero. Delta figures are
   `tabular-nums` so the two lines of one tile line up; the value keeps the font's own figures
   (ticket 51).

### Seen at 1024, left as it is

With the sidebar expanded the tiles are 166px wide: the delta lines wrap as they did in ticket
51, and the Needs review period and first line wrap too, so the four cards are equal in height
but their lower lines are not on the same rows. With the rail they are (only Net's second delta
wraps). Below `lg` the grid is two by two, unchanged.
