"""The merchant sets the prototypes run on. Nothing private: the synthetic year and public
brand names written the way a Sparkasse export prints them.

`SYNTHETIC_REVIEW` is what step 1 (the quality review) runs the loop on: twenty booking strings
from `fixtures/synthetic/sparkasse-2025.csv`, well-known and unknown mixed, so the run shows
how the loop behaves when it already knows and when it does not.

`LABELED` is the measurement set for step 3a: merchants outside the seed dictionary, each with
a hand-assigned truth. `truth` is a set of acceptable categories (one where the case is clear,
two where a household could file it either way), `sub` the expected subcategory or None when
none is clearly right. `tier` is `chain` for a national brand every model has seen, `local` for
a regional, generic, badly-tokenized or fictional name, which is where the web should matter.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    counterparty: str
    description: str
    truth: frozenset[str]
    sub: str | None
    tier: str
    average_cents: int
    incoming: bool = False

    @property
    def label(self) -> str:
        return self.counterparty


def case(counterparty, description, truth, sub, tier, cents, incoming=False) -> Case:
    truth = {truth} if isinstance(truth, str) else set(truth)
    return Case(counterparty, description, frozenset(truth), sub, tier, cents, incoming)


# (description, counterparty) straight from the synthetic CSV.
SYNTHETIC_REVIEW: list[tuple[str, str | None]] = [
    ("LIDL DANKT IHNEN", "LIDL Vertriebs GmbH"),
    ("DM FIL 8817 BERLIN", "dm drogerie markt"),
    ("NETTO FILIALE 3312", "NETTO MARKEN-DISCOUNT"),
    ("LIEFERANDO BESTELLUNG", "Lieferando.de"),
    ("DEAN+DAVID 1188", "DEAN AND DAVID"),
    ("DOENER HAUS", "Döner Haus Kreuzberg"),
    ("CAFE MILCHBART", "Cafe Milchbart"),
    ("VAPIANO MITTE", "VAPIANO Berlin Mitte"),
    ("UBER TRIP HELP.UBER.COM", "UBER BV"),
    ("SHELL STATION 1204", "SHELL DEUTSCHLAND"),
    ("MAGENTA ZUHAUSE 100 MBIT", "Telekom Deutschland GmbH"),
    ("ADOBE CREATIVE CLOUD ABO", "ADOBE SYSTEMS SOFTWARE"),
    ("DEUTSCHLANDTICKET 03/2025", "BVG Berliner Verkehrsbetriebe"),
    ("STROM ABSCHLAG 03/2025", "Vattenfall Europe Sales GmbH"),
    ("HAUSRAT UND HAFTPFLICHT 03/2025", "Allianz Versicherungs-AG"),
    ("GA NR00012345 BLZ12030000 01.03/BERLIN", "Sparkasse Geldautomat"),
    ("MIETE WOHNUNG 12 03/2025", "Hausverwaltung Bergmann GmbH"),
    ("GEHALT 03/2025 PERS.NR 4711", "Mustermann Systems GmbH"),
    ("RECHNUNG 2025-8841", "Zahnarztpraxis Dr. Lorenz"),
    ("APOTHEKE AM MARKT", "Apotheke am Markt"),
    ("PP.4711.PP . ANNA WEBER, Ihre Zahlung", "PayPal Europe S.a.r.l."),
]

# The four synthetic merchants the dictionary does not place, with the generator's truth.
SYNTHETIC_UNKNOWN: list[Case] = [
    case("Hausverwaltung Bergmann GmbH", "MIETE WOHNUNG 12 03/2025", "Housing", "Rent", "local", -115000),
    case("Mustermann Systems GmbH", "GEHALT 03/2025 PERS.NR 4711", "Income", "Salary", "local", 285000, True),
    case("Zahnarztpraxis Dr. Lorenz", "RECHNUNG 2025-8841", "Health", "Doctor", "local", -18900),
    case("PayPal Europe S.a.r.l.", "PP.4711.PP . ANNA WEBER, Ihre Zahlung", "Transfers", "Friends and family", "local", -2400),
    case("PayPal Europe S.a.r.l.", "PP.4711.PP . MAX SCHULZ, Ihre Zahlung", "Transfers", "Friends and family", "local", -2100),
]

LABELED: list[Case] = [
    # Groceries
    case("Combi Verbrauchermarkt", "COMBI FRISCH NEBENAN", "Groceries", "Supermarket", "local", -3450),
    case("HIT Handelsgruppe", "HIT MARKT 0812", "Groceries", "Supermarket", "local", -4120),
    case("nahkauf Kraemer", "NAHKAUF SAGT DANKE", "Groceries", "Supermarket", "local", -1830),
    case("Brezelbaeckerei Ditsch GmbH", "DITSCH HBF BERLIN", "Groceries", "Bakery", "local", -480),
    case("BackFactory GmbH", "BACKFACTORY 0771", "Groceries", "Bakery", "chain", -520),
    case("BUDNI Handels- und Service GmbH", "BUDNIKOWSKY 0233", "Groceries", "Drugstore", "local", -1870),
    case("Flaschenpost SE", "FLASCHENPOST BESTELLUNG", "Groceries", "Supermarket", "chain", -3890),
    case("HelloFresh Deutschland SE", "HELLOFRESH BOX", {"Groceries", "Dining"}, None, "chain", -5990),
    case("Metzgerei Huber", "METZGEREI HUBER", "Groceries", None, "local", -1890),
    # Dining
    case("NORDSEE GmbH", "NORDSEE 4711", "Dining", None, "chain", -1290),
    case("Block House Restaurantbetriebe AG", "BLOCK HOUSE", "Dining", "Restaurant", "chain", -6420),
    case("Five Guys Germany GmbH", "FIVE GUYS BERLIN", "Dining", "Takeaway", "chain", -2380),
    case("Coffee Fellows GmbH", "COFFEE FELLOWS 118", "Dining", "Cafe", "chain", -640),
    case("Espresso House Germany GmbH", "ESPRESSO HOUSE", "Dining", "Cafe", "chain", -590),
    case("Sausalitos Holding GmbH", "SAUSALITOS", "Dining", "Restaurant", "chain", -4370),
    case("Peter Pane Burgergrill", "PETER PANE", "Dining", "Restaurant", "local", -3120),
    # Transport
    case("Sixt GmbH & Co Autovermietung KG", "SIXT AUTOVERMIETUNG", "Transport", "Car", "chain", -12900),
    case("MILES Mobility GmbH", "MILES TRIP", "Transport", None, "chain", -1840),
    case("TIER Mobility SE", "TIER SCOOTER", "Transport", None, "chain", -380),
    case("FlixTrain GmbH", "FLIXTRAIN TICKET", "Transport", "Public transport", "chain", -2990),
    case("JET Tankstellen Deutschland GmbH", "JET 3311 BERLIN", "Transport", "Fuel", "chain", -6230),
    case("Deutsche Tamoil GmbH", "HEM TANKSTELLE 0451", "Transport", "Fuel", "local", -5890),
    case("ADAC e.V.", "ADAC MITGLIEDSBEITRAG", {"Transport", "Insurance"}, None, "chain", -9400),
    # Shopping
    case("TEDi GmbH & Co. KG", "TEDI 3101", "Shopping", "Home", "chain", -1230),
    case("Action Deutschland GmbH", "ACTION 2211", "Shopping", "Home", "chain", -1890),
    case("KiK Textilien und Non-Food GmbH", "KIK 4432", "Shopping", "Clothing", "chain", -2450),
    case("Deichmann SE", "DEICHMANN 0914", "Shopping", "Clothing", "chain", -4990),
    case("Parfuemerie Douglas GmbH", "DOUGLAS 0455", "Shopping", None, "chain", -3990),
    case("Snipes SE", "SNIPES 0288", "Shopping", "Clothing", "chain", -7990),
    case("Intersport Deutschland eG", "INTERSPORT VOSWINKEL", "Shopping", "Clothing", "chain", -5990),
    case("toom Baumarkt GmbH", "TOOM BAUMARKT 3390", "Shopping", "Home", "chain", -4320),
    case("POCO Einrichtungsmaerkte GmbH", "POCO 1180", "Shopping", "Home", "chain", -12900),
    case("About You SE", "ABOUT YOU", "Shopping", "Clothing", "chain", -6490),
    case("Temu", "TEMU.COM", "Shopping", "Online marketplace", "chain", -2390),
    case("Fressnapf Tiernahrungs GmbH", "FRESSNAPF 0721", "Shopping", None, "chain", -3450),
    case("Conrad Electronic SE", "CONRAD 0102", "Shopping", "Electronics", "chain", -4990),
    case("Hugendubel Digital GmbH", "HUGENDUBEL 0338", "Leisure", "Books", "chain", -2490),
    case("Blumen Riedel", "BLUMEN RIEDEL", {"Shopping", "Leisure"}, None, "local", -1500),
    # Subscriptions
    case("Sky Deutschland Fernsehen GmbH", "SKY ABO", "Subscriptions", "Streaming", "chain", -2999),
    case("Deezer SA", "DEEZER PREMIUM", "Subscriptions", "Music", "chain", -1199),
    case("Xbox Game Pass", "XBOX GAME PASS ULTIMATE", {"Subscriptions", "Leisure"}, None, "chain", -1499),
    case("Duolingo Inc", "DUOLINGO", {"Education", "Subscriptions"}, None, "chain", -899),
    case("Zeit Online GmbH", "ZEIT DIGITAL ABO", "Subscriptions", "News", "local", -2199),
    # Health
    case("clever fit GmbH", "CLEVER FIT MITGLIEDSBEITRAG", "Health", "Fitness", "chain", -2990),
    case("FitX Deutschland GmbH", "FITX MITGLIEDSBEITRAG", "Health", "Fitness", "chain", -2500),
    case("Shop Apotheke B.V.", "SHOP APOTHEKE BESTELLUNG", "Health", "Pharmacy", "chain", -4390),
    case("Apollo-Optik Holding GmbH", "APOLLO OPTIK", "Health", None, "chain", -19900),
    case("Kieser Training AG", "KIESER TRAINING", "Health", "Fitness", "chain", -6900),
    case("Physiotherapie Am Park", "PHYSIO REZEPT", "Health", "Doctor", "local", -3500),
    # Insurance
    case("Debeka Krankenversicherungsverein a.G.", "KV BEITRAG", "Insurance", "Health insurance", "chain", -42000),
    case("ERGO Versicherung AG", "HAFTPFLICHT BEITRAG", "Insurance", "Liability", "chain", -8900),
    case("BARMER", "KRANKENVERSICHERUNG BEITRAG", "Insurance", "Health insurance", "chain", -21000),
    # Housing and communication
    case("E.ON Energie Deutschland GmbH", "STROM ABSCHLAG", "Housing", "Electricity", "local", -8900),
    case("Yello Strom GmbH", "YELLO ABSCHLAG", "Housing", "Electricity", "chain", -7800),
    case("Octopus Energy Germany GmbH", "STROM ABSCHLAG", "Housing", "Electricity", "chain", -8100),
    case("1&1 Telecom GmbH", "DSL RECHNUNG", {"Housing", "Communication"}, None, "local", -3999),
    case("freenet DLS GmbH", "KLARMOBIL RECHNUNG", "Communication", "Mobile", "local", -1499),
    # Leisure
    case("CinemaxX Entertainment GmbH", "CINEMAXX 0510", "Leisure", "Events", "chain", -2650),
    case("Tierpark Berlin-Friedrichsfelde GmbH", "TIERPARK BERLIN", "Leisure", "Events", "local", -1800),
    case("Jochen Schweizer GmbH", "JOCHEN SCHWEIZER ERLEBNIS", "Leisure", "Events", "chain", -12900),
    case("Karls Markt OHG", "KARLS ERLEBNIS DORF", {"Leisure", "Groceries"}, None, "local", -3400),
    # Fees and taxes
    case("ARD ZDF Deutschlandradio Beitragsservice", "RUNDFUNKBEITRAG", {"Fees and taxes", "Housing", "Subscriptions"}, None, "chain", -5508),
    case("Finanzamt Berlin Mitte/Tiergarten", "EINKOMMENSTEUER", "Fees and taxes", "Taxes", "local", -45000),
    case("Landeshauptkasse Berlin", "BUSSGELD AKTENZEICHEN", "Fees and taxes", None, "local", -3500),
    # Transfers and income
    case("Trade Republic Bank GmbH", "SPARPLAN", "Transfers", "Savings", "chain", -20000),
    case("Scalable Capital GmbH", "SPARPLAN ETF", "Transfers", "Savings", "chain", -15000),
    case("Bundesagentur fuer Arbeit", "ARBEITSLOSENGELD", "Income", "Other income", "chain", 145000, True),
    # Education
    case("Fahrschule Mobil GmbH", "FAHRSTUNDEN", "Education", "Courses", "local", -25000),
    case("VHS Berlin Mitte", "KURSGEBUEHR", "Education", "Courses", "local", -12000),
]

# Receipt headers as the receipt reader returned them (the 2026-09-05 receipts review) plus
# the four synthetic bills. What a store resolver would get.
RECEIPT_HEADERS: list[str] = [
    "Combi. Frisch. Nebenan.",
    "HIT-Tankstelle",
    "Saurüsselalm",
    "NEUHAUSER AUGUSTINER",
    "Fressnapf Köln-Ehrenfeld",
    "Ecenter EDEKA",
    "SCHLÖCKER",
    "VOGTLANDBAHN-GMBH",
    "Kreiller Str. 81673 München",
    "ALDI HESEL, IM BRINK 8",
    "ROSSMANN Mein Drogeriemarkt",
    "Esso Station",
    "EDEKA Sander",
    "OBI Baumarkt",
    "HANS IM GLUECK Burgergrill",
    "ROSSMANN Drogeriemarkt",
]
