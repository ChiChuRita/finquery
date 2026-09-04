"""Merchant enrichment: from a bank booking text to a clean merchant, without a model.

A German booking text is the merchant plus noise: the card processor that took the payment,
the branch number, the date the terminal printed, the legal form, the city. Stage two of
categorization strips all of that (`merchant_of`) and looks the result up in a seed dictionary
of the merchants a German household meets (`DICTIONARY`). A hit carries a category, a
subcategory and the friendly title and short description that every row gets as its
enrichment, and it costs no model call.

Everything here is pure text work, so it is testable without a database and reusable by the
rule stage: `fold` is the one normalization both stages compare through.
"""

import re
from dataclasses import dataclass

UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue"})
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")
_WHITESPACE = re.compile(r"\s+")


def fold(text: str | None) -> str:
    """Lower case, umlauts spelled out, punctuation to spaces: the form both stages match on.

    `ALDI SÜD` and `Aldi-Sued` fold to `aldi sued`, so a pattern typed either way matches
    either booking.
    """
    if not text:
        return ""
    lowered = text.translate(UMLAUTS).casefold()
    return _WHITESPACE.sub(" ", _NOT_ALNUM.sub(" ", lowered)).strip()


def contains(folded_text: str, pattern: str) -> bool:
    """Does `pattern` start a word in `folded_text`?

    Word start, not whole word, so `apotheke` matches `apotheken am markt` and `zahnarzt`
    matches `zahnarztpraxis`, while `dm` does not match `edmond`.
    """
    needle = fold(pattern)
    if not needle:
        return False
    return re.search(rf"(?:^|\s){re.escape(needle)}", folded_text) is not None


# Card processors and payment services. They are the counterparty of the booking while the
# merchant or the person is in the text next to them, so their own words never belong to the
# merchant.
PROCESSORS: dict[str, str] = {
    "paypal": "PayPal",
    "pp": "PayPal",
    "sumup": "SumUp",
    "zettle": "Zettle",
    "izettle": "Zettle",
    "stripe": "Stripe",
    "klarna": "Klarna",
    "adyen": "Adyen",
    "mollie": "Mollie",
    "sq": "Square",
}

# Words a merchant name never needs: the booking kind the bank prints, legal forms, the
# terminal's pleasantries, the region.
NOISE = {
    "kartenzahlung", "kartenzahl", "karte", "girocard", "debitk", "debitkarte", "kreditkarte",
    "elv", "sepa", "lastschrift", "folgelastschrift", "dauerauftrag", "ueberweisung", "online",
    "gutschrift", "einzugsauftrag", "basislastschrift", "kauf", "kaufumsatz", "umsatz", "um",
    "nr", "fil", "filiale", "station", "markt", "marktes", "vielen", "dank", "danke", "dankt",
    "sagt", "ihnen", "bis", "bald", "ihre", "ihr", "zahlung", "zahlungen", "bestellung",
    "gmbh", "mbh", "ag", "kg", "kgaa", "ohg", "ek", "ug", "se", "co", "sarl", "sa", "rl", "bv",
    "nv", "ab", "as", "inc", "ltd", "plc", "llc", "holding", "vertriebs", "vertrieb", "handels",
    "deutschland", "germany", "europe", "european", "international", "de", "eu", "berlin",
    "hamburg", "muenchen", "koeln", "frankfurt", "stuttgart", "leipzig", "dresden", "and", "und",
    "the", "von", "am", "an", "im", "in", "fuer", "mit", "ref", "tan", "blz", "iban", "eur",
}
_DIGITS = re.compile(r"^\d+$")
MAX_KEY_WORDS = 4


@dataclass(frozen=True)
class Merchant:
    """One merchant as the pipeline sees it.

    `key` is the token the rules and the dictionary match on, and the pattern a Question card
    answer becomes a rule for. `title` is what the table and the charts show.
    """

    key: str
    title: str
    via: str | None = None
    """The processor the payment went through, when one was stripped ("PayPal")."""


def _words(source: str) -> list[str]:
    """The words of a booking text that could be part of a merchant name.

    Out go the noise words, the processors, the branch and reference numbers, and the single
    letters a folded legal form leaves behind (`S.a.r.l.` folds to `s a r l`).
    """
    return [
        word
        for word in fold(source).split()
        if word not in NOISE and word not in PROCESSORS and len(word) > 1 and not _DIGITS.match(word)
    ]


def _processor(folded: str) -> str | None:
    for token in folded.split():
        if label := PROCESSORS.get(token):
            return label
    return None


_VOWELS = set("aeiouy")


def _titled(words: list[str]) -> str:
    """Title case, except that a short word without a vowel is an abbreviation: DB, BVG, DM."""
    return " ".join(
        word.upper() if len(word) <= 4 and not (_VOWELS & set(word)) else word.capitalize() for word in words
    )


