# 66: Sidebar margins and equal dashboard tiles (micro-ticket)

**What to build:** Two visual fixes the user saw on 2026-09-06: some margins in the new sidebar are off (uneven gaps between header, groups, footer and the rail edge, and between rows), and the dashboard tiles are no longer the same size since ticket 51 gave the three money tiles two delta lines while Needs review has one. The tiles should read as one row of equal cards, Apple style: same height, same padding, same type scale, aligned baselines; when the content differs, the shorter card keeps its height and its text sits on the same lines.

**Blocked by:** 49, 51 (merged)

**Status:** ready-for-agent

Decisions:
- Sidebar: use the shadcn Sidebar's own spacing tokens (group padding, menu item height, header and footer padding) consistently; no ad hoc margins on rows; the brand row, the New chat button, the pages group, the Recent group and the footer share one horizontal inset; the collapsed rail keeps icons centred. Check the tabs strip and the page bar align with the sidebar header height.
- Tiles: one grid with `items-stretch`, cards as flex columns with the value line and the notes area at fixed positions, Needs review getting a second line of equal height (for example "of 433 bookings" or the month) so all four cards carry label, value, two notes. Numbers keep tabular alignment where they are compared. Both themes, 1024 and 1440. No new dependency, no restructuring beyond the two areas.

- [ ] Before and after screenshots of the sidebar (expanded and rail) and the dashboard tiles, both themes, 1024 and 1440, in `/tmp/finquery-66/`
- [ ] Sidebar spacing on the component's tokens; tiles equal; `npm run build` clean; oxlint at or below 36; a short Comments note
