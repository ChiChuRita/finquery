"""The merchant token: the only thing about the household that may leave the machine.

It starts from the merchant the categorizer already works with (`merchants.merchant_of`, which
strips card processors, branch numbers, legal forms, the terminal's pleasantries and the city),
and then takes away everything that stage had no reason to remove:

- amounts and dates (`-1.150,00 EUR`, `03/2025`, `MAERZ`),
- IBANs, card numbers, customer and reference numbers with the label that introduces them
  (`DE89 3704 0044 0532 0130 00`, `PERS.NR 4711`, `NR00012345`),
- personal names.

A personal name is not scrubbed word by word, it is refused: if the counterparty (or, when the
counterparty is only the payment processor, the booking text) reads as a person rather than a
business, no lookup happens at all and nothing leaves. That is why `scrub` returns a token that
can be empty with a reason instead of a best-effort string.

The rule for a person, from the spec: exactly two capitalized words with no legal form.
`BUSINESS_WORDS` is what keeps a two-word company ("Hausverwaltung Bergmann", "Mustermann
Systems") out of that rule. Being wrong in that direction costs a lookup; being wrong in the
other direction would leak a name, so anything ambiguous counts as a person.

TODO: a booking text that spells a person in lower case is not recognized (the rule is about
capitalized words). A list of common given names is the upgrade path if a real export needs it.
"""

import re
from dataclasses import dataclass

from finquery.categorize.merchants import NOISE, PROCESSORS, fold, lookup, merchant_of

MAX_TOKEN_WORDS = 4
MAX_TOKEN_CHARS = 60
MIN_TOKEN_CHARS = 3
NAME_WORDS = 2
"""A person is exactly two capitalized words: a given name and a surname. Three or more is a
brand ("Xbox Game Pass", "Hans im Glueck"). A nobiliary particle is noise, so "Anna von Weber"
is two words here too.
TODO: a middle name is not covered. Widening this refuses brands, so it needs a name list."""

# Month names, so a booking that carries its period in words loses it the way a numeric date
# already loses it to `fold` (which turns 03/2025 into two number words).
DATE_WORDS = {
    "januar", "februar", "maerz", "april", "mai", "juni", "juli", "august", "september",
    "oktober", "november", "dezember", "jan", "feb", "mrz", "apr", "jun", "jul", "aug", "sep",
    "sept", "okt", "nov", "dez", "january", "march", "may", "june", "july", "october",
    "december", "mar", "oct", "dec", "kw", "q1", "q2", "q3", "q4",
}

# The words a bank prints in front of a number. The number itself is gone with the digits, and
# the label that introduced it is not part of a merchant name either.
REFERENCE_WORDS = {
    "pers", "persnr", "personalnr", "kunde", "kundennr", "kundennummer", "kdnr", "vertrag",
    "vertragsnr", "vertragskonto", "rechnung", "rechnungsnr", "beleg", "belegnr", "auftrag",
    "auftragsnr", "mandat", "mandatsreferenz", "referenz", "verwendungszweck", "konto",
    "kontonr", "kartennr", "bic", "swift", "steuernr", "ustid",
}

# What tells a two-word business name from a person's name, matched as the whole word or its
# ending (plus a plural s), because German business names are compounds: "Hausverwaltung" ends
# in "verwaltung", "Baumarkt" in "markt", "Systems" is "system". Matching anywhere in the word
# would swallow surnames instead: "Hoffmann" starts with "hof", "Bauer" with "bau".
BUSINESS_WORDS = (
    "verwaltung", "immobilien", "system", "solution", "service", "technik", "technology",
    "group", "gruppe", "media", "markt", "market", "shop", "store", "apotheke", "praxis",
    "klinik", "bau", "energie", "strom", "versicher", "bank", "kasse", "werke", "hotel",
    "restaurant", "cafe", "bar", "kueche", "grill", "baeckerei", "metzger", "friseur",
    "studio", "sport", "fitness", "reise", "logistik", "transport", "consulting", "partner",
    "druck", "garten", "elektro", "sanitaer", "auto", "mobil", "pharma", "labor", "agentur",
    "verlag", "handel", "vertrieb", "zentrum", "center", "haus", "hof", "stube", "laden",
    "discount", "digital", "software", "telekom", "energy", "farm", "brauerei", "kiosk",
)

