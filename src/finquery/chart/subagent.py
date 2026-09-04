"""The chart sub-agent: two passes on the fast slot, both forced single tools.

Pass one plans (shape, title, columns and the data question). Pass two writes the chart
definition as a JavaScript function body over the allowlisted globals. Both prompts are pure
functions of their input, so the later adapter training can rebuild the exact text the model saw
next to what it wrote (ADR 0002 pins sub-agents to the fast slot).

The contract the second pass writes against is documented for humans in `docs/chart-runtime.md`
and enforced by `finquery.chart.selfcheck`.
"""

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from finquery.chart.selfcheck import SAMPLE_ROWS
from finquery.chart.shapes import MAX_SLICES, SHAPE_MENU, SHAPE_NAMES, Shape
from finquery.query import QueryContext, profile_facts

PLAN_INSTRUCTIONS = """\
You plan one chart for a personal-finance assistant. You are given a request and the shape of
one household's bank transactions. Call `chart_plan` exactly once. You never explain and never
answer the request in words: the plan is the answer.
"""

PLAN_RULES = f"""\
Rules:
- Pick the shape that makes the comparison the request asks for the most direct one to read.
  When the request names a shape, use it unless it cannot carry the data.
- The title is a short caption without any figure in it, in the language of the request.
- The question is the data question standing on its own: name the period, the topic and the
  grouping, and ask for exactly the columns you list. The SQL writer sees neither the request
  nor this plan.
- Spending is a positive figure in euros. Name the euro column total_eur unless something else
  reads better.
- A series over time asks for `month` formatted as 'YYYY-MM', ordered, one row per month.
- bar or bar_horizontal: one row per category or merchant, ordered by the figure, at most twelve.
- bar_grouped or bar_stacked: three columns, one row per month and group. Name the group column
  `topic`, never `category`: the taxonomy is often empty, so the group is built from the
  merchants and an alias that reuses a view column name breaks the grouping.
- doughnut: at most {MAX_SLICES} rows, so ask for the largest {MAX_SLICES - 1} plus a rest row
  when there are more categories than that.
- sankey: one row per flow with the columns source, target and amount_eur. Every amount is a
  positive figure and no row may miss a source or a target, so ask for the household's income as
  one source ('Einkommen') flowing into the spending groups, or for the income streams by name.
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
- Month values look like 2025-01, so their axis gets `axis: { ticks: { format: monthShort } }`.
- Every chart carries `tooltip: { use: tooltip, format: (point) => ... }` and formats euros
  with `eur`.
- A legend only when there is more than one series, and then
  `color: { legend: colorLegend({ placement: 'bottom' }) }`.
- Never set a height, a width, a title or a theme: the card owns all four.
- Every value is read from `data` through a channel name such as `y: 'total_eur'`. Never type a
  number into the code.
- Keep it short: no comments, no helper functions you do not need.
"""

EXAMPLES: dict[Shape, str] = {
    "line": """\
Columns: month, total_eur
return defineChart({
  marks: [
    lineY(data, { x: 'month', y: 'total_eur', stroke: palette[0], strokeWidth: 2.25, points: true }),
  ],
  scales: {
    x: { scale: () => scalePoint().padding(0.06), axis: { ticks: { format: monthShort } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});""",
    "area": """\
Columns: month, cumulative_eur
return defineChart({
  marks: [
    areaY(data, { x: 'month', y: 'cumulative_eur', fill: palette[0], fillOpacity: 0.18 }),
    lineY(data, { x: 'month', y: 'cumulative_eur', stroke: palette[0], strokeWidth: 2 }),
  ],
  scales: {
    x: { scale: () => scalePoint().padding(0.02), axis: { ticks: { format: monthShort } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => monthShort(point.datum.month) + ': ' + eur(point.datum.cumulative_eur),
  },
});""",
    "bar": """\
Columns: category, total_eur
return defineChart({
  marks: [
    barY(data, { x: 'category', y: 'total_eur', fill: palette[0], radius: 4 }),
  ],
  scales: {
    x: { scale: () => scaleBand().padding(0.26) },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.category + ': ' + eur(point.datum.total_eur),
  },
});""",
    "bar_horizontal": """\
Columns: merchant, total_eur
return defineChart({
  marks: [
    barX(data, { x: 'total_eur', y: 'merchant', fill: palette[0], radius: 4 }),
  ],
  scales: {
    x: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
    y: { scale: () => scaleBand().padding(0.22) },
  },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.merchant + ': ' + eur(point.datum.total_eur),
  },
});""",
    "bar_grouped": """\
Columns: month, category, total_eur
const short = (name) => (name.length > 18 ? name.slice(0, 17) + '.' : name);
return defineChart({
  marks: [
    barY(data, { x: 'month', y: 'total_eur', z: 'category', color: (row) => short(row.category), layout: group({ padding: 0.12 }), radius: 2 }),
  ],
  scales: {
    x: { scale: () => scaleBand().padding(0.2), axis: { ticks: { format: monthShort } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.category + ' ' + monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});""",
    "bar_stacked": """\
Columns: month, category, total_eur
const short = (name) => (name.length > 18 ? name.slice(0, 17) + '.' : name);
return defineChart({
  marks: [
    barY(data, { x: 'month', y: 'total_eur', z: 'category', color: (row) => short(row.category), radius: 2 }),
  ],
  scales: {
    x: { scale: () => scaleBand().padding(0.22), axis: { ticks: { format: monthShort } } },
    y: { scale: scaleLinear, nice: true, grid: true, axis: { ticks: { format: eurShort } } },
  },
  color: { legend: colorLegend({ placement: 'bottom', itemWidth: 150 }) },
  tooltip: {
    use: tooltip,
    format: (point) => point.datum.category + ' ' + monthShort(point.datum.month) + ': ' + eur(point.datum.total_eur),
  },
});""",
    "doughnut": """\
Columns: merchant, total_eur
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
    "sankey": """\
Columns: source, target, amount_eur
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
}

