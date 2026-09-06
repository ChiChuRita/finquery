# The chart runtime contract

A chart in FinQuery is a piece of JavaScript the chart sub-agent writes, checked in-process and
then rendered in a sandboxed frame. This page is that contract: the globals the code may use,
the shapes it may draw, the house rules it must obey and the messages between the card and the
frame. It is the reference for `src/finquery/chart/` (which enforces it), for
`frontend/src/chart-runtime/` (which implements it) and for the later generation of training
data for the chart adapter, which has to produce exactly this dialect.

## The code

The sub-agent returns a short **reasoning** (three to five one-line steps: the shape and its
mark, the columns of these rows and which one holds the numbers, what each axis is) and then
**the body of one function**. The reasoning is filled first, so the model commits to a reading
of the rows before it writes a channel name, and it is narrated into the thinking panel rather
than into the answer. The body receives `data`, an array of row objects that a query already
returned, and must `return` a TanStack Charts definition:

```js
const amounts = data.map((row) => row.total_eur);
return defineChart({
  marks: [lineY(data, { x: 'month', y: 'total_eur', stroke: palette[0], strokeWidth: 2.25 })],
  scales: {
    x: { scale: () => scalePoint().padding(0.06), axis: { ticks: { format: monthShort } } },
    y: {
      scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)]),
      nice: true,
      grid: true,
      axis: { ticks: { format: eurShort } },
    },
  },
  tooltip: { use: tooltip, format: (point) => eur(point.datum.total_eur) },
});
```

There are no imports, no JSX, no `await`, no browser APIs and no globals beyond the list below.
The code is evaluated with `new Function('data', ...names, body)`, so it may use plain
JavaScript (`Math`, `Array`, `Object`, arrow functions, `const`).

## The globals

Twenty-six names, in the order the runtime and the check pass them. TanStack Charts is pinned
to 0.16.0; every name below is a public export of that version.

| Global                                       | From                                | What it is                              |
| -------------------------------------------- | ----------------------------------- | --------------------------------------- |
| `defineChart(spec)`                          | `@tanstack/charts`                  | The definition; called once, returned   |
| `lineY`, `areaY`, `barY`, `barX`             | `@tanstack/charts`                  | Cartesian marks, `(rows, options)`      |
| `ruleY(values, options)`                     | `@tanstack/charts`                  | A horizontal reference line, one per chart |
| `link`, `rect`, `text`                       | `@tanstack/charts`                  | The child marks of a sankey             |
| `stack()`, `group()`                         | `@tanstack/charts`                  | Bar layouts                             |
| `polar(options)`                             | `@tanstack/charts/polar`            | The radial container                    |
| `pie(rows, { value })`                       | `@tanstack/charts/polar`            | Rows to angular slices, a row transform |
| `radialArc(slices, options)`                 | `@tanstack/charts/polar`            | Draws slices, only inside `polar`       |
| `sankeyDiagram(options)`                     | `@tanstack/charts/network/sankey`   | The flow layout                         |
| `scaleLinear`                                | `@tanstack/charts/scales/linear`    | The euro axis                           |
| `scaleBand`, `scalePoint`                    | `@tanstack/charts/scales/{band,point}` | The category axis                    |
| `scaleOrdinal`                               | `@tanstack/charts/scales/ordinal`   | A fixed colour mapping                  |
| `colorLegend(options)`                       | `@tanstack/charts`                  | The legend, for `color.legend`          |
| `tooltip`                                    | `@tanstack/charts/tooltip`          | The tooltip extension                   |
| `palette`                                    | FinQuery                            | The theme's six colours, `palette[0]` first |
| `eur(value)`                                 | FinQuery                            | "1.234,56 €", for tooltips              |
| `eurShort(value)`                            | FinQuery                            | A compact euro label, for axis ticks    |
| `monthShort('2025-01')`                      | FinQuery                            | "Jan 25", or "Mar 14" for a day           |
| `mean(data, 'total_eur')`                    | FinQuery                            | The average of one column of the rows   |

There is no time scale in TanStack Charts, which is why months are categories on a band or point
scale and `monthShort` formats their labels. It is the one global that is not the same function
every time: the frame builds it from the chart's `language`, so an English question gets "Mar 25"
and a German one "Mär 25", and a value that carries a day ('2025-03-14') is labelled with the day
rather than with its month nineteen times over. Money stays German in both: `eur` and `eurShort`
are always `de-DE`, because the product writes money that way whatever the answer language is.

