# 49: One dark canvas: the sidebar on the shadcn Sidebar component

**What to build:** The app shell reads as one surface. Today the content area is near-black and the sidebar is a lighter gray panel behind a hard border, with the conversation tabs strip and the page header in that same gray. The user likes the black content and the AI Elements components and does not like the two-tone shell. Grilled on 2026-09-06; decisions below are settled.

**Blocked by:** 45 (merge first; both touch the theme tokens)

**Status:** ready-for-agent

Decisions, settled with the user:
- One surface, hairline dividers. Sidebar, conversation tabs strip and page header bars take the same background as the content (`--background`), separated by thin borders only. Cards, the composer and popovers keep their slightly lighter surface (`--card`), so the chat keeps its look. The light theme mirrors the rule: one white canvas, hairlines and faint tints do the separation.
- The shadcn Sidebar component replaces the custom `app-sidebar.tsx` aside: `npx shadcn add sidebar` (brings sheet, tooltip, skeleton if missing) through the repo-local shadcn skill; `SidebarProvider`, `Sidebar collapsible="icon"`, `SidebarHeader`, `SidebarContent`, `SidebarGroup` for the pages and for Recent, `SidebarFooter` for Settings and the profile switcher, `SidebarRail` and `SidebarTrigger` in the page header, the keyboard shortcut the component ships, the mobile sheet replacing the current mobile drawer. Collapsed state persisted the way the component does it (cookie or localStorage) so a laptop demo can keep the rail.
- Active state is quiet: a faint tint on the active row and full-foreground text, inactive rows muted; no accent colour in the navigation. The green stays for the brand mark and the primary action (New chat, send). Active conversation tab marked the same way.
- Recent conversations keep rename and delete (the current inline rename and confirmation), shown as `SidebarMenuAction` on hover and focus; in the icon rail the Recent group collapses away and the pages show tooltips.
- Tokens: set `--sidebar` equal to `--background` in both themes and tune `--sidebar-accent` to the faint tint; `conversation-tabs.tsx` and `page.tsx` (PageBar) drop `bg-sidebar` for the canvas with a bottom hairline. No new colours.
- Both themes, 1024 and 1440 and the mobile width, before and after screenshots and contact sheets like ticket 26. No em dashes. `npm run build` clean, oxlint at baseline, suite green (the sidebar has no backend).

- [ ] Before screenshots: chat with a conversation open, dashboard, transactions, settings, both themes, 1440, 1024, 390 wide
- [ ] shadcn Sidebar in place with the structure above, collapsible to the icon rail, trigger in the page header, keyboard shortcut, mobile sheet; every current sidebar behaviour kept (new chat, pages, recent with rename and delete, settings, profile switcher, theme toggle)
- [ ] One canvas: tokens changed, tabs strip and page bars on the canvas with hairlines, quiet active states, light theme mirrored
- [ ] After screenshots of the same inventory, contact sheets, a note under Comments with what changed and why; zero console errors; build, lint and suite green
