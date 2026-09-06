# 49: One dark canvas: the sidebar on the shadcn Sidebar component

**What to build:** The app shell reads as one surface. Today the content area is near-black and the sidebar is a lighter gray panel behind a hard border, with the conversation tabs strip and the page header in that same gray. The user likes the black content and the AI Elements components and does not like the two-tone shell. Grilled on 2026-09-06; decisions below are settled.

**Blocked by:** 45 (merge first; both touch the theme tokens)

**Status:** done

Decisions, settled with the user:
- One surface, hairline dividers. Sidebar, conversation tabs strip and page header bars take the same background as the content (`--background`), separated by thin borders only. Cards, the composer and popovers keep their slightly lighter surface (`--card`), so the chat keeps its look. The light theme mirrors the rule: one white canvas, hairlines and faint tints do the separation.
- The shadcn Sidebar component replaces the custom `app-sidebar.tsx` aside: `npx shadcn add sidebar` (brings sheet, tooltip, skeleton if missing) through the repo-local shadcn skill; `SidebarProvider`, `Sidebar collapsible="icon"`, `SidebarHeader`, `SidebarContent`, `SidebarGroup` for the pages and for Recent, `SidebarFooter` for Settings and the profile switcher, `SidebarRail` and `SidebarTrigger` in the page header, the keyboard shortcut the component ships, the mobile sheet replacing the current mobile drawer. Collapsed state persisted the way the component does it (cookie or localStorage) so a laptop demo can keep the rail.
- Active state is quiet: a faint tint on the active row and full-foreground text, inactive rows muted; no accent colour in the navigation. The green stays for the brand mark and the primary action (New chat, send). Active conversation tab marked the same way.
- Recent conversations keep rename and delete (the current inline rename and confirmation), shown as `SidebarMenuAction` on hover and focus; in the icon rail the Recent group collapses away and the pages show tooltips.
- Tokens: set `--sidebar` equal to `--background` in both themes and tune `--sidebar-accent` to the faint tint; `conversation-tabs.tsx` and `page.tsx` (PageBar) drop `bg-sidebar` for the canvas with a bottom hairline. No new colours.
- Both themes, 1024 and 1440 and the mobile width, before and after screenshots and contact sheets like ticket 26. No em dashes. `npm run build` clean, oxlint at baseline, suite green (the sidebar has no backend).

- [x] Before screenshots: chat with a conversation open, dashboard, transactions, settings, both themes, 1440, 1024, 390 wide
- [x] shadcn Sidebar in place with the structure above, collapsible to the icon rail, trigger in the page header, keyboard shortcut, mobile sheet; every current sidebar behaviour kept (new chat, pages, recent with rename and delete, settings, profile switcher, theme toggle)
- [x] One canvas: tokens changed, tabs strip and page bars on the canvas with hairlines, quiet active states, light theme mirrored
- [x] After screenshots of the same inventory, contact sheets, a note under Comments with what changed and why; zero console errors; build, lint and suite green

## Comments

Done 2026-09-06. `npm run build` is clean, `oxlint` is at its baseline (41 warnings on main, 41
here), `uv run pytest` is 326 passed, 4 skipped (nothing under `src/` moved). Zero console
messages and zero page errors over the whole session, no 4xx or 5xx in the server log, no chat
turn spent (the sample year loads without a model; OpenRouter on port 8149, throwaway database
under `/tmp/finquery-49/data`, headed session `ticket49`). Screenshots: `/tmp/finquery-49/before/`
(68 files) and `/tmp/finquery-49/after/` (79 files), both themes, 1440x900, 1024x768 and 390x844;
contact sheets in `/tmp/finquery-49/sheets/` (18 sheets, before left, after right, the six
variants as rows; the rail, its tooltip and the phone sheet as after-only sheets). Inventory:
chat with the sample year open (its Question card), dashboard, transactions, imports, memory,
feedback, settings, the empty chat, onboarding steps 1 and 3, the conversation menu, the inline
rename, the delete dialog, the profile menu, the icon rail on the chat and the dashboard, a rail
tooltip, the phone sheet.

### What changed, by root cause