## The shapes

| Shape            | Marks                                | For                                                |
| ---------------- | ------------------------------------ | -------------------------------------------------- |
| `line`           | `lineY` (+ optional series, + optional `ruleY`) | a figure over ordered months or days, or one line per name |
| `area`           | `areaY` (+ optional `lineY` outline, + optional series, + optional `ruleY`) | a running total or a filled trend |
| `bar`            | `barY` (+ optional `ruleY`)          | one figure per named category or month, above and below zero |
| `bar_horizontal` | `barX`                               | a ranking with long labels                         |
| `bar_grouped`    | `barY` + `layout: group()` + series  | two dimensions side by side, at most six groups    |
| `bar_stacked`    | `barY` + series                      | the same two dimensions when the total matters     |
| `doughnut`       | `polar` + `pie` + `radialArc`        | a share of a whole, at most six slices             |
| `sankey`         | `sankeyDiagram` + `link`/`rect`/`text` | a flow from sources to targets                   |

A series is a `z` or `color` channel: a column name or an accessor. The table lives in
`src/finquery/chart/shapes.py`, which the plan prompt, the code prompt and the check all read.
Four flags on a row carry more than the marks do, and they are deliberately not one flag:

- **`series`** means the shape tells its data apart by colour, so it needs a `color` (or `z`)
  channel and a legend. The grouped and stacked bars do; so does a doughnut, whose slices are
  its series. Six colours is the ceiling, because that is how long the theme's palette is: a
  seventh group is painted like the first, and two categories in one picture wearing one colour
  is not a chart anybody can read.
- **`may_series`** means the shape carries a series when the request asks for one and reads
  fine without it. The line and the area do: "spending at my five grocery stores per month" is
  one `lineY` with a `color` channel, five strokes and a legend, and the same request about one
  store is the plain two-column line with neither. Its rows come long, one per (position, name)
  pair, like a grouped bar's. Kept apart from `series` because nothing is missing when there is
  only one column of euros, which is what made the repair loop drop every store but one before
  ticket 50.
- **`crossed`** means the shape needs two dimensions that really cross, one figure per (position,
  series) pair. Only the grouped and stacked bars do, which is why a doughnut is not downgraded
  to bars when its rows carry a single dimension. A line with a series needs its pairs to be
  unique too, but not to be complete: a store with no booking in March is a gap in one stroke.
- **`zero_from_mark`** means the mark contributes its own zero baseline to the inferred domain.
  Bars and areas do. A line does not, and has to name the domain itself.

## The house rules

Every rule below is checked before the browser sees the code. A failing rule becomes a repair
instruction in the same words.

- `defineChart` is called exactly once and its result is returned.
- `scales` always declares both `x` and `y`; `null` says an axis is unused.
- The euro axis is `scaleLinear` with `nice: true`, `grid: true` and
  `axis: { ticks: { format: eurShort } }`. The other axis carries no grid.
- The euro axis includes zero. A bar and an area rest on it by themselves; a line names it,
  `scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)])`, and a domain
  written inside a `() =>` factory is refused because the chart infers it again and throws that
  one away.
- Month and day values (`2025-01`, `2025-03-14`) get `axis: { ticks: { format: monthShort } }`
  and may be thinned, because a reader reads a missing month off its neighbours.
- A category axis carries names, and a name cannot be read off its neighbours, so every one of
  them is drawn: `axis: { tickLabels: { thin: false } }`, plus `rotate` when the names sit on x.
- Two marks may not draw two different euro columns with nothing to tell them apart: that stacks
  income on top of spending into a total nobody asked for. A mark that carries a series is
  telling them apart, so it is not what this rule is about.
- A line or an area with a series draws one stroke per name: `z` and `color` both name the
  column of names, the euro domain covers every figure in the rows, and the legend goes on. At
  most six of them, the same ceiling as the bars. `areaY` stacks its bands unless it is given
  explicit boundaries, so an area comparing periods gives every band the same floor,
  `y1: 0, y2: 'cumulative_eur'`: two periods are read off the gap between them, never off their
  sum. The browser drew that sum on 2026-09-06 before the worked example said so.
- Every chart carries `tooltip: { use: tooltip, format: ... }` and formats euros with `eur`.
- A legend only with more than one series, and then
  `color: { legend: colorLegend({ placement: 'bottom' }) }`.
