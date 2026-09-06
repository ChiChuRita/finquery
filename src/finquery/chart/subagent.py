"""The chart sub-agent: two passes on the fast slot, both forced single tools.

Pass one plans (shape, title, columns and the data question). Pass two writes the chart
definition as a JavaScript function body over the allowlisted globals. Both prompts are pure
functions of their input, so the later adapter training can rebuild the exact text the model saw
next to what it wrote (ADR 0002 pins sub-agents to the fast slot).

The contract the second pass writes against is documented for humans in `docs/chart-runtime.md`
and enforced by `finquery.chart.selfcheck`.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.chart.selfcheck import SAMPLE_ROWS
from finquery.chart.shapes import MAX_SERIES, MAX_SLICES, SHAPE_MENU, SHAPE_NAMES, Language, Shape
from finquery.query import QueryContext, profile_facts

PLAN_INSTRUCTIONS = """\
You plan one chart for a personal-finance assistant. You are given a request and the shape of
one household's bank transactions. Call `chart_plan` exactly once. You never explain and never
answer the request in words: the plan is the answer.
"""

PLAN_RULES = f"""\
Rules:
- Decide `language` first, and decide it from the request alone: a request written in English is
  `en` even though this household's categories, merchants and account are German. It is `de`
  only when the request itself is German.
- Pick the shape that makes the comparison the request asks for the most direct one to read.
  When the request names a shape, use it unless it cannot carry the data.
- The title is a short caption without any figure in it, written in `language`. An English
  request never gets a German caption.
- The question is the data question standing on its own: name the period, the topic and the
  grouping, and ask for exactly the columns you list. The SQL writer sees neither the request
  nor this plan.
- Spending is a positive figure in euros. Name the euro column total_eur unless something else
  reads better.
- A series over time asks for the period the request named, ordered, one row per period:
  `month` as 'YYYY-MM' for months and days, a `quarter` column as '2025-Q1' when the request
  says quarters. A chart captioned by quarter never has months along its axis.
- bar or bar_horizontal: one row per category or merchant, ordered by the figure, at most twelve.
  A merchant is named by its enriched `title` (Edeka, Amazon), never by the raw booking text, so
  ask for `coalesce(title, counterparty, description)`: those names are short enough to sit
  under an axis and inside a legend.
- bar_grouped or bar_stacked: three columns in this order, the month, the group name and the
  euro figure (`month`, `topic`, `total_eur`), one row per month and group, and never two rows
  with the same month and group. The euro figure is always the last of the three.
  The group column holds names and never a second euro column: two figures in the same row
  cannot be drawn side by side, so income against spending is one row per month and per name,
  from a UNION of the two.
  Name that column `topic`, never `category`: an alias that reuses a view column name breaks
  the grouping. The group itself always comes from the household's own `category` column, with
  the uncategorized bookings as one 'Needs review' bucket; never ask for a grouping derived
  from the booking text.
  When the request names the categories it wants, ask for those by name and for nothing else.
  When it asks for all of them, ask for all of them under their own names: never ask for an
  'Other' or 'Sonstige' group and never ask for the largest few. A chart has {MAX_SERIES}
  colours and the app itself keeps the {MAX_SERIES - 1} largest and sums the rest, after the
  query, where summing is arithmetic rather than a rewritten statement.
- doughnut: at most {MAX_SLICES} rows, so ask for the largest {MAX_SLICES - 1} plus a rest row
  when there are more categories than that. A rest row that would hold most of the money says
  nothing, so ask for the largest {MAX_SLICES} instead when a handful of buckets carry the
  spending.
- sankey: one row per flow with the columns source, target and amount_eur. Every amount is a
  positive figure and no row may miss a source or a target, so ask for the household's income as
  a single source named in `language` ('Einkommen' or 'Income') flowing into the spending
  groups, or for the income streams by name. One picture is one flow: never two names for the
  same thing, and never a second flow beside the first.
  Say in the question that the source and the target of a row must differ and that no total row
  belongs in the result: a row from Income into Income is a flow into itself, which a sankey
  refuses, and "where does my income go" asked plainly is exactly how one gets written.
