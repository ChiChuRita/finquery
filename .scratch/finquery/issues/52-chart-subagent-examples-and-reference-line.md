# 52: Worked examples for the chart sub-agent, and a reference line

**What to build:** Proposal B of `docs/research/charts-and-dashboard-2026-09-06.md`, accepted by the user on 2026-09-06. No new shape family beyond ticket 50. Three worked examples teach the existing shapes the household questions they were failing: this month against last month by category (grouped bars with the period as the series), net per month above and below zero (diverging bars), and cumulative spending this year against last year (a two-series area after ticket 50). One small contract change: a reference line, `ruleY`, for "am I above my usual" questions, whose value is computed from the rows in the code, never typed.

**Blocked by:** 42 (merged); 50 for the two-series area example and for the series-aware checks

**Status:** ready-for-agent

Decisions, settled:
- Examples follow the ticket 42 style (reasoning before the answer, the plan and the code passes) and are drawn from new cases added to the chart benchmark's training split, one German and one English per example; the held-out third is never touched. `bench/README.md` counts updated. Each example's code passes the self-check on the rows its SQL returns from the shipped dataset, verified by a test.
- Period comparison: a plan example and a query hint that says "two periods as the series, long rows (category, period, total)"; the code is the existing grouped bar. The plan prompt's shape menu line for `bar_grouped` mentions period comparison.
- Diverging bars: a plan example for `bar` with signed net per month; the domain includes both signs (already true through zero-from-mark and nice); the tooltip formats negatives with `eur`.
- Cumulative two-year area: `SUM(-amount) OVER (PARTITION BY year ORDER BY month)` as the running figure, `year` as the series, `area` with two series (ticket 50's flag), a legend. Do this example last, after merging main once ticket 50 is in.
- Reference line: a new global `ruleY` in `frontend/src/chart-runtime/globals.ts` (TanStack's `ruleY` mark) and a stub in the self-check's JavaScript report; allowed on `line`, `area` and `bar` only; at most one rule per chart; its `y` must be an expression over `data` (a `reduce` or an average helper the frame provides, `mean(data, 'column')`, which is the simpler thing for a small model), and a literal number is refused by the static scan as every literal figure already is; the rule carries a label through the mark's own option if 0.16 has one, otherwise the caption names it. `docs/chart-runtime.md` gets the global and the rule. A plan and a code example ("my monthly spending with my average as a line").
- Frontend: `SHAPE_LABELS` unchanged; the legend and the tooltip already render; verify the rule draws in both themes with the muted foreground colour.

- [ ] Benchmark cases (two per example, training split) and `bench/README.md` counts
- [ ] Period comparison plan example and query hint; diverging bars plan example; tests that the example code passes the self-check on real rows
- [ ] `ruleY` global, `mean` helper, self-check stub and rules (allowed shapes, one rule, value from data), docs, plan and code example, tests (a rule with a literal fails, a rule from `mean` passes, a rule on a doughnut fails)
- [ ] After merging main once ticket 50 is in: the cumulative two-year area example with two series and its test
- [ ] `uv run pytest` green, `npm run build` clean; headful browser verification (named session, own port above 8100, throwaway database with the sample year, Gemini 3.8 Flash, at most six chat turns): the four questions in chat drawn correctly, the reference line visible with its label, both themes; screenshots in `/tmp/finquery-52/`; if OpenRouter credit is above 2 USD, `uv run finquery-bench run --set chart --model google/gemini-3.8-flash` on the new cases only and the numbers in Comments, otherwise say it was skipped