- The definition sets no `height`, `width`, `title` or `theme`: the card owns all four.
- A doughnut has at most six slices and an `innerRadius`.
- Every column a channel names exists in the rows it was given, and no mark gets an empty array.
- A reference line is `ruleY([mean(data, 'total_eur')])`, at most one per chart, and only on a
  line, an area or a bar: the shapes with a euro axis to lie across. Its value is computed from
  `data`, with `mean` or a `reduce`, and a typed one (`ruleY([1200])`, or a name assigned a bare
  number above it) is refused by the static scan, because a figure nobody executed is exactly
  what ADR 0004 is about. The mark carries no label in 0.16 and emits no tooltip point, so the
  caption is what names it.
- The values are read from `data` through channels. Numbers are never typed into the code.
- Nothing outside the allowlist: no `import`, `require`, `fetch`, `window`, `document`, `eval`,
  `setTimeout` or `globalThis`.

One thing the worked examples teach is not on that list, because nothing refuses a fat bar:
`maxThickness: 32` on `barY` and `barX`, so the mark stays thin and the band's leftover is air.
Two bars filling half a card each is what it prevents.

Three rules are polish rather than correctness: the two legend rules and the six-colour ceiling.
If they are the only thing left after the last repair round, the chart is shown with a note
instead of being thrown away, because a chart whose seventh colour repeats still answers the
question and no chart at all does not. `selfcheck.is_cosmetic` is the one place that says which.

Every finding appears once in a round, however many marks earned it: eight marks reading the same
missing column is one thing to fix, and the round's findings are the model's whole instruction.

## The check

`finquery.chart.selfcheck` compiles and runs the code inside QuickJS against stub globals that
record what was asked for instead of drawing it, then judges the recording:

1. a static scan (forbidden names, data typed into the code, a reference line's value typed
   into it rather than computed from the rows);
2. compilation, then one run with the real rows, so a thrown error is a finding;
3. the rules above, over the recorded marks, scales, channels and series.

Two rules are about the rows rather than about the code, so `data_findings(shape, columns,
rows)` judges them before a line is written and no repair round is spent on them:

- a chart with a series needs **one figure per (position, series) pair**, which is the stacked
  and grouped bars and a line or an area whose rows carry a name column. Two rows for
  2025-01 / Groceries cannot be drawn by any definition, and TanStack says so as "A stack
  requires at most one value for each position and series";
- a sankey needs links that **go somewhere and do not come back**: three columns, so every link
  has both ends, no row flowing from a name into itself, no cycle over the source and target
  columns, and a positive amount on every link. The QuickJS stub applies the same rules to
  whatever graph the code builds, so a definition that assembles its own links is caught too.

A third case is decided on the rows and downgraded rather than refused: a chart the rows cannot
carry becomes plain bars, narrated. A grouped or stacked chart whose rows carry a single series
does, and so does a line or an area over fewer than three points along its axis, because a stroke
from January to July says something about the five months the query did not return. Points and
not rows: five stores over two months are ten rows and still two points each.

A fourth is folded rather than repaired. Folding is arithmetic, so it is not left to a repair
round and never to the SQL: the rows the card shows are the rows the chart drew, and every fold
is narrated. `chart.fold.fold_rows(shape, columns, rows, language=...)` is all three of them, one
per shape and keyed by what the columns are for, and it runs before a line of code is written:

- a **doughnut** over more rows than it has slices keeps the five largest and sums the rest into
  one slice named `Other` or `Sonstige`, in the request's language. The local fast model lost a
  twelve-category doughnut three rounds running before this existed;
- a **grouped or stacked bar** over more groups than the palette has colours keeps the five
  largest by total and sums the rest into one such group per position. The query is therefore
  asked for each group under its own name and told not to fold: asking the statement for it is
  what produced `CASE ... 'Other'` beside `GROUP BY month`, so every month came back carrying
  several 'Other' rows and no definition could stack them;
- a **line or an area carrying a series** over more names than the palette has colours keeps the
  six largest by total and leaves the rest out, naming them in the note. It is the one fold that
  drops instead of summing: nobody spends money at 'Sonstige', so a seventh line holding the
  tail is a stroke a reader takes for a shop;
- a **sankey** row flowing from a name into itself is a total and not a flow, so it is left out
  and the omission is narrated. One such row, which "show me where my income goes" produces
  readily, otherwise refuses the whole graph. Rows that are nothing but self loops are left
  alone, because then there is no flow to draw and the rule above says so in one sentence.

