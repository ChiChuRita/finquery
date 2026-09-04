"""Drawing a chart the user can trust.

`runner.run_chart` is the whole path: the chart sub-agent plans the shape on the fast slot, the
query sub-agent supplies the rows, the sub-agent writes a chart definition in plain JavaScript,
and `selfcheck` compiles and judges it in-process before the browser ever sees it. The chat
agent's `chart` tool is a thin wrapper around it.

The contract between the generated code and the browser runtime is documented in
`docs/chart-runtime.md`.
"""

from finquery.chart.runner import ATTEMPTS, NO_DATA, ChartOutcome, run_chart
from finquery.chart.selfcheck import GLOBAL_NAMES, CheckResult, check_chart_code
from finquery.chart.shapes import MAX_SLICES, SHAPE_NAMES, SHAPES, Shape
from finquery.chart.subagent import ChartPlan, code_prompt, plan_prompt, write_code, write_plan

__all__ = [
    "ATTEMPTS",
    "GLOBAL_NAMES",
    "MAX_SLICES",
    "NO_DATA",
    "SHAPES",
    "SHAPE_NAMES",
    "ChartOutcome",
    "ChartPlan",
    "CheckResult",
    "Shape",
    "check_chart_code",
    "code_prompt",
    "plan_prompt",
    "run_chart",
    "write_code",
    "write_plan",
]