_IBAN = re.compile(r"^[a-z]{2}\d{2}[a-z0-9]{6,}$")
_HAS_DIGIT = re.compile(r"\d")
_LEGAL_FORMS = {
    "gmbh", "mbh", "ag", "kg", "kgaa", "ohg", "ek", "ug", "se", "co", "sarl", "sa", "rl",
    "bv", "nv", "ab", "as", "inc", "ltd", "plc", "llc", "eg", "gbr", "mbb",
}


@dataclass(frozen=True)
class MerchantToken:
    """The scrubbed merchant, or nothing plus the reason it is nothing.

    `text` is the same string the categorizer uses as its merchant key when nothing had to be
    taken away, which is what makes the lookup cache line up with the rules and the Question
    cards.
    """

    text: str
    reason: str | None = None
    """Why there is no token, in one sentence the assistant can repeat to the user."""

    def __bool__(self) -> bool:
        return bool(self.text)


def _informative(word: str) -> bool:
    """Is this word part of a merchant name rather than a number, a date or a legal form?"""
    if word in DATE_WORDS or word in REFERENCE_WORDS or word in NOISE or word in PROCESSORS:
        return False
    if word in _LEGAL_FORMS:
        return False
    if len(word) < 2:
        return False
    if _IBAN.match(word):
        return False
    # An amount, a card, customer or reference number, or an amount with its currency glued on
    # ("00eur"). A two-character name with a digit is a brand, not a number ("o2").
    return not (_HAS_DIGIT.search(word) and len(word) > 2)


def _business_word(word: str) -> bool:
    """Does this word name a trade or a legal shape rather than a person?"""
    # Both forms, because dropping the plural s would also eat the s of "Autohaus".
    forms = {word, word[:-1]} if word.endswith("s") and len(word) > 3 else {word}
    return any(form == business or form.endswith(business) for form in forms for business in BUSINESS_WORDS)


def _capitalized_words(text: str) -> list[str]:
    """The words of a name as it was written, without the noise the bank printed around it."""
    return [
        word
        for word in re.split(r"[^A-Za-zÀ-ÿ]+", text)
        if len(word) >= 2 and word[0].isupper() and _informative(fold(word))
    ]


def looks_like_a_person(description: str, counterparty: str | None = None) -> bool:
    """Exactly two capitalized words, no legal form and no business word: a person.

    The counterparty is the field to read, exactly as `merchant_of` reads it, except when it is
    only the processor that moved the money: a PayPal booking names PayPal as the counterparty
    and the person in the booking text.
    """
    source = counterparty if counterparty and _capitalized_words(counterparty) else description
    words = _capitalized_words(source)
    if len(words) != NAME_WORDS:
        return False
    folded = [fold(word) for word in words]
    if any(_business_word(word) for word in folded):
        return False
    # A merchant the app already knows is a merchant, whatever its name looks like.
    return lookup(" ".join(folded)) is None and all(lookup(word) is None for word in folded)


def scrub(description: str, counterparty: str | None = None) -> MerchantToken:
    """The merchant token for a booking, or nothing when nothing may leave.

    `description` is also where a merchant the user typed in chat arrives, with no counterparty.
    """
    if looks_like_a_person(description, counterparty):
        return MerchantToken(
            "",
            "that looks like a person's name, and a person's name never leaves this machine",
        )
    key = merchant_of(description, counterparty).key
    words = [word for word in key.split() if _informative(word)][:MAX_TOKEN_WORDS]
    token = " ".join(words)[:MAX_TOKEN_CHARS].strip()
    if len(token) < MIN_TOKEN_CHARS:
        return MerchantToken("", "there is no merchant name in that booking, only numbers and dates")
    return MerchantToken(token)


def safe_query(query: str, token: MerchantToken) -> str:
    """The search query, held to the same rule as the token before it is sent.

    The model that writes the query has never seen anything but the token and the category
    list, so this is a guard at the boundary rather than a filter: it drops any word that
    carries a number or reads as a date, and falls back to the token itself when the query lost
    the merchant on the way.
    """
    words = [word for word in query.split() if not _HAS_DIGIT.search(word) and fold(word) not in DATE_WORDS]
    cleaned = " ".join(words)[: MAX_TOKEN_CHARS * 2].strip()
    if not cleaned or token.text not in fold(cleaned):
        return token.text
    return cleaned