"""

# Two worked plans, drawn from the training half of the chart benchmark (13-doughnut-categories-en
# and 10-quarter-groups-de, both judged correct on 2026-09-05). They are the two decisions the
# small model gets wrong most: the language of an English request about German data, and a
# request naming quarters that comes back with months along its axis.
PLAN_EXAMPLES = """\
Two worked plans:

Request: Show the share of my 2025 spending by category as a doughnut.
reasoning:
the request is written in English, so language en, whatever language the data is in
it asks how one whole splits up, and it names the doughnut
the buckets are the household's own categories, so one row per category
the columns are the name and the euro figure, the figure last
-> shape doughnut, language en, title "Spending by category in 2025",
   columns topic, total_eur,
   question "the five largest spending categories of 2025 with their totals, one row per
   category, columns topic and total_eur"

Request: Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte Balken.
reasoning:
the request is German, so language de
two topics are compared over four quarters, so two dimensions that cross
grouped bars put the two side by side per quarter, which is what the request names
the request says quarters, so the position column is a quarter and never a month
-> shape bar_grouped, language de, title "Lebensmittel und Essengehen pro Quartal",
   columns quarter, topic, total_eur,
   question "spending on Groceries and on Dining per quarter of 2025, one row per quarter and
   category, columns quarter as '2025-Q1', topic and total_eur"
"""

CONTRACT = """\
You write the body of one JavaScript function. It receives `data`, an array of row objects that
a query already returned, and must `return` a TanStack Charts definition. There are no imports,
no JSX, no `await` and no browser APIs. These globals are all that exist:

  defineChart(spec)              the definition; call it once and return it
  lineY, areaY, barY, barX       Cartesian marks, called as (rows, options)
  link, rect, text               the child marks of a sankey
  stack(), group()               bar layouts
  polar(options)                 the radial container
  pie(rows, { value })           turns rows into angular slices
  radialArc(slices, options)     draws slices, only inside polar
  sankeyDiagram(options)         the flow layout
  scaleLinear                    the euro axis
  scaleBand, scalePoint          the category axis (bars use band, lines use point)
  scaleOrdinal                   a fixed colour mapping
  colorLegend(options)           the legend
  tooltip                        the tooltip extension
  palette                        the theme colours, palette[0] first
  eur(value)                     "1.234,56 €", for tooltips
  eurShort(value)                a short euro label, for axis ticks
  monthShort('2025-01')          "Jan 25", for month axes

House rules, all checked before the user sees the chart:
- `scales` always declares both `x` and `y`. `null` is how you say an axis is unused.
- The euro axis is `scaleLinear` with `nice: true`, `grid: true` and
  `axis: { ticks: { format: eurShort } }`. The other axis never carries a grid.
- `scaleLinear` on its own is the factory and the chart infers its domain from the data.
  `scaleLinear()` is a configured scale that keeps its own domain, which is 0 to 1 until you
  give it one, so never write `scaleLinear()` or `scaleLinear().nice(true)` on their own.
- The euro axis includes zero. Bars and areas rest on it by themselves, so their euro axis is
  the bare factory `scale: scaleLinear` and never names a domain: a stack's total is taller than
  any single value in the rows, and the chart works that out for itself.
- A line has no baseline of its own, so a line, and only a line, gives its euro axis
  `scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)])` over the
  figures it draws, otherwise a change of a few percent is drawn as a cliff. Write that
  configured scale itself, never `() => scaleLinear().domain(...)`: a zero-argument factory has
  its domain inferred again and yours is thrown away.
- Month and day values look like 2025-01 and 2025-03-14, so their axis gets
  `axis: { ticks: { format: monthShort } }`, and they may be thinned:
  `tickLabels: { thin: { minGap: 6, priority: 'ends' } }`. They are never rotated.
- A category axis carries names, and a name cannot be guessed from its neighbours, so no label
  may be dropped: `axis: { tickLabels: { thin: false } }`. Names on the x axis also need
  `rotate`, about -28 degrees, once there are more than six of them or one of them is long.
