"""The chart shapes and what each one has to look like.

One table, read by three callers: the plan prompt (which shapes exist), the code prompt (which
example and which rules a shape gets) and the self-check (what to verify). A new shape needs a
row here, an example in `subagent.EXAMPLES`, a label in `frontend/src/components/chart-tool.tsx`
and, when its geometry has rules of its own the way the doughnut and the sankey do, a branch in
`selfcheck._shape_findings`.

The three flags on a row are deliberately not one flag, and `may_series` is the fourth: what a
shape must do (`series`), what it may do (`may_series`), what its rows must cross (`crossed`)
and what its mark brings to the euro axis (`zero_from_mark`) are four different questions.
`docs/chart-runtime.md` says the same in prose.
"""

from dataclasses import dataclass
from typing import Literal, get_args

# The two languages a request arrives in. It is a decision of the plan pass rather than of the
# data: an English question about a German household still gets an English caption, and the
# frame writes the month labels in it (review of 2026-09-04: "Jan 25 ... Dez 25" under an
# English title).
Language = Literal["de", "en"]

Shape = Literal[
    "line",
    "area",
    "bar",
    "bar_horizontal",
    "bar_grouped",
    "bar_stacked",
    "doughnut",
    "sankey",
]
SHAPE_NAMES: tuple[Shape, ...] = get_args(Shape)

# The marks that carry data. `link`, `rect` and `text` only ever appear inside a sankey, so they
# are not part of a shape's signature. `ruleY` is one of them because a shape that may not carry
# a reference line has to say so: the check refuses a family mark a shape neither requires nor
# allows, which is how a rule across a doughnut is caught (ticket 52).
FAMILY_MARKS = ("lineY", "areaY", "barY", "barX", "radialArc", "sankeyDiagram", "ruleY")

# The reference line, `ruleY`, is allowed on the shapes that have a euro axis to draw it across
# and one figure per position to compare it with. One per chart, and its value is computed from
# the rows in the code, never typed (`selfcheck._rule_findings`).
MAX_RULES = 1

MAX_SLICES = 6

# The palette the theme hands the frame is six colours long, and a seventh series would reuse
# the first one, so two categories in the same chart would share a colour. That is the ceiling
# on every shape that separates its data by colour.
MAX_SERIES = 6


@dataclass(frozen=True)
class ShapeRule:
    """What a shape means, for the prompt and for the check."""

    purpose: str
    """One line the plan prompt shows so the model can pick between shapes."""
    required: tuple[str, ...]
    """Marks that must be called."""
    also_allowed: tuple[str, ...] = ()
    """Further family marks the shape may use (an area may draw its own outline)."""
    value_axis: Literal["x", "y"] | None = None
    """The axis carrying euros: it gets the grid and the EUR tick format."""
    category_axis: Literal["x", "y"] | None = None
    """The axis carrying the category or the month."""
    series: bool = False
    """True when the shape *must* separate its data by colour, so it needs a `color` (or `z`)
    channel and a legend. A doughnut does that with its slices, a grouped bar with its groups."""
    may_series: bool = False
    """True when the shape *may* carry a series and reads fine without one. A line over one
    figure per month is a line; the same line over five grocery stores is five strokes and a
    legend, from rows that come long (month, name, figure). Kept apart from `series` because
    nothing here is missing when a line carries one column of euros, and apart from `crossed`
    because the rows may be sparse: a store with no booking in March is a gap in one stroke,
    not a chart that cannot be drawn (ticket 50)."""
    crossed: bool = False
    """True when the shape needs two dimensions that really cross: one figure per (position,
    series) pair. Only the grouped and stacked bars do, which is why this is not `series`."""
    grouped: bool = False
    """True when the bars must sit side by side (`layout: group()`)."""
    zero_from_mark: bool = False
    """True when the mark itself baselines at zero, so the euro axis needs no domain of its own.
    Bars and areas do; a line does not, which is how a 25 percent range once read as a cliff."""


SHAPES: dict[Shape, ShapeRule] = {
    "line": ShapeRule(
        purpose=(
            f"a figure over ordered months or days, or one line per name when the request names "
            f"several of them, at most {MAX_SERIES}"
        ),
        required=("lineY",),
        also_allowed=("ruleY",),
        value_axis="y",
        category_axis="x",
        may_series=True,
    ),
    "area": ShapeRule(
        purpose=(
            f"a running total or a filled trend over months, or one band per name when the "
            f"request names several of them, at most {MAX_SERIES}"
        ),
        required=("areaY",),
        also_allowed=("lineY", "ruleY"),
        value_axis="y",
        category_axis="x",
        may_series=True,
        zero_from_mark=True,
    ),
    "bar": ShapeRule(
        purpose=(
            "one figure per named category or month, up to about twelve of them, and the figure "
            "may be negative, which draws the bar below the zero line"
        ),
        required=("barY",),
        also_allowed=("ruleY",),
        value_axis="y",
        category_axis="x",
        zero_from_mark=True,
    ),
    "bar_horizontal": ShapeRule(
        purpose="a ranking with long labels, such as the top merchants",
        required=("barX",),
        value_axis="x",
        category_axis="y",
        zero_from_mark=True,
    ),
    "bar_grouped": ShapeRule(
        purpose=(
            f"two dimensions side by side, month by category, or one period against another by "
            f"category, at most {MAX_SERIES} groups"
        ),
        required=("barY",),
        value_axis="y",
        category_axis="x",
        series=True,
        crossed=True,
        grouped=True,
        zero_from_mark=True,
    ),
    "bar_stacked": ShapeRule(
        purpose=f"the same two dimensions when the total matters, at most {MAX_SERIES} groups",
        required=("barY",),
        value_axis="y",
        category_axis="x",
        series=True,
        crossed=True,
        zero_from_mark=True,
    ),
    "doughnut": ShapeRule(
        purpose=f"a share of a whole with at most {MAX_SLICES} slices",
        required=("radialArc",),
        series=True,
    ),
    "sankey": ShapeRule(
        purpose="a flow from sources to targets, such as income into categories",
        required=("sankeyDiagram",),
    ),
}

SHAPE_MENU = "\n".join(f"- {name}: {rule.purpose}" for name, rule in SHAPES.items())
