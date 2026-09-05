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


def empty_list(value: object) -> object:
    """`[]` when a model wrote nothing where a list belongs, otherwise the value untouched.

    A small model asked for an optional list writes `null` rather than leaving it out, and a
    field typed `list[...]` refuses that. `"legs": null` on a recategorize is what burned both
    `propose_changeset` attempts of the 9B review of 2026-09-05: three retries, then a turn with
    no answer, no card and nothing for the user to act on.
    """
    return [] if nullish(value) is None else value


def empty_list_before(*fields: str):  # type: ignore[no-untyped-def]
    """A `field_validator` in mode "before" that reads nothing in a list field as an empty list."""
    return field_validator(*fields, mode="before")(staticmethod(empty_list))


def nullish_before(*fields: str):  # type: ignore[no-untyped-def]
    """A `field_validator` in mode "before" that empties those fields when they say nothing.

    Before validation, so `"amount_cents": "null"` becomes `None` rather than failing the int
    and taking the whole card or intent down with it.
    """
    return field_validator(*fields, mode="before")(staticmethod(nullish))
