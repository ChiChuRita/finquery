# 35: Dashboard with persistent charts

**What to build:** A Dashboard page per profile with the most useful charts on it, and a way to add new charts that stay. The charts on the dashboard are the same house-style TanStack charts the chat draws, and every number on them still comes from an executed, guarded query. Requested by the user on 2026-09-05 (this reverses the spec's "no dashboard page"; see the Amendments).

**Blocked by:** 06, 22, 25, 33 (merged)

**Status:** ready-for-agent

Decisions, settled:
- A `dashboard_chart` row per card: profile, position, title, shape, request (the words it was made from, may be empty for a default), plan, sql, code, language, created_from (chat tool call or dashboard), created_at, refreshed_at. The code is fixed; the SQL is re-run through the same guard on every load, so the numbers are always current and never stored.
- Defaults on first visit, created in code without a model call from fixed SQL and definitions that pass the chart self-check: spending per month for the last twelve months (line), spending by category for the last three months (doughnut, six plus rest), income against spending per month (grouped bars), top ten merchants this year (horizontal bars). Four summary tiles above them, plain numbers from guarded queries: spent this month, income this month, net this month, bookings needing review (a link to the review conversation or chat).
- Adding a chart: (a) every chart card in chat gets an "Add to dashboard" action that stores that chart's title, sql, code, plan and shape; (b) the dashboard has an "Add chart" composer line ("spending on groceries per month") that runs the chart sub-agent through the existing run_chart on the fast slot, shows the result as a card with Keep and Discard, and stores it on Keep; (c) cards can be renamed inline, removed (confirmation), moved left and right, and refreshed (re-runs the SQL); reordering by drag is not needed.
- An empty profile shows the tiles at zero and the four defaults as empty-state cards saying to import first, with the composer's drop path linked.
- Layout: responsive grid, two columns at 1024, three at 1440, the chart frame at its 280px height, cards using the same chart card component as chat minus the transcript-only parts (thumbs, Regenerate, details stay behind a toggle).

- [ ] Table, endpoints (list, create from a chat tool call, create from a request through run_chart, patch title and position, delete, refresh which re-runs the SQL), defaults created on first list for a profile
- [ ] Dashboard route in the sidebar above Transactions, tiles, grid, empty state, both themes at 1024 and 1440, following the repo's AI Elements and shadcn skills and the dataviz skill's tile and grid guidance
- [ ] "Add to dashboard" on the chat chart card, with the card saying it is on the dashboard afterwards
- [ ] Add chart on the dashboard through the sub-agent, with Keep and Discard, a running state while it is made, and the plan visible in the card details like in chat
- [ ] Every stored SQL re-runs through the same guard and profile scoping as chat; a chart whose SQL no longer runs (a deleted category) shows a readable reason on its card instead of breaking the page
- [ ] HTTP-seam tests: defaults created once per profile and profile-scoped, pin from a chat chart, add from a request with the scripted sub-agent, patch and delete, refresh re-runs and returns fresh rows, a failing SQL yields the reason; suite green; build clean; browser verification of the whole page in both themes