def merchant_of(description: str, counterparty: str | None = None) -> Merchant:
    """Strip the noise off a booking and name the merchant.

    The counterparty is the better source when the export carries one, except when it is only
    the processor that moved the money: a PayPal booking names PayPal as the counterparty and
    the person or the shop in the description, and the description is what the user recognizes.
    """
    via = _processor(fold(counterparty)) or _processor(fold(description))
    words = _words(counterparty or "") or _words(description)
    if not words:
        words = fold(description).split()[:MAX_KEY_WORDS]
    words = words[:MAX_KEY_WORDS]
    key = " ".join(words)
    derived = _titled(words) or "Unnamed"
    entry = lookup(key) or lookup(f"{key} {fold(counterparty)} {fold(description)}")
    if entry is None:
        return Merchant(key=key, title=derived, via=via)
    # A generic entry ("cafe", "apotheke") names the trade, not the shop, so the shop's own
    # name stays the title and only the category comes from the dictionary.
    return Merchant(key=key or fold(entry.title), title=derived if entry.generic else entry.title, via=via)


@dataclass(frozen=True)
class Known:
    """A merchant the app recognizes without asking a model."""

    pattern: str
    title: str
    blurb: str
    category: str
    subcategory: str | None = None
    generic: bool = False
    """True for a trade rather than a chain ("cafe", "apotheke"): it names the category but the
    shop keeps its own title."""


