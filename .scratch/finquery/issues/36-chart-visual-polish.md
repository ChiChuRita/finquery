# 36: Visual polish of the charts and of chart generation

**What to build:** The charts themselves and everything around making one should look finished: the rendering inside the frame (typography, spacing, axes, ticks, grid, colours, legend, tooltip, animation, empty and single-point cases), the chart card chrome in chat and on the dashboard (header, title, caption, footer actions, details, the pair view, the failed state), and the generation experience (the running state, the chain of thought, the moment the frame appears). Requested by the user on 2026-09-05: "they still look a little bit unpolished".

**Blocked by:** 25, 34, 35 (merged)

**Status:** done

Constraints: the runtime contract (globals, shapes, house rules in docs/chart-runtime.md) stays stable because the sub-agent's few-shot and the training data depend on it; visual defaults live in the frame's theme and host code, not in the generated code. The self-check rules stay. Dark and light parity is required. No new dependencies.

- [x] Before screenshots of every shape (line, area, bars, horizontal bars, grouped, stacked, doughnut, sankey) in chat and on the dashboard, both themes, 1024 and 1440, plus the running, failed and pair states
- [x] Inside the frame: one type scale for axis ticks, labels and legend matching the app's font and sizes; consistent margins so nothing touches the frame edge; tick density that never overlaps; short EUR ticks; a light horizontal grid only; bars with a sensible band padding and radius; lines and areas with the house stroke and a soft fill; a doughnut with an inner radius, a centered total or caption, and slice labels only where they fit; a sankey with readable node labels and ribbons that do not overlap; palette order stable per series; the tooltip styled like the app's tooltip (surface, border, radius, shadow, EUR format, series colour swatch); a subtle animation on first draw only; a clean empty and single-point rendering
- [x] The card chrome: one header pattern (title, shape badge, actions) shared by chat and dashboard, the caption under the frame in the answer language, a footer that does not fight the header, the details toggle with plan, chain of thought, SQL and rows in one consistent layout, the pair view as two equal frames with Pick and a clear chosen state, the failed card with the reason and the details, all in both themes
- [x] Generation: a running card that holds the final height so the transcript does not jump, the chain of thought advancing step by step, the frame fading in when ready, the dashboard's Add chart running state identical
- [x] After screenshots of the same inventory, contact sheets per shape and state, and a short note on what changed in the theme and card components; typecheck (npm run build) and suite green; zero console errors

## Comments

Done 2026-09-05. `uv run pytest` is 269 passed, 4 skipped (unchanged: the self-check and prompt
tests were not touched, because the contract was not). `npm run build` is clean, `oxlint` is at
its baseline. Zero browser console messages and no 4xx or 5xx in the server log over the whole
session (OpenRouter, Gemini 3.8 Flash on both slots, port 8111, throwaway database, headed
session `charts-polish`). Screenshots: `/tmp/finquery-36/before/` and `/tmp/finquery-36/after/`
(every shape in chat and on the dashboard, both themes, 1440 and 1024, plus running, failed and
pair), contact sheets per shape and state in `/tmp/finquery-36/sheets/` (before left, after
right, the four variants as rows): `chat-line`, `chat-area`, `chat-bar`, `chat-barh`,
`chat-grouped`, `chat-stacked`, `chat-doughnut`, `chat-sankey`, `chat-twobars`, `chat-failed`,
`chat-pair`, `chat-running`, `dashboard-all`, `dashboard-running`.

The generated code contract did not move: same twenty-four globals, same shapes, same house
rules, no change to `selfcheck.py` or the sub-agent prompt. Every stored chart on the dashboard
(the four defaults and the nine pinned from the session) took the new look on reload without
being regenerated, which is the point of keeping the look in the frame.

### What was unpolished, by root cause

