# 74: Five new chart shapes, validated visually before any of them is added

**What to build:** A throwaway prototype, not a feature. Five candidate shapes for the chart
sub-agent, each rendered through the real chart frame with rows from the shipped synthetic year,
in both themes, at the size the chat card draws a chart, and screenshotted, so the user can judge
whether each one looks polished enough to ship. The user's rule (2026-09-07): a shape is added
only if it looks amazing in the browser first. Nothing on main changes in this ticket.

**Candidates**, in the order of value for personal finance:
1. `waterfall`: income at the left, each expense category stepping down, net at the right; for
   one month or a year. Marks: `barY` with explicit bottoms and tops, or `rect`, plus connector
   `ruleY`-like steps if the library draws them cleanly.
2. `heatmap`: category by month (about ten by twelve cells) with euro intensity. Mark: `cell`.
3. `treemap`: spending share with subcategories nested in categories, labels inside the cells.
   TanStack Charts 0.16 has hierarchy modules (`hierarchy-tree`, `hierarchy-sunburst`,
   `hierarchy-flat-internal`); find out whether a treemap layout is exported. If it is not, a
   sunburst is the fallback candidate to try, and the report says why.
4. `bar_line`: monthly spend as bars with a three-month moving average as a line over them, one
   shared euro axis. Marks: `barY` plus `lineY`, both already globals.
5. `scatter`: one dot per booking over the year, size or colour by category, the outliers
   visible. Mark: `dot`.

**Status:** claimed

Decisions:
- Work in a worktree. The frame's global list (`frontend/src/chart-runtime/globals.ts`) may grow
  by the marks the prototypes need (`dot`, `cell`, a hierarchy layout), and the harness page may
  live under `frontend/prototype/`; none of it is merged. What comes back is screenshots, the
  code of each chart, the list of globals each needed, and a short report.
- The harness reuses the real frame (`/chart-runtime.html`, `ChartRenderMessage` from
  `frontend/src/lib/chart-frame.ts`) and the real theme colours read from the app's CSS variables
  in light and in dark, at 640 by 280 pixels (the chat card) and once at 400 by 280 (a dashboard
  tile), so what is judged is what the product would draw.
- Rows come from the shipped synthetic year through the product's own guard
  (`bench/finquery_bench/dataset.py` `fresh_database`, `finquery.query.guard.execute_read_only`),
  never typed by hand, so the figures and the label lengths are the real ones.
- The dataviz skill's rules apply (read it first): the palette is the theme's six colours, one
  type size for ticks, the grid is the only line, no chart junk.

- [ ] Harness renders the five shapes in both themes; screenshots in `/tmp/finquery-74/`
- [ ] `docs/prototypes/74-chart-shapes.md` in the worktree: per shape the code, the globals it needed, what looks good and what does not, the library limits found
- [ ] The branch is left for review, nothing merged
