"""Generate the shipped synthetic German household dataset.

One canonical year (2025) of a Berlin household: salary, rent, utilities, several grocery
chains, transport, subscriptions, PayPal to friends, Amazon, restaurants and cash withdrawals.
The same bookings are written three ways so every reader has something to chew on:

- `sparkasse-2025.csv`: Sparkasse CAMT layout, semicolon, cp1252, `1.234,56`, DD.MM.YYYY.
- `unknown-bank-2025.csv`: renamed and reordered headers with separate Soll and Haben columns,
  the file the mapping sub-agent is exercised against.
- `sparkasse-kontoauszug-2025.pdf`: text PDF with a running balance whose opening balance plus
  all bookings equals the printed closing balance.
- four bill images whose line items sum to the total of a booking that is in the CSV, so the
  bill photo flow has something real to match against.

Everything is deterministic. Run it with `uv run python scripts/generate_synthetic.py`; the
output is committed under `fixtures/synthetic/`.
"""

from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
YEAR = 2025
IBAN = "DE02120300000000202051"
BIC = "BYLADEM1001"
HOLDER = "Lena Mustermann"
OPENING_CENTS = 421055
SEED = 20250101

FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)


@dataclass(frozen=True)
class Booking:
    booked_on: date
    amount_cents: int
    booking_text: str
    counterparty: str
    reference: str


@dataclass(frozen=True)
class Bill:
    slug: str
    merchant: str
    address: str
    booked_on: date
    time: str
    items: tuple[tuple[str, int], ...]

    @property
    def total_cents(self) -> int:
        return sum(cents for _, cents in self.items)


BILLS = (
    Bill(
        slug="edeka",
        merchant="EDEKA Sander",
        address="Danziger Str. 42, 10435 Berlin",
        booked_on=date(YEAR, 3, 14),
        time="18:37",
        items=(
            ("Vollmilch 3,5% 1L", 129),
            ("Vollkornbrot 750g", 249),
            ("Bio-Eier 10 Stk", 349),
            ("Rispentomaten 500g", 219),
            ("Spuelmittel Zitrone", 199),
            ("Kuechenrolle 4x", 229),
            ("Waschmittel 20WL", 699),
        ),
    ),
    Bill(
        slug="rossmann",
        merchant="ROSSMANN Drogeriemarkt",
        address="Frankfurter Allee 111, 10247 Berlin",
        booked_on=date(YEAR, 5, 8),
        time="11:04",
        items=(
            ("Zahnpasta Complete", 245),
            ("Duschgel Sport 300ml", 329),
            ("Shampoo Repair", 419),
            ("Vitamin D3 Tabletten", 899),
        ),
    ),
    Bill(
        slug="obi",
        merchant="OBI Baumarkt",
        address="Landsberger Allee 277, 13055 Berlin",
        booked_on=date(YEAR, 7, 19),
        time="10:22",
        items=(
            ("Spanplattenschrauben 4x40", 499),
            ("Wandfarbe weiss 5L", 2499),
            ("Pinselset 3-teilig", 849),
            ("Abdeckfolie 4x5m", 329),
        ),
    ),
    Bill(
        slug="hans-im-glueck",
        merchant="HANS IM GLUECK Burgergrill",
        address="Alexanderplatz 7, 10178 Berlin",
        booked_on=date(YEAR, 9, 6),
        time="20:12",
        items=(
            ("Der Grosse Bruder Burger", 1390),
            ("Suesskartoffel Pommes", 390),
            ("Hausgemachte Limonade", 350),
            ("Craft Beer 0,33l", 460),
        ),
    ),
)

GROCERS = (
    ("EDEKA Sander", "EDEKA SAGT DANKE", 900, 6800),
    ("REWE Markt GmbH", "REWE SAGT DANKE. BIS BALD", 1100, 7200),
    ("ALDI SÜD", "ALDI SUED SAGT DANKE", 700, 5400),
    ("LIDL Vertriebs GmbH", "LIDL DANKT IHNEN", 800, 5900),
    ("NETTO MARKEN-DISCOUNT", "NETTO FILIALE 3312", 600, 4200),
    ("KAUFLAND BERLIN", "KAUFLAND 4711 BERLIN", 1500, 8900),
    ("dm drogerie markt", "DM FIL 8817 BERLIN", 500, 3900),
    ("Bäckerei Steinecke", "BAECKEREI STEINECKE", 250, 1400),
)

