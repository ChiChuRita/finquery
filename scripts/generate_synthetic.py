"""Generate the shipped synthetic German household dataset.

One canonical year (2025) of a Berlin household: salary, rent, utilities, several grocery
chains, transport, subscriptions, PayPal to friends, Amazon, restaurants and cash withdrawals.
The same bookings are written three ways so every reader has something to chew on:

- `sparkasse-2025.csv`: Sparkasse CAMT layout, semicolon, cp1252, `1.234,56`, DD.MM.YYYY.
- `sparkasse-2025.xlsx`: the same export as an Excel workbook, with the dates and the amounts
  as real cells rather than as text, which is what the workbook reader is for.
- `unknown-bank-2025.csv`: renamed and reordered headers with separate Soll and Haben columns,
  the file the mapping sub-agent is exercised against.
- `sparkasse-kontoauszug-2025.pdf`: text PDF with a running balance whose opening balance plus
  all bookings equals the printed closing balance.
- `statement-excerpt.docx`: fifteen bookings of the same year as a Word document, with an
  opening and a closing balance, for the text path and its two guards.
- four bill images whose line items sum to the total of a booking that is in the CSV, so the
  bill photo flow has something real to match against.

Everything is deterministic. Run it with `uv run python scripts/generate_synthetic.py`; the
output is committed under `fixtures/synthetic/`.
"""

from __future__ import annotations

import csv
import io
import json
import random
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import docx
import openpyxl
from fpdf import FPDF
from openpyxl.writer.excel import ExcelWriter
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "synthetic"
YEAR = 2025
IBAN = "DE02120300000000202051"
BIC = "BYLADEM1001"
HOLDER = "Lena Mustermann"
OPENING_CENTS = 421055
SEED = 20250101

DOCX_BOOKINGS = 15
"""Bookings in the Word excerpt: enough for a running balance to prove itself, short enough to
read on a card."""

EPOCH = (1980, 1, 1, 0, 0, 0)
"""The timestamp every entry of a generated OOXML file gets. A zip stores the clock, and this
script promises the same bytes on every run."""

FIXED_TIME = datetime(YEAR, 12, 31, 12, 0, tzinfo=UTC)
"""What the document properties of the workbook and the Word document say, for the same reason."""

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