The fold is a function of its own because it happens twice for the same chart. A chart pinned to
the dashboard stores the statement and not the figures, so `dashboard.run_card` re-runs the SQL
through the guard on every load and refresh and folds what comes back with the same call
(ticket 39): before that, a stack that showed six series in the chat showed eleven on the
dashboard and cycled the palette. The column roles are read off the order the query was asked
for its columns in, which `runner._euro_last` fixes before the statement is written and a stored
statement keeps.

The stub mimics the parts of the library the rules need: `pie` allocates real angles and rejects
a negative value, `sankeyDiagram` validates the graph and calls the `marks` callback with node
and link rows that carry the documented fields (`x0`, `x1`, `y0`, `y1`, `x`, `y`, `key`, `value`,
`data`), and channel accessors are called the way a mark would call them. It never renders: a
browser renders, the check judges intent.

Two repair rounds follow a first failure (`ATTEMPTS = 3`). Each round's findings go back to the
sub-agent with the refused code, and each is narrated into the transcript's thinking panel. A
round is framed as a correction and not as a new request (`subagent.repair_prompt`): the model
is shown its own reasoning and its own code, then the findings, and is asked for the corrected
reasoning and code with what changed on the first line. Three rounds that only said "it failed,
write it again" returned the same finding three times on 2026-09-05.

## The frame

`frontend/chart-runtime.html` is a second Vite entry, built to `dist/chart-runtime.html`. The
card embeds it as

```html
<iframe src="/chart-runtime.html" sandbox="allow-scripts" />
```

so the generated code runs in a document with an opaque origin: no access to the app, its
storage or its API. Because the origin is opaque, the built bundle is fetched as a CORS request,
which is why the app answers `/assets/*` with `access-control-allow-origin: *`
(`finquery.app.create_app`).

Messages, both with `targetOrigin: '*'` (there is no origin to name):

| Direction      | Message                                                                  |
| -------------- | ------------------------------------------------------------------------ |
| frame to card  | `{ source: 'finquery-chart-runtime', kind: 'hello' }` once it is ready    |
| card to frame  | `{ source: 'finquery-chart', kind: 'render', title, language, code, rows, theme }` |
| frame to card  | `{ source: 'finquery-chart-runtime', kind: 'ready' }` after it painted    |
| frame to card  | `{ source: 'finquery-chart-runtime', kind: 'error', message }`            |

The card posts on the frame's `load` event as well, because the `hello` can arrive before React
has run the card's effects. `theme` carries colours already resolved from the app's CSS
variables (`--foreground`, `--muted-foreground`, `--border`, `--card`, `--chart-1` to
`--chart-6`), so the frame needs no stylesheet of ours. The card watches the `class` attribute of
`<html>` and re-posts on a theme switch; the frame paints its surface, sets the definition's
`theme` and remounts.

