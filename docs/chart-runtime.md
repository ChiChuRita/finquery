# The chart runtime contract

A chart in FinQuery is a piece of JavaScript the chart sub-agent writes, checked in-process and
then rendered in a sandboxed frame. This page is that contract: the globals the code may use,
the shapes it may draw, the house rules it must obey and the messages between the card and the
frame. It is the reference for `src/finquery/chart/` (which enforces it), for
`frontend/src/chart-runtime/` (which implements it) and for the later generation of training
data for the chart adapter, which has to produce exactly this dialect.

## The code

The sub-agent returns **the body of one function**. It receives `data`, an array of row objects
that a query already returned, and must `return` a TanStack Charts definition:

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

Twenty-four names, in the order the runtime and the check pass them. TanStack Charts is pinned
to 0.16.0; every name below is a public export of that version.

| Global                                       | From                                | What it is                              |
| -------------------------------------------- | ----------------------------------- | --------------------------------------- |
| `defineChart(spec)`                          | `@tanstack/charts`                  | The definition; called once, returned   |
| `lineY`, `areaY`, `barY`, `barX`             | `@tanstack/charts`                  | Cartesian marks, `(rows, options)`      |
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

There is no time scale in TanStack Charts, which is why months are categories on a band or point
scale and `monthShort` formats their labels. It is the one global that is not the same function
every time: the frame builds it from the chart's `language`, so an English question gets "Mar 25"
and a German one "Mär 25", and a value that carries a day ('2025-03-14') is labelled with the day
rather than with its month nineteen times over. Money stays German in both: `eur` and `eurShort`
are always `de-DE`, because the product writes money that way whatever the answer language is.

## The shapes

| Shape            | Marks                                | For                                                |
| ---------------- | ------------------------------------ | -------------------------------------------------- |
| `line`           | `lineY`                              | a figure over ordered months or days               |
| `area`           | `areaY` (+ optional `lineY` outline) | a running total or a filled trend                  |
| `bar`            | `barY`                               | one figure per named category                      |
| `bar_horizontal` | `barX`                               | a ranking with long labels                         |
| `bar_grouped`    | `barY` + `layout: group()` + series  | two dimensions side by side, at most six groups    |
| `bar_stacked`    | `barY` + series                      | the same two dimensions when the total matters     |
| `doughnut`       | `polar` + `pie` + `radialArc`        | a share of a whole, at most six slices             |
| `sankey`         | `sankeyDiagram` + `link`/`rect`/`text` | a flow from sources to targets                   |

A series is a `z` or `color` channel: a column name or an accessor. The table lives in
`src/finquery/chart/shapes.py`, which the plan prompt, the code prompt and the check all read.
Three flags on a row carry more than the marks do, and they are deliberately not one flag:

- **`series`** means the shape tells its data apart by colour, so it needs a `color` (or `z`)
  channel and a legend. The grouped and stacked bars do; so does a doughnut, whose slices are
  its series. Six colours is the ceiling, because that is how long the theme's palette is: a
  seventh group is painted like the first, and two categories in one picture wearing one colour
  is not a chart anybody can read.
- **`crossed`** means the shape needs two dimensions that really cross, one figure per (position,
  series) pair. Only the grouped and stacked bars do, which is why a doughnut is not downgraded
  to bars when its rows carry a single dimension.
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
  income on top of spending into a total nobody asked for.
- Every chart carries `tooltip: { use: tooltip, format: ... }` and formats euros with `eur`.
- A legend only with more than one series, and then
  `color: { legend: colorLegend({ placement: 'bottom' }) }`.
- The definition sets no `height`, `width`, `title` or `theme`: the card owns all four.
- A doughnut has at most six slices and an `innerRadius`.
- Every column a channel names exists in the rows it was given, and no mark gets an empty array.
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

1. a static scan (forbidden names, data typed into the code);
2. compilation, then one run with the real rows, so a thrown error is a finding;
3. the rules above, over the recorded marks, scales, channels and series.

Two rules are about the rows rather than about the code, so `data_findings(shape, columns,
rows)` judges them before a line is written and no repair round is spent on them:

- a stacked or grouped bar needs **one figure per (position, series) pair**. Two rows for
  2025-01 / Groceries cannot be drawn by any definition, and TanStack says so as "A stack
  requires at most one value for each position and series";
- a sankey needs links that **go somewhere and do not come back**: three columns, so every link
  has both ends, no row flowing from a name into itself, no cycle over the source and target
  columns, and a positive amount on every link. The QuickJS stub applies the same rules to
  whatever graph the code builds, so a definition that assembles its own links is caught too.

A third case is decided on the rows and downgraded rather than refused: a chart the rows cannot
carry becomes plain bars, narrated. A grouped or stacked chart whose rows carry a single series
does, and so does a line or an area over fewer than three points, because a stroke from January
to July says something about the five months the query did not return.

The stub mimics the parts of the library the rules need: `pie` allocates real angles and rejects
a negative value, `sankeyDiagram` validates the graph and calls the `marks` callback with node
and link rows that carry the documented fields (`x0`, `x1`, `y0`, `y1`, `x`, `y`, `key`, `value`,
`data`), and channel accessors are called the way a mark would call them. It never renders: a
browser renders, the check judges intent.

Two repair rounds follow a first failure (`ATTEMPTS = 3`). Each round's findings go back to the
sub-agent with the refused code, and each is narrated into the transcript's thinking panel.

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
the language the month labels are written in.

## The tool result

`run_chart` returns one payload, which is both what the chat agent reads and what the card
renders:

```json
{
  "request": "...", "title": "...", "shape": "line", "language": "en",
  "plan": "Chart plan: line, ...",
  "sql": "SELECT ...", "row_count": 12, "columns": ["month", "total_eur"], "rows": [ ... ],
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
no colour, the figures instead. The card shows the title, the frame, the thumbs and
Regenerate, and, on demand, the request, the plan, the repairs, the SQL and the rows.

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

Regenerate runs this whole path again for the same request through
`POST /api/preferences/chart-alternative`, which is not a chat turn: the second chart lives in
the card, both are shown side by side, and the pick stores the two definitions with the shared
SQL as a preference record (`src/finquery/preferences.py`). That pair is the chart adapter's
training data, which is why the payload carries the plan and the statement and not just the
drawing.
