# FinQuery: default dashboard and sub-agent chart shapes

Research note, 2026-09-06. Reading only; nothing in the repo was changed.

## 1. What we have now

| Piece | Today | Notes |
| --- | --- | --- |
| Tiles (4) | Spent, Income, Net for the newest booking's month; Needs review count | Plain figures, no comparison to a previous period (`dashboard.py`, `dashboard-page.tsx`) |
| Default 1 | Spending per month, last 12 months, `line` | One series, `points: true` |
| Default 2 | Spending by category, last 3 months, `doughnut` | Five slices plus Other, folded in SQL and again in `run_card` |
| Default 3 | Income against spending per month, `bar_grouped` | UNION of two halves, `topic` as series |
| Default 4 | Top ten merchants this year, `bar_horizontal` | `coalesce(title, counterparty, description)` |
| Shapes (8) | line, area, bar, bar_horizontal, bar_grouped, bar_stacked, doughnut, sankey | `shapes.py`; six-colour ceiling on every series shape |
| Ticket 50 (in flight) | Optional series on `line` and `area` | Long rows (month, series, figure); fold keeps the six largest series and drops the rest |
| Ticket 44 (done 2026-09-06) | Date range with presets on the dashboard; agent-kept charts; Add line removed | Every stored statement and the tiles are narrowed through the temp view |
| Data (`transaction_view`) | booked_on, amount (EUR), amount_cents, description, counterparty, title, enrichment, category, subcategory, account, source | No balances, no budgets, no recurring flag. Net worth and budget-versus-actual are not drawable from what we store |
| Local model, chart set | Gemma 4 E4B: 48 % figure match, 73 % drawn | Per shape: line 90/90, bar_horizontal 83/83, bar 67/87, doughnut 38/12, bar_stacked 33/83, bar_grouped 17/100, area 0/50, sankey 0/67 (figure match / drawn, `bench/results/20260905T183745Z-local-fast-chart.md`) |

The benchmark row drives Proposal B.

## 2. What the market shows by default

| App | Default overview | Chart types | Why it earns its place | Source |
| --- | --- | --- | --- | --- |
| Copilot Money | Month-to-date spending line against a dotted "last month, spread evenly" pacing line; To Review; Budgets left; Upcoming recurrings; Net this month versus previous month-to-date | Cumulative line with reference line, list tiles, delta figure | Answers "am I ahead or behind last month today?" and "what is about to leave the account?" | https://help.copilot.money/en/articles/6045480-dashboard-tab-overview |
| Monarch Money | Widgets: net worth, budget, recurring, spending trend, transactions, investments; drag to reorder; Cash Flow page by category, group or merchant, monthly to yearly | Trend line, breakdown bars, recurring calendar or list | The user chooses; recurring and spending trend are on by default | https://help.monarch.com/hc/en-us/articles/360058127551-Customizing-Your-Dashboard, https://www.experian.com/blogs/ask-experian/monarch-money-review/ |
| Rocket Money | Total monthly spend versus previous months, top categories, top merchants, income versus expenses over weekly to yearly ranges, recurring list, net worth | Bars over months, ranked bars, grouped income/expense | Merchant ranking and recurring detection are its selling points | https://www.rocketmoney.com/learn/personal-finance/tracking-expenses-with-rocket-money |
| YNAB (Reflect) | Net worth, Spending Breakdown, Spending Trends, Income v Expense, Age of Money | Bar graph of totals over time; breakdown by category; month-by-month table with averages and totals | Trends are bars, not lines: discrete months. Income v Expense is a table because exact figures matter | https://support.ynab.com/en_us/spending-trends-H1inlhzAc, https://support.ynab.com/en_us/income-v-expense-Byu1BYWRq |
| Mint (archived) | Overview with net worth on top; Trends with bars or pies for spending, income, net income over custom periods; budgets | Bars, pies | Month-over-month spending was the daily use | https://www.moneycrashers.com/mint-review/ |
| Empower | Net worth column, circular budget meter, cash flow inflow/outflow for current and previous month, expenses by category and month over month | Gauge, grouped bars, category bars | Current versus previous month everywhere | https://support-personalwealth.empower.com/hc/en-us/articles/201169740-Dashboard-Overview, https://www.benzinga.com/money/empower-personal-dashboard-review-budgeting-cash-flow-planner-tested |
| Finanzguru | Monatsauswertung by category, Verträge (recognised contracts with next debit and amount), budgets | Category breakdown, contract list | Contracts are the German household's first question: what leaves every month | https://finanzguru.de/finanzwissen/finanzguru-app, https://apps.apple.com/de/app/finanzguru-konten-vertr%C3%A4ge/id1214803607 |
| Outbank | Cards: Ausgaben/Einnahmen per category (pie), tags as green/red bars, Entwicklungen (average of the last four periods); monthly, mid-month, quarterly, yearly, custom | Pie, signed bars | Period selector plus a rolling average card | https://help.outbankapp.com/de/kb/articles/wie-kann-ich-die-auswertung-in-der-outbank-app-nutzen |
| Revolut | Spent this cycle at the top, averages as bars, last period as a line, breakdown by category, merchant, country or card; week to year plus custom; bar, pie or line switch | Headline figure, bars, comparison line, breakdown | Comparison to average and to last period is the default reading | https://help.revolut.com/en-US/help/accounts/budget-and-analytics/how-can-i-see-my-spending-and-income-analytics/ |
| N26 Insights | Monthly spend by category, top categories and retailers, spending against the usual three-month average, recurring payments at a glance, Monthly Wrap-Up | Category bars, average comparison, recurring list | The three-month average is the anchor, not last month alone | https://smebanking.agency/platform/take-control-of-your-spending-with-n26-insights/, https://n26.com/en-at/blog/monthly-wrap-up |
| Apple Card / Wallet | Week, Month, Year toggle; total with a sentence "how much more or less than the previous period"; category breakdown; swipe to earlier periods | Bars per period, category list | The delta sentence is the whole insight | https://support.apple.com/en-us/102329 |
| Emma | Pie charts, cash flow timelines, spend over time, recurring payments with price-rise alerts | Pie, timeline | Subscriptions are "the quickest wins" | https://emma-app.com/features/recurring-payments, https://moneytothemasses.com/banking/emma-review-is-it-the-best-budgeting-app |
| Cleo | Spending breakdown, categories, recurring bills, chat coach | Category chart | Chat-first, like us | https://www.moneycrashers.com/cleo-review/ |
| Trade Republic | No spending analytics found; third-party tools fill the gap | | Not a reference here | https://www.finanztip.de/daily/trade-republic-so-findest-du-raus-wo-dein-geld-ueberhaupt-liegt/ |

