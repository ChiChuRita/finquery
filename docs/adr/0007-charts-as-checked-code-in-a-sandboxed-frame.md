# ADR 0007: A chart is generated code, checked in-process and rendered in a sandboxed frame

Date: 2026-09-04
Status: accepted

## Context

Charts have to look like they belong to the app across eight shapes, respect the theme, format
euros, and be produced by a small model that will later be fine-tuned for exactly this job
(spec: "the chart sub-agent plans the chart, writes it, checks it in-process and repairs it up
to twice before I see it"). Three routes were possible: a fixed set of chart components the
sub-agent parameterises, a chart spec in JSON that our code renders, or generated code.

A component set cannot express a sankey, a grouped stack and a doughnut fold without growing
into a chart library of our own. A JSON spec is a chart library of our own with extra steps: any
option TanStack Charts gains has to be plumbed through it. Generated code has the opposite
problem: it is untrusted input, and a broken chart is worse than no chart.

## Decision

- The chart sub-agent writes **the body of one JavaScript function** over an allowlisted set of
  globals (24 names) and returns a TanStack Charts definition. The contract is documented once
  in `docs/chart-runtime.md`; `src/finquery/chart/shapes.py` is its machine-readable half.
- Before the browser sees it, the code is compiled and run **in-process by QuickJS** against
  stub globals that record calls instead of drawing (`finquery.chart.selfcheck`). The recording
  is judged against the house rules: one definition, columns that exist, the planned shape, both
  positional scales, EUR ticks on the euro axis, grid on that axis only, a tooltip, a legend only
  with several series, no height and no data typed into the code.
- A failing rule is a repair instruction in the same words. Two repair rounds follow the first
  attempt; the plan and every round are narrated into the turn's thinking panel through
  `ChatDeps.narrate`. After the last round a readable sentence replaces the chart, except when
  only polish is left (a legend nobody needs), which is shown with a note.
- The browser renders it in a **second Vite entry loaded as `<iframe sandbox="allow-scripts">`**,
  so generated code runs in a document with an opaque origin and no access to the app, its
  storage or its API. Rows, code and the resolved theme colours arrive by `postMessage`; errors
  travel back and the card shows them inline.
- The frame owns everything the code may not: the height (280), the responsive width, the
  palette, the animation and the accessible name. The card owns the title, the rating placeholder
  and the expandable SQL and rows.
- A shape the rows cannot carry is downgraded rather than repaired: a stacked chart whose query
  returned a single series becomes plain bars, with a line in the thinking panel saying so.

## Consequences

- Anything TanStack Charts can draw is reachable by adding a global to three lists (the runtime,
  the stub, the docs) instead of designing a spec for it.
- The check is the specification of the house style, which makes it the reward signal for the
  chart adapter later: the same prompt, the same rules, the same words.
- Two implementations of the globals exist, the real one in TypeScript and the recording stub in
  JavaScript inside `selfcheck.py`. They are listed side by side in `docs/chart-runtime.md`, and
  a global that only exists in one of them is either an unusable name or an unchecked one.
- The sandbox costs one header: the built assets answer with `access-control-allow-origin: *`,
  because an opaque origin fetches the entry bundle as a CORS request.
- A chart is auditable the same way a number is (ADR 0004): the card carries the executed SQL
  and its rows next to the drawing.