CODE_INSTRUCTIONS = """\
You write TanStack Charts definitions for a personal-finance assistant. Call `chart_code`
exactly once with the function body. You never explain and never write prose: the code is the
answer.
"""


class ChartPlan(BaseModel):
    """The shape of the chart and the data it needs, decided before any SQL is written."""

    shape: Shape = Field(description="One of: " + ", ".join(SHAPE_NAMES))
    title: str = Field(description="A short caption without figures, in the language of the request.")
    question: str = Field(description="The data question for the SQL writer, standing on its own.")
    columns: list[str] = Field(description="The column names the query must return, in order.")
    reason: str = Field(description="One sentence on why this shape answers the request.")

    def as_text(self) -> str:
        """The plan as the reasoning panel shows it."""
        return (
            f"Chart plan: {self.shape}, titled \"{self.title}\", over "
            f"{', '.join(self.columns)}. {self.reason}"
        )


class ChartCode(BaseModel):
    """The chart definition as a JavaScript function body."""

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


def plan_prompt(request: str, context: QueryContext, *, hints: str | None = None) -> str:
    """Everything the planning pass sees. Pure function, reused by training."""
    sections = [
        f"Shapes:\n{SHAPE_MENU}",
        PLAN_RULES,
        profile_facts(context),
        f"Request: {request.strip()}",
    ]
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
    previous_code: str | None = None,
    findings: str | None = None,
) -> str:
    """Everything the code pass sees, including a repair round. Pure function."""
    examples = [EXAMPLES[plan.shape]]
    if plan.shape != "line":
        examples.append(EXAMPLES["line"])
    sections = [
        CONTRACT,
        "Worked examples:\n\n" + "\n\n".join(examples),
        _rows_brief(columns, rows),
        f"Chart to write: shape {plan.shape}, titled \"{plan.title}\". {plan.reason}",
    ]
    if previous_code is not None and findings is not None:
        sections.append(
            "Your previous code did not pass the checks. Write it again, fixing every point.\n\n"
            f"Your code:\n{previous_code.strip()}\n\nFindings:\n{findings}"
        )
    return "\n\n".join(sections)


async def write_plan(
    model: Model,
    request: str,
    context: QueryContext,
    *,
    hints: str | None = None,
    model_settings: ModelSettings | None = None,
) -> ChartPlan:
    """Ask the fast slot for the shape, the title and the data question."""
    result = await plan_agent.run(
        plan_prompt(request, context, hints=hints), model=model, model_settings=model_settings
    )
    return result.output


async def write_code(
    model: Model,
    plan: ChartPlan,
    columns: list[str],
    rows: list[dict[str, Any]],
    *,
    previous_code: str | None = None,
    findings: str | None = None,
    model_settings: ModelSettings | None = None,
) -> str:
    """Ask the fast slot for one chart definition, or for a repair of the last one."""
    result = await code_agent.run(
        code_prompt(plan, columns, rows, previous_code=previous_code, findings=findings),
        model=model,
        model_settings=model_settings,
    )
    return result.output.code.strip()