**Patterns that recur.** (1) A headline figure with a delta against the previous period or a rolling average (Apple, Copilot, N26, Revolut, Empower, Outbank). (2) Spending over months as bars, not lines (YNAB, Apple, Revolut, Rocket, Mint). (3) A category breakdown everywhere; pies in YNAB, Emma, Outbank, ranked bars or lists elsewhere. (4) Income against spending (Copilot, Empower, Rocket, YNAB, Outbank). (5) Recurring payments with amount and next date (Monarch, Copilot, Rocket, Finanzguru, N26, Emma, Cleo). (6) Top merchants (Rocket, N26, Monarch). (7) A review queue (Copilot, us). Net worth and budgets are everywhere too; we hold neither balances nor budgets.

**What dataviz practice adds.** Stephen Few: pies only when part-to-whole is the message and slices are few; comparing parts is a bar's job; a dashboard is one screen read in a glance, so every figure needs a comparison (https://www.perceptualedge.com/articles/visual_business_intelligence/save_the_pies_for_dessert.pdf, https://www.uxmatters.com/mt/archives/2007/04/book-review-information-dashboard-design.php). "400 EUR on food" beats "17 % of spending" (https://medium.com/the-mission/to-pie-charts-3b1f57bcb34a). Small multiples with shared axes beat many overlaid lines (https://www.juiceanalytics.com/writing/better-know-visualization-small-multiples). TanStack's guide: bars for discrete periods, include zero, no dual axes (`docs/guides/choosing-a-chart.md` in the package).

## 3. Proposal A: the default dashboard

`LATEST` below is `(SELECT MAX(booked_on) FROM transaction_view)`; ticket 44's range narrows the view underneath, so "newest booking" becomes the range's end. Every candidate is one statement; deltas and averages are arithmetic on returned rows in the frontend, the same way `fold_rows` is arithmetic, never a model figure.

