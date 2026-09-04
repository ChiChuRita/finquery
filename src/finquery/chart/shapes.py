"""The chart shapes and what each one has to look like.

One table, read by three callers: the plan prompt (which shapes exist), the code prompt (which
example and which rules a shape gets) and the self-check (what to verify). A new shape needs a
row here, an example in `subagent.EXAMPLES`, a label in `frontend/src/components/chart-tool.tsx`
and, when its geometry has rules of its own the way the doughnut and the sankey do, a branch in
`selfcheck._shape_findings`.
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
# are not part of a shape's signature.
FAMILY_MARKS = ("lineY", "areaY", "barY", "barX", "radialArc", "sankeyDiagram")

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
    """True when the shape separates its data by colour, so it needs a `color` (or `z`) channel
    and a legend. A doughnut does that with its slices, a grouped bar with its groups."""
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
        purpose="a figure over ordered months or days",
        required=("lineY",),
        value_axis="y",
        category_axis="x",
    ),
    "area": ShapeRule(
        purpose="a running total or a filled trend over months",
        required=("areaY",),
        also_allowed=("lineY",),
        value_axis="y",
        category_axis="x",
        zero_from_mark=True,
    ),
    "bar": ShapeRule(
        purpose="one figure per named category, up to about twelve of them",
        required=("barY",),
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
        purpose=f"two dimensions side by side, month by category, at most {MAX_SERIES} groups",
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
