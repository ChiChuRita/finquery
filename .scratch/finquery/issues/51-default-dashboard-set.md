# 51: The default dashboard: tiles with deltas and six cards

**What to build:** The dashboard's default set as decided from `docs/research/charts-and-dashboard-2026-09-06.md` (Proposal A, accepted by the user on 2026-09-06): four tiles that carry a comparison, and six default cards that answer a household's questions in order (trend, income against spending, where, what changed, what is fixed, who), with a seventh, month pacing, once ticket 50 is merged. Every figure still comes from one guarded statement per card; deltas, averages and folds are arithmetic on the returned rows, like `fold_rows`.

**Blocked by:** 44, 45 (merged); 50 for the pacing card only

**Status:** done

Decisions, settled:
- Tiles: Spent, Income, Net for the newest month of the range, each with "vs last month" and "vs 6-month average" as signed deltas (euro and percent, coloured by whether the direction is good: spending down is good, income up is good, net up is good), and Needs review as today. One statement returns the last seven months; the frontend takes the last row as the month, the one before as last month, the mean of the earlier rows as the average (fewer months means the average says over how many). No sparklines in this ticket.
- Cards, in this order, created from fixed SQL and code in `dashboard.py` like today, each passing the self-check in the tests: (1) Spending per month, 12 months, `bar` (replaces the line: months are discrete, bars rest on zero, and a one-month range still reads). (2) Income against spending per month, `bar_grouped`, unchanged. (3) Top categories for the range, eight plus Other, `bar_horizontal` (replaces the doughnut). (4) This month against last month, top six categories, `bar_grouped` with `period` as the series, long rows, the shared fold keeping the six largest categories per period. (5) Regular payments: merchants seen in at least three of the last four months with a steady amount (max within 15 percent of min), average monthly amount, `bar_horizontal`, ten rows; the card's details say it is a heuristic and how it is defined. (6) Top ten merchants for the range, `bar_horizontal`, scoped by the range instead of "this year". (7) After ticket 50 lands: month pacing, cumulative spending by day of month, this month against last month, two-series `line` over `day` with `SUM() OVER`.
- The SQL sketches in the research note are the starting point; "newest booking" stays `MAX(booked_on)` over the (range-narrowed) view so the presets from ticket 44 mean the same thing on every card.
- Existing profiles: `profile.dashboard_seeded` means the old four stay where they are. Add one action in the page's overflow menu, "Restore default cards", which adds any default card the profile is missing (matched by a stable `default_key` on the card, a new nullable column via `db.NEW_COLUMNS`) without touching user-made cards. The demo starts on a fresh profile anyway.
- The doughnut stays a chat shape. No change to `shapes.py` or the runtime.
- Both themes, 1024 and 1440; the card order above is the position order; the grid stays as it is.

- [x] Tiles statement and the delta arithmetic in the frontend, with the direction colouring and the "over n months" note; empty profile still shows zeros
- [x] Six default cards in `dashboard.py` with `default_key`, all passing the self-check in `tests/test_dashboard.py` against the shipped dataset, each drawing on the sample year; the regular-payments card's details name the heuristic
- [x] "Restore default cards" in the page's overflow menu and its endpoint; adds only missing defaults; tests
- [x] After merging main once ticket 50 is in: the pacing card as the seventh default, passing the self-check with two series and a legend
- [x] `uv run pytest` green, `npm run build` clean, oxlint at baseline; headful browser verification (named session, own port above 8100, throwaway database with the sample year; the page needs no model call): the tiles with deltas, all cards drawn, the range presets changing every card, Restore default cards on a profile that had the old four, both themes; screenshots in `/tmp/finquery-51/`; Comments in the ticket 35 style

## Comments

Done 2026-09-06. `uv run pytest` is 343 passed, 4 skipped (the four are the usual environmental
ones). The count on `main` before this ticket was 334 and after merging tickets 45, 49 and 50 it
was 339; four tests are new here, one was replaced (the four defaults no longer cover four
different shapes, so their keys are what is asserted), and every count in
`tests/test_dashboard.py` now reads `len(DEFAULTS)` instead of a literal, so the eighth default
will not cost a rewrite.
`npm run build` and `npx tsc --noEmit` are clean and `oxlint` is 41 warnings, which is the
baseline on `main`.

### As built

**The tiles are one statement over seven months, and the page subtracts.** `MONEY_SQL` returns
the last `TILE_MONTHS` months of the range (`booked_on >= date(LATEST_DAY, 'start of month',
'-6 months')`), oldest first, with spent, income and net per month. The response carries them as
`tiles.months` next to the three flat figures, which are the newest row. The page takes the last
row as the month, the one before it as last month and the mean of the earlier rows as the
average, and colours each delta by whether that direction is good: spending down, income and net
up. Both figures are signed (`formatEurDelta`, `formatPercentDelta`), so the colour is a second
reading of the direction and never the only one, and the line carries the month or the months it
compared with in its `title`. A range holding fewer months says so: "vs 3-month average" under
Last 3 months, and no delta line at all under This month, where there is nothing to compare with.
An empty profile shows the four tiles at zero with no delta lines, as before.

**Six default cards, then seven.** `DEFAULTS` is the set of Proposal A in the order the household
asks its questions, each with a stable `default_key` (a new nullable column through
`db.NEW_COLUMNS`):