| # | Display | Household question | Type | Drawable today | Recommendation |
| --- | --- | --- | --- | --- | --- |
| 1 | Tiles with deltas: Spent, Income, Net, each "vs last month" and "vs 6-month average"; Needs review | Is this month normal? | Tiles with a delta line | Frontend only, no frame | **Ship.** Upgrade the four tiles |
| 2 | Spending per month, 12 months | Where is the trend going? | `bar` | Yes | **Ship.** Replace the `line` with `bar` |
| 3 | Income against spending per month | Are we living within income? | `bar_grouped` | Yes | **Ship.** Keep |
| 4 | Top categories for the range, 8 bars plus Other | Where does the money go? | `bar_horizontal` | Yes | **Ship.** Replace the doughnut |
| 5 | This month against last month, top 6 categories | What changed, and where? | `bar_grouped` | Yes | **Ship.** Add |
| 6 | Regular payments: merchants seen in 3 of the last 4 months at a steady amount | What leaves every month regardless? | `bar_horizontal` | Yes | **Ship.** Add |
| 7 | Top ten merchants for the range | Who gets the most? | `bar_horizontal` | Yes | **Ship.** Keep, scoped by range |
| 8 | Month pacing: cumulative spending by day, this month against last | Am I ahead of last month today? | `line` with series | After ticket 50 | Add later, first in line |
| 9 | Net per month, 12 months, bars above and below zero | Which months went red? | `bar` (diverging) | Yes | Not by default; the Net tile and #3 cover it |
| 10 | Spending by account | Which account carries the load? | `bar_horizontal` | Yes | Not by default; one account is the common case |

**SQL sketches.**

1. Tiles: one statement, last seven months, the frontend takes the last row as the month, the one before as last month and the mean of the earlier six as the average.
```sql
SELECT strftime('%Y-%m', booked_on) AS month,
       ROUND(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 2) AS spent_eur,
       ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) AS income_eur,
       ROUND(SUM(amount), 2) AS net_eur
FROM transaction_view
WHERE booked_on > date(LATEST, 'start of month', '-7 months')
GROUP BY month ORDER BY month
```
2. Spending per month: `MONTHLY_SQL` unchanged, code swaps `lineY`/`scalePoint` for `barY`/`scaleBand`.

4. Top categories: `CATEGORY_SQL` with `place <= 8` and the doughnut code replaced by the merchants' `barX` code, `y: 'category'`.

5. This month against last month by category (long rows, `period` is the series):
```sql
SELECT coalesce(category, 'Needs review') AS category,
       CASE WHEN strftime('%Y-%m', booked_on) = strftime('%Y-%m', LATEST)
            THEN 'This month' ELSE 'Last month' END AS period,
       ROUND(-SUM(amount), 2) AS total_eur
FROM transaction_view
WHERE amount < 0 AND booked_on >= date(LATEST, 'start of month', '-1 month')
GROUP BY category, period ORDER BY category, period
```
`run_card`'s fold keeps the six largest categories and sums the rest per period.

