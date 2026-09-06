# 52: Worked examples for the chart sub-agent, and a reference line

**What to build:** Proposal B of `docs/research/charts-and-dashboard-2026-09-06.md`, accepted by the user on 2026-09-06. No new shape family beyond ticket 50. Three worked examples teach the existing shapes the household questions they were failing: this month against last month by category (grouped bars with the period as the series), net per month above and below zero (diverging bars), and cumulative spending this year against last year (a two-series area after ticket 50). One small contract change: a reference line, `ruleY`, for "am I above my usual" questions, whose value is computed from the rows in the code, never typed.

**Blocked by:** 42 (merged); 50 for the two-series area example and for the series-aware checks

**Status:** done

Decisions, settled:
- Examples follow the ticket 42 style (reasoning before the answer, the plan and the code passes) and are drawn from new cases added to the chart benchmark's training split, one German and one English per example; the held-out third is never touched. `bench/README.md` counts updated. Each example's code passes the self-check on the rows its SQL returns from the shipped dataset, verified by a test.
- Period comparison: a plan example and a query hint that says "two periods as the series, long rows (category, period, total)"; the code is the existing grouped bar. The plan prompt's shape menu line for `bar_grouped` mentions period comparison.
- Diverging bars: a plan example for `bar` with signed net per month; the domain includes both signs (already true through zero-from-mark and nice); the tooltip formats negatives with `eur`.
- Cumulative two-year area: `SUM(-amount) OVER (PARTITION BY year ORDER BY month)` as the running figure, `year` as the series, `area` with two series (ticket 50's flag), a legend. Do this example last, after merging main once ticket 50 is in.
- Reference line: a new global `ruleY` in `frontend/src/chart-runtime/globals.ts` (TanStack's `ruleY` mark) and a stub in the self-check's JavaScript report; allowed on `line`, `area` and `bar` only; at most one rule per chart; its `y` must be an expression over `data` (a `reduce` or an average helper the frame provides, `mean(data, 'column')`, which is the simpler thing for a small model), and a literal number is refused by the static scan as every literal figure already is; the rule carries a label through the mark's own option if 0.16 has one, otherwise the caption names it. `docs/chart-runtime.md` gets the global and the rule. A plan and a code example ("my monthly spending with my average as a line").
- Frontend: `SHAPE_LABELS` unchanged; the legend and the tooltip already render; verify the rule draws in both themes with the muted foreground colour.

- [x] Benchmark cases (two per example, training split) and `bench/README.md` counts
- [x] Period comparison plan example and query hint; diverging bars plan example; tests that the example code passes the self-check on real rows
- [x] `ruleY` global, `mean` helper, self-check stub and rules (allowed shapes, one rule, value from data), docs, plan and code example, tests (a rule with a literal fails, a rule from `mean` passes, a rule on a doughnut fails)
- [x] After merging main once ticket 50 is in: the cumulative two-year area example with two series and its test
- [x] `uv run pytest` green, `npm run build` clean; headful browser verification (named session, own port above 8100, throwaway database with the sample year, Gemini 3.8 Flash, at most six chat turns): the four questions in chat drawn correctly, the reference line visible with its label, both themes; screenshots in `/tmp/finquery-52/`; if OpenRouter credit is above 2 USD, `uv run finquery-bench run --set chart --model google/gemini-3.8-flash` on the new cases only and the numbers in Comments, otherwise say it was skipped

## Comments

Done 2026-09-06. `uv run pytest` is 344 passed, 4 skipped, up from 339 passed, 4 skipped on the
merge base: five tests new, all in `tests/test_chart.py`. The four skips are the usual
environmental ones. `npm run build` in `frontend/` is clean. Six small commits, merged from main
once ticket 50 was in.

### What changed, by file

**`bench/chart-benchmark.json`.** Eight cases, four pairs, one German and one English each:
`35/36-this-month-versus-last` (the period comparison), `37/38-change-per-month` (the diverging
bars), `39/40-average-line` (the reference line) and `41/42-cumulative-halves` (the two-band
area). Gold rebuilt with `build_gold.py`, the split rewritten with `split.py` and the validation
page's sample with `finquery-bench sample --seed 7`; `bench/README.md` carries the new counts
(73 charts, 24 held out) and a paragraph on what the four pairs are for.

Two of the ticket's own words moved, and both because of the shipped dataset:

- **"net per month above and below zero" is the change to the month before.** This household's
  monthly net never goes negative (the salary covers every month), so a signed net per month
  draws twelve bars above the line and teaches nothing about the zero baseline; and
  `24-net-per-month-de`, which asks exactly that, is held out, so a training pair with its
  statement would have taught the model a held-out answer. The pair asks "how much more or less
  than the month before" instead: eleven bars, six below the baseline and five above it, from a
  `LAG` over the monthly totals.
- **"this year against last year" is the first half against the second.** The shipped year is
  one year, so a `PARTITION BY year` returns one band and `build_gold.py` would have nothing to
  compare. The pair partitions by the half of the year and puts the month inside the half on the
  axis, which is the same picture, the same statement shape and the same reading (the gap
  between two bands). The `why` of both cases says a second year would only change the series
  column.

**`chart/shapes.py`.** `ruleY` joins `FAMILY_MARKS` and the `also_allowed` of `line`, `area` and
`bar`, which is the whole "only these three shapes" rule: the check already refuses a family
mark a shape neither requires nor allows, so a rule across a doughnut is caught with no new
branch. `MAX_RULES = 1`. The `bar` and `bar_grouped` purposes in the shape menu say what they
now also answer: a figure that may be negative, and one period against another by category.

**`chart/selfcheck.py`.** `ruleY` and `mean` are the twenty-fifth and twenty-sixth globals, in
`GLOBAL_NAMES` and in the QuickJS stub (`mean` is the same arithmetic as the frame's). Two
rules: at most one rule per chart, and the rule's value comes from the rows. The second is the
static scan, `_rule_findings`: it reads the first argument of every `ruleY(` call and a `y`
option, refuses a figure typed into either, and refuses a value that never touches `data`,
including one hidden behind `const usual = 2100`. Stroke options are left alone, because a width
is not a figure. The finding is one sentence and names the fix.

**`chart/runner.py`.** The query hint for a grouped chart whose series column names periods
(`period`, `Zeitraum`, `year`, `month`, ...) no longer asks for the groups to be built from the
`category` column: "this month against last month by category" turns the grouped bar around, the
categories go on the axis and the periods into the colour. The same branch leaves out the
paragraph about folding a tail of groups, because two periods are two colours and nothing to
fold, and asking for the six largest categories is a limit on the positions rather than on the
groups.

**`chart/subagent.py`.** Four plan rules (period comparison, a signed figure, a cumulative
comparison, the average as a line), three worked plans (period comparison, diverging, the
average) and a fourth for the cumulative area, all drawn from the training half. Two code
examples: `line` gains the reference line (`ruleY([mean(data, 'total_eur')])`) and `area` gains
two bands over long rows. The contract gains the two globals and two rules, and the borrowing
rule shrank: no shape is shown the line's second and third examples any more, because the area,
the only other shape that may carry a series, now teaches one itself.

**`frontend/src/chart-runtime/globals.ts`.** `ruleY` and `mean` for real. The frame gives the
rule the theme's muted foreground, 1.5 px, dashed `5 4`, so the generated code names no colour
and a stored card takes today's muted colour in either theme; a `stroke` the code writes still
wins. No `radius` and no `cornerRadius` anywhere near it.

**`docs/chart-runtime.md`.** Twenty-six globals, the rule in the house rules, the area's
stacking in the multi-series rule, the frame's look for the rule, and the static scan's third
job.

### The self-check rules added

1. `ruleY` on anything but a line, an area or a bar: "`ruleY` does not belong in a doughnut
   chart. Remove that mark." (the existing family-mark rule, from the new `also_allowed`).
2. More than one rule: "A chart carries at most 1 reference line and this one draws 2. A rule has
   no label of its own, so keep the one the request asks about, the average or the limit, and
   drop the rest."
3. A typed value: "The reference line's value is typed into the code. It has to be computed from
   the rows the chart draws, `ruleY([mean(data, 'total_eur')])` or a `reduce` over `data`, so the
   line moves with the query instead of standing where a figure was remembered." Fatal, not
   cosmetic: a figure nobody executed is the one thing ADR 0004 forbids.

`ruleY` carries no label option in 0.16 and emits no interaction point, so the caption names the
line, which is what the worked plan's title does ("Monatliche Ausgaben mit Durchschnitt").

### The benchmark, on the eight new cases

`google/gemini-3.8-flash`, 2026-09-06, the eight new datapoints and nothing else (the CLI takes
`--n` and a seed rather than a list of ids, so the run filtered `load("chart")` and called
`run_points` the way `command_run` does). Credit before the run: 4,14 USD of 15.

| | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 8 | **100 %** | 100 % | 100 % | 75 % | 100 % | 100 % | 100 % | 7.5 |
| bar_grouped | 2 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 7.5 |
| bar | 2 | 100 % | 100 % | 100 % | 0 % | 100 % | 100 % | 100 % | 7.0 |
| line | 2 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 6.7 |
| area | 2 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 8.0 |

Every one of the eight drew on the first attempt with the right shape, the right language and
the gold figures. The two `columns map` misses are both the diverging pair and neither is a
chart failure: the model's `LAG` statement keeps January, whose difference to the month before
is `NULL`, so the euro column is not numeric in every row and the scorer says so. The chart draws
the other eleven months and the gap where January would be. The reference statement filters that
row out; leaving the metric strict is the honest reading, because a null in the euro column is a
bar that is not there.

Result files: `bench/results/20260906T104911Z-google-gemini-3.8-flash-ticket52-chart.{json,md}`.

### Prompt growth, in the app's own estimator

| prompt | before (ticket 50) | after | growth |
| --- | ---: | ---: | ---: |
| plan (shape menu, rules, worked plans) | 1769 | 3020 | +1251 |
| code, line | 1725 | 2232 | +507 |
| code, area | 2178 | 2416 | +238 |
| code, bar | 1655 | 1889 | +234 |
| code, bar_grouped | 1707 | 1941 | +234 |
| code, doughnut | 1934 | 2168 | +234 |

The plan pass carries the whole growth: four rules and four worked plans, which is what a pass
that picks the wrong shape 67 percent of the time for grouped bars costs. Neither sub-agent
prompt has a budget on it (the chat agent's does, and nothing here touches it). The code side
grew by the two contract lines everywhere, by its own example on the line and the area, and by
nothing at all on the shapes that borrow: the doughnut is shown one line example as before.

### What the browser showed

OpenRouter, Gemini 3.8 Flash on both slots, port 8152, throwaway database under
`/tmp/finquery-52/data`, headed session `ticket52`, five chat turns. Screenshots in
`/tmp/finquery-52/` (ten, both themes). Zero browser console messages, zero page errors, and no
4xx or 5xx in either server log.

1. "Vergleiche Dezember 2025 mit November 2025 nach Kategorie." Grouped bars, the two months as
   the legend, six categories tilted on the axis, one figure per pair, first attempt.
2. "Zeig mir für jeden Monat 2025, wie viel mehr oder weniger ich als im Monat davor ausgegeben
   habe." Eleven bars, six below the zero line and five above it, months formatted by
   `monthShort`, the answer quoting +459,76 EUR in July and -481,96 EUR in August.
3. "Zeig meine Ausgaben pro Monat 2025 und wo mein Durchschnitt liegt." A line with one dashed
   rule across it in the muted colour, captioned "Monatliche Ausgaben mit Durchschnitt". The
   agent kept it, so the same card is on the Dashboard, where `run_card` re-runs the statement
   and the rule is recomputed from the rows of that load: the average is never stored.
4. "Vergleiche, wie sich meine Ausgaben im ersten und im zweiten Halbjahr 2025 aufsummiert
   haben." Two bands, a legend, the month of the half on the axis.

**The one thing the browser caught.** The first cumulative chart drew the two bands *stacked*:
`areaY` stacks its series unless the code names the interval, so the axis ran to 28.535 EUR, the
sum of the two halves, which is a figure nobody asked for. The worked example now gives every
band the same floor (`y1: 0, y2: 'cumulative_eur'`), the contract and `docs/chart-runtime.md`
say why, and the re-asked question drew both bands from zero with the axis ending at the real
maximum (screenshots 04 before and 05 after). A zero floor is not a figure typed into the code,
the same line the euro domain has always been allowed. No self-check rule was added for it: a
stacked area over categories is a legitimate chart, and the example is what the model copies.

### What is left

- The two German halves of three of the four new pairs are held out, so the worked plans are
  their English twins, except the average and the cumulative ones, where the hash went the other
  way. `20-daily-march-en` moved into the training half when the strata were re-cut, which is
  the splitter doing its job and the same thing that happened in ticket 50.
- Nothing measures a stacked two-band area being drawn by mistake. If the repair loop ever
  spends a round on it, the rule to add is "an area with a series and no `y1`/`y2`", and it would
  have to admit a deliberate stack.
