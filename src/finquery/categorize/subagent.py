"""The categorizer sub-agent: merchants in, a category and an enrichment per merchant out.

Fast slot, one forced tool call, no free text (ADR 0002 pins every sub-agent to fast). It is
stage three, so it only ever sees what the profile's rules and the merchant dictionary could
not place.

It is asked per merchant, not per booking. The 433 bookings of the shipped year are 39
merchants, so one batch of 25 entries answers hundreds of rows: same per-row output, a
fraction of the tokens, and the confidence lands on the merchant, which is also the thing a
Question card asks about and a rule matches on.

`categorize_prompt` is a pure function of the batch and the taxonomy, so a training row is the
text the model saw plus the answer it gave.
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

BATCH_SIZE = 25
"""Merchants per model call."""

CONFIDENCE_THRESHOLD = 0.75
"""Below this the row stays Needs review and the merchant becomes a Question card entry."""

INSTRUCTIONS = """\
You categorize the merchants of a German household's bank statement. You are given the
household's category list and a batch of merchants, each with the booking text it appears
under, how many bookings it has and what they are worth. Call `categorize` exactly once and
return one entry for every merchant you were given, keyed by the `key` you were given.
You never explain and never answer in words: the entries are the answer.
"""

RULES = """\
Rules:
- `category` must be one of the household's categories, spelled exactly as listed.
- `subcategory` must be one of that category's subcategories, or null when none fits.
- Never answer `Unknown`. Unknown is a category only a human assigns. If nothing fits, pick the
  closest category and give it a low confidence.
- `confidence` is 0.0 to 1.0: how sure you are that this is where the household would file it.
  Be honest. A well-known chain is 0.9 or more. A trade you can read from the text (a bakery, a
  pharmacy, a dentist) is around 0.85. A landlord, an employer or a utility you can read from
  the booking text is around 0.8. A person's name, a payment to a friend, an abbreviation you
  do not recognize or anything where two categories are equally likely is 0.5 or less: the
  household will be asked instead.
- Money in (a positive amount) is `Income` when it is a salary or interest, otherwise a refund
  or a transfer; never file incoming money under a spending category.
- `title` is the friendly merchant name, at most 40 characters: no legal form, no branch
  number, no city, no card wording. `Edeka Filiale 1234` becomes `EDEKA`.
- `description` is at most 60 characters and says what the merchant is, lower case, no full
  stop: `supermarket`, `rail travel`, `payment to a friend`, `landlord`.
"""

EXAMPLE = """\
Example entries and good answers:

  key: hausverwaltung bergmann | 12 bookings, money out, about -1150.00 EUR each
  text: "MIETE WOHNUNG 12 03/2025" (counterparty: Hausverwaltung Bergmann GmbH)
  -> category Housing, subcategory Rent, confidence 0.85, title "Hausverwaltung Bergmann",
     description "landlord, monthly rent"

  key: anna weber | 6 bookings, money out, about -24.00 EUR each, via PayPal
  text: "PP.4711.PP . ANNA WEBER, Ihre Zahlung" (counterparty: PayPal Europe S.a.r.l.)
  -> category Transfers, subcategory Friends and family, confidence 0.4, title "Anna Weber",
     description "PayPal payment to a person"
"""


class MerchantCategory(BaseModel):
    """Where one merchant belongs, and how it should read in the table."""

    key: str = Field(description="The merchant key you were given, copied exactly.")
    category: str = Field(description="One of the household's categories.")
    subcategory: str | None = Field(default=None, description="One of that category's subcategories, or null.")
    confidence: float = Field(ge=0.0, le=1.0, description="0.0 to 1.0.")
    title: str = Field(description="Friendly merchant title, at most 40 characters.")
    description: str = Field(description="What the merchant is, at most 60 characters.")


class Categorization(BaseModel):
    """One entry per merchant in the batch."""

    merchants: list[MerchantCategory]


@dataclass(frozen=True)
class MerchantBatchEntry:
    """One merchant as the sub-agent sees it: no ids, no account, no personal data beyond the
    booking text the bank itself printed."""

    key: str
    sample_description: str
    counterparty: str | None
    bookings: int
    average_cents: int
    incoming: bool
    via: str | None = None

    def as_prompt(self) -> str:
        direction = "money in" if self.incoming else "money out"
        via = f", via {self.via}" if self.via else ""
        counterparty = f" (counterparty: {self.counterparty})" if self.counterparty else ""
        return (
            f"  key: {self.key} | {self.bookings} booking(s), {direction}, "
            f"about {self.average_cents / 100:.2f} EUR each{via}\n"
            f'  text: "{self.sample_description}"{counterparty}'
        )


categorizer_agent = Agent(
    instructions=INSTRUCTIONS,
    output_type=ToolOutput(Categorization, name="categorize"),
    name="finquery-categorizer",
)


def taxonomy_block(taxonomy: tuple[tuple[str, tuple[str, ...]], ...]) -> str:
    lines = ["The household's categories:"]
    for name, subcategories in taxonomy:
        lines.append(f"- {name}: {', '.join(subcategories) if subcategories else 'no subcategories'}")
    return "\n".join(lines)


def categorize_prompt(
    entries: list[MerchantBatchEntry], taxonomy: tuple[tuple[str, tuple[str, ...]], ...]
) -> str:
    """The whole prompt the categorizer sees. Pure function, reused by training."""
    batch = "\n\n".join(entry.as_prompt() for entry in entries)
    return "\n\n".join(
        [
            taxonomy_block(taxonomy),
            RULES,
            EXAMPLE,
            f"Categorize these {len(entries)} merchant(s):\n\n{batch}",
        ]
    )


async def categorize_merchants(
    model: Model,
    entries: list[MerchantBatchEntry],
    taxonomy: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    model_settings: ModelSettings | None = None,
) -> dict[str, MerchantCategory]:
    """Ask the fast slot about a batch of merchants, keyed by merchant key.

    A batch that comes back short or with a key nobody asked about simply leaves those
    merchants unanswered, which the pipeline reads as Needs review.
    """
    if not entries:
        return {}
    result = await categorizer_agent.run(
        categorize_prompt(entries, taxonomy), model=model, model_settings=model_settings
    )
    asked = {entry.key for entry in entries}
    return {answer.key: answer for answer in result.output.merchants if answer.key in asked}


def batched(entries: list[MerchantBatchEntry], size: int = BATCH_SIZE) -> list[list[MerchantBatchEntry]]:
    return [entries[start : start + size] for start in range(0, len(entries), size)]
