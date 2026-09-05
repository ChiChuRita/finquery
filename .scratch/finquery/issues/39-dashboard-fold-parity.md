# 39: A dashboard chart re-runs with the same folds as in chat

**What to build:** The chart runner folds a stacked chart's small series into six and a doughnut's slices into five plus rest before the code pass, but the fold lives in the runner, not in the stored SQL. A chart pinned to the dashboard re-runs its SQL unfolded, so a stacked chart that showed six series in chat shows eleven on the dashboard and the palette cycles. Found by ticket 36.

**Blocked by:** 35, 36 (merged)

**Status:** done

- [x] The fold step is one shared function used by the runner and by the dashboard's load and refresh, keyed by the stored shape, so a stored chart renders exactly as it did in chat
- [x] Test at the HTTP seam: a pinned stacked chart with more than six series returns folded rows from GET /api/dashboard and after refresh
- [x] Browser check on the dashboard in both themes

## Comments

Done 2026-09-05. `uv run pytest` is 270 passed, 4 skipped (269 before; the four skips are the
usual environmental ones). `npm run build` is clean, and the frontend was not touched: the fold
is entirely behind the API, and a card's rows arrive folded the way a chat chart's rows do.

### As built

**One function, two callers.** `finquery.chart.fold.fold_rows(shape, columns, rows, language=...)`
is the whole fold: the doughnut's tail into one `Other` or `Sonstige` slice, the stacked or
grouped bar's tail into one such group per position, and a sankey's self loops dropped. It
returns the rows and the one sentence that says what happened (`Folded.note`, `None` when nothing
was folded, and then the rows are the query's own list). The three cases are keyed by the shape
and are mutually exclusive, so there is at most one note.

- `chart.runner.run_chart` calls it once, where `_drop_self_loops` and `_fold_groups` used to be:
  before the rows are judged by `data_findings` and before a line of code is written. Moving the
  doughnut's fold up to the same place changes nothing, because `data_findings` has no rule for a
  doughnut and `_honest_shape` never turns a shape into or out of one.
- `dashboard.run_card` calls it after the guard has run the stored statement, so it covers both
  `GET /api/dashboard` and `POST /api/dashboard/charts/{id}/refresh`, which share `_out`.

**The column roles are the order the query was asked for its columns in**: position, group,
figure for a crossed shape, label and figure for a doughnut, source, target and amount for a
sankey. The plan lists them in that order and `runner._euro_last` puts the euro column last
before the statement is written, so a stored statement returns them in the same order the runner
read. Nothing new is stored on `dashboard_chart`. The ceiling is written as a TODO in the
module: a statement whose SELECT order is not the plan's would make the fold a no-op (the value
column would not hold numbers), and if one ever has to be folded anyway, the roles go on the card
when it is stored and get passed in here.

**Left as it was.** The `Spending by category` default still folds in its own SQL, which it may
because that statement is ours; `run_card` folds whatever comes back anyway, so the two agree.
The dashboard does not show the fold's sentence: the card's notes are the sub-agent's repair
rounds, and the chat narrates the fold into the turn's thinking rather than into `notes`, so
adding it would have put a fold under the self-check's step in the chain of thought. The rows,
the row count and the drawing are identical to the chat's, which is what the ticket asked for.

### Tests

One new test at the HTTP seam, `test_a_pinned_stacked_chart_draws_the_rows_it_drew_in_the_chat`:
a scripted chat draws a stack over seven groups, the card is pinned from that turn, and the card
that comes back from `GET /api/dashboard` and again from `POST .../refresh` carries the same rows
object for object, six groups with `Sonstige` among them, one figure per (month, group) pair and
every euro the statement returned. It fails on `main` with eleven groups and 132 rows.
`test_every_default_draws_from_the_rows_its_own_statement_returns` still passes, so the four
defaults are unchanged by the fold on the load path.

### Verified on OpenRouter, port 8113, throwaway database, session `fq39`

A fresh profile through onboarding with "Load the sample year", then two cards stored through
`POST /api/dashboard/charts` whose statements return far more series than the palette has: a
stacked "Spending per month and merchant" (38 merchants, 309 unfolded pairs) and a doughnut
"Share of spending by merchant" (38 slices). Both draw folded on the dashboard: six series over
46 rows and six slices over 6 rows, with `Other` in each and no colour used twice. Refreshed both
from their cards, which kept the fold and wrote "Refreshed 05.09.2026, 15:33". Both themes at
1440. Zero browser console messages and no 4xx or 5xx in the server log.

Screenshots: `/tmp/finquery-39/dashboard-dark-1440.png`,
`/tmp/finquery-39/dashboard-dark-1440-refreshed.png`, `/tmp/finquery-39/dashboard-light-1440.png`.