- Bars stay thin: `maxThickness: 32` on `barY` and `barX`.
- Every chart carries `tooltip: { use: tooltip, format: (point) => ... }` and formats euros
  with `eur`.
- A legend only when there is more than one series, and then
  `color: { legend: colorLegend({ placement: 'bottom' }) }`.
- Never set a height, a width, a title or a theme: the card owns all four.
- Every value is read from `data` through a channel name such as `y: 'total_eur'`. Never type a
  number into the code. A zero baseline is not a value, so `Math.min(0, ...)` is fine.
- Every column a channel names is one of the columns listed under "The query returned" below.
  The worked examples have columns of their own, and copying a name out of an example that your
  rows do not carry draws nothing at all.
- A quarter (`2025-Q1`) or any other label is a name and not a month: no `monthShort` on it, and
  no label of it may be dropped.
- Keep it short: no comments, no helper functions you do not need. Answer with the body itself,
  never wrapped in `function (data) { ... }` and never inside a markdown fence.
"""


@dataclass(frozen=True)
class Example:
    """One worked example of the code pass: the rows it was written for, and what it did.

    `columns` is the first line the model reads, so it sees at once that these column names
    belong to this example and not to its own rows. `reasoning` is the same short field the
    answer carries, filled the way the answer should fill it.
    """

    columns: str
    reasoning: str
    code: str

    def as_prompt(self) -> str:
        return f"Columns: {self.columns}\nreasoning:\n{self.reasoning}\ncode:\n{self.code}"


EXAMPLES: dict[Shape, tuple[Example, ...]] = {
    "line": (
        Example(
            columns="month, total_eur",
            reasoning=(
                "the shape is line, so the mark is lineY over the rows\n"
                "the columns are month and total_eur, and total_eur holds the numbers\n"
                "months on x with monthShort, euros on y\n"
                "a line brings no baseline of its own, so its euro axis names the domain over the amounts"
            ),
            code="""\
