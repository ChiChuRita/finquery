# 36: Visual polish of the charts and of chart generation

**What to build:** The charts themselves and everything around making one should look finished: the rendering inside the frame (typography, spacing, axes, ticks, grid, colours, legend, tooltip, animation, empty and single-point cases), the chart card chrome in chat and on the dashboard (header, title, caption, footer actions, details, the pair view, the failed state), and the generation experience (the running state, the chain of thought, the moment the frame appears). Requested by the user on 2026-09-05: "they still look a little bit unpolished".

**Blocked by:** 25, 34, 35 (merged)

**Status:** ready-for-agent

Constraints: the runtime contract (globals, shapes, house rules in docs/chart-runtime.md) stays stable because the sub-agent's few-shot and the training data depend on it; visual defaults live in the frame's theme and host code, not in the generated code. The self-check rules stay. Dark and light parity is required. No new dependencies.

- [ ] Before screenshots of every shape (line, area, bars, horizontal bars, grouped, stacked, doughnut, sankey) in chat and on the dashboard, both themes, 1024 and 1440, plus the running, failed and pair states
- [ ] Inside the frame: one type scale for axis ticks, labels and legend matching the app's font and sizes; consistent margins so nothing touches the frame edge; tick density that never overlaps; short EUR ticks; a light horizontal grid only; bars with a sensible band padding and radius; lines and areas with the house stroke and a soft fill; a doughnut with an inner radius, a centered total or caption, and slice labels only where they fit; a sankey with readable node labels and ribbons that do not overlap; palette order stable per series; the tooltip styled like the app's tooltip (surface, border, radius, shadow, EUR format, series colour swatch); a subtle animation on first draw only; a clean empty and single-point rendering
- [ ] The card chrome: one header pattern (title, shape badge, actions) shared by chat and dashboard, the caption under the frame in the answer language, a footer that does not fight the header, the details toggle with plan, chain of thought, SQL and rows in one consistent layout, the pair view as two equal frames with Pick and a clear chosen state, the failed card with the reason and the details, all in both themes
- [ ] Generation: a running card that holds the final height so the transcript does not jump, the chain of thought advancing step by step, the frame fading in when ready, the dashboard's Add chart running state identical
- [ ] After screenshots of the same inventory, contact sheets per shape and state, and a short note on what changed in the theme and card components; typecheck (npm run build) and suite green; zero console errors
