"""`ask_user`: the tool the assistant answers with a card in the transcript instead of prose.

It is a deferred tool, so it has no function on the server. The model calls it, the run ends
with the call pending (no model slot is held while a human thinks), the Vercel adapter streams
the call as a tool part in state `input-available`, the browser renders a Question card, and
the answer comes back as the tool's output on the next request, where it resumes the same run.

The shape is deliberately generic: a title, an optional note, the rows being asked about with
their own buttons, question-level buttons for a single choice, and a free text field. Ticket 07
uses it for categorization, ticket 08 for the CSV mapping confirmation and the preview of a
typed booking, ticket 10 for duplicate decisions, and ticket 11 will reuse it for the
extraction review.

Wire contract:

    input   {"title": str, "note": str | null,
             "rows": [{"ref": str, "label": str, "description": str | null,
                       "amount_cents": int | null, "date": "YYYY-MM-DD" | null,
                       "bookings": int | null, "options": [{"label": str, "value": str}]}],
             "options": [{"label": str, "value": str}],
             "allow_free_text": bool,
             "apply": {"kind": str} | null}
    output  {"answers": [{"ref": str, "value": str | null, "text": str | null}],
             "applied": str | null}

An answer whose `ref` is empty answers the question itself rather than one of its rows. A row
the user skipped simply has no answer.

`apply` says what the answers mean, so the server can act on them in code before the run
continues: `finquery.answers` applies them and writes what it did into `applied`, which is
part of the tool result the model reads. Nothing about that is the model's arithmetic, and a
card whose kind nobody handles is simply handed to the model as it came.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_ai.tools import GenerateToolJsonSchema, ToolDefinition
from pydantic_ai.toolsets import ExternalToolset

ASK_USER = "ask_user"

NULLISH = {"null", "none", "nil", ""}
"""What a model writes when it stringifies its own JSON arguments.

`"amount_cents": "null"` reaches us from the fast slot (OpenRouter, 2026-09-04). Read as a
value it fails validation, and a card that fails validation is a card whose answers apply
nothing (`finquery.answers`), so the optional fields treat it as the null it meant to be."""


def _nullish(value: object) -> object:
    return None if isinstance(value, str) and value.strip().casefold() in NULLISH else value


class AskOption(BaseModel):
    """One button on a card."""

    label: str = Field(description="What the button says.")
    value: str = Field(description="What comes back when it is clicked.")


class AskRow(BaseModel):
    """One thing being asked about: a merchant, a duplicate candidate, a booking."""

    ref: str = Field(description="What an answer to this row refers to, copied back verbatim.")
    label: str = Field(description="The heading of the row, for instance the merchant.")
    description: str | None = Field(default=None, description="The booking text, shown smaller.")
    amount_cents: int | None = Field(default=None, description="Signed cents, negative is money out.")
    date: str | None = Field(default=None, description="Booking date as YYYY-MM-DD.")
    bookings: int | None = Field(default=None, description="How many bookings this row stands for.")
    options: list[AskOption] = Field(default_factory=list, description="Buttons for this row.")

    _nulls = field_validator("description", "amount_cents", "date", "bookings", mode="before")(
        staticmethod(_nullish)
    )


ApplyKind = Literal["category_rule", "duplicate_decision", "mapping_confirmation", "transaction_draft"]
"""What kind of decision a card collects.