def write_sparkasse_csv(bookings: list[Booking], path: Path, *, iban: str = IBAN) -> None:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(SPARKASSE_HEADER)
    for booking in bookings:
        writer.writerow(
            (
                iban,
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
    # Fixed so re-running the generator does not rewrite the committed file.
    pdf.set_creation_date(datetime(YEAR, 12, 31, 12, 0, tzinfo=UTC))
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


def _deterministic(data: bytes) -> bytes:
    """An OOXML file whose zip entries carry no clock, so re-running rewrites nothing.

    An `.xlsx` and a `.docx` are zip archives, and both libraries stamp every entry with the
    time it was written. The committed fixtures would then differ on every run.
    """
    source = zipfile.ZipFile(io.BytesIO(data))
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as written:
        for entry in source.infolist():
            fixed = zipfile.ZipInfo(entry.filename, date_time=EPOCH)
            fixed.compress_type = zipfile.ZIP_DEFLATED
            fixed.external_attr = entry.external_attr
            written.writestr(fixed, source.read(entry.filename))
    source.close()
    return target.getvalue()


def write_sparkasse_xlsx(bookings: list[Booking], path: Path) -> None:
    """The Sparkasse export as a workbook: the same header, the cells typed.

    The point of the file is that a date is a date and an amount is a number, so the reader has
    nothing to parse out of a string and a preset's "German decimal comma" does not apply to
    them (`finquery.ingest.xlsx.with_cell_types`).
    """
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Umsaetze"
    sheet.append(SPARKASSE_HEADER)
    for booking in bookings:
        sheet.append(
            (
                IBAN,
                booking.booked_on,
                booking.booked_on,
                booking.booking_text,
                booking.reference,
                None,
                None,
                None,
                None,
                None,
                None,
                booking.counterparty,
                None,
                None,
                Decimal(booking.amount_cents) / 100,
                "EUR",
                "Umsatz gebucht",
            )
        )
    for cell in sheet["B"][1:] + sheet["C"][1:]:
        cell.number_format = "DD.MM.YYYY"
    for cell in sheet["O"][1:]:
        cell.number_format = "#,##0.00"
    workbook.properties.created = FIXED_TIME
    workbook.properties.modified = FIXED_TIME
    # `Workbook.save` stamps `modified` with the clock of the run, which would rewrite the
    # committed file every time. `ExcelWriter` is the same writer without that one line, and it
    # closes the archive itself.
    buffer = io.BytesIO()
    ExcelWriter(workbook, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, allowZip64=True)).save()
    path.write_bytes(_deterministic(buffer.getvalue()))


def write_statement_docx(bookings: list[Booking], path: Path) -> None:
    """A statement excerpt as a Word document: paragraphs, one table, two printed balances.

    It is read as text, so what matters is that every figure is printed in it and that the
    running balance closes: that is what the verbatim guard and the reconciliation guard have to
    work with (ADR 0011).
    """
    document = docx.Document()
    document.add_paragraph("Sparkasse Musterstadt")
    document.add_paragraph(f"Kontoauszug Nr. 1/{YEAR} (Auszug)")
    document.add_paragraph(f"Kontoinhaber: {HOLDER}   IBAN {IBAN}   BIC {BIC}")
    document.add_paragraph(f"Alter Kontostand: {euro(OPENING_CENTS)} EUR")

    table = document.add_table(rows=1, cols=5)
    for cell, heading in zip(
        table.rows[0].cells,
        ("Buchung", "Valuta", "Buchungstext / Verwendungszweck", "Betrag EUR", "Saldo EUR"),
        strict=True,
    ):
        cell.text = heading
    balance = OPENING_CENTS
    for booking in bookings:
        balance += booking.amount_cents
        cells = table.add_row().cells
        cells[0].text = f"{booking.booked_on:%d.%m.%y}"
        cells[1].text = f"{booking.booked_on:%d.%m.%y}"
        cells[2].text = f"{booking.booking_text}  {booking.counterparty}"
        cells[3].text = euro(booking.amount_cents)
        cells[4].text = euro(balance)

    document.add_paragraph(f"Neuer Kontostand: {euro(balance)} EUR")
    document.add_paragraph(
        f"Summe der Buchungen: {euro(balance - OPENING_CENTS)} EUR aus {len(bookings)} Buchungen"
    )
    properties = document.core_properties
    properties.created = FIXED_TIME.replace(tzinfo=None)
    properties.modified = FIXED_TIME.replace(tzinfo=None)
    properties.revision = 1
    buffer = io.BytesIO()
    document.save(buffer)
    path.write_bytes(_deterministic(buffer.getvalue()))


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


# ---------------------------------------------------------------------------------------
# Five more households, for the adapter training sets (ticket 62).
#
# The shipped year above is one Berlin household, so every training question would inherit its
# merchants, its salary and its twelve equal months. Five more households give the writers of
# ticket 64 six sets of merchants, six taxonomies in use and six shapes of income to ask about:
# a student on BAfoeG, a family with two children, a freelancer whose income is irregular, a
# pensioner, and a couple who keep a joint account beside a personal one.
#
# Each is a full year 2025 in the Sparkasse layout, so it goes through the same preset, the same
# reader and the same categorizer as the shipped file, and each is deterministic: one seed per
# household, one derived seed per account.
# ---------------------------------------------------------------------------------------

HOUSEHOLDS_OUT = OUT / "households"
MONTHS = tuple(range(1, 13))
QUARTERLY = (1, 4, 7, 10)
TODAY = date(YEAR, 12, 31)
"""What a question about this data is asked on. The same pin the benchmark uses: without it
"last month" would ask about a month a year after the newest booking."""

NEEDS_REVIEW = "Needs review"
"""What the truth file calls the absence of a category, exactly as the query prompt does."""


@dataclass(frozen=True)
class Shop:
    """One merchant a household visits, and where the categorizer puts it.

    `category` is `None` when no dictionary entry knows the name, which is what leaves the
    booking in Needs review: a rent, a salary and a public office are that everywhere, and a
    household with no Needs review bucket would not be an honest one to ask questions about.
    """

    counterparty: str
    reference: str
    low: int
    high: int
    category: str | None = None
    subcategory: str | None = None


@dataclass(frozen=True)
class Habit:
    """How often a household buys from a pool of shops in a month, and for how much."""

    shops: tuple[Shop, ...]
    low: int
    high: int
    text: str = "KARTENZAHLUNG"
    busier: tuple[tuple[int, int], ...] = ()
    """Months that carry extra bookings: the holiday, the run-up to Christmas."""


@dataclass(frozen=True)
class Fixed:
    """A booking that repeats: the rent, the salary, an abo, a quarterly tax payment."""

    day: int
    cents: int
    text: str
    counterparty: str
    reference: str
    category: str | None = None
    subcategory: str | None = None
    months: tuple[int, ...] = MONTHS


@dataclass(frozen=True)
class Once:
    """One booking on one day: the edge cases each household is worth asking about."""

    month: int
    day: int
    cents: int
    text: str
    counterparty: str
    reference: str
    category: str | None = None
    subcategory: str | None = None


@dataclass(frozen=True)
class Ledger:
    """One account of a household: one CSV file, imported under one account name."""

    account: str
    file_name: str
    iban: str
    opening_cents: int
    fixed: tuple[Fixed, ...] = ()
    habits: tuple[Habit, ...] = ()
    once: tuple[Once, ...] = ()


@dataclass(frozen=True)
class Household:
    """One synthetic household: who they are, and the accounts they keep."""

    slug: str
    label: str
    holder: str
    note: str
    seed: int
    ledgers: tuple[Ledger, ...]
    edge_cases: tuple[str, ...] = ()


@dataclass(frozen=True)
class Row:
    """One generated booking with the category the import path will give it."""

    booking: Booking
    category: str | None
    subcategory: str | None

    @property
    def topic(self) -> str:
        return self.category or NEEDS_REVIEW


CASH = Shop("Sparkasse Geldautomat", "GA NR00012345 AUSZAHLUNG", 5000, 20000, "Cash", "Cash withdrawal")

STUDENT = Household(
    slug="student",
    label="Student in Leipzig",
    holder="Tim Baumgartner",
    note=(
        "A student on BAfoeG and a university job: small amounts, discounters, a semester fee "
        "twice a year and one big purchase in October."
    ),
    seed=20250201,
    edge_cases=(
        "the semester fee is paid twice, in April and in October, to the same office",
        "the Zalando refund in March is money coming in on a shopping merchant",
        "the notebook in October costs more than a whole month of groceries",
        "BAfoeG and the university job are both income and both stay in Needs review",
    ),
    ledgers=(
        Ledger(
            account="Sparkasse Leipzig Girokonto",
            file_name="student-2025.csv",
            iban="DE21860555920001234567",
            opening_cents=184200,
            fixed=(
                Fixed(1, -38000, "DAUERAUFTRAG", "WG Hausverwaltung Lindenau", "MIETE WG ZIMMER {month:02d}/{year}"),
                Fixed(2, -2900, "FOLGELASTSCHRIFT", "Deutsche Bahn AG", "DEUTSCHLANDTICKET {month:02d}/{year}", "Transport", "Public transport"),
                Fixed(5, -599, "FOLGELASTSCHRIFT", "SPOTIFY AB", "SPOTIFY PREMIUM STUDENT", "Subscriptions", "Music"),
                Fixed(7, -499, "FOLGELASTSCHRIFT", "NETFLIX INTERNATIONAL BV", "NETFLIX BASIS ABO", "Subscriptions", "Streaming"),
                Fixed(10, -1990, "FOLGELASTSCHRIFT", "McFIT GmbH", "MITGLIEDSBEITRAG {month:02d}/{year}", "Health", "Fitness"),
                Fixed(12, -1299, "FOLGELASTSCHRIFT", "congstar GmbH", "MOBILFUNK {month:02d}/{year}", "Communication", "Mobile"),
                Fixed(15, 99200, "GUTSCHRIFT", "Studentenwerk Leipzig", "BAFOEG {month:02d}/{year}"),
                Fixed(28, 52000, "LOHN  GEHALT", "Universitaet Leipzig", "HIWI VERTRAG {month:02d}/{year}"),
            ),
            habits=(
                Habit(
                    (
                        Shop("ALDI SÜD", "ALDI SUED SAGT DANKE", 480, 3900, "Groceries", "Supermarket"),
                        Shop("LIDL Vertriebs GmbH", "LIDL DANKT IHNEN", 520, 4200, "Groceries", "Supermarket"),
                        Shop("NETTO MARKEN-DISCOUNT", "NETTO FILIALE 2201", 430, 3300, "Groceries", "Supermarket"),
                        Shop("PENNY Markt GmbH", "PENNY 4408 LEIPZIG", 390, 2900, "Groceries", "Supermarket"),
                        Shop("Bäckerei Steinecke", "BAECKEREI STEINECKE", 190, 980, "Groceries", "Bakery"),
                        Shop("dm drogerie markt", "DM FIL 4412 LEIPZIG", 420, 2600, "Groceries", "Drugstore"),
                    ),
                    8,
                    12,
                ),
                Habit(
                    (
                        Shop("Döner Haus Connewitz", "DOENER HAUS CONNEWITZ", 550, 1200, "Dining", "Takeaway"),
                        Shop("MCDONALDS DEUTSCHLAND", "MCDONALDS 1188 LEIPZIG", 480, 1400, "Dining", "Takeaway"),
                        Shop("Lieferando.de", "LIEFERANDO BESTELLUNG", 990, 2900, "Dining", "Delivery"),
                        Shop("Cafe Puschkin", "CAFE PUSCHKIN LEIPZIG", 320, 1450, "Dining", "Cafe"),
                    ),
                    3,
                    6,
                ),
                Habit(
                    (
                        Shop("AMAZON EU S.A R.L.", "AMZN Mktp DE 774512", 890, 6400, "Shopping", "Online marketplace"),
                        Shop("Thalia Bücher GmbH", "THALIA LEIPZIG HAUPTBAHNHOF", 1200, 4900, "Leisure", "Books"),
                        Shop("Decathlon Deutschland", "DECATHLON LEIPZIG", 1900, 7900, "Shopping", "Clothing"),
                    ),
                    1,
                    2,
                ),
                Habit((CASH,), 1, 2, text="BARGELDAUSZAHLUNG"),
            ),
            once=(
                Once(3, 22, 4990, "GUTSCHRIFT", "Zalando SE", "ZALANDO RETOURE ERSTATTUNG", "Shopping", "Clothing"),
                Once(4, 14, -26000, "ONLINE-UEBERWEISUNG", "Universitaet Leipzig", "SEMESTERBEITRAG SS 2025"),
                Once(7, 2, -18900, "KARTENZAHLUNG", "FlixBus DACH GmbH", "FLIXBUS LEIPZIG AMSTERDAM", "Transport", "Public transport"),
                Once(10, 8, -26000, "ONLINE-UEBERWEISUNG", "Universitaet Leipzig", "SEMESTERBEITRAG WS 2025/26"),
                Once(10, 12, -74900, "KARTENZAHLUNG", "MediaMarkt Leipzig", "MEDIAMARKT NOTEBOOK", "Shopping", "Electronics"),
                Once(12, 3, -3500, "KARTENZAHLUNG", "Apotheke am Markt", "APOTHEKE AM MARKT LEIPZIG", "Health", "Pharmacy"),
            ),
        ),
    ),
)

FAMILY = Household(
    slug="family",
    label="Family with two children in Dortmund",
    holder="Familie Aksoy",
    note=(
        "Two salaries, Kindergeld, a Kita fee and the biggest grocery bill of the six: the "
        "household whose months are not equal, with a holiday in July and Christmas in December."
    ),
    seed=20250302,
    edge_cases=(
        "July is the holiday month and December the most expensive one",
        "the electricity settlement in June is money coming back on a spending category",
        "the school supplies land in August and nowhere else",
        "Kindergeld and both salaries are income that stays in Needs review",
    ),
    ledgers=(
        Ledger(
            account="Sparkasse Dortmund Girokonto",
            file_name="family-2025.csv",
            iban="DE31440501990002345678",
            opening_cents=512300,
            fixed=(
                Fixed(1, -145000, "DAUERAUFTRAG", "Wohnungsgenossenschaft Dortmund-Sued", "MIETE {month:02d}/{year}"),
                Fixed(2, -25000, "FOLGELASTSCHRIFT", "Stadt Dortmund Elternbeitrag", "KITA BEITRAG {month:02d}/{year}"),
                Fixed(3, -8900, "FOLGELASTSCHRIFT", "Stadtwerke Dortmund AG", "STROM ABSCHLAG {month:02d}/{year}", "Housing", "Electricity"),
                Fixed(4, -4999, "FOLGELASTSCHRIFT", "Telekom Deutschland GmbH", "MAGENTA ZUHAUSE XL", "Communication"),
                Fixed(6, -1799, "FOLGELASTSCHRIFT", "Vodafone GmbH", "MOBILFUNK FAMILIE {month:02d}/{year}", "Communication", "Mobile"),
                Fixed(7, -899, "KARTENZAHLUNG", "DISNEY PLUS", "DISNEY PLUS STANDARD", "Subscriptions", "Streaming"),
                Fixed(8, -1799, "FOLGELASTSCHRIFT", "SPOTIFY AB", "SPOTIFY FAMILY", "Subscriptions", "Music"),
                Fixed(9, -899, "KARTENZAHLUNG", "AMAZON PRIME MEMBERSHIP", "AMZN PRIME DE MITGLIEDSCHAFT", "Subscriptions", "Streaming"),
                Fixed(12, -6800, "FOLGELASTSCHRIFT", "Allianz Versicherungs-AG", "HAUSRAT HAFTPFLICHT UNFALL", "Insurance"),
                Fixed(14, -22000, "FOLGELASTSCHRIFT", "Techniker Krankenkasse", "ZUSATZBEITRAG {month:02d}/{year}", "Insurance", "Health insurance"),
                Fixed(15, 50000, "GUTSCHRIFT", "Familienkasse Nordrhein-Westfalen", "KINDERGELD {month:02d}/{year}"),
                Fixed(16, 232000, "LOHN  GEHALT", "Hoesch Werkstoffe Personal", "GEHALT {month:02d}/{year} PERS.NR 8812"),
                Fixed(25, -9800, "FOLGELASTSCHRIFT", "Deutsche Bahn AG", "DEUTSCHLANDTICKET 2 PERSONEN {month:02d}/{year}", "Transport", "Public transport"),
                Fixed(28, 268000, "LOHN  GEHALT", "Klinikum Dortmund gGmbH", "GEHALT {month:02d}/{year} PERS.NR 3390"),
            ),
            habits=(
                Habit(
                    (
                        Shop("KAUFLAND DORTMUND", "KAUFLAND 2210 DORTMUND", 2400, 12900, "Groceries", "Supermarket"),
                        Shop("REWE Markt GmbH", "REWE SAGT DANKE. BIS BALD", 1900, 9800, "Groceries", "Supermarket"),
                        Shop("EDEKA Sander", "EDEKA SAGT DANKE", 1700, 8900, "Groceries", "Supermarket"),
                        Shop("ALDI SÜD", "ALDI SUED SAGT DANKE", 1500, 7400, "Groceries", "Supermarket"),
                        Shop("Bäckerei Kamps", "KAMPS BACKSTUBE", 380, 1900, "Groceries", "Bakery"),
                        Shop("Rossmann Drogeriemarkt", "ROSSMANN FIL 1104", 890, 4600, "Groceries", "Drugstore"),
                    ),
                    12,
                    16,
                    busier=((12, 4),),
                ),
                Habit(
                    (
                        Shop("MCDONALDS DEUTSCHLAND", "MCDONALDS 4471 DORTMUND", 1400, 3900, "Dining", "Takeaway"),
                        Shop("Pizzeria Da Vinci", "PIZZERIA DA VINCI", 1900, 5400, "Dining", "Restaurant"),
                        Shop("Lieferando.de", "LIEFERANDO BESTELLUNG", 1900, 5900, "Dining", "Delivery"),
                        Shop("BURGER KING", "BURGER KING 2201", 1100, 3400, "Dining", "Takeaway"),
                    ),
                    3,
                    5,
                ),
                Habit(
                    (
                        Shop("ARAL Tankstelle", "ARAL STATION 4471", 4900, 9800, "Transport", "Fuel"),
                        Shop("Shell Station", "SHELL STATION 2109", 4500, 9400, "Transport", "Fuel"),
                    ),
                    2,
                    3,
                ),
                Habit(
                    (
                        Shop("AMAZON EU S.A R.L.", "AMZN Mktp DE 118902", 1200, 8900, "Shopping", "Online marketplace"),
                        Shop("Zalando SE", "ZALANDO BESTELLUNG", 2400, 12900, "Shopping", "Clothing"),
                        Shop("OTTO GmbH", "OTTO BESTELLUNG", 2900, 14900, "Shopping", "Online marketplace"),
                        Shop("Decathlon Deutschland", "DECATHLON DORTMUND", 1900, 8900, "Shopping", "Clothing"),
                    ),
                    2,
                    3,
                    busier=((12, 3),),
                ),
                Habit(
                    (Shop("Apotheke am Westenhellweg", "APOTHEKE WESTENHELLWEG", 890, 4900, "Health", "Pharmacy"),),
                    0,
                    2,
                ),
                Habit((CASH,), 1, 2, text="BARGELDAUSZAHLUNG"),
            ),
            once=(
                Once(3, 11, -32000, "FOLGELASTSCHRIFT", "Zahnarztpraxis Dr. Kienzle", "RECHNUNG 2025-1187", "Health", "Doctor"),
                Once(6, 18, 18700, "GUTSCHRIFT", "Stadtwerke Dortmund AG", "JAHRESABRECHNUNG STROM GUTSCHRIFT", "Housing", "Electricity"),
                Once(7, 5, -68900, "ONLINE-UEBERWEISUNG", "Ferienpark Sonnenhof Sylt", "FERIENWOHNUNG JULI 2025"),
                Once(7, 6, -34800, "KARTENZAHLUNG", "Deutsche Bahn AG", "DB FERNVERKEHR FAMILIENTICKET", "Transport", "Public transport"),
                Once(8, 21, -8900, "KARTENZAHLUNG", "Thalia Bücher GmbH", "THALIA SCHULBEDARF", "Leisure", "Books"),
                Once(8, 22, -12900, "KARTENZAHLUNG", "Decathlon Deutschland", "DECATHLON SCHULSPORT", "Shopping", "Clothing"),
                Once(12, 14, -39900, "KARTENZAHLUNG", "MediaMarkt Dortmund", "MEDIAMARKT WEIHNACHTEN", "Shopping", "Electronics"),
            ),
        ),
    ),
)

FREELANCER = Household(
    slug="freelancer",
    label="Freelance designer in Hamburg",
    holder="Nora Wendt",
    note=(
        "Income that does not arrive on the 28th: fifteen invoices over the year, two months "
        "with none at all, quarterly VAT going out and a studio rent going out every month."
    ),
    seed=20250403,
    edge_cases=(
        "August and September carry no client payment at all",
        "the VAT payments to the tax office are quarterly, not monthly",
        "one client pays two invoices in the same week of October",
        "the health insurance refund in November is money in on an Insurance merchant",
    ),
    ledgers=(
        Ledger(
            account="Hamburger Sparkasse Geschaeftskonto",
            file_name="freelancer-2025.csv",
            iban="DE07200505501003456789",
            opening_cents=862000,
            fixed=(
                Fixed(1, -78000, "DAUERAUFTRAG", "Atelierhaus Ottensen GbR", "ATELIERMIETE {month:02d}/{year}"),
                Fixed(2, -19900, "FOLGELASTSCHRIFT", "Betahaus Hamburg", "COWORKING FLEX {month:02d}/{year}"),
                Fixed(3, -1899, "KARTENZAHLUNG", "GitHub Inc", "GITHUB TEAM ABO", "Subscriptions", "Software"),
                Fixed(5, -3999, "FOLGELASTSCHRIFT", "Telefonica Germany GmbH", "MOBILFUNK {month:02d}/{year}", "Communication", "Mobile"),
                Fixed(6, -4900, "FOLGELASTSCHRIFT", "Urban Sports Club GmbH", "MITGLIEDSCHAFT M {month:02d}/{year}", "Health", "Fitness"),
                Fixed(9, -1199, "KARTENZAHLUNG", "Dropbox International", "DROPBOX PLUS", "Subscriptions", "Software"),
                Fixed(10, -180000, "ONLINE-UEBERWEISUNG", "Finanzamt Hamburg-Nord", "UMSATZSTEUER VORANMELDUNG", months=QUARTERLY),
                Fixed(11, -1099, "KARTENZAHLUNG", "Microsoft Ireland Operations", "MICROSOFT 365 SINGLE", "Subscriptions", "Software"),
                Fixed(15, -84000, "FOLGELASTSCHRIFT", "Techniker Krankenkasse", "KRANKENVERSICHERUNG {month:02d}/{year}", "Insurance", "Health insurance"),
                Fixed(22, -6499, "KARTENZAHLUNG", "Adobe Systems Software", "ADOBE CREATIVE CLOUD ABO", "Subscriptions", "Software"),
                Fixed(25, -4900, "FOLGELASTSCHRIFT", "HVV Hamburger Verkehrsverbund", "DEUTSCHLANDTICKET {month:02d}/{year}", "Transport", "Public transport"),
            ),
            habits=(
                Habit(
                    (
                        Shop("REWE Markt GmbH", "REWE SAGT DANKE. BIS BALD", 1200, 6400, "Groceries", "Supermarket"),
                        Shop("BIO COMPANY SE", "BIO COMPANY HAMBURG", 1400, 5900, "Groceries", "Supermarket"),
                        Shop("Alnatura Produktions", "ALNATURA HAMBURG", 1600, 6900, "Groceries", "Supermarket"),
                        Shop("DENNS BIOMARKT", "DENNS BIOMARKT OTTENSEN", 1300, 5400, "Groceries", "Supermarket"),
                        Shop("dm drogerie markt", "DM FIL 2207 HAMBURG", 590, 3400, "Groceries", "Drugstore"),
                    ),
                    7,
                    11,
                ),
                Habit(
                    (
                        Shop("Starbucks Coffee", "STARBUCKS MOENCKEBERGSTRASSE", 390, 1290, "Dining", "Cafe"),
                        Shop("dean and david", "DEAN+DAVID 2201", 990, 1890, "Dining", "Takeaway"),
                        Shop("Cafe Elbgold", "CAFE ELBGOLD OTTENSEN", 420, 1690, "Dining", "Cafe"),
                        Shop("Lieferando.de", "LIEFERANDO BESTELLUNG", 1400, 3900, "Dining", "Delivery"),
                    ),
                    4,
                    7,
                ),
                Habit(
                    (
                        Shop("FREENOW GmbH", "FREENOW FAHRT", 890, 2900, "Transport", "Ride hailing"),
                        Shop("Deutsche Bahn AG", "DB FERNVERKEHR TICKET", 2900, 14900, "Transport", "Public transport"),
                    ),
                    1,
                    3,
                ),
                Habit(
                    (Shop("AMAZON EU S.A R.L.", "AMZN Mktp DE 552108", 1400, 9800, "Shopping", "Online marketplace"),),
                    1,
                    2,
                ),
                Habit((CASH,), 1, 1, text="BARGELDAUSZAHLUNG"),
            ),
            once=(
                Once(1, 17, 268000, "GUTSCHRIFT", "Kreativagentur Nord GmbH", "RECHNUNG 2025-001 WEBDESIGN"),
                Once(2, 6, 142000, "GUTSCHRIFT", "Verlag Hoffmann KG", "RECHNUNG 2025-002 ILLUSTRATION"),
                Once(2, 24, 318000, "GUTSCHRIFT", "Werft Digital GmbH", "RECHNUNG 2025-003 RELAUNCH"),
                Once(3, 19, -189900, "KARTENZAHLUNG", "Cyberport GmbH", "CYBERPORT NOTEBOOK PRO", "Shopping", "Electronics"),
                Once(3, 27, 96000, "GUTSCHRIFT", "Kreativagentur Nord GmbH", "RECHNUNG 2025-004 KORREKTUR"),
                Once(4, 22, 224000, "GUTSCHRIFT", "Werft Digital GmbH", "RECHNUNG 2025-005 KAMPAGNE"),
                Once(5, 9, 187000, "GUTSCHRIFT", "Verlag Hoffmann KG", "RECHNUNG 2025-006 COVER"),
                Once(6, 3, 342000, "GUTSCHRIFT", "Nordlicht Brauerei GmbH", "RECHNUNG 2025-007 ETIKETTEN"),
                Once(6, 26, 118000, "GUTSCHRIFT", "Kreativagentur Nord GmbH", "RECHNUNG 2025-008 SOCIAL"),
                Once(7, 15, 264000, "GUTSCHRIFT", "Werft Digital GmbH", "RECHNUNG 2025-009 APP ICONS"),
                Once(10, 7, 158000, "GUTSCHRIFT", "Verlag Hoffmann KG", "RECHNUNG 2025-010 REIHE"),
                Once(10, 9, 206000, "GUTSCHRIFT", "Verlag Hoffmann KG", "RECHNUNG 2025-011 REIHE ZWEI"),
                Once(11, 4, 289000, "GUTSCHRIFT", "Nordlicht Brauerei GmbH", "RECHNUNG 2025-012 MESSESTAND"),
                Once(11, 18, 42000, "GUTSCHRIFT", "Techniker Krankenkasse", "BEITRAGSERSTATTUNG 2024", "Insurance", "Health insurance"),
                Once(12, 12, 372000, "GUTSCHRIFT", "Kreativagentur Nord GmbH", "RECHNUNG 2025-013 JAHRESABSCHLUSS"),
                Once(12, 19, 134000, "GUTSCHRIFT", "Werft Digital GmbH", "RECHNUNG 2025-014 WARTUNG"),
            ),
        ),
    ),
)

PENSIONER = Household(
    slug="pensioner",
    label="Pensioner in Muenster",
    holder="Helga Brinkmann",
    note=(
        "A pension and a company pension in, a small rent out, the pharmacy every other week "
        "and more cash than any other household: few card payments, many standing orders."
    ),
    seed=20250504,
    edge_cases=(
        "the heating settlement in February is the largest single payment of the year",
        "the pharmacy is visited two to four times a month, in small amounts",
        "the donation in December goes to a name the dictionary does not know",
        "cash withdrawals are a real category here, not a rounding error",
    ),
    ledgers=(
        Ledger(
            account="Sparkasse Muensterland Girokonto",
            file_name="pensioner-2025.csv",
            iban="DE95400501500004567890",
            opening_cents=738000,
            fixed=(
                Fixed(1, 158000, "GUTSCHRIFT", "Deutsche Rentenversicherung Bund", "RENTE {month:02d}/{year}"),
                Fixed(1, -72000, "DAUERAUFTRAG", "Hausverwaltung Muenster-West", "MIETE {month:02d}/{year}"),
                Fixed(4, -3499, "FOLGELASTSCHRIFT", "Telekom Deutschland GmbH", "FESTNETZ UND INTERNET", "Communication"),
                Fixed(5, -9800, "FOLGELASTSCHRIFT", "Stadtwerke Muenster GmbH", "STROM UND GAS ABSCHLAG {month:02d}/{year}", "Housing", "Electricity"),
                Fixed(8, -4200, "FOLGELASTSCHRIFT", "HUK-COBURG Versicherung", "HAUSRAT UND HAFTPFLICHT", "Insurance"),
                Fixed(12, -6800, "FOLGELASTSCHRIFT", "Techniker Krankenkasse", "ZUSATZVERSICHERUNG {month:02d}/{year}", "Insurance", "Health insurance"),
                Fixed(15, 32000, "GUTSCHRIFT", "Ruhegehaltskasse Westfalen", "BETRIEBSRENTE {month:02d}/{year}"),
                Fixed(18, -2499, "FOLGELASTSCHRIFT", "Der Spiegel Verlag", "SPIEGEL JAHRESABO RATE", "Subscriptions", "News"),
                Fixed(25, -4900, "FOLGELASTSCHRIFT", "Deutsche Bahn AG", "DEUTSCHLANDTICKET {month:02d}/{year}", "Transport", "Public transport"),
            ),
            habits=(
                Habit(
                    (
                        Shop("EDEKA Kaufpark", "EDEKA SAGT DANKE", 1400, 6900, "Groceries", "Supermarket"),
                        Shop("NETTO MARKEN-DISCOUNT", "NETTO FILIALE 1180", 890, 4200, "Groceries", "Supermarket"),
                        Shop("ALDI SÜD", "ALDI SUED SAGT DANKE", 990, 4400, "Groceries", "Supermarket"),
                        Shop("Bäckerei Kamps", "KAMPS BACKSTUBE MUENSTER", 240, 1290, "Groceries", "Bakery"),
                    ),
                    8,
                    11,
                ),
                Habit(
                    (
                        Shop("Loewen-Apotheke Muenster", "LOEWEN APOTHEKE", 490, 3900, "Health", "Pharmacy"),
                        Shop("Apotheke am Prinzipalmarkt", "APOTHEKE PRINZIPALMARKT", 540, 4400, "Health", "Pharmacy"),
                    ),
                    2,
                    4,
                ),
                Habit(
                    (
                        Shop("Cafe Extrablatt", "CAFE EXTRABLATT MUENSTER", 690, 2400, "Dining", "Cafe"),
                        Shop("Pizzeria Da Vinci", "PIZZERIA DA VINCI MUENSTER", 1400, 3900, "Dining", "Restaurant"),
                    ),
                    1,
                    3,
                ),
                Habit(
                    (
                        Shop("Thalia Bücher GmbH", "THALIA MUENSTER", 990, 3900, "Leisure", "Books"),
                        Shop("AMAZON EU S.A R.L.", "AMZN Mktp DE 330219", 890, 5400, "Shopping", "Online marketplace"),
                    ),
                    0,
                    2,
                ),
                Habit((CASH,), 2, 4, text="BARGELDAUSZAHLUNG"),
            ),
            once=(
                Once(2, 12, -87400, "FOLGELASTSCHRIFT", "Hausverwaltung Muenster-West", "HEIZKOSTENNACHZAHLUNG 2024"),
                Once(3, 6, -48000, "FOLGELASTSCHRIFT", "Zahnarztpraxis Dr. Lemke", "RECHNUNG 2025-0442", "Health", "Doctor"),
                Once(7, 24, 12000, "GUTSCHRIFT", "Stadtwerke Muenster GmbH", "JAHRESABRECHNUNG GUTSCHRIFT", "Housing", "Electricity"),
                Once(9, 17, -32900, "KARTENZAHLUNG", "Fielmann AG", "FIELMANN BRILLE", "Health"),
                Once(12, 9, -20000, "ONLINE-UEBERWEISUNG", "Deutsches Rotes Kreuz Muenster", "JAHRESSPENDE 2025"),
            ),
        ),
    ),
)

COUPLE = Household(
    slug="couple",
    label="Couple with a joint account in Stuttgart",
    holder="Jonas und Miriam Riedel",
    note=(
        "Two accounts in one profile: a joint account that pays the household and a personal "
        "account that pays into it every month. A question here says which account it means, "
        "or means both."
    ),
    seed=20250605,
    edge_cases=(
        "the monthly transfer leaves the personal account and arrives on the joint one",
        "the tax refund in March is the largest single amount coming in",
        "the car repair and the holiday flat are names the dictionary does not know",
        "REWE is paid from both accounts, so a merchant total spans them",
    ),
    ledgers=(
        Ledger(
            account="Sparkasse Stuttgart Gemeinschaftskonto",
            file_name="couple-joint-2025.csv",
            iban="DE44600501010005678901",
            opening_cents=421000,
            fixed=(
                Fixed(1, -132000, "DAUERAUFTRAG", "Immobilien Schmid Verwaltung", "MIETE {month:02d}/{year}"),
                Fixed(2, 150000, "GUTSCHRIFT", "Jonas Riedel", "HAUSHALT {month:02d}/{year}"),
                Fixed(2, 150000, "GUTSCHRIFT", "Miriam Riedel", "HAUSHALT {month:02d}/{year}"),
                Fixed(5, -11200, "FOLGELASTSCHRIFT", "Stadtwerke Stuttgart GmbH", "STROM ABSCHLAG {month:02d}/{year}", "Housing", "Electricity"),
                Fixed(7, -4999, "FOLGELASTSCHRIFT", "Vodafone GmbH", "KABEL UND MOBILFUNK {month:02d}/{year}", "Communication", "Mobile"),
                Fixed(9, -5400, "FOLGELASTSCHRIFT", "Allianz Versicherungs-AG", "HAUSRAT UND HAFTPFLICHT", "Insurance"),
                Fixed(12, -1799, "KARTENZAHLUNG", "NETFLIX INTERNATIONAL BV", "NETFLIX STANDARD ABO", "Subscriptions", "Streaming"),
                Fixed(25, -9800, "FOLGELASTSCHRIFT", "Deutsche Bahn AG", "DEUTSCHLANDTICKET 2 PERSONEN", "Transport", "Public transport"),
            ),
            habits=(
                Habit(
                    (
                        Shop("REWE Markt GmbH", "REWE SAGT DANKE. BIS BALD", 1900, 8900, "Groceries", "Supermarket"),
                        Shop("Alnatura Produktions", "ALNATURA STUTTGART", 1600, 6400, "Groceries", "Supermarket"),
                        Shop("EDEKA Nagel", "EDEKA SAGT DANKE", 1700, 7900, "Groceries", "Supermarket"),
                        Shop("dm drogerie markt", "DM FIL 7701 STUTTGART", 690, 3900, "Groceries", "Drugstore"),
                        Shop("Bäckerei Treiber", "BAECKEREI TREIBER", 320, 1490, "Groceries", "Bakery"),
                    ),
                    10,
                    14,
                ),
                Habit(
                    (
                        Shop("Vapiano SE", "VAPIANO STUTTGART", 2400, 5900, "Dining", "Restaurant"),
                        Shop("Starbucks Coffee", "STARBUCKS STUTTGART", 420, 1390, "Dining", "Cafe"),
                        Shop("Lieferando.de", "LIEFERANDO BESTELLUNG", 1900, 4900, "Dining", "Delivery"),
                    ),
                    3,
                    6,
                ),
                Habit(
                    (
                        Shop("ARAL Tankstelle", "ARAL STATION 7710", 4400, 9400, "Transport", "Fuel"),
                        Shop("Shell Station", "SHELL STATION 7702", 4200, 9100, "Transport", "Fuel"),
                    ),
                    1,
                    3,
                ),
                Habit(
                    (
                        Shop("IKEA Deutschland", "IKEA SINDELFINGEN", 2900, 18900, "Shopping", "Home"),
                        Shop("AMAZON EU S.A R.L.", "AMZN Mktp DE 990112", 1200, 7900, "Shopping", "Online marketplace"),
                        Shop("Zalando SE", "ZALANDO BESTELLUNG", 2400, 11900, "Shopping", "Clothing"),
                    ),
                    1,
                    3,
                ),
            ),
            once=(
                Once(3, 14, 230000, "GUTSCHRIFT", "Finanzamt Stuttgart", "STEUERERSTATTUNG 2024"),
                Once(5, 2, -34000, "KARTENZAHLUNG", "Deutsche Bahn AG", "DB FERNVERKEHR URLAUB", "Transport", "Public transport"),
                Once(5, 3, -89000, "ONLINE-UEBERWEISUNG", "Ferienhaus Alpenblick", "FERIENWOHNUNG MAI 2025"),
                Once(8, 8, -68900, "KARTENZAHLUNG", "Autohaus Schwaben Service", "INSPEKTION UND BREMSEN"),
                Once(9, 20, -124900, "KARTENZAHLUNG", "IKEA Deutschland", "IKEA KUECHENZEILE", "Shopping", "Home"),
            ),
        ),
        Ledger(
            account="Sparkasse Stuttgart Privatkonto Jonas",
            file_name="couple-personal-2025.csv",
            iban="DE18600501010006789012",
            opening_cents=218000,
            fixed=(
                Fixed(1, -150000, "DAUERAUFTRAG", "Gemeinschaftskonto Riedel", "HAUSHALT {month:02d}/{year}"),
                Fixed(6, -4900, "FOLGELASTSCHRIFT", "Urban Sports Club GmbH", "MITGLIEDSCHAFT L {month:02d}/{year}", "Health", "Fitness"),
                Fixed(11, -1099, "KARTENZAHLUNG", "SPOTIFY AB", "SPOTIFY PREMIUM", "Subscriptions", "Music"),
                Fixed(22, -2379, "KARTENZAHLUNG", "Adobe Systems Software", "ADOBE FOTO ABO", "Subscriptions", "Software"),
                Fixed(28, 312000, "LOHN  GEHALT", "Bosch Rexroth Personalservice", "GEHALT {month:02d}/{year} PERS.NR 2214"),
            ),
            habits=(
                Habit(
                    (
                        Shop("Starbucks Coffee", "STARBUCKS STUTTGART HBF", 390, 1290, "Dining", "Cafe"),
                        Shop("dean and david", "DEAN+DAVID 7711", 890, 1790, "Dining", "Takeaway"),
                        Shop("Döner Haus Bad Cannstatt", "DOENER HAUS CANNSTATT", 590, 1290, "Dining", "Takeaway"),
                    ),
                    4,
                    7,
                ),
                Habit(
                    (Shop("REWE Markt GmbH", "REWE SAGT DANKE. BIS BALD", 690, 3400, "Groceries", "Supermarket"),),
                    2,
                    4,
                ),
                Habit(
                    (
                        Shop("AMAZON EU S.A R.L.", "AMZN Mktp DE 771204", 990, 6400, "Shopping", "Online marketplace"),
                        Shop("Decathlon Deutschland", "DECATHLON STUTTGART", 1900, 8900, "Shopping", "Clothing"),
                        Shop("Thalia Bücher GmbH", "THALIA STUTTGART", 890, 3400, "Leisure", "Books"),
                    ),
                    1,
                    3,
                ),
                Habit((CASH,), 1, 2, text="BARGELDAUSZAHLUNG"),
            ),
            once=(
                Once(10, 4, -12900, "KARTENZAHLUNG", "Thalia Bücher GmbH", "THALIA BUCHGESCHENK", "Leisure", "Books"),
                Once(12, 16, -45000, "KARTENZAHLUNG", "MediaMarkt Stuttgart", "MEDIAMARKT KOPFHOERER", "Shopping", "Electronics"),
            ),
        ),
    ),
)

HOUSEHOLDS = (STUDENT, FAMILY, FREELANCER, PENSIONER, COUPLE)


def generate_ledger(ledger: Ledger, seed: int) -> list[Row]:
    """One account's year. Deterministic for the seed, sorted the way the CSV is written."""
    rng = random.Random(seed)
    rows: list[Row] = []
    for month in MONTHS:
        for fixed in ledger.fixed:
            if month not in fixed.months:
                continue
            rows.append(
                Row(
                    Booking(
                        clamp_day(month, fixed.day),
                        fixed.cents,
                        fixed.text,
                        fixed.counterparty,
                        fixed.reference.format(month=month, year=YEAR),
                    ),
                    fixed.category,
                    fixed.subcategory,
                )
            )
        for habit in ledger.habits:
            count = rng.randint(habit.low, habit.high) + dict(habit.busier).get(month, 0)
            for _ in range(count):
                shop = rng.choice(habit.shops)
                rows.append(
                    Row(
                        Booking(
                            clamp_day(month, rng.randint(1, 28)),
                            -rng.randrange(shop.low, shop.high, 10),
                            habit.text,
                            shop.counterparty,
                            shop.reference,
                        ),
                        shop.category,
                        shop.subcategory,
                    )
                )
    for once in ledger.once:
        rows.append(
            Row(
                Booking(clamp_day(once.month, once.day), once.cents, once.text, once.counterparty, once.reference),
                once.category,
                once.subcategory,
            )
        )
    rows.sort(key=lambda row: (row.booking.booked_on, row.booking.counterparty, row.booking.amount_cents))
    return rows


def generate_household(household: Household) -> list[list[Row]]:
    """Every account of one household, in the order the household lists them."""
    return [generate_ledger(ledger, household.seed + index * 101) for index, ledger in enumerate(household.ledgers)]


def _eur(cents: int) -> float:
    return round(cents / 100, 2)


def _merchant_truth(rows: list[Row]) -> list[dict[str, object]]:
    """One entry per merchant: where the categorizer puts it, and what it came to."""
    merchants: dict[str, dict[str, int]] = {}
    placed: dict[str, tuple[str, str | None]] = {}
    for row in rows:
        name = row.booking.counterparty
        placed[name] = (row.topic, row.subcategory)
        entry = merchants.setdefault(name, {"bookings": 0, "spent": 0, "received": 0})
        entry["bookings"] += 1
        if row.booking.amount_cents < 0:
            entry["spent"] -= row.booking.amount_cents
        else:
            entry["received"] += row.booking.amount_cents
    ordered = sorted(merchants.items(), key=lambda item: (-item[1]["spent"], item[0]))
    return [
        {
            "name": name,
            "category": placed[name][0],
            "subcategory": placed[name][1],
            "bookings": totals["bookings"],
            "spent_eur": _eur(totals["spent"]),
            "received_eur": _eur(totals["received"]),
        }
        for name, totals in ordered
    ]


def _category_truth(rows: list[Row]) -> list[dict[str, object]]:
    """One entry per category, `Needs review` included, the way a breakdown groups them."""
    totals: dict[str, list[int]] = {}
    for row in rows:
        bucket = totals.setdefault(row.topic, [0, 0, 0])
        bucket[0] += 1
        if row.booking.amount_cents < 0:
            bucket[1] -= row.booking.amount_cents
        else:
            bucket[2] += row.booking.amount_cents
    return [
        {"category": name, "bookings": counts[0], "spent_eur": _eur(counts[1]), "received_eur": _eur(counts[2])}
        for name, counts in sorted(totals.items())
    ]


def _monthly_truth(rows: list[Row]) -> list[dict[str, object]]:
    """One entry per month: what went out, what came in, and what each category cost."""
    months: dict[str, list[int]] = {}
    per_category: dict[str, dict[str, int]] = {}
    for row in rows:
        key = f"{row.booking.booked_on:%Y-%m}"
        bucket = months.setdefault(key, [0, 0, 0])
        bucket[0] += 1
        if row.booking.amount_cents < 0:
            bucket[1] -= row.booking.amount_cents
            topics = per_category.setdefault(key, {})
            topics[row.topic] = topics.get(row.topic, 0) - row.booking.amount_cents
        else:
            bucket[2] += row.booking.amount_cents
    return [
        {
            "month": month,
            "bookings": counts[0],
            "spent_eur": _eur(counts[1]),
            "received_eur": _eur(counts[2]),
            "spent_by_category_eur": {
                name: _eur(cents) for name, cents in sorted(per_category.get(month, {}).items())
            },
        }
        for month, counts in sorted(months.items())
    ]


def household_truth(household: Household, ledgers: list[list[Row]]) -> dict[str, object]:
    """What the generator knows about a household, so a judge can recompute a figure itself."""
    every = [row for rows in ledgers for row in rows]
    accounts = []
    for ledger, rows in zip(household.ledgers, ledgers, strict=True):
        closing = ledger.opening_cents + sum(row.booking.amount_cents for row in rows)
        accounts.append(
            {
                "name": ledger.account,
                "file": f"households/{ledger.file_name}",
                "iban": ledger.iban,
                "bookings": len(rows),
                "opening_eur": _eur(ledger.opening_cents),
                "closing_eur": _eur(closing),
            }
        )
    dates = sorted(row.booking.booked_on for row in every)
    return {
        "slug": household.slug,
        "label": household.label,
        "holder": household.holder,
        "note": household.note,
        "seed": household.seed,
        "today": TODAY.isoformat(),
        "accounts": accounts,
        "bookings": len(every),
        "first_booked_on": dates[0].isoformat(),
        "last_booked_on": dates[-1].isoformat(),
        "needs_review_bookings": sum(1 for row in every if row.category is None),
        "spent_eur": _eur(-sum(row.booking.amount_cents for row in every if row.booking.amount_cents < 0)),
        "received_eur": _eur(sum(row.booking.amount_cents for row in every if row.booking.amount_cents > 0)),
        "edge_cases": list(household.edge_cases),
        "merchants": _merchant_truth(every),
        "categories": _category_truth(every),
        "monthly": _monthly_truth(every),
    }


HOUSEHOLDS_README = """\
# Five more households

Generated by `scripts/generate_synthetic.py` beside the shipped year, for the query and chart
adapters (ticket 62). Deterministic: one seed per household and one derived seed per account, so
re-running the generator reproduces these files byte for byte. No personal data.

Every file is the Sparkasse CAMT layout of `../sparkasse-2025.csv`, so it is read by the same
preset and categorized by the same rules and the same merchant dictionary, with no model in the
loop.

| Household | Accounts | Bookings | What it is |
| --- | ---: | ---: | --- |
{table}

`households.json` is the truth the generator knows: every merchant with the category the import
path gives it, the totals per category and the totals per month per category. A judge checks a
figure against that file, or against the CSV itself, and never against the model that wrote the
SQL.

The databases are built from these files by `training/data/households.py` and cached under
`training/data/.db/`, which is not committed.
"""


def write_households() -> list[dict[str, object]]:
    """Write every household's CSV files, the truth file and the README beside them."""
    HOUSEHOLDS_OUT.mkdir(parents=True, exist_ok=True)
    truths: list[dict[str, object]] = []
    lines: list[str] = []
    for household in HOUSEHOLDS:
        ledgers = generate_household(household)
        for ledger, rows in zip(household.ledgers, ledgers, strict=True):
            write_sparkasse_csv([row.booking for row in rows], HOUSEHOLDS_OUT / ledger.file_name, iban=ledger.iban)
        truth = household_truth(household, ledgers)
        truths.append(truth)
        lines.append(f"| `{household.slug}` | {len(household.ledgers)} | {truth['bookings']} | {household.note} |")
    (HOUSEHOLDS_OUT / "households.json").write_text(
        json.dumps({"year": YEAR, "today": TODAY.isoformat(), "households": truths}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (HOUSEHOLDS_OUT / "README.md").write_text(HOUSEHOLDS_README.format(table="\n".join(lines)), encoding="utf-8")
    return truths


README = """\
# Synthetic dataset

One canonical year (2025) of a German household, generated by `scripts/generate_synthetic.py`.
Deterministic: re-running the script reproduces these files byte for byte. No personal data.

| File | What it is |
| ---- | ---------- |
| `sparkasse-2025.csv` | Sparkasse CAMT export layout: semicolon, cp1252, `1.234,56`, DD.MM.YYYY. Matches the `sparkasse` preset. |
| `sparkasse-2025.xlsx` | The same export as an Excel workbook, one sheet, dates and amounts as typed cells. Matches the `sparkasse` preset too. |
| `unknown-bank-2025.csv` | The same bookings with headers no preset knows and separate `Soll` and `Haben` columns. Exercises the mapping sub-agent. |
| `sparkasse-kontoauszug-2025.pdf` | Text PDF statement. Opening balance plus all bookings equals the printed closing balance. |
| `statement-excerpt.docx` | The first {docx_rows} bookings of the year as a Word document, with the two printed balances the reconciliation guard checks. |
| `bill-*.png` | Four receipts whose line items sum to the total of a booking that is in the CSV, so a bill photo can match an existing transaction. |

Figures: {count} bookings, opening balance {opening} EUR, closing balance {closing} EUR. The
Word excerpt closes at {docx_closing} EUR after its {docx_rows} bookings.
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
    write_sparkasse_xlsx(bookings, OUT / "sparkasse-2025.xlsx")
    write_statement_docx(bookings[:DOCX_BOOKINGS], OUT / "statement-excerpt.docx")
    write_unknown_bank_csv(bookings, OUT / "unknown-bank-2025.csv")
    write_statement_pdf(bookings, OUT / "sparkasse-kontoauszug-2025.pdf")
    for bill in BILLS:
        write_bill_image(bill, OUT / f"bill-{bill.slug}-{bill.booked_on:%Y-%m-%d}.png")

    closing = OPENING_CENTS + sum(booking.amount_cents for booking in bookings)
    excerpt = OPENING_CENTS + sum(booking.amount_cents for booking in bookings[:DOCX_BOOKINGS])
    (OUT / "README.md").write_text(
        README.format(
            count=len(bookings),
            opening=euro(OPENING_CENTS),
            closing=euro(closing),
            docx_rows=DOCX_BOOKINGS,
            docx_closing=euro(excerpt),
        ),
        encoding="utf-8",
    )
    print(f"{len(bookings)} bookings, closing balance {euro(closing)} EUR, written to {OUT}")

    for truth in write_households():
        print(
            f"{truth['slug']}: {truth['bookings']} bookings over "
            f"{len(truth['accounts'])} account(s), written to {HOUSEHOLDS_OUT}"  # type: ignore[arg-type]
        )


if __name__ == "__main__":
    main()