The frame owns what the code may not: `height: 280`, the responsive width, the palette,
`svgAnimation: { duration: 320, easing: 'ease-out' }`, the `ariaLabel` (the chart's title) and
the language the month labels are written in. It also decides how finely a `nice: true` axis
rounds its end: TanStack Charts rounds to the tick count it will draw, one tick per 48 pixels of
plot height, so a 300 pixel frame in a side by side pair took 13.800 EUR to an axis ending at
20.000 EUR, and a legend under the plot left the top gridline without a label. The frame
rewrites `nice: true` to `nice: 4` and gives that axis `ticks: { count: 4 }` before it renders,
so the end stays near the data and the last gridline is always labelled: 0, 5.000, 10.000,
15.000 EUR for 13.800 EUR, whatever the width.

### What the frame's theme sets

Everything visual that the dataviz method fixes across charts lives in the frame
(`chart-runtime/main.tsx`, `chart-runtime/globals.ts`, `chart-runtime.html`), never in the
generated code, so a definition stored months ago on the dashboard gets today's look without
being regenerated (ticket 36):

- **Type.** The runtime page loads the app's face (Geist) and sets one size, 11 px, on every
  axis tick label; the legend and the doughnut's centre share it. Figures are tabular.
- **Axis chrome.** No axis line and no tick stubs on either axis (`axis.line: false`,
  `ticks.size: 0`, `ticks.padding: 8`): the euro axis's hairline grid is the only line, and the
  zero gridline is the baseline. What the code set on a label (format, thinning, rotation) is
  kept.
- **Room.** The page keeps 12 px at the sides and 6 px at the top around the plot, so no label
  or sankey node touches the frame's edge.
- **Surface gaps.** `barY` and `barX` with a series (`z` or `color`) get a 1 px stroke in the
  card's surface colour, `radialArc` a 2 px one, so stacked segments, grouped bars and doughnut
  slices are told apart by a hairline of surface rather than by touching. The code's own
  `stroke` wins when it names one.
- **The reference line.** `ruleY` is drawn in the theme's muted foreground, 1.5 px, dashed
  `5 4`, because it is the chart annotating its own marks and not a series of its own. The
  generated code names no colour for it, so a stored card takes today's muted colour in either
  theme; a `stroke` the code does write still wins.
- **Corners.** Nothing inside a chart is rounded: `barY`, `barX` and `radialArc` drop a
  `radius` or `cornerRadius` the code wrote, and the legend's swatches are squares (ticket 45).
  Rounding stays on the card and on the tooltip, which are the app's chrome, not the chart's.
- **The doughnut's centre.** `pie` records the total of the slices it allocated, and the frame
  writes it into the hole ("28.535,89 €" over "Total" or "Gesamt", by language). The figure
  is the query's rows added up, never typed.
- **Tooltip.** The code's `format` text is shown as one row of the app's tooltip: the series
  swatch, the label and the figure right-aligned, split at the text's last ": ". The surface,
  border, radius, shadow and type are the card's own (`--ts-chart-tooltip-*`), and the focus
  marker's inner fill is the surface, so a focused point reads as a dot with a surface ring.
- **Euro ticks.** `eurShort` writes whole euros with the German grouping ("5.000 €",
  "10.000 €") and only turns compact ("1,2 Mio. €") from a million.
- **Motion.** The 320 ms entrance plays on the first draw only: a theme switch updates the
  mounted chart in place instead of remounting it.
- **Palette.** Both palettes (`--chart-1` to `--chart-6` in `index.css`) pass the dataviz
  method's palette validator for their own surface, the dark set stepped into its darker band
  rather than lifted. The card resolves them and posts them; the frame paints with them in
  that order.

The card around the frame reserves the frame's height while a chart is being made, fades the
frame in when the runtime says it painted, and advances the plan, query, code and check steps of
its details from the sub-agent's narration as the lines arrive.

## The tool result

`run_chart` returns one payload, which is both what the chat agent reads and what the card
renders:

```json
{
  "request": "...", "title": "...", "shape": "line", "language": "en",
  "plan": "Chart plan: line, ...",
  "sql": "SELECT ...", "row_count": 12, "columns": ["month", "total_eur"], "rows": [ ... ],
  "figures": ["month 2025-01, total_eur 2.265,34 EUR", ...],
  "code": "return defineChart({ ... });", "notes": ["Repair 1 of 2: ..."],
  "summary": "...", "error": null, "rendered": true
}
```

`language` is the plan pass's own decision about the request, `de` or `en`. The caption is
written in it and the frame writes the chart's month labels in it, which is what stopped an
English question coming back as "Monatliche Ausgaben 2025" over "Jan 25 ... Dez 25".

`code` is `null` when no chart could be drawn, and `error` says why in one sentence.
`rendered` is the field the chat agent reads before it writes a word about the picture: false
means there is none, so the answer says so and gives the figures from `rows` instead of
describing a drawing that is not there. `summary` is the last thing the model reads, so on a
failure it repeats the instruction in full (`runner.NO_PICTURE`): no picture, no shape, no axis,
no colour, the figures instead. On a drawn chart it names that chart and carries that chart's
own figures, and it ends with "describe only this chart, never one from an earlier turn": a
second chart in a row was answered with the first one's sentence, word for word, on 2026-09-05,
and the cure is leaving nothing to reach back for. The card shows the title, the frame, the
Add to dashboard, and, on demand, the request, the plan, the repairs, the SQL and the rows.

## When the browser refuses anyway

The check judges intent against a stub, so a real layout can still throw on rows the stub was
happy with. The frame posts its error to the card, and the card posts it to
`POST /api/charts/render-failure` (`src/finquery/api/charts.py`), which does two things:

- it **records the failure on the turn**: the stored chart loses its `code` and carries
  `rendered: false`, the frame's message and the reason. A reload shows the failed card, and no
  later reading of that turn can claim a chart that was never on screen;
- it runs **one retry** through `run_chart` with the same request and hints. The sub-agent is
  not deterministic, so a second definition usually draws; when it does, it replaces the chart
  on the turn and the card swaps its content.

One retry per chart, ever: the recorded failure is the flag, so a second report only records.
