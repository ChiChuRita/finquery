# 35: Dashboard with persistent charts

**What to build:** A Dashboard page per profile with the most useful charts on it, and a way to add new charts that stay. The charts on the dashboard are the same house-style TanStack charts the chat draws, and every number on them still comes from an executed, guarded query. Requested by the user on 2026-09-05 (this reverses the spec's "no dashboard page"; see the Amendments).

**Blocked by:** 06, 22, 25, 33 (merged)

**Status:** done

Decisions, settled:
- A `dashboard_chart` row per card: profile, position, title, shape, request (the words it was made from, may be empty for a default), plan, sql, code, language, created_from (chat tool call or dashboard), created_at, refreshed_at. The code is fixed; the SQL is re-run through the same guard on every load, so the numbers are always current and never stored.
- Defaults on first visit, created in code without a model call from fixed SQL and definitions that pass the chart self-check: spending per month for the last twelve months (line), spending by category for the last three months (doughnut, six plus rest), income against spending per month (grouped bars), top ten merchants this year (horizontal bars). Four summary tiles above them, plain numbers from guarded queries: spent this month, income this month, net this month, bookings needing review (a link to the review conversation or chat).
- Adding a chart: (a) every chart card in chat gets an "Add to dashboard" action that stores that chart's title, sql, code, plan and shape; (b) the dashboard has an "Add chart" composer line ("spending on groceries per month") that runs the chart sub-agent through the existing run_chart on the fast slot, shows the result as a card with Keep and Discard, and stores it on Keep; (c) cards can be renamed inline, removed (confirmation), moved left and right, and refreshed (re-runs the SQL); reordering by drag is not needed.
- An empty profile shows the tiles at zero and the four defaults as empty-state cards saying to import first, with the composer's drop path linked.
- Layout: responsive grid, two columns at 1024, three at 1440, the chart frame at its 280px height, cards using the same chart card component as chat minus the transcript-only parts (thumbs, Regenerate, details stay behind a toggle).

- [x] Table, endpoints (list, create from a chat tool call, create from a request through run_chart, patch title and position, delete, refresh which re-runs the SQL), defaults created on first list for a profile
- [x] Dashboard route in the sidebar above Transactions, tiles, grid, empty state, both themes at 1024 and 1440, following the repo's AI Elements and shadcn skills and the dataviz skill's tile and grid guidance
- [x] "Add to dashboard" on the chat chart card, with the card saying it is on the dashboard afterwards
- [x] Add chart on the dashboard through the sub-agent, with Keep and Discard, a running state while it is made, and the plan visible in the card details like in chat
- [x] Every stored SQL re-runs through the same guard and profile scoping as chat; a chart whose SQL no longer runs (a deleted category) shows a readable reason on its card instead of breaking the page
- [x] HTTP-seam tests: defaults created once per profile and profile-scoped, pin from a chat chart, add from a request with the scripted sub-agent, patch and delete, refresh re-runs and returns fresh rows, a failing SQL yields the reason; suite green; build clean; browser verification of the whole page in both themes

## Comments

Done 2026-09-05. `uv run pytest` is 269 passed, 4 skipped (the four are environmental: the two
private Trade Republic fixtures, the private statement PDF and the opt-in local smoke suite);
256 before. `npx tsc --noEmit` and `npm run build` are clean; `oxlint` is 40 warnings against a
baseline of 38, the two new ones being the `only-export-components` warning that every file
exporting a helper next to a component already earns (`query-result.tsx` has it too), for
`SHAPE_LABELS` and `failureLine` now being read by the dashboard card.

### As built

**A card stores a drawing, never a figure.** `dashboard_chart` holds profile, position, title,
shape, language, request, plan, sql, code, notes, created_from (`default`, `chat` or
`dashboard`), the turn and tool call it was pinned from, created_at and refreshed_at. A whole new
table needs no `NEW_COLUMNS` entry; the one column that was added to an existing table has one:
`profile.dashboard_seeded`, which is why a dashboard the user emptied stays empty instead of
growing its four defaults back on the next visit.

**Every load is a query.** `dashboard.run_card` sends each stored statement through
`validate_sql` and `execute_read_only` with the card's own profile, which is the same guard, the
same temp view and the same `PRAGMA query_only` a question in the chat gets (ADR 0004). Nothing
about a card is cached, so `GET /api/dashboard` is the page: the tiles, and every card with the
rows its statement returns right now.

**Endpoints** (`src/finquery/api/dashboard.py`):

- `GET /dashboard` - the tiles and every card, seeding the four defaults on the first visit
- `GET /dashboard/pins` - the tool call ids that are on the dashboard, so a chart card in a
  transcript still says "On the dashboard" after a reload. One cheap query, shared by every card
  in the chat through one react-query key
- `POST /dashboard/charts/from-turn` - pin a chart drawn in a chat, by turn and tool call id.
  Idempotent: a second Add finds the card it already made
- `POST /dashboard/charts/preview` - run `run_chart` for a request and store nothing
- `POST /dashboard/charts` - keep what the preview drew
- `PATCH /dashboard/charts/{id}` - rename, move, or both. A move renumbers the rest, so the
  order stays dense
- `DELETE /dashboard/charts/{id}` and `POST /dashboard/charts/{id}/refresh`

Every one of them is profile-scoped by id; another profile's card is a 404, and a statement the
guard would refuse is a 422 before it is ever stored.

**The four defaults are code, and a test holds them to the same rules as the sub-agent's
output.** `finquery.dashboard` has the statement and the definition of each of the four, written
against `docs/chart-runtime.md`.
`test_every_default_draws_from_the_rows_its_own_statement_returns` imports the shipped year,
gives the bookings categories, runs each card's statement through the guard and then its code
through `chart.selfcheck.check_chart_code` with those real rows, asserting no finding. A rule
that changes in the self-check therefore fails here rather than leaving the four behind.

**Now is the newest booking, not today.** The tiles and the twelve-month charts read the month
from `MAX(booked_on)`, because the shipped year is 2025 and a dashboard of four empty charts says
nothing about a household that imported in January. The tiles name the month they are about
("December 2025") so the figure is never read as this calendar month.

**The doughnut folds in SQL**, not in the runner: the rows are re-read on every load, so a
household that gains a category between two visits would otherwise hand a six-colour palette
seven slices. `ROW_NUMBER()` keeps the largest five and sums the rest into `Other`.

**Three states per card, all readable.** Drawn; "The query behind this chart returns no rows
right now", which is what a deleted category produces for a chart that filtered on it; and the
guard's or SQLite's own sentence for a statement that cannot run at all. The frame is never
handed an empty array, because a mark over no rows throws.

**Reuse, not a fork.** `chart-tool.tsx` now exports `ChartFrame`, `Footer`, `ChartCard`,
`ChartCardHeader`, `failureLine` and `SHAPE_LABELS`; `ChartToolOutput` was split so its details
half (`ChartDetails`) is what the footer and the chain of thought take. The dashboard card is
those pieces plus its own header actions, so the runtime, the message protocol and the details
toggle have one implementation.

**One bug found and fixed on the way.** A browser reloads an iframe whose element is re-inserted
into the DOM, which is exactly what moving a card does. `ChartFrame` had a `ready` flag, so the
reloaded frame waited for a render message that never came and showed its own white surface. It
now counts the reasons to post (`hello` and every `load`) and re-sends, and says "Drawing..."
while a reloaded frame is blank.

### Tests

Thirteen new in `tests/test_dashboard.py`, all at the HTTP seam: the defaults created once and
staying removed, a dashboard per profile with another profile's card a 404, every default drawn
and checked against the rows its statement returns, the tiles as the newest month of the data, an
empty profile at zero with four rowless cards, a chart pinned from a scripted chat turn (twice,
finding the same card), a preview that stores nothing and a Keep that does, rename and move with
the positions renumbered, refresh returning smaller figures after twenty bookings were deleted, a
stored statement that no longer runs reported on its own card with the rest of the page unharmed,
a statement the guard refuses never stored, and a chart that was never drawn refused for pinning.

### Verified on OpenRouter, port 8109, throwaway database, session `dashboard`

A fresh profile through onboarding with "Load the sample year" (433 rows, 25 needing review),
then: the Dashboard with four tiles carrying real figures (2.346,34 EUR spent, 2.850,00 EUR
income, 503,66 EUR net, 25 needing review, December 2025) and the four defaults drawn (`01`,
`02`); a chart asked for in the chat and added with "Add to dashboard" (`03`, `04`), which shows
up as the fifth card (`05`); "spending on groceries per month" typed into the page, its running
card showing the same chain of thought a chat shows (`06`), the drawn card with Keep, Discard and
the plan under Details (`07`), kept (`08`); renamed (`09`, `10`), moved left and right (`11`),
refreshed with "Refreshed 05.09.2026, 14:15" on the card (`12`), removed through its confirmation
(`13`, `14`); the Groceries category deleted in Settings, after which the doughnut and the pinned
chat chart redraw with a "Needs review" bucket and the groceries card says its query returns no
rows (`15`); a card whose statement names a column that is gone, stored with curl, showing the
guard path's sentence (`16`); both themes at 1440 (`17`, `18`, `24`) and at 1024 (`19`, `20`,
`21`); a second, empty profile's dashboard with the tiles at zero and four cards saying to drop a
statement into a chat (`22`); and the chat card still reading "On the dashboard" after a profile
switch and a reload (`23`). Zero browser console messages and no 4xx or 5xx in the server log for
the whole session. Screenshots: `/tmp/finquery-35/`.

### For the demo script

`docs/demo-script.md` should open on the Dashboard rather than on an empty chat: after the sample
year is imported, the four tiles and the four charts are the fastest picture of what the product
does, and they cost no model call. Then, after the chart step in the chat, press "Add to
dashboard" and come back to the page to show it there, and type "spending on groceries per month"
into the Add line to show the sub-agent making a card in about thirty seconds. The line worth
saying out loud is that nothing on the page is stored: every figure was queried through the same
guard on load, which is why deleting a category in Settings changes what the cards draw.

### Left, seen in passing

- A dialog or a dropdown over a chart looks transparent in a CDP screenshot: the runtime frame is
  a sandboxed, opaque-origin document, so it is an out-of-process iframe and the screenshot
  compositor paints it over the overlay. The real browser stacks it correctly and the dialog's
  buttons take the clicks, which is how the removal was driven.
- `eurShort` writes 5000 EUR without a thousands separator and 10.000 EUR with one, which shows
  up on the merchants axis. It is the existing formatter, unchanged by this ticket.