DINING = (
    ("VAPIANO Berlin Mitte", "VAPIANO MITTE", 1400, 3400),
    ("DEAN AND DAVID", "DEAN+DAVID 1188", 900, 1900),
    ("Döner Haus Kreuzberg", "DOENER HAUS", 550, 1400),
    ("Cafe Milchbart", "CAFE MILCHBART", 380, 1250),
    ("Lieferando.de", "LIEFERANDO BESTELLUNG", 1600, 4200),
)

TRANSPORT = (
    ("Deutsche Bahn AG", "DB FERNVERKEHR TICKET", 1900, 8900),
    ("SHELL DEUTSCHLAND", "SHELL STATION 1204", 4200, 8500),
    ("UBER BV", "UBER TRIP HELP.UBER.COM", 900, 2600),
)

MONTHLY = (
    # day, cents, Buchungstext, counterparty, Verwendungszweck
    (1, -115000, "DAUERAUFTRAG", "Hausverwaltung Bergmann GmbH", "MIETE WOHNUNG 12 {month:02d}/{year}"),
    (1, -3990, "FOLGELASTSCHRIFT", "Fitness First Germany", "MITGLIEDSBEITRAG {month:02d}/{year}"),
    (2, -4250, "FOLGELASTSCHRIFT", "Allianz Versicherungs-AG", "HAUSRAT UND HAFTPFLICHT {month:02d}/{year}"),
    (5, -3999, "FOLGELASTSCHRIFT", "Telekom Deutschland GmbH", "MAGENTA ZUHAUSE 100 MBIT"),
    (7, -1299, "FOLGELASTSCHRIFT", "NETFLIX INTERNATIONAL BV", "NETFLIX STANDARD ABO"),
    (8, -1999, "FOLGELASTSCHRIFT", "Vodafone GmbH", "MOBILFUNK RECHNUNG {month:02d}/{year}"),
    (11, -1099, "FOLGELASTSCHRIFT", "SPOTIFY AB", "SPOTIFY PREMIUM"),
    (15, -7800, "FOLGELASTSCHRIFT", "Vattenfall Europe Sales GmbH", "STROM ABSCHLAG {month:02d}/{year}"),
    (19, -899, "KARTENZAHLUNG", "AMAZON PRIME MEMBERSHIP", "AMZN PRIME DE MITGLIEDSCHAFT"),
    (22, -2379, "KARTENZAHLUNG", "ADOBE SYSTEMS SOFTWARE", "ADOBE CREATIVE CLOUD ABO"),
    (25, -4900, "FOLGELASTSCHRIFT", "BVG Berliner Verkehrsbetriebe", "DEUTSCHLANDTICKET {month:02d}/{year}"),
    (28, 285000, "LOHN  GEHALT", "Mustermann Systems GmbH", "GEHALT {month:02d}/{year} PERS.NR 4711"),
)

FRIENDS = ("ANNA WEBER", "MAX SCHULZ", "JONAS KELLER", "LEA HOFFMANN")


