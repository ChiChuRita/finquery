# 69: Transactions table: what the visual review left open

**What to build:** Smaller things seen during the review of ticket 68 and not changed there.
Each one a judgement call, so one ticket, decide per item.

**Blocked by:** 68 (done)

**Status:** open

Seen on 2026-09-07, 1440x900 and 1024x800, both themes, sample year loaded:

1. **Subcategory clips at 1440.** "Cash withdrawal" and "Public transport" show as
   "Cash withdr…" and "Public trans…" because Category, Subcategory and Account share the
   remaining width at 1fr each. Either give Subcategory `minmax(9rem, 1fr)` or let Description
   give up some of its 1.6fr. Check 1024 keeps the "Scroll for more columns" behaviour.
2. **Recategorize reads as a dead button.** In the selection bar it is disabled until a target
   is picked in "Move them to…", which is right, but a grey button next to a live Delete looks
   broken. Options: hide it until a target is chosen, or make the select itself the action
   (choosing a category opens the confirm dialog). Pick one.
3. **Header checkbox has no visible column title.** Fine for sighted users, but the accessible
   name is only on the checkbox. Confirm with a screen reader pass or leave.
4. **The split editor's help text is two lines of prose.** "Queries and charts count the legs of
   a split, never the transaction itself. This transaction is one booking in one category. Add a
   leg to spread it over several." Could be one line plus the button. Copy only.
5. **The theme row in the sidebar keeps its focus ring after a click.** Visible in every
   screenshot taken after switching the theme. Check the `SidebarMenuButton` focus-visible
   handling; it may be a browser focus-after-click and not ours.

Rules for whoever takes this: implementation through an Opus sub-agent, verification headful on
a port the agent owns (never 8000 or 5173), throwaway database, named browser session, before
and after screenshots under `/tmp/finquery-69/`, no new dependency.
