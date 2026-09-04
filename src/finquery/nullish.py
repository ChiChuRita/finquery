"""The one place that knows what a model writes when it means "nothing".

A model asked for an optional field sometimes fills it with the word instead of the value:
`"counterparty": "null"`, `"subcategory": "None"`. Read as data those strings are real, so a
booking ends up with the counterparty `null` and a row with the subcategory `None`, both of
which the review of 2026-09-04 saw on screen. Every model boundary that takes an optional
string or number therefore runs its input through `nullish_before`, so the absence the model
meant is the absence we store.

Used by `finquery.ask_user` (card fields), `finquery.changesets` (the intent a writing tool
takes) and `finquery.ingest.typed` (a booking read out of the user's words).
"""

from pydantic import field_validator

NULLISH = {"null", "none", "nil", "nan", "undefined", ""}
"""The words a model writes for nothing. Compared case-folded and stripped."""


def nullish(value: object) -> object:
    """`None` when this is a model's way of writing nothing, otherwise the value untouched."""
    return None if isinstance(value, str) and value.strip().casefold() in NULLISH else value


def nullish_before(*fields: str):  # type: ignore[no-untyped-def]
    """A `field_validator` in mode "before" that empties those fields when they say nothing.

    Before validation, so `"amount_cents": "null"` becomes `None` rather than failing the int
    and taking the whole card or intent down with it.
    """
    return field_validator(*fields, mode="before")(staticmethod(nullish))
