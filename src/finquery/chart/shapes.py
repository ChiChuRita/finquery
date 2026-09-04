"""The chart shapes and what each one has to look like.

One table, read by three callers: the plan prompt (which shapes exist), the code prompt (which
example and which rules a shape gets) and the self-check (what to verify). Adding a shape is a
row here plus an example in `subagent.EXAMPLES`.
"""

from dataclasses import dataclass
from typing import Literal, get_args

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
    """True when the shape needs a `z` or `color` channel (one colour per series)."""
    grouped: bool = False
    """True when the bars must sit side by side (`layout: group()`)."""


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
    ),
    "bar": ShapeRule(
        purpose="one figure per named category, up to about twelve of them",
        required=("barY",),
        value_axis="y",
        category_axis="x",
    ),
    "bar_horizontal": ShapeRule(
        purpose="a ranking with long labels, such as the top merchants",
        required=("barX",),
        value_axis="x",
        category_axis="y",
    ),
    "bar_grouped": ShapeRule(
        purpose="two dimensions side by side, such as month by category",
        required=("barY",),
        value_axis="y",
        category_axis="x",
        series=True,
        grouped=True,
    ),
    "bar_stacked": ShapeRule(
        purpose="the same two dimensions when the stacked total matters",
        required=("barY",),
        value_axis="y",
        category_axis="x",
        series=True,
    ),
    "doughnut": ShapeRule(
        purpose=f"a share of a whole with at most {MAX_SLICES} slices",
        required=("radialArc",),
    ),
    "sankey": ShapeRule(
        purpose="a flow from sources to targets, such as income into categories",
        required=("sankeyDiagram",),
    ),
}

SHAPE_MENU = "\n".join(f"- {name}: {rule.purpose}" for name, rule in SHAPES.items())
