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

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

logger = logging.getLogger(__name__)

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
A worked batch. The reasoning is written first, one line per merchant, and only then the
entries:

  key: hausverwaltung bergmann | 12 bookings, money out, about -1150.00 EUR each
  text: "MIETE WOHNUNG 12 03/2025" (counterparty: Hausverwaltung Bergmann GmbH)

  key: nordlicht systeme | 12 bookings, money in, about 2850.00 EUR each
  text: "GEHALT 03/2025 PERS.NR 4711" (counterparty: Nordlicht Systeme GmbH)

  key: anna weber | 6 bookings, money out, about -24.00 EUR each, via PayPal
  text: "PP.4711.PP . ANNA WEBER, Ihre Zahlung" (counterparty: PayPal Europe S.a.r.l.)

  key: pfand | 1 booking, money out, about -0.25 EUR each
  text: "Pfand" (a line item of a receipt)

reasoning:
Bergmann: MIETE is rent and the counterparty is a property manager, so Housing over Rent
Nordlicht: money in and GEHALT, so Income over Salary and not a spending category
Anna Weber: a person's name through PayPal, so Transfers, but which one is the household's call
Pfand: a deposit line of a shop receipt, so it belongs where the shopping does

entries:
  hausverwaltung bergmann -> category Housing, subcategory Rent, confidence 0.85,
     title "Hausverwaltung Bergmann", description "landlord, monthly rent"
  nordlicht systeme -> category Income, subcategory Salary, confidence 0.9,
     title "Nordlicht Systeme", description "employer, monthly salary"
  anna weber -> category Transfers, subcategory Friends and family, confidence 0.4,
     title "Anna Weber", description "PayPal payment to a person"
  pfand -> category Groceries, subcategory Supermarket, confidence 0.8, title "Pfand",
     description "bottle deposit on a shop receipt"
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
    """One entry per merchant in the batch, and the reading behind them.

    `reasoning` is first so the batch is read before it is filed: a small model that starts
    with the entries files the second merchant where it filed the first (ticket 42).
    """

    reasoning: str = Field(
        description=(
            "One very short line per merchant, written before the entries: what you read the "
            "merchant as, and whether a subcategory of that category really fits or none does. "
            "No prose, no repetition of the booking text."
        )
    )
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


def refusals(
    answer: Categorization,
    entries: list[MerchantBatchEntry],
    taxonomy: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[str]:
    """What is wrong with this batch, in the words the resubmit uses.

    Three things, all of which leave a merchant Needs review when nobody says so: a category
    that is not the household's, a subcategory that belongs to another category, and a merchant
    of the batch with no entry at all. An entry for a merchant nobody asked about is not one of
    them: it is dropped where the answers are read, and asking again would cost a call to lose
    the same line.
    """
    categories = {name: set(subs) for name, subs in taxonomy}
    found: list[str] = []
    answered: set[str] = set()
    asked = {entry.key for entry in entries}
    for entry in answer.merchants:
        if entry.key not in asked:
            continue
        answered.add(entry.key)
        if entry.category not in categories:
            found.append(
                f"`{entry.key}`: this household has no category `{entry.category}`. Pick one of "
                f"the categories listed above, spelled exactly as it is listed."
            )
        elif entry.subcategory and entry.subcategory not in categories[entry.category]:
            listed = ", ".join(sorted(categories[entry.category])) or "none"
            found.append(
                f"`{entry.key}`: `{entry.subcategory}` is not a subcategory of "
                f"{entry.category}. Its subcategories are: {listed}. Use one of them or null."
            )
    for key in (entry.key for entry in entries if entry.key not in answered):
        found.append(f"`{key}` has no entry. Every merchant of the batch needs one.")
    return found


def resubmit_prompt(answer: Categorization, found: list[str]) -> str:
    """A resubmit: the answer that was refused, what is wrong with it, and the correction."""
    entries = "\n".join(
        f"  {entry.key} -> {entry.category}"
        + (f" > {entry.subcategory}" if entry.subcategory else "")
        + f", confidence {entry.confidence}"
        for entry in answer.merchants
    )
    return (
        "Your last answer could not be filed. This is a correction of it, not a new batch: "
        "keep every entry the points below do not name.\n\n"
        f"Your reasoning was:\n{answer.reasoning.strip()}\n\n"
        f"Your entries were:\n{entries}\n\n"
        "What is wrong with it:\n" + "\n".join(f"- {line}" for line in found) + "\n\n"
        "Answer again with the corrected reasoning and the full set of entries. The first line "
        "of the reasoning says what you changed."
    )


async def categorize_merchants(
    model: Model,
    entries: list[MerchantBatchEntry],
    taxonomy: tuple[tuple[str, tuple[str, ...]], ...],
    *,
    model_settings: ModelSettings | None = None,
) -> dict[str, MerchantCategory]:
    """Ask the fast slot about a batch of merchants, keyed by merchant key.

    An answer naming a category this household does not have, or leaving a merchant out, is
    handed back once with what is wrong with it, because both of those silently cost the
    merchant its category and the second answer usually has it. Whatever is still unanswered or
    unusable after that is left out, which the pipeline reads as Needs review.
    """
    if not entries:
        return {}
    prompt = categorize_prompt(entries, taxonomy)
    result = await categorizer_agent.run(prompt, model=model, model_settings=model_settings)
    found = refusals(result.output, entries, taxonomy)
    if found:
        logger.info("the categorizer is resubmitting a batch of %d: %s", len(entries), "; ".join(found))
        result = await categorizer_agent.run(
            f"{prompt}\n\n{resubmit_prompt(result.output, found)}",
            model=model,
            model_settings=model_settings,
        )
    asked = {entry.key for entry in entries}
    return {answer.key: answer for answer in result.output.merchants if answer.key in asked}


def batched(entries: list[MerchantBatchEntry], size: int = BATCH_SIZE) -> list[list[MerchantBatchEntry]]:
    return [entries[start : start + size] for start in range(0, len(entries), size)]
