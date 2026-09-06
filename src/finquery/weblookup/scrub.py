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

The rule for a person is read in this order, and the order is the whole privacy argument
(ticket 53, the review of 2026-09-06):

1. **A legal form anywhere wins.** `GmbH`, `AG`, `SE`, `KG`, `e.V.`, `a.G.`, `B.V.`, `& Co` and
   the rest are the strongest business signal a booking carries, and they are read before the
   words are counted. Before this they were dropped as uninformative and what was left ("Sixt
   ... Autovermietung", "ERGO Versicherung") was counted as two words and refused: 24 of the 28
   refusals in the review's set were companies.
2. **A common German given name in either position refuses.** "Anna Weber", "ANNA WEBER" and
   "Weber Anna" are all a person, and this fires before the business-word exemption, so "Anna
   Bauer" is a person even though "Bauer" ends in a trade.
3. **Then the old two-word rule**: exactly two capitalized words with no business word.

The legal form is read from the same string the person rule reads, never from the counterparty
when the counterparty is only the processor: a PayPal booking names `PayPal Europe S.a.r.l.`
as the counterparty and a friend in the text, and reading the form there would send the friend.

Being wrong towards refusing costs a lookup; being wrong the other way would leak a name, so
anything ambiguous still counts as a person.
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
    "tankstelle", "parfuemerie", "fernsehen", "mobility",
)

# The same signal at the other end of the word: a trade that starts a compound rather than
# ending one. "Versicherungs-AG", "Metzgerei", "Physiotherapie", "Tankstellen", "Parfuemerie",
# "Einrichtungsmaerkte", "Fernsehen", "Mobility", "Capital" and "Entertainment" were all read
# as surnames while `BUSINESS_WORDS` only matched an ending (F2 of the review).
BUSINESS_STEMS = (
    "versicher", "metzger", "physio", "tankstell", "parfuem", "einrichtung", "fernseh",
    "mobility", "capital", "entertainment",
)

# The two hundred most common German given names, folded the way `fold` folds them. Plain data
# on purpose: a name list is the upgrade path ADR 0010 named, and it is only ever read, never
# sent. A name here in either position of a two-word counterparty refuses the whole lookup.
GIVEN_NAMES = frozenset(
    """
    alexander alina amelie andrea andreas angelika anna annika anton antonia barbara ben
    benjamin bernd bernhard birgit bjoern brigitte bruno carla carolin caroline charlotte
    christian christiane christina christoph claudia clara constantin cornelia daniel daniela
    david dennis dieter dirk doris dominik dorothea elena elias elisabeth elke ella emil emilia
    emma erik erika ernst eva fabian felix finn florian frank franz franziska frieda friedrich
    gabriele georg gerhard gisela greta gudrun guenter hannah hanna hans harald heike heinrich
    heinz helena helga helmut henri henry herbert hermann holger horst ida ingrid irene iris
    isabel isabella jan jana jasmin jennifer jens jessica joachim johanna johannes jonas
    jonathan joerg josef judith julia julian juergen karin karl katharina katrin kerstin kevin
    klaus konstantin lara lars laura lea lena leon leonie liam lina lisa louisa luca lukas
    ludwig luisa luise manfred manuel marcel marco maria marie mario marion markus marlene
    martin martina mathilda matthias maximilian melanie michael michaela mika mila monika
    moritz nele nico niklas nils nina noah norbert oliver oskar paul paula petra philipp
    rainer ralf regina reinhard renate rene richard rita robert rolf romy rudolf sabine sara
    sarah sebastian silke silvia simon simone sophia sophie stefan stefanie stephan stephanie
    susanne sven tanja theo thomas tim tobias tom ulrich ulrike ursula ute uwe valentin
    vanessa verena vincent volker waltraud walter werner wilhelm wolfgang yvonne
    """.split()
)

# A word the merchant key drops as noise that is half a merchant's name in a search token.
# `Zeit Online` folded to `zeit` alone (F4), because "online" is the channel a bank prints
# ("ONLINE UEBERWEISUNG") and not usually part of a name. Only a word on this fixed list can
# come back, so nothing personal can arrive this way.
KEPT_NOISE = ("online",)

_IBAN = re.compile(r"^[a-z]{2}\d{2}[a-z0-9]{6,}$")
_NUMBERISH = re.compile(r"\d\d")
"""Two digits next to each other: an amount, a date, a branch, a card or a reference number.
A brand keeps a lone digit (`o2`, `1und1`, `3M`), which is how F4's `1&1 Telecom` keeps its
name instead of leaving as `telecom`."""

_LEGAL_FORMS = {
    "gmbh", "ggmbh", "mbh", "ag", "kg", "kgaa", "ohg", "ek", "ug", "se", "co", "sarl", "sa",
    "rl", "bv", "nv", "ab", "as", "inc", "ltd", "plc", "llc", "eg", "gbr", "mbb", "ev", "srl",
    "spa", "aps", "oy",
}
"""Read off the token, so a legal form never becomes part of what is searched for."""

LEGAL_FORMS = _LEGAL_FORMS - {"ab", "as", "co", "rl"}
"""Read as the business signal that short-circuits the person rule. Four forms are left out of
it because they are also ordinary words a booking text can carry on its own; `& Co` is caught
by `AND_CO` instead, and `S.a.r.l.` arrives here as `sarl`."""

