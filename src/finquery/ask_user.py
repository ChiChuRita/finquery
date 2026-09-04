"""`ask_user`: the tool the assistant answers with a card in the transcript instead of prose.

It is a deferred tool, so it has no function on the server. The model calls it, the run ends
with the call pending (no model slot is held while a human thinks), the Vercel adapter streams
the call as a tool part in state `input-available`, the browser renders a Question card, and
the answer comes back as the tool's output on the next request, where it resumes the same run.

The shape is deliberately generic: a title, an optional note, the rows being asked about with
their own buttons, question-level buttons for a single choice, and a free text field. Ticket 07
uses it for categorization, and tickets 08, 10 and 11 reuse it for the CSV mapping
confirmation, duplicate decisions and the review of a flagged extraction.

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

from pydantic import BaseModel, Field
from pydantic_ai.tools import GenerateToolJsonSchema, ToolDefinition
from pydantic_ai.toolsets import ExternalToolset

ASK_USER = "ask_user"


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


ApplyKind = Literal["category_rule", "mapping_confirmation", "transaction_draft", "extraction_review"]
"""What kind of decision a card collects.

Two of them the server applies itself (`finquery.answers.APPLIERS`): `category_rule` turns
every answer into a category rule, and `extraction_review` commits the rows of a statement
extraction the user accepted. The other two name a card whose answers the model acts on with a
tool of its own (`import_file(confirmed=true)`, `add_transaction(ref)`), so they exist to say
"not categorization": without them a card that declares nothing would be read as a
categorization card and its Confirm answers would be offered to `set_rule` as category names.
Ticket 10 adds its duplicate kind here the same way.
"""

CATEGORY_RULE: ApplyKind = "category_rule"
MAPPING_CONFIRMATION: ApplyKind = "mapping_confirmation"
TRANSACTION_DRAFT: ApplyKind = "transaction_draft"
EXTRACTION_REVIEW: ApplyKind = "extraction_review"


class AskApply(BaseModel):
    """What the server does with the answers before the model is asked to continue."""

    kind: ApplyKind = Field(
        default=CATEGORY_RULE,
        description=(
            "`category_rule` means every answer becomes a category rule for that merchant, and "
            "`extraction_review` that the accepted bookings are imported. The other kinds are "
            "handled by a tool you call yourself. Copy whichever one the tool that gave you the "
            "rows returned."
        ),
    )


class AskUser(BaseModel):
    """One card in the transcript."""

    title: str = Field(description="The question, one short line.")
    note: str | None = Field(default=None, description="One more line of context, optional.")
    rows: list[AskRow] = Field(default_factory=list, description="Up to five rows, each answered on its own.")
    options: list[AskOption] = Field(
        default_factory=list, description="Buttons for the question itself, used when there are no rows."
    )
    allow_free_text: bool = Field(default=True, description="Whether the card offers a free text field.")
    apply: AskApply | None = Field(
        default=None,
        description="What the answers mean, copied from the tool that handed you the rows.",
    )


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
- Say nothing else in the same turn: the card is the message.
"""

ASK_USER_TOOL = ToolDefinition(
    name=ASK_USER,
    description=DESCRIPTION,
    parameters_json_schema=AskUser.model_json_schema(schema_generator=GenerateToolJsonSchema),
)

ask_user_toolset: ExternalToolset[object] = ExternalToolset([ASK_USER_TOOL], id="ask-user")
"""The toolset that makes `ask_user` a deferred tool of the chat agent."""