1. **Two surfaces in one shell.** `--sidebar` was a step lighter than `--background` in both
   themes (0.205 over 0.145 dark, 0.985 over 1 light) and the tabs strip painted `bg-sidebar`
   too, so the sidebar, the strip and the page bar read as one gray frame around a black page.
   Fixed in the tokens: `--sidebar` is `var(--background)` in both themes; the strip drops
   `bg-sidebar` (its sticky New chat button now paints `bg-background` over the scrolling tabs).
   The page bar never had a surface of its own, so it needed nothing. Cards, the composer and
   popovers stay on `--card`.
2. **Loud active states.** `--sidebar-accent` was `--muted` (0.269 dark, 0.97 light), the same
   block a hovered ghost button gets, and the active tab was a bordered `bg-background` chip
   with a shadow, which on one canvas would have been invisible. Fixed in the tokens and the
   strip: `--sidebar-accent` is a faint tint of the foreground (7 percent white on dark, 4
   percent black on light), `--sidebar-accent-foreground` the full foreground, and the open tab
   takes the same tint and the full foreground with no border. Rows are `text-muted-foreground`
   until hovered or active, when the component gives them the tint and the foreground. The
   only colour left in the navigation is the brand mark and the plus of New chat.
3. **A hand-rolled aside.** `app-sidebar.tsx` was its own `aside` with its own row classes, no
   collapsed state, no phone layout (at 390 wide the sidebar kept its 256 pixels and the chat
   had 134 left; see `before/chat-dark-390.png`). Replaced with the shadcn Sidebar:
   `SidebarProvider` and `SidebarInset` in the root layout, `Sidebar collapsible="icon"`, the
   brand and New chat in `SidebarHeader` (New chat is the `outline` menu button, the one
   bordered row), the pages and Recent as `SidebarGroup`s, Settings and the profile switcher in
   `SidebarFooter`, `SidebarRail`, `SidebarTrigger` at the start of `PageBar`, of
   `DocumentPage` and of the empty chat page. The component's cookie holds the collapsed state
   and the layout reads it back on load; Cmd+B (Ctrl+B) toggles. Recent keeps the inline rename
   (`SidebarInput`) and the delete confirmation; its menu is a `SidebarMenuAction` shown on
   hover, focus and while open; the group folds away in the rail and the pages show tooltips
   there (their longer `title` waits for the expanded sidebar so the two do not stack). Under
   768 pixels the sidebar is the component's sheet and following a link closes it.
4. **A profile switcher that could not collapse.** Its trigger was a full-width ghost `Button`
   with a 24 pixel avatar, so the rail would have clipped it. The trigger is a
   `SidebarMenuButton` with the tooltip naming the profile; the menu opens to the right of the
   rail and above the expanded row. The theme toggle sits beside it, and under it in the rail.
5. **Focus rings in two colours.** `--sidebar-ring` was gray while every other control rings
   teal. Set to the app's `--ring` in both themes.
6. **Two lint warnings from what `shadcn add` brought.** `use-mobile.ts` set state inside its
   effect; it reads the width on the first render instead (a browser app has it) and the
   effect only follows changes. `ui/sidebar.tsx` exported `useSidebar` beside its components;
   the context and the hook live in `hooks/use-sidebar.ts`, which is where the app imports the
   hook from. `SIDEBAR_COOKIE_NAME` is exported (a constant export is allowed).

### Checked, and left as they are

- The chat, the AI Elements components, the cards, the composer and every popover: untouched,
  still on `--card` and `--popover`.
- `dashboard-page.tsx`, `dashboard-card.tsx`, `chart-tool.tsx` and the route definitions in
  `routes.tsx` (ticket 44 owns them); only the root layout wrapper and the empty chat page
  changed in `routes.tsx`. The dashboard's page bar took the trigger through `PageBar`.
- Onboarding has no trigger of its own: the rail, the rail edge and the shortcut still work
  there, and the flow is seen once per profile.
- The `Skeleton` primitive came with the component and is not used yet; the conversation list
  never had a loading state.
- Ticket 26's New chat button was a bordered `outline` `Button`; the outline menu button keeps
  that shape and collapses to a square in the rail.