const amounts = data.map((row) => row.total_eur);
return defineChart({
  marks: [
    lineY(data, { x: 'month', y: 'total_eur', stroke: palette[0], strokeWidth: 2.25, points: true }),
  ],
  scales: {
    x: {
      scale: () => scalePoint().padding(0.06),
      axis: { ticks: { format: monthShort }, tickLabels: { thin: { minGap: 6, priority: 'ends' } } },
    },
    y: {
      scale: scaleLinear().domain([Math.min(0, ...amounts), Math.max(0, ...amounts)]),
      nice: true,
      grid: true,
      axis: { ticks: { format: eurShort } },
    },
  },
  tooltip: {
    use: tooltip,
    format: (point) => monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});""",
        ),
    ),
    "area": (
        Example(
            columns="month, cumulative_eur",
            reasoning=(
                "the shape is area, so areaY draws the band and lineY its edge\n"
                "the columns are month and cumulative_eur, and cumulative_eur holds the numbers\n"
                "months on x with monthShort, euros on y\n"
                "an area rests on zero, so its euro axis is the bare scaleLinear factory"
            ),
            code="""\
return defineChart({
  marks: [
    areaY(data, { x: 'month', y: 'cumulative_eur', fill: palette[0], fillOpacity: 0.18 }),
    lineY(data, { x: 'month', y: 'cumulative_eur', stroke: palette[0], strokeWidth: 2 }),
  ],
  scales: {
    x: {
      scale: () => scalePoint().padding(0.02),
      axis: { ticks: { format: monthShort }, tickLabels: { thin: { minGap: 6, priority: 'ends' } } },
    },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => monthShort(point.datum.month) + ': ' + eur(point.datum.cumulative_eur),
  },
});""",
        ),
        Example(
            columns="quarter, total_eur",
            reasoning=(
                "the shape is area, so areaY draws the band and lineY its edge\n"
                "the columns are quarter and total_eur, and total_eur holds the numbers\n"
                "a quarter reads 2025-Q1, which is a name and not a month, so no monthShort and no label dropped\n"
                "an area rests on zero, so its euro axis is the bare scaleLinear factory"
            ),
            code="""\
return defineChart({
  marks: [
    areaY(data, { x: 'quarter', y: 'total_eur', fill: palette[0], fillOpacity: 0.18 }),
    lineY(data, { x: 'quarter', y: 'total_eur', stroke: palette[0], strokeWidth: 2 }),
  ],
  scales: {
    x: { scale: () => scalePoint().padding(0.06), axis: { tickLabels: { thin: false } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.quarter + ': ' + eur(point.datum.total_eur),
  },
});""",
        ),
    ),
    "bar": (
        Example(
            columns="category, total_eur",
            reasoning=(
                "the shape is bar, so the mark is barY\n"
                "the columns are category and total_eur, and total_eur holds the numbers\n"
                "names on x on a band scale, no label dropped, tilted once they are many or long\n"
                "a bar rests on zero, so its euro axis is the bare scaleLinear factory"
            ),
            code="""\
const names = data.map((row) => String(row.category));
const tilt = names.length > 6 || names.some((name) => name.length > 9) ? -28 : 0;
return defineChart({
  marks: [
    barY(data, { x: 'category', y: 'total_eur', fill: palette[0], radius: 4, maxThickness: 32 }),
  ],
  scales: {
    x: { scale: () => scaleBand().padding(0.26), axis: { tickLabels: { rotate: tilt, thin: false } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.category + ': ' + eur(point.datum.total_eur),
  },
});""",
        ),
    ),
    "bar_horizontal": (
        Example(
            columns="merchant, total_eur",
            reasoning=(
                "the shape is bar_horizontal, so the mark is barX and nothing else\n"
                "the columns are merchant and total_eur, and total_eur holds the numbers\n"
                "barX draws sideways, so the euro column is x and the names are y\n"
                "scales.x is therefore the euro axis and scales.y the band of names, none dropped"
            ),
            code="""\
return defineChart({
  marks: [
    barX(data, { x: 'total_eur', y: 'merchant', fill: palette[0], radius: 4, maxThickness: 32 }),
  ],
  scales: {
    x: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
    y: { scale: () => scaleBand().padding(0.22), axis: { tickLabels: { thin: false } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.merchant + ': ' + eur(point.datum.total_eur),
  },
});""",
        ),
    ),
    "bar_grouped": (
        Example(
            columns="month, topic, total_eur",
            reasoning=(
                "the shape is bar_grouped, so barY carries a series and layout: group()\n"
                "the columns are month, topic and total_eur, and total_eur holds the numbers\n"
                "topic is the series, so it is the z and the color channel and it needs a legend\n"
                "months on x on a band scale, euros on y from the bare factory"
            ),
            code="""\
const short = (name) => (name.length > 18 ? name.slice(0, 17) + '.' : name);
return defineChart({
  marks: [
    barY(data, { x: 'month', y: 'total_eur', z: 'topic', color: (row) => short(row.topic), layout: group({ padding: 0.12 }), radius: 2, maxThickness: 32 }),
  ],
  scales: {
    x: {
      scale: () => scaleBand().padding(0.2),
      axis: { ticks: { format: monthShort }, tickLabels: { thin: { minGap: 6, priority: 'ends' } } },
    },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.topic + ' ' + monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});""",
        ),
    ),
    "bar_stacked": (
        Example(
            columns="month, topic, total_eur",
            reasoning=(
                "the shape is bar_stacked, so barY carries a series and no layout\n"
                "the columns are month, topic and total_eur, and total_eur holds the numbers\n"
                "topic is the series, so it is the z and the color channel and it needs a legend\n"
                "a stack is taller than any single row, so the euro axis names no domain"
            ),
            code="""\
const short = (name) => (name.length > 18 ? name.slice(0, 17) + '.' : name);
return defineChart({
  marks: [
    barY(data, { x: 'month', y: 'total_eur', z: 'topic', color: (row) => short(row.topic), radius: 2, maxThickness: 32 }),
  ],
  scales: {
    x: {
      scale: () => scaleBand().padding(0.22),
      axis: { ticks: { format: monthShort }, tickLabels: { thin: { minGap: 6, priority: 'ends' } } },
    },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.topic + ' ' + monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});""",
        ),
    ),
    "doughnut": (
        Example(
            columns="merchant, total_eur",
            reasoning=(
                "the shape is doughnut, so pie allocates the slices and radialArc draws them\n"
                "the columns are merchant and total_eur, and total_eur is the value pie reads\n"
                "the slices are the series, so color and key both name merchant, the column of names\n"
                "a doughnut has no axes, so scales.x and scales.y are null and the legend is on"
            ),
            code="""\
const short = (name) => (name.length > 18 ? name.slice(0, 17) + '.' : name);
const slices = pie(data, { value: 'total_eur' });
return defineChart({
  marks: [
    polar({
      inset: 6,
      radiusRatio: 0.92,
      marks: [
        radialArc(slices, {
          innerRadius: ({ radius }) => radius * 0.62,
          cornerRadius: 3,
          color: (slice) => short(slice.merchant),
          key: 'merchant',
        }),
      ],
      scales: { angle: null, radius: null },
    }),
  ],
  scales: { x: null, y: null },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.merchant + ': ' + eur(point.datum.total_eur),
  },
});""",
        ),
        Example(
            columns="label, total_eur",
            reasoning=(
                "the shape is doughnut, so pie allocates the slices and radialArc draws them\n"
                "the columns here are label and total_eur, so nothing reads merchant or category\n"
                "the slices are the series, so color and key both name label, the column of names\n"
                "three slices, so no rest slice and no fold: the rows are drawn as they came"
            ),
            code="""\
const slices = pie(data, { value: 'total_eur' });
return defineChart({
  marks: [
    polar({
      inset: 6,
      radiusRatio: 0.92,
      marks: [
        radialArc(slices, {
          innerRadius: ({ radius }) => radius * 0.62,
          cornerRadius: 3,
          color: (slice) => slice.label,
          key: 'label',
        }),
      ],
      scales: { angle: null, radius: null },
    }),
  ],
  scales: { x: null, y: null },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.label + ': ' + eur(point.datum.total_eur),
  },
});""",
        ),
    ),
    "sankey": (
        Example(
            columns="source, target, amount_eur",
            reasoning=(
                "the shape is sankey, so sankeyDiagram lays the flow out\n"
                "the columns are source, target and amount_eur, and amount_eur holds the numbers\n"
                "the nodes are the names of both ends, collected from the rows themselves\n"
                "the child marks read the layout's own fields (x0, x1, y0, y1, key), never a column of the query"
            ),
            code="""\
const names = [];
data.forEach((row) => {
  if (names.indexOf(row.source) === -1) names.push(row.source);
  if (names.indexOf(row.target) === -1) names.push(row.target);
});
const nodes = names.map((name) => ({ id: name }));
return defineChart({
  marks: [
    sankeyDiagram({
      nodes: nodes,
      links: data,
      nodeKey: 'id',
      source: 'source',
      target: 'target',
      value: 'amount_eur',
      align: 'justify',
      nodeWidth: 14,
      nodePadding: 16,
      inset: 8,
      marks: (context) => [
        link(context.links, {
          x1: 'x1',
          y1: 'y1',
          x2: 'x2',
          y2: 'y2',
          key: 'key',
          stroke: palette[1],
          strokeOpacity: 0.3,
          strokeWidth: (flow) => Math.max(1, flow.width),
          lineCap: 'butt',
        }),
        rect(context.nodes, { x1: 'x0', x2: 'x1', y1: 'y0', y2: 'y1', key: 'key', fill: palette[0], inset: 0 }),
        text(context.nodes, {
          x: 'x',
          y: 'y',
          key: 'key',
          text: (node) => node.data.id,
          dx: (node) => (node.depth === 0 ? 12 : -12),
          anchor: (node) => (node.depth === 0 ? 'start' : 'end'),
          fontSize: 11,
        }),
      ],
    }),
  ],
  scales: { x: null, y: null },
  guides: false,
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.source + ' to ' + point.datum.target + ': ' + eur(point.datum.amount_eur),
  },
});""",
        ),
    ),
}


CODE_INSTRUCTIONS = """\
You write TanStack Charts definitions for a personal-finance assistant. Call `chart_code`
exactly once with the function body. You never explain and never write prose: the code is the
answer.
"""


class ChartPlan(BaseModel):
    """The shape of the chart and the data it needs, decided before any SQL is written.

    `reasoning` is first on purpose: a small model that writes the shape before it has read the
    request picks the shape of the last chart it saw, so the field it fills first is the one
    that makes it read (ticket 42).
    """

    reasoning: str = Field(
        description=(
            "Three to five very short steps, one per line, written before you decide anything "
            "else: the language of the request, what it compares, the shape that reads that "
            "comparison, the columns the query has to return, the period it covers. No prose."
        )
    )
    shape: Shape = Field(description="One of: " + ", ".join(SHAPE_NAMES))
    language: Language = Field(
        description=(
            "The language of the request itself, 'de' or 'en', never the language of the "
                "household's data. The title and the chart's month labels are written in it."
        )
    )
    title: str = Field(description="A short caption without figures, written in `language`.")
    question: str = Field(description="The data question for the SQL writer, standing on its own.")
    columns: list[str] = Field(description="The column names the query must return, in order.")

    def as_text(self) -> str:
        """The plan as the reasoning panel shows it, its own steps included."""
        steps = " ".join(line.strip() for line in self.reasoning.splitlines() if line.strip())
        return (
            f"Chart plan: {self.shape}, titled \"{self.title}\", over "
            f"{', '.join(self.columns)}. {steps}"
        )


class ChartCode(BaseModel):
    """The chart definition as a JavaScript function body, with the steps behind it."""

    reasoning: str = Field(
        description=(
            "Three to five very short steps, one per line, written before the code: the shape "
            "and the mark it needs, the column names from the rows above and which one holds "
            "the numbers, what each axis is. On a repair, the first step says what you changed."
        )
    )
    code: str = Field(description="The body of a function of `data` that returns defineChart(...).")


plan_agent = Agent(
    instructions=PLAN_INSTRUCTIONS,
    output_type=ToolOutput(ChartPlan, name="chart_plan"),
    name="finquery-chart-plan",
)

code_agent = Agent(
    instructions=CODE_INSTRUCTIONS,
    output_type=ToolOutput(ChartCode, name="chart_code"),
    name="finquery-chart-code",
)


PREVIOUS_VERSION = """\
This chart already exists and the user is changing it. The version on their dashboard:
- title: "{title}"
- plan: {plan}
- statement: {sql}

The request below says what to change about it. Change that and keep the rest: the same topic
and the same period unless the request names another, and the same shape unless it asks for
another one."""


def previous_hint(*, title: str, plan: str, sql: str) -> str:
    """What an edit hands the planning pass about the chart it is editing."""
    return PREVIOUS_VERSION.format(title=title.strip(), plan=plan.strip(), sql=sql.strip())


def plan_prompt(
    request: str,
    context: QueryContext,
    *,
    hints: str | None = None,
    previous: str | None = None,
) -> str:
    """Everything the planning pass sees. Pure function, reused by training.

    `previous` is the one section only an edit carries (`previous_hint`): a chart that is being
    changed rather than made, so the pass keeps what the request does not mention.
    """
    sections = [
        f"Shapes:\n{SHAPE_MENU}",
        PLAN_RULES,
        PLAN_EXAMPLES,
        profile_facts(context),
    ]
    if previous:
        sections.append(previous)
    sections.append(f"Request: {request.strip()}")
    if hints:
        sections.append(f"The assistant adds: {hints.strip()}")
    return "\n\n".join(sections)


def _column_brief(column: str, rows: list[dict[str, Any]]) -> str:
    """One line per column: what is in it, so the channels are chosen from data, not from hope."""
    values = [row.get(column) for row in rows]
    present = [value for value in values if value is not None]
    blank = " and some rows have none" if len(present) < len(values) else ""
    numbers = [value for value in present if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if numbers and len(numbers) == len(present):
        return f"- {column}: numbers from {min(numbers)} to {max(numbers)}{blank}"
    distinct = list(dict.fromkeys(str(value) for value in present))
    shown = ", ".join(repr(value) for value in distinct[:4]) or "none"
    if len(distinct) <= 1:
        return f"- {column}: one value only ({shown}), so it cannot be a series{blank}"
    return f"- {column}: {len(distinct)} values, for instance {shown}{blank}"


def _rows_brief(columns: list[str], rows: list[dict[str, Any]]) -> str:
    lines = [f"The query returned {len(rows)} rows:"]
    lines.extend(_column_brief(column, rows) for column in columns)
    lines.append("The first rows:")
    lines.extend(
        ", ".join(f"{column}={row.get(column)!r}" for column in columns) for row in rows[:SAMPLE_ROWS]
    )
    return "\n".join(lines)


def code_prompt(
    plan: ChartPlan,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    previous: ChartCode | None = None,
    findings: str | None = None,
) -> str:
    """Everything the code pass sees, including a repair round. Pure function."""
    examples = list(EXAMPLES[plan.shape])
    if plan.shape != "line":
        examples.extend(EXAMPLES["line"])
    sections = [
        CONTRACT,
        "Worked examples:\n\n" + "\n\n".join(example.as_prompt() for example in examples),
        _rows_brief(columns, rows),
        # The plan's own reasoning stays out: it is about the request, and this pass writes from
        # the shape, the title and the rows it was given. What it needs of the plan is here.
        f"Chart to write: shape {plan.shape}, titled \"{plan.title}\".",
    ]
    if previous is not None and findings is not None:
        sections.append(repair_prompt(previous, findings))
    return "\n\n".join(sections)


def repair_prompt(previous: ChartCode, findings: str) -> str:
    """A repair round: the last answer, what the check found, and the correction asked for.

    A round that only says "it failed, write it again" gets a chart written from scratch, which
    is how the same finding came back twice in a row on 2026-09-05 (07-top-merchants-en, three
    rounds, the same domain-in-a-factory finding each time). So the model is shown its own
    reasoning and its own code, told which lines are wrong, and asked for a correction of them
    rather than for another chart.
    """
    return (
        "Your last answer did not pass the check. This is a correction of it, not a fresh "
        "start: keep every line the findings do not mention.\n\n"
        f"Your reasoning was:\n{previous.reasoning.strip()}\n\n"
        f"Your code was:\n{previous.code.strip()}\n\n"
        f"The check found:\n{findings.strip()}\n\n"
        "Answer again with the corrected reasoning and the corrected code. The first line of "
        "the reasoning says what you changed and why, one line per finding."
    )


async def write_plan(
    model: Model,
    request: str,
    context: QueryContext,
    *,
    hints: str | None = None,
    previous: str | None = None,
    model_settings: ModelSettings | None = None,
) -> ChartPlan:
    """Ask the fast slot for the shape, the title and the data question."""
    result = await plan_agent.run(
        plan_prompt(request, context, hints=hints, previous=previous),
        model=model,
        model_settings=model_settings,
    )
    return result.output


async def write_code(
    model: Model,
    plan: ChartPlan,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    previous: ChartCode | None = None,
    findings: str | None = None,
    model_settings: ModelSettings | None = None,
) -> ChartCode:
    """Ask the fast slot for one chart definition, or for a repair of the last one.

    Returns the answer whole, reasoning included: the runner narrates those lines into the
    thinking panel, which is the one place a step already renders them.
    """
    result = await code_agent.run(
        code_prompt(plan, columns, rows, previous=previous, findings=findings),
        model=model,
        model_settings=model_settings,
    )
    return result.output.model_copy(update={"code": result.output.code.strip()})