1. `spending_per_month`, twelve months, `bar` instead of the line. A month is a discrete period,
   a bar rests on zero by itself, and under the This month preset one bar still reads where a
   single point said nothing.
2. `income_against_spending`, `bar_grouped`, unchanged.
3. `top_categories`, the range's eight largest plus Other, `bar_horizontal` instead of the
   doughnut. It folds in its own statement, which it may because the statement is ours.
4. `month_over_month`, `bar_grouped`: the newest month against the one before it, the period as
   the series and the category as the position, so it is six category names with two bars each.
   The statement asks for its columns in the order period, category, euros, which is the order
   `fold_rows` reads the position, the group and the figure off, so ticket 39's shared fold keeps
   the five largest categories and sums the rest into one Other group per period. The statement
   itself folds nothing.
5. `regular_payments`, `bar_horizontal`, ten rows: merchants paid in at least three of the last
   four months whose largest month is within fifteen percent of its smallest, drawn as the
   average of those months. It is a heuristic and the card's Details say so in full, because we
   store no recurring flag and a bar that looks like a fact has to name the rule it came from.
6. `top_merchants`, `bar_horizontal`, scoped by the range instead of by the calendar year, so
   every preset means the same thing on every card.
7. `month_pacing`, `line` with two series (ticket 50): spending added up from the first of the
   month, `SUM(eur) OVER (PARTITION BY period ORDER BY day)`, with the day number on x so the two
   strokes lie on top of each other. Every label is kept (`thin: false`) and the tick format
   prints the first and every fifth day, because thirty-one numbers under a 280 pixel frame is a
   smudge and a day is read off its neighbours anyway.

`test_every_default_draws_from_the_rows_its_own_statement_returns` runs all seven through
`chart.selfcheck.check_chart_code` against the shipped year, so the pacing card's legend and its
two series are held to the sub-agent's own rules. Nothing in `shapes.py` or the runtime moved and
no `radius` or `cornerRadius` was written (ticket 45).

**Restore default cards.** `POST /api/dashboard/restore-defaults` adds every default whose
`default_key` is not on the profile, at the end, and returns what it added next to the whole
page. Matching is by that key and by nothing else, so a default the user renamed, moved or edited
counts as present and no card the user made is touched. A profile seeded before this ticket
carries no key on any card, which is why the seven arrive next to its old four: those four are
the user's cards now. The action sits in a new overflow menu on the page bar and says what
happened ("One default card was added at the end", "Every default card is already on this
dashboard"). `ensure_defaults` is unchanged apart from the key: a dashboard the user emptied
still stays empty, because restoring is a deliberate action and never something a load does.

### Tests

Four new at the HTTP seam in `tests/test_dashboard.py`: the seven months the deltas are computed
from (their arithmetic checked per row, and a three-month range returning three of them); the
month comparison folded to six categories with Other, one figure per pair and every euro still on
the chart; Restore adding only what is missing, at the end, leaving a renamed default alone and
adding nothing the second time; Restore on a profile whose cards carry no key, which keeps its
four and adds seven after them; and the keys themselves, unique and in the page's order. The
pacing card's two series, its ordering and its running totals are asserted inside the defaults
test, whose last assertion is that the newest stroke ends on the Spent tile's own figure.

### Verified headful on port 8171, throwaway database, session `ticket51`

A fresh profile through onboarding with "Load the sample year", then the dashboard with the four
tiles and all seven cards drawn, no model call anywhere on the page. The tiles read 2.346,34 EUR
spent (-73,80 EUR, -3 % vs last month; -72,69 EUR, -3 % vs the 6-month average, both in the
positive colour because spending fell), 2.850,00 EUR income (0,00 EUR, 0 %, muted, because the
sample year pays the same salary every month), 503,66 EUR net (+73,80 EUR, +17,2 %; +72,69 EUR,
+16,9 %) and 25 needing review. The presets narrow everything: Last 3 months leaves four bars on
the trend, eight rows on the income chart, a different merchant ranking, 8 needing review and a
label that reads "vs 3-month average" with both deltas turning red (September is in the range
from the 28th, so the average it is against is low); This month leaves one bar, 3 needing review,
no delta lines at all and "Regular payments" saying its query returns no rows, which is what a
one-month range means for a merchant seen in three of four months. Removing Regular payments and
pressing Restore default cards brought it back at the end with "One default card was added at the
end"; a second profile whose four cards had their keys cleared and whose titles were the old ones
kept those four in place and gained seven after them ("7 default cards were added at the end"),
each of them the empty-state card, because that profile holds no bookings. Both themes at 1440
and at 1024, where the delta lines wrap onto two lines rather than truncating. Zero browser
console messages, zero page errors, and 446 requests in the server log with no 4xx and no 5xx.
Screenshots: `/tmp/finquery-51/`.

### Left, seen in passing

- The chart runtime's own screenshot path was flaky for the harness, not for the app: a headed
  Chrome that has been driven for a while starts answering `Page.captureScreenshot` with a
  timeout on every page, charts or not, and closing and reopening the session fixes it. Nothing
  in the console or the server log goes with it.
- `top_categories` and `top_merchants` are both scoped by the range now, so under All they cover
  the whole history rather than the last three months and the calendar year. That is the point of
  the range, but it does mean the two cards say more than their titles do when the range is open.
- The 6-month average is over the months the range holds, so a range that starts mid-month
  averages a partial month with whole ones. The label says how many months it averaged, which is
  the honest half of it; naming the days would need a second figure the tile has no room for.