# About sixty merchants a German household meets, longest pattern first where one contains
# another ("amazon prime" before "amazon", "uber eats" before "uber").
DICTIONARY: tuple[Known, ...] = (
    # Groceries
    Known("rewe", "REWE", "supermarket", "Groceries", "Supermarket"),
    Known("edeka", "EDEKA", "supermarket", "Groceries", "Supermarket"),
    Known("lidl", "Lidl", "discount supermarket", "Groceries", "Supermarket"),
    Known("aldi", "ALDI", "discount supermarket", "Groceries", "Supermarket"),
    Known("kaufland", "Kaufland", "supermarket", "Groceries", "Supermarket"),
    Known("penny", "Penny", "discount supermarket", "Groceries", "Supermarket"),
    Known("netto", "Netto", "discount supermarket", "Groceries", "Supermarket"),
    Known("norma", "Norma", "discount supermarket", "Groceries", "Supermarket"),
    Known("tegut", "tegut", "supermarket", "Groceries", "Supermarket"),
    Known("globus", "Globus", "hypermarket", "Groceries", "Supermarket"),
    Known("alnatura", "Alnatura", "organic supermarket", "Groceries", "Supermarket"),
    Known("denns", "denn's Biomarkt", "organic supermarket", "Groceries", "Supermarket"),
    Known("bio company", "Bio Company", "organic supermarket", "Groceries", "Supermarket"),
    Known("backwerk", "BackWerk", "bakery", "Groceries", "Bakery"),
    Known("kamps", "Kamps", "bakery", "Groceries", "Bakery"),
    Known("steinecke", "Steinecke", "bakery", "Groceries", "Bakery"),
    Known("dm", "dm", "drugstore", "Groceries", "Drugstore"),
    Known("rossmann", "Rossmann", "drugstore", "Groceries", "Drugstore"),
    Known("mueller", "Mueller", "drugstore", "Groceries", "Drugstore"),
    # Dining
    Known("lieferando", "Lieferando", "food delivery", "Dining", "Delivery"),
    Known("uber eats", "Uber Eats", "food delivery", "Dining", "Delivery"),
    Known("wolt", "Wolt", "food delivery", "Dining", "Delivery"),
    Known("mcdonalds", "McDonald's", "fast food", "Dining", "Takeaway"),
    Known("burger king", "Burger King", "fast food", "Dining", "Takeaway"),
    Known("hans im glueck", "Hans im Glueck", "burger restaurant", "Dining", "Restaurant"),
    Known("dean david", "dean&david", "salads and bowls", "Dining", "Takeaway"),
    Known("vapiano", "Vapiano", "italian restaurant", "Dining", "Restaurant"),
    Known("l osteria", "L'Osteria", "italian restaurant", "Dining", "Restaurant"),
    Known("starbucks", "Starbucks", "coffee house", "Dining", "Cafe"),
    # Transport
    Known("deutsche bahn", "Deutsche Bahn", "rail travel", "Transport", "Public transport"),
    Known("db fernverkehr", "Deutsche Bahn", "rail travel", "Transport", "Public transport"),
    Known("bvg", "BVG", "Berlin public transport", "Transport", "Public transport"),
    Known("hvv", "HVV", "Hamburg public transport", "Transport", "Public transport"),
    Known("mvg", "MVG", "Munich public transport", "Transport", "Public transport"),
    Known("flixbus", "FlixBus", "coach travel", "Transport", "Public transport"),
    Known("uber", "Uber", "ride hailing", "Transport", "Ride hailing"),
    Known("bolt", "Bolt", "ride hailing", "Transport", "Ride hailing"),
    Known("freenow", "FREENOW", "ride hailing", "Transport", "Ride hailing"),
    Known("shell", "Shell", "petrol station", "Transport", "Fuel"),
    Known("aral", "Aral", "petrol station", "Transport", "Fuel"),
    Known("esso", "Esso", "petrol station", "Transport", "Fuel"),
    Known("total energies", "TotalEnergies", "petrol station", "Transport", "Fuel"),
    # Subscriptions
    Known("netflix", "Netflix", "video streaming", "Subscriptions", "Streaming"),
    Known("amazon prime", "Amazon Prime", "video streaming and delivery", "Subscriptions", "Streaming"),
    Known("amzn prime", "Amazon Prime", "video streaming and delivery", "Subscriptions", "Streaming"),
    Known("disney", "Disney+", "video streaming", "Subscriptions", "Streaming"),
    Known("dazn", "DAZN", "sports streaming", "Subscriptions", "Streaming"),
    Known("spotify", "Spotify", "music streaming", "Subscriptions", "Music"),
    Known("adobe", "Adobe", "creative software", "Subscriptions", "Software"),
    Known("microsoft", "Microsoft", "software", "Subscriptions", "Software"),
    Known("dropbox", "Dropbox", "cloud storage", "Subscriptions", "Software"),
    Known("github", "GitHub", "developer platform", "Subscriptions", "Software"),
    Known("audible", "Audible", "audiobooks", "Subscriptions", "News"),
    Known("spiegel", "Der Spiegel", "news subscription", "Subscriptions", "News"),
    # Shopping
    Known("amazon", "Amazon", "online marketplace", "Shopping", "Online marketplace"),
    Known("amzn", "Amazon", "online marketplace", "Shopping", "Online marketplace"),
    Known("zalando", "Zalando", "fashion online", "Shopping", "Clothing"),
    Known("otto", "OTTO", "online department store", "Shopping", "Online marketplace"),
    Known("mediamarkt", "MediaMarkt", "electronics store", "Shopping", "Electronics"),
    Known("saturn", "Saturn", "electronics store", "Shopping", "Electronics"),
    Known("cyberport", "Cyberport", "electronics store", "Shopping", "Electronics"),
    Known("ikea", "IKEA", "furniture store", "Shopping", "Home"),
    Known("obi", "OBI", "hardware store", "Shopping", "Home"),
    Known("bauhaus", "Bauhaus", "hardware store", "Shopping", "Home"),
    Known("hornbach", "Hornbach", "hardware store", "Shopping", "Home"),
    Known("zara", "Zara", "fashion store", "Shopping", "Clothing"),
    Known("decathlon", "Decathlon", "sports store", "Shopping", "Clothing"),
    Known("thalia", "Thalia", "book store", "Leisure", "Books"),
    # Communication
    Known("telekom", "Deutsche Telekom", "telecoms", "Communication", None),
    Known("vodafone", "Vodafone", "telecoms", "Communication", "Mobile"),
    Known("congstar", "congstar", "mobile network", "Communication", "Mobile"),
    Known("telefonica", "o2", "mobile network", "Communication", "Mobile"),
    # Housing
    Known("vattenfall", "Vattenfall", "electricity supplier", "Housing", "Electricity"),
    Known("gasag", "GASAG", "gas supplier", "Housing", "Heating"),
    # Health, insurance, cash
    Known("fitness first", "Fitness First", "gym membership", "Health", "Fitness"),
    Known("mcfit", "McFIT", "gym membership", "Health", "Fitness"),
    Known("urban sports", "Urban Sports Club", "gym membership", "Health", "Fitness"),
    Known("fielmann", "Fielmann", "optician", "Health", None),
    Known("allianz", "Allianz", "insurer", "Insurance", None),
    Known("huk", "HUK-COBURG", "insurer", "Insurance", None),
    Known("axa", "AXA", "insurer", "Insurance", None),
    Known("techniker krankenkasse", "Techniker Krankenkasse", "health insurer", "Insurance", "Health insurance"),
    Known("geldautomat", "Cash withdrawal", "cash from an ATM", "Cash", "Cash withdrawal"),
    Known("bargeldauszahlung", "Cash withdrawal", "cash from an ATM", "Cash", "Cash withdrawal"),
    # Trades rather than chains: they name the category, the shop keeps its own title.
    Known("baeckerei", "Baeckerei", "bakery", "Groceries", "Bakery", generic=True),
    Known("doener", "Doener", "kebab shop", "Dining", "Takeaway", generic=True),
    Known("pizzeria", "Pizzeria", "pizza restaurant", "Dining", "Restaurant", generic=True),
    Known("cafe", "Cafe", "cafe", "Dining", "Cafe", generic=True),
    Known("stadtwerke", "Stadtwerke", "municipal utilities", "Housing", "Electricity", generic=True),
    Known("apotheke", "Apotheke", "pharmacy", "Health", "Pharmacy", generic=True),
    Known("zahnarzt", "Zahnarzt", "dental practice", "Health", "Doctor", generic=True),
)


def lookup(folded_text: str) -> Known | None:
    """The first dictionary entry whose pattern starts a word in this folded text."""
    for entry in DICTIONARY:
        if contains(folded_text, entry.pattern):
            return entry
    return None