6. Regular payments (a heuristic, named as such in the card's details):
```sql
WITH monthly AS (
  SELECT coalesce(title, counterparty, description) AS merchant,
         strftime('%Y-%m', booked_on) AS month, -SUM(amount) AS eur
  FROM transaction_view
  WHERE amount < 0 AND booked_on > date(LATEST, 'start of month', '-4 months')
  GROUP BY merchant, month)
SELECT merchant, ROUND(AVG(eur), 2) AS monthly_eur
FROM monthly GROUP BY merchant
HAVING COUNT(*) >= 3 AND MAX(eur) <= MIN(eur) * 1.15
ORDER BY monthly_eur DESC LIMIT 10
```
8. Pacing (after ticket 50): `day_of_month`, `period`, `SUM(-amount) OVER (PARTITION BY period ORDER BY day)` as the running figure; x is the day number, `monthShort` passes a plain number through as text.

**Why the current four stay or go.**

- *Spending per month*: stays, as bars. Months are discrete periods, every reference app draws them as bars, a bar rests on zero without the line's domain rule, and under ticket 44's "This month" preset a 12-month line collapses to one point and is downgraded anyway; one bar still reads.
- *Doughnut by category*: goes. It caps at six slices while a profile seeds about fifteen categories, it reads percent where a household thinks in euros, and area comparison is the weakest encoding (Few). Ranked horizontal bars show eight categories with long German names and the same fold. If the doughnut is wanted for its look, keep it as the seventh card, not instead of the bars.
- *Income against spending*: stays. It is the one chart every app agrees on.
- *Top merchants*: stays, scoped to the range instead of "this year" so the presets mean the same thing on every card.

**The shipped set**: four tiles with deltas plus six cards (#2 to #7). Two full rows at 1440, three at 1024. #8 joins once ticket 50 is merged. Order on the page follows the questions: trend, income versus spending, where, what changed, what is fixed, who.

## 4. Proposal B: chart types for the sub-agent

A shape costs a `ShapeRule` row, a plan and a code example, self-check stubs, a frontend label and training data in the exact dialect. The local model loses about half its hit rate on any shape with a second dimension or a callback, so the bar for "add" is a real household question no existing shape answers, with code no harder than a grouped bar.

| Rank | Shape | Question | TanStack 0.16 | Small-model risk | Self-check rules needed | Recommendation |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Multi-series line and area (ticket 50) | Five stores over time; this year against last year cumulative | `lineY`/`areaY` with `color` | Medium: long rows, legend | Ceiling of six series, legend with more than one, no false "two euro columns" finding (already in the ticket) | **Monday** (in flight). Add a plan example for "cumulative this year vs last year" with `SUM() OVER` so `area` with two series covers the two-year question |
| 2 | Period comparison bars (this vs last month, this vs last year by category) | What changed, and where? | `barY` + `group()` (existing `bar_grouped`) | Medium: E4B picks the wrong shape 67 % of the time for grouped | None new. A plan example and a query hint: "two periods as the series, long rows" | **Monday.** Prompt work, not a shape |
| 3 | Diverging bars (net per month above and below zero) | Which months went red? | `barY` with negative values, implicit diverging stack | Low: same code as `bar` | Domain must include both signs (already true: zero-from-mark, nice) | **Monday.** One plan example for `bar` |
| 4 | Reference line: average, or a stated limit | Am I above my usual? (N26, Revolut, Copilot) | `ruleY` exists; needs a new global | Medium: the value must be computed from `data` in JS (`reduce`), never typed | New: `ruleY` allowed on line/bar/area only; its value must derive from `data` (static scan already refuses literals); at most one rule; tooltip untouched since rules emit no points | **Add later**, first after 50. Small contract change, big reading gain |
| 5 | Waterfall (income to categories to what is left) | How did income become the remainder? | `waterfall` transform + `barY` with `y1`/`y2`; both need new globals | High: sign conventions, ordering, one total row | New: `y1` and `y2` both set, first interval starts at zero, exactly one total, categories in row order (`thin: false`) | **Later, low priority.** The sankey already asks this question and E4B scores 0 % on it; a waterfall is more readable but is a second flow shape |
| 6 | Sparkline tiles | Trend inside the tile | Frontend `lineY` on the tiles' rows, no sub-agent | None for the model | None; not generated code | **Dashboard work**, part of Proposal A #1, not a shape |
| 7 | Small multiples (facet) | One panel per category over months | `facet` exists (child spec per group, outer shared axes) | High: nested spec in a callback, incompatible cells throw | Would need to compile each child through the check; six panels in 280 px are about 110 px tall | **Skip.** Ticket 50's six-series line covers the household case; facets do not fit the frame |
| 8 | Calendar heatmap (weekday by week) | Which days do I spend on? | `cell` with two band scales and a continuous colour scale (`colorGradientLegend`, not in globals) | High: continuous colour breaks the six-colour rule and the euro-axis rules | New axis rules, new legend kind | **Skip.** Decorative for a household; the question is rarely asked and a bar per weekday answers it |
| 9 | Bullet or budget bar | Spent against a limit | `barX` + `tickX` or `ruleX` | Low once budgets exist | Target must come from a budget row, and there is no budget table | **Skip until budgets exist**; say so in a line |
| 10 | Dumbbell or slopegraph | Same as #2, lighter ink | `link` + `dot` | High: per-row endpoints | New endpoint rules | **Skip.** Grouped bars answer it with a shape the check knows |
| 11 | Scatter or dot plot | Every booking by day and amount | `dot` exists | Medium | Euro axis, point ceiling | **Skip.** A table answers it; households do not read scatterplots |
| 12 | Treemap | Nested share, category to subcategory | `hierarchy/treemap` | High: labels at 280 px, fifteen categories, six colours | New everything | **Skip.** Area encoding, the pie's weakness with more of it |
| 13 | 100 % stacked bars | Share per month | `normalize` + `barY` | High: a percent axis breaks the euro-axis rule | New axis mode | **Skip.** Stacked bars and the doughnut already exist |

## 5. What to skip, and why

- **Net worth and balances.** We store bookings, not balances; a running sum without an opening figure is not a balance. Not drawable.
- **Budget versus actual, bullet bars, gauges.** No budget table; Empower's meter and Few's bullet graph both need a target. A backlog line, not code.
- **Doughnut as the default category card.** Stays a shape for chat (a share question is real), leaves the default set for the reasons in Proposal A.
- **Calendar heatmap, treemap, facets, scatter, 100 % stacks.** Each needs new globals and new axis or colour rules, and the benchmark says a 4B model will not hit them. None answers a household question the existing shapes plus a reference line cannot.
- **Sankey by default.** Stays a shape; E4B draws it correctly least often, and "where does income go" reads better as top categories next to income against spending.
- **Dual axes.** TanStack's guide and every source above agree.

**In one line.** Proposal A: tiles with deltas, spending as bars, ranked category bars instead of the doughnut, plus month comparison and regular payments; six cards, all drawable today. Proposal B: finish ticket 50, add prompt examples for period comparison, diverging net and cumulative two-year area (no new shapes), then `ruleY` as the one small contract change.