Two of them the server applies itself (`finquery.answers.APPLIERS`): `category_rule` turns
every answer into a category rule, and `duplicate_decision` inserts the bookings the user kept
and discards the ones they removed. The other two name a card whose answers the model acts on
with a tool of its own (`import_file(confirmed=true)`, `add_transaction(ref)`), so they exist
to say "not categorization": without them a card that declares nothing would be read as a
categorization card and its Confirm answers would be offered to `set_rule` as category names.
"""

CATEGORY_RULE: ApplyKind = "category_rule"
DUPLICATE_DECISION: ApplyKind = "duplicate_decision"
MAPPING_CONFIRMATION: ApplyKind = "mapping_confirmation"
TRANSACTION_DRAFT: ApplyKind = "transaction_draft"


class AskApply(BaseModel):
    """What the server does with the answers before the model is asked to continue."""

    kind: ApplyKind = Field(
        default=CATEGORY_RULE,
        description=(
            "`category_rule` means every answer becomes a category rule for that merchant, "
            "`duplicate_decision` that a kept booking is inserted and a removed one is not. "
            "The other kinds are handled by a tool you call yourself, so copy whichever one the "
            "tool that gave you the rows returned."
        ),
    )


class AskUser(BaseModel):
    """One card in the transcript."""

    title: str = Field(description="The question, one short line.")
    note: str | None = Field(default=None, description="One more line of context, optional.")
    rows: list[AskRow] = Field(default_factory=list, description="Up to five rows, each answered on its own.")
    options: list[AskOption] = Field(
        default_factory=list,
        description="Buttons for the question itself rather than for one row, used when there are no rows.",
    )
    allow_free_text: bool = Field(default=True, description="Whether the card offers a free text field.")
    apply: AskApply | None = Field(
        default=None,
        description="What the answers mean, copied from the tool that handed you the rows.",
    )

    _nulls = field_validator("note", "apply", mode="before")(staticmethod(_nullish))


MAX_UNWRAP = 3
"""How deep a wrapped card is unwrapped. Two levels were seen; three is room to spare."""


def unwrap_card(args: dict[str, object]) -> dict[str, object]:
    """The card's own fields, even when the model handed the object back under a `card` key.

    A tool that builds a ready card returns it as `card`, and the assistant is told to pass its
    fields as the arguments of `ask_user`. The fast model sometimes passes the object instead
    (`{"card": {"card": {...}}}` on OpenRouter, 2026-09-04), which would render a card with no
    title and no rows and, worse, would not validate here, so the answers would apply nothing.
    Unwrapping it costs one call and keeps a question answerable. The browser does the same
    before it renders (`question-card.tsx`).
    """
    outer = args
    for _ in range(MAX_UNWRAP):
        inner = args.get("card")
        if not isinstance(inner, dict):
            break
        args = inner
    if args is outer:
        return args
    # The apply hint sometimes stays on the wrapper, and losing it would send the answers to
    # the wrong applier, so the innermost card keeps whichever one it has.
    return {**args, "apply": args.get("apply") or outer.get("apply")}


class AskAnswer(BaseModel):
    """What the user chose for one row, or for the question when `ref` is empty."""

    ref: str = ""
    value: str | None = None
    text: str | None = None


class AskAnswers(BaseModel):
    """The output the browser sends back as the tool result.

    `applied` is added by the server, not by the browser: it is the one line saying what the
    answers already changed, so the model summarizes instead of repeating the work.
    """

    answers: list[AskAnswer] = Field(default_factory=list)
    applied: str | None = None


DESCRIPTION = """\
Ask the user a question they answer by clicking, instead of asking in prose.

Use it for anything only the user can decide: which category a merchant belongs to, whether
two bookings are the same payment, whether a mapping is right. The card appears in the
transcript, the run pauses until the user answers, and the answers come back as this tool's
result.

Rules:
- At most five rows per card. Ask about one thing per row.
- `ref` is the handle an answer comes back with. For a categorization question it is the
  merchant pattern from `review_batch`, copied exactly, never a booking id.
- Give each row the `options` that came with it, as label and value pairs. A value like
  "Groceries > Supermarket" is a category and its subcategory.
- `title` says what you want to know; the row labels carry the merchants.
- Leave `allow_free_text` true so the user can type a category that is not a button.
- Copy the `apply` object from the tool that gave you the rows (`review_batch` returns one).
  It is what makes the answers take effect in code, without you having to act on them.
- When a tool hands you a whole `card`, pass its fields as your own arguments, unchanged: the
  same title, the same `note`, the same rows in the same order. Never leave a field out, never
  shorten one, and never pass the card as a `card` argument.
- Say nothing else in the same turn: the card is the message.
"""

ASK_USER_TOOL = ToolDefinition(
    name=ASK_USER,
    description=DESCRIPTION,
    parameters_json_schema=AskUser.model_json_schema(schema_generator=GenerateToolJsonSchema),
)

ask_user_toolset: ExternalToolset[object] = ExternalToolset([ASK_USER_TOOL], id="ask-user")
"""The toolset that makes `ask_user` a deferred tool of the chat agent."""