AND_CO = ("& co", "&co", "u. co")
_ABBREVIATION = re.compile(r"(?:[a-zà-ÿ]\.){2,}")
_ACRONYM_DOT = re.compile(r"(?<![A-Za-zÀ-ÿ])([A-Za-zÀ-ÿ])\.(?=[A-Za-zÀ-ÿ])")
_AMPERSAND_DIGITS = re.compile(r"(\d)\s*&\s*(\d)")


@dataclass(frozen=True)
class MerchantToken:
    """The scrubbed merchant, or nothing plus the reason it is nothing.

    `text` is the same string the categorizer uses as its merchant key when nothing had to be
    taken away, which is what makes the lookup cache line up with the rules and the Question
    cards.
    """

    text: str
    reason: str | None = None
    """Why there is no token: one whole sentence, because it is what the transcript prints."""

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
    return not _NUMBERISH.search(word)


def _business_word(word: str) -> bool:
    """Does this word name a trade or a legal shape rather than a person?"""
    # Both forms, because dropping the plural s would also eat the s of "Autohaus".
    forms = {word, word[:-1]} if word.endswith("s") and len(word) > 3 else {word}
    if any(form.startswith(stem) for form in forms for stem in BUSINESS_STEMS):
        return True
    return any(form == business or form.endswith(business) for form in forms for business in BUSINESS_WORDS)


def has_legal_form(text: str) -> bool:
    """Does this string carry a legal form anywhere in it?

    Read on the text as printed, with abbreviations squashed first (`e.V.` to `ev`, `a.G.` to
    `ag`, `S.a.r.l.` to `sarl`), because folding splits them into single letters that say
    nothing. `& Co` counts too: "Sixt GmbH & Co Autovermietung KG" is a company by any reading.
    """
    squashed = _ABBREVIATION.sub(lambda match: match.group(0).replace(".", ""), text.casefold())
    if any(form in squashed for form in AND_CO):
        return True
    return any(word in LEGAL_FORMS for word in re.split(r"[^a-z0-9à-ÿ]+", squashed))


def _normalized(text: str) -> str:
    """`E.ON` to `EON` and `1&1` to `1und1`, so a brand's short parts survive the fold.

    Folding splits on every non-alphanumeric character and single characters are dropped, so
    `E.ON Energie` left as `on energie` and `1&1 Telecom` as `telecom` (F4): a token that is
    not the merchant, in the outbound log for the user to read.
    """
    return _ACRONYM_DOT.sub(r"\1", _AMPERSAND_DIGITS.sub(r"\1und\2", text))


def _capitalized_words(text: str) -> list[str]:
    """The words of a name as it was written, without the noise the bank printed around it."""
    return [
        word
        for word in re.split(r"[^A-Za-zÀ-ÿ]+", text)
        if len(word) >= 2 and word[0].isupper() and _informative(fold(word))
    ]


def _name_source(description: str, counterparty: str | None) -> str:
    """The string the person rule reads, exactly as `merchant_of` reads it.

    The counterparty, except when it is only the processor that moved the money: a PayPal
    booking names PayPal as the counterparty and the person in the booking text. Everything
    below reads this and nothing else, the legal form included, so `PayPal Europe S.a.r.l.`
    can never make a friend's name look like a company.
    """
    return counterparty if counterparty and _capitalized_words(counterparty) else description


def looks_like_a_person(description: str, counterparty: str | None = None) -> bool:
    """Whether this booking names a person. The order is in the module docstring."""
    source = _name_source(description, counterparty)
    if has_legal_form(source):
        return False
    words = _capitalized_words(source)
    if len(words) != NAME_WORDS:
        return False
    folded = [fold(word) for word in words]
    # A merchant the app already knows is a merchant, whatever its name looks like.
    if lookup(fold(source)) is not None or lookup(" ".join(folded)) is not None:
        return False
    if any(lookup(word) is not None for word in folded):
        return False
    if any(word in GIVEN_NAMES for word in folded):
        return True
    return not any(_business_word(word) for word in folded)


def scrub(description: str, counterparty: str | None = None) -> MerchantToken:
    """The merchant token for a booking, or nothing when nothing may leave.

    `description` is also where a merchant the user typed in chat arrives, with no counterparty.
    """
    if looks_like_a_person(description, counterparty):
        return MerchantToken(
            "",
            "That booking names a person, and a person's name never leaves this machine, so "
            "nothing was looked up.",
        )
    described = _normalized(description)
    party = _normalized(counterparty) if counterparty else None
    key = merchant_of(described, party).key
    words = [word for word in key.split() if _informative(word)][:MAX_TOKEN_WORDS]
    for word in fold(party or described).split():
        if word in KEPT_NOISE and word not in words and len(words) < MAX_TOKEN_WORDS:
            words.append(word)
    token = " ".join(words)[:MAX_TOKEN_CHARS].strip()
    if len(token) < MIN_TOKEN_CHARS:
        return MerchantToken(
            "",
            "There is no merchant name in that booking, only numbers and dates, so there was "
            "nothing to look up.",
        )
    return MerchantToken(token)


def safe_query(query: str, token: MerchantToken) -> str:
    """The search query, held to the same rule as the token before it is sent.

    The model that writes the query has never seen anything but the token and the category
    list, so this is a guard at the boundary rather than a filter: it drops any word that
    carries a number or reads as a date, and falls back to the token itself when the query lost
    the merchant on the way.
    """
    words = [word for word in query.split() if not _NUMBERISH.search(word) and fold(word) not in DATE_WORDS]
    cleaned = " ".join(words)[: MAX_TOKEN_CHARS * 2].strip()
    if not cleaned or token.text not in fold(cleaned):
        return token.text
    return cleaned