def month_days(month: int) -> int:
    following = date(YEAR + month // 12, month % 12 + 1, 1)
    return (following - timedelta(days=1)).day


def clamp_day(month: int, day: int) -> date:
    return date(YEAR, month, min(day, month_days(month)))


def generate() -> list[Booking]:
    rng = random.Random(SEED)
    bookings: list[Booking] = []

    for month in range(1, 13):
        for day, cents, booking_text, counterparty, reference in MONTHLY:
            bookings.append(
                Booking(
                    clamp_day(month, day),
                    cents,
                    booking_text,
                    counterparty,
                    reference.format(month=month, year=YEAR),
                )
            )

        for _ in range(rng.randint(9, 13)):
            counterparty, reference, low, high = rng.choice(GROCERS)
            bookings.append(
                Booking(
                    clamp_day(month, rng.randint(1, 28)),
                    -rng.randrange(low, high, 10),
                    "KARTENZAHLUNG",
                    counterparty,
                    reference,
                )
            )

        for _ in range(rng.randint(3, 6)):
            counterparty, reference, low, high = rng.choice(DINING)
            bookings.append(
                Booking(
                    clamp_day(month, rng.randint(1, 28)),
                    -rng.randrange(low, high, 10),
                    "KARTENZAHLUNG",
                    counterparty,
                    reference,
                )
            )

        for _ in range(rng.randint(1, 3)):
            counterparty, reference, low, high = rng.choice(TRANSPORT)
            bookings.append(
                Booking(
                    clamp_day(month, rng.randint(1, 28)),
                    -rng.randrange(low, high, 10),
                    "KARTENZAHLUNG",
                    counterparty,
                    reference,
                )
            )

        for _ in range(rng.randint(1, 3)):
            bookings.append(
                Booking(
                    clamp_day(month, rng.randint(1, 28)),
                    -rng.randrange(890, 12900, 10),
                    "KARTENZAHLUNG",
                    "AMAZON EU S.A R.L.",
                    f"AMZN Mktp DE {rng.randrange(100000, 999999)}",
                )
            )

        for _ in range(rng.randint(1, 3)):
            friend = rng.choice(FRIENDS)
            bookings.append(
                Booking(
                    clamp_day(month, rng.randint(1, 28)),
                    -rng.randrange(800, 4500, 50),
                    "ONLINE-UEBERWEISUNG",
                    "PayPal Europe S.a.r.l.",
                    f"PP.4711.PP . {friend}, Ihre Zahlung",
                )
            )

        for _ in range(rng.randint(1, 2)):
            bookings.append(
                Booking(
                    clamp_day(month, rng.randint(1, 28)),
                    -rng.choice((5000, 10000, 20000)),
                    "BARGELDAUSZAHLUNG",
                    "Sparkasse Geldautomat",
                    f"GA NR00012345 BLZ12030000 {clamp_day(month, 1):%d.%m}/BERLIN",
                )
            )

    for bill in BILLS:
        bookings.append(
            Booking(bill.booked_on, -bill.total_cents, "KARTENZAHLUNG", bill.merchant, f"{bill.merchant.upper()} BERLIN")
        )

    bookings.append(Booking(date(YEAR, 4, 3), 3490, "GUTSCHRIFT", "AMAZON EU S.A R.L.", "AMZN RETOUR ERSTATTUNG"))
    bookings.append(Booking(date(YEAR, 6, 12), -2340, "KARTENZAHLUNG", "Apotheke am Markt", "APOTHEKE AM MARKT"))
    bookings.append(Booking(date(YEAR, 11, 21), -18900, "FOLGELASTSCHRIFT", "Zahnarztpraxis Dr. Lorenz", "RECHNUNG 2025-8841"))

    bookings.sort(key=lambda booking: (booking.booked_on, booking.counterparty))
    return bookings


def euro(cents: int) -> str:
    """German money: 1.234,56 and -1.234,56."""
    sign = "-" if cents < 0 else ""
    whole, remainder = divmod(abs(cents), 100)
    return f"{sign}{whole:,}".replace(",", ".") + f",{remainder:02d}"


SPARKASSE_HEADER = (
    "Auftragskonto",
    "Buchungstag",
    "Valutadatum",
    "Buchungstext",
    "Verwendungszweck",
    "Glaeubiger ID",
    "Mandatsreferenz",
    "Kundenreferenz (End-to-End)",
    "Sammlerreferenz",
    "Lastschrift Ursprungsbetrag",
    "Auslagenersatz Ruecklastschrift",
    "Beguenstigter/Zahlungspflichtiger",
    "Kontonummer/IBAN",
    "BIC (SWIFT-Code)",
    "Betrag",
    "Waehrung",
    "Info",
)


def write_sparkasse_csv(bookings: list[Booking], path: Path) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(SPARKASSE_HEADER)
    for booking in bookings:
        writer.writerow(
            (
                IBAN,
                f"{booking.booked_on:%d.%m.%Y}",
                f"{booking.booked_on:%d.%m.%Y}",
                booking.booking_text,
                booking.reference,
                "",
                "",
                "",
                "",
                "",
                "",
                booking.counterparty,
                "",
                "",
                euro(booking.amount_cents),
                "EUR",
                "Umsatz gebucht",
            )
        )
    path.write_bytes(buffer.getvalue().encode("cp1252"))


def write_unknown_bank_csv(bookings: list[Booking], path: Path) -> None:
    """The same year with headers no preset knows and outflow and inflow in two columns."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(("Belegnr", "Empfänger/Auftraggeber", "Datum", "Vorgangsart", "Buchungsinfo", "Soll", "Haben", "Wg"))
    for number, booking in enumerate(bookings, start=1):
        outgoing = euro(-booking.amount_cents) if booking.amount_cents < 0 else ""
        incoming = euro(booking.amount_cents) if booking.amount_cents > 0 else ""
        writer.writerow(
            (
                f"B{number:05d}",
                booking.counterparty,
                f"{booking.booked_on:%d.%m.%Y}",
                booking.booking_text.title(),
                booking.reference,
                outgoing,
                incoming,
                "EUR",
            )
        )
    path.write_bytes(buffer.getvalue().encode("cp1252"))


class Statement(FPDF):
    def header(self) -> None:
        self.set_font("Helvetica", "B", 13)
        self.cell(120, 6, "Sparkasse Musterstadt", new_x="LEFT", new_y="NEXT")
        self.set_font("Helvetica", "", 8)
        self.cell(120, 4, "Kontoauszug Nr. 1/2025", new_x="LEFT", new_y="NEXT")
        self.set_xy(140, 10)
        self.set_font("Helvetica", "", 8)
        self.cell(60, 4, f"Seite {self.page_no()}", align="R", new_x="LEFT", new_y="NEXT")
        self.set_xy(10, 26)
        self.set_font("Helvetica", "B", 8)
        self.cell(18, 5, "Buchung")
        self.cell(18, 5, "Valuta")
        self.cell(96, 5, "Buchungstext / Verwendungszweck")
        self.cell(26, 5, "Betrag EUR", align="R")
        self.cell(26, 5, "Saldo EUR", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y() + 0.5, 200, self.get_y() + 0.5)
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 7)
        self.cell(0, 4, f"IBAN {IBAN}  BIC {BIC}  Kontoinhaber {HOLDER}", align="C")


def write_statement_pdf(bookings: list[Booking], path: Path) -> None:
    pdf = Statement(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(10, 10, 10)
    pdf.add_page()

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, f"Kontoinhaber: {HOLDER}    Zeitraum: 01.01.{YEAR} - 31.12.{YEAR}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"Alter Kontostand: {euro(OPENING_CENTS)} EUR", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    balance = OPENING_CENTS
    for booking in bookings:
        balance += booking.amount_cents
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(18, 4.4, f"{booking.booked_on:%d.%m.%y}")
        pdf.cell(18, 4.4, f"{booking.booked_on:%d.%m.%y}")
        pdf.cell(96, 4.4, f"{booking.booking_text}  {booking.counterparty}"[:64])
        pdf.cell(26, 4.4, euro(booking.amount_cents), align="R")
        pdf.cell(26, 4.4, euro(balance), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "I", 7)
        pdf.cell(36, 4, "")
        pdf.cell(96, 4, booking.reference[:70], new_x="LMARGIN", new_y="NEXT")

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 6, f"Neuer Kontostand: {euro(balance)} EUR", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(
        0,
        5,
        f"Summe der Buchungen: {euro(balance - OPENING_CENTS)} EUR aus {len(bookings)} Buchungen",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.output(str(path))


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)


def write_bill_image(bill: Bill, path: Path) -> None:
    width, line_height = 620, 26
    image = Image.new("RGB", (width, 400 + line_height * (len(bill.items) + 6)), "#f7f6f2")
    draw = ImageDraw.Draw(image)
    title, body, small = _font(26), _font(19), _font(15)

    def row(y: int, left: str, right: str = "", font=body) -> None:  # noqa: ANN001
        draw.text((40, y), left, fill="#111111", font=font)
        if right:
            draw.text((width - 40, y), right, fill="#111111", font=font, anchor="ra")

    y = 40
    draw.text((width // 2, y), bill.merchant, fill="#111111", font=title, anchor="ma")
    y += 40
    draw.text((width // 2, y), bill.address, fill="#333333", font=small, anchor="ma")
    y += 26
    draw.text((width // 2, y), "Tel. 030 / 55 44 21", fill="#333333", font=small, anchor="ma")
    y += 40
    row(y, f"{bill.booked_on:%d.%m.%Y}", bill.time, small)
    y += 30
    draw.line((40, y, width - 40, y), fill="#999999", width=2)
    y += 18

    for name, cents in bill.items:
        row(y, name, euro(cents))
        y += line_height

    y += 6
    draw.line((40, y, width - 40, y), fill="#999999", width=2)
    y += 18
    row(y, "SUMME EUR", euro(bill.total_cents), title)
    y += 44
    row(y, "Kartenzahlung EC", euro(bill.total_cents), small)
    y += 26
    row(y, "MwSt 19% enthalten", euro(round(bill.total_cents * 19 / 119)), small)
    y += 40
    draw.text((width // 2, y), "Vielen Dank fuer Ihren Einkauf", fill="#333333", font=small, anchor="ma")
    image.crop((0, 0, width, y + 44)).save(path, optimize=True)


README = """\
# Synthetic dataset

One canonical year (2025) of a German household, generated by `scripts/generate_synthetic.py`.
Deterministic: re-running the script reproduces these files byte for byte. No personal data.

| File | What it is |
| ---- | ---------- |
| `sparkasse-2025.csv` | Sparkasse CAMT export layout: semicolon, cp1252, `1.234,56`, DD.MM.YYYY. Matches the `sparkasse` preset. |
| `unknown-bank-2025.csv` | The same bookings with headers no preset knows and separate `Soll` and `Haben` columns. Exercises the mapping sub-agent. |
| `sparkasse-kontoauszug-2025.pdf` | Text PDF statement. Opening balance plus all bookings equals the printed closing balance. |
| `bill-*.png` | Four receipts whose line items sum to the total of a booking that is in the CSV, so a bill photo can match an existing transaction. |

Figures: {count} bookings, opening balance {opening} EUR, closing balance {closing} EUR.
"""


def check(bookings: list[Booking]) -> int:
    """The dataset only makes sense if the year reconciles and the account stays in the black."""
    balance = OPENING_CENTS
    lowest = balance
    for booking in bookings:
        balance += booking.amount_cents
        lowest = min(lowest, balance)
    if lowest < 0:
        raise SystemExit(f"the balance dips to {euro(lowest)} EUR; raise OPENING_CENTS")
    if balance != OPENING_CENTS + sum(booking.amount_cents for booking in bookings):
        raise SystemExit("the running balance does not reconcile")
    return balance


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    bookings = generate()
    check(bookings)
    write_sparkasse_csv(bookings, OUT / "sparkasse-2025.csv")
    write_unknown_bank_csv(bookings, OUT / "unknown-bank-2025.csv")
    write_statement_pdf(bookings, OUT / "sparkasse-kontoauszug-2025.pdf")
    for bill in BILLS:
        write_bill_image(bill, OUT / f"bill-{bill.slug}-{bill.booked_on:%Y-%m-%d}.png")

    closing = OPENING_CENTS + sum(booking.amount_cents for booking in bookings)
    (OUT / "README.md").write_text(
        README.format(count=len(bookings), opening=euro(OPENING_CENTS), closing=euro(closing)), encoding="utf-8"
    )
    print(f"{len(bookings)} bookings, closing balance {euro(closing)} EUR, written to {OUT}")


if __name__ == "__main__":
    main()
