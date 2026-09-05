# 39: A dashboard chart re-runs with the same folds as in chat

**What to build:** The chart runner folds a stacked chart's small series into six and a doughnut's slices into five plus rest before the code pass, but the fold lives in the runner, not in the stored SQL. A chart pinned to the dashboard re-runs its SQL unfolded, so a stacked chart that showed six series in chat shows eleven on the dashboard and the palette cycles. Found by ticket 36.

**Blocked by:** 35, 36 (merged)

**Status:** ready-for-agent

- [ ] The fold step is one shared function used by the runner and by the dashboard's load and refresh, keyed by the stored shape, so a stored chart renders exactly as it did in chat
- [ ] Test at the HTTP seam: a pinned stacked chart with more than six series returns folded rows from GET /api/dashboard and after refresh
- [ ] Browser check on the dashboard in both themes