**Theme (the frame's page and definition theme)**

- The frame never loaded the app's face: axis ticks, legend and tooltip rendered in the system
  font (only `index.css` imported Geist), ticks at 10 px, tooltip in `system-ui`.
- Tick stubs and solid axis lines on both axes, so every chart carried two rules the grid
  already gave it.
- The tooltip's chrome was half themed: surface and border from the card, but a heavy shadow, a
  system font and no series swatch (the contract's `format` text wins over the built-in rows).
- The dark palette failed the dataviz validator's lightness band on all six slots (L 0.72 to
  0.82 against a 0.48 to 0.67 band): pastel marks glowing on the dark card. The light palette
  had `--chart-6` on the chroma floor and `--chart-3` at 2.96:1 contrast.
- `eurShort` wrote "5000 €" next to "10.000 €" (Intl compact leaves four digits ungrouped).

**Mount options (`buildChart`)**

- `nice: 5` against a height-derived tick count left the top of the plot unlabelled whenever a
  legend shortened it (the grouped bars rose above their last gridline), and a 300 px pair frame
  still rounded 13.800 EUR to 20.000.
- Stacked segments and doughnut slices touched with nothing between them; a line's focused point
  was a second filled disc.
- The plot ran to the frame's edge: "Dec 25" and the sankey's nodes sat on the border.
- A doughnut had a hole and nothing in it.
- The entrance animation replayed on every theme switch (the frame remounted on a key that
  included the theme colour).

**Card chrome**

- Two failed states: the chat card's uppercase "ERROR" section over a red box plus two grey
  lines, the frame's own red pill, the dashboard's third variant.
- The dashboard header could not take the shape badge (four actions beside the title), so the
  two headers differed in more than the actions.

**Generation state**

- The chat's running card was three lines tall and the frame's 280 px arrived under it, so the
  transcript jumped; the dashboard's Add line already reserved the height.
- The chain of thought sat on "Planning the chart" for the whole run although the sub-agent had
  long narrated its plan and its row count into the thinking panel.
- The frame appeared as a hard cut from "Drawing..." to the picture.

### What changed

**Theme** (`frontend/chart-runtime.html`, `chart-runtime/main.tsx`, `index.css`). The runtime
entry imports `@fontsource-variable/geist` (already a dependency; the font files are served with
the `/assets/*` CORS header the sandboxed frame needs). One tick size, 11 px, tabular figures.
`axis.line: false`, `ticks.size: 0`, `ticks.padding: 8` on every axis; what the code set on a
label is kept. 12 px at the sides and 6 px at the top of the page, the chart 6 px shorter. The
tooltip takes the card's surface, border, `0.625rem` radius, the app's soft shadow and Geist at
12 px; `--ts-chart-focus-fill` is the surface, so a focused point is a dot with a surface ring.
Both palettes now pass the dataviz validator for their own surface (`validate_palette.js`,
light on `#ffffff`, dark on `#171717`): light `--chart-3` to L 0.66, `--chart-6` to C 0.12; the
dark set stepped to L 0.64 to 0.67 instead of lifted to 0.72 to 0.82, worst adjacent CVD
delta E 13.7, all six above 3:1. `eurShort` writes whole euros with the German grouping up to a
million and compact from there.

**Mount** (`chart-runtime/main.tsx`, `chart-runtime/globals.ts`). `nice: true` becomes `nice: 4`
and `ticks.count: 4` together, so the euro axis ends near the data and its last gridline is
always labelled (0, 5.000, 10.000, 15.000 for 13.800 EUR). The code's `tooltip.format` text is
shown as one row of the built-in tooltip, swatch, label and right-aligned figure, split at the
last ": ". `barY`/`barX` with a `z` or `color` channel get a 1 px surface stroke, `radialArc` a
2 px one, the dataviz method's surface gap; the code's own `stroke` wins. `pie` records the total
of the slices it allocated and the frame writes it into the hole over "Total" or "Gesamt",
positioned from the polar group's own `translate`. The chart is keyed by its code alone, so a
theme switch updates it in place and the 320 ms entrance plays once. `globalValues` now takes
the theme rather than the palette; the names and their order are unchanged.

**Card chrome and generation** (`components/chart-tool.tsx`, `dashboard-card.tsx`,
`chat-view.tsx`). `FailedBody`, one `Alert` for the chat card, the dashboard card and the
frame's own refusal: the reason, the hint, and the "answer already written" note where it
applies. `RunningBody`, the frame's height with the shimmer, shared by the chat's running card
and the dashboard's Add line. The frame fades in over 300 ms when the runtime posts `ready`.
`runningSteps` reads the sub-agent's narration ("Chart plan:", "Data: N rows", "Repair k of 2:",
"Self-check passed") out of the turn's thinking, which `chat-view` passes to the running card,
so the rail advances as the lines arrive; the finished card's chain is as before. The dashboard
header keeps ticket 35's choice of no badge: tried, and it cut every title to a word and a half.

**Docs.** `docs/chart-runtime.md`, "The frame": the nice/count rule corrected, and a "What the
frame's theme sets" list.

### Decided, and left

- The title in the header is the chart's caption and is already in the answer language; no
  second caption line was added under the frame.
- Bars keep the radius the code gives them, on all four corners: TanStack's `radius` is the SVG
  rect's, and rounding only the data end would need a custom mark.
- Gemini 3.8 Flash wrote the identical line definition three times in a row, so the pair state
  was captured on the category bars instead.
- Seen, not this ticket: a stacked chart the runner folded to six series in chat re-runs its SQL
  unfolded on the dashboard (eleven series, 132 rows) and cycles the palette. The fold lives in
  the runner, not in the stored statement.
- The chain advancing live was verified by the code path, not on screen: with Gemini 3.8 Flash a
  chart is planned, queried, written and checked in under six seconds.
