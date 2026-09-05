"""The bytes of a PDF or a photo: its text layer, and its pages as images.

Two readers, one file. `read_pdf` pulls the words out of a page with pdfplumber and groups them
back into the visual lines they were printed as, because a bank statement is a table without
ruling lines: the column a figure sits in is an x position, and a booking is one line plus a
reference line under it. The numbered lines are what the extraction sub-agent reads and what
the verbatim guard checks an amount against, so both halves see exactly the same text.

`render` is the other path. A scanned page has no text layer to read, so pypdfium2 (already a
dependency of pdfplumber) rasterizes it at 150 dpi and the page goes to the model as an image.
A photo is passed through `as_image`, which only shrinks it: a 12 megapixel phone picture is
tokens nobody needs.
"""

import io
from dataclasses import dataclass
from functools import cached_property

import pdfplumber
import pypdfium2
from PIL import Image, ImageOps

RENDER_DPI = 150
"""What a scanned page is rasterized at. Enough for 8 pt German statement type, and about
250 KB a page as PNG."""

MAX_IMAGE_SIDE = 1600
"""Longest side of an image sent to the model. A phone photo is shrunk to it."""

MIN_TEXT_CHARS = 60
"""Characters a page needs before it counts as having a text layer. A scan of a statement
carries a few stray characters from the OCR-free PDF wrapper, never a page of them."""

COLUMN_GAP = 3.0
"""Points between two words that read as a column boundary rather than a space. Kerning inside
a word pair is under a point; the gaps between statement columns are tens of points."""

LINE_TOLERANCE = 1.8
"""How far apart two words may be vertically and still be on the same printed line."""


class PdfUnreadable(ValueError):
    """The file is not a PDF we can open."""


@dataclass(frozen=True)
class Page:
    """One page as text, in the order it was printed."""

    number: int
    """1-based, the way the page prints its own number."""
    lines: tuple[str, ...]

    @cached_property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def scanned(self) -> bool:
        """True when there is no text layer worth reading, so the page has to be looked at."""
        return len(self.text.strip()) < MIN_TEXT_CHARS

    def numbered(self) -> str:
        """The page as the sub-agent sees it: one numbered line per printed line.

        The numbers are how a row points back at what it was read from, and they are what makes
        a flagged row reviewable: the user is shown the line, not a page.
        """
        return "\n".join(f"{number:>4}| {line}" for number, line in enumerate(self.lines, start=1))


@dataclass(frozen=True)
class Document:
    """Every page of a file, with the whole text for the verbatim guard to search."""

    pages: tuple[Page, ...]

    @cached_property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)

    @property
    def scanned_pages(self) -> tuple[Page, ...]:
        return tuple(page for page in self.pages if page.scanned)


def _lines_of(page: pdfplumber.page.Page) -> tuple[str, ...]:
    """Group the words of a page back into printed lines, left to right.

    pdfplumber's own `extract_text` reads a two-column statement in one pass and glues the
    columns of different rows together (seen on the real Trade Republic export). Grouping by
    the top coordinate and then sorting by x keeps every line the line it was, and a column
    boundary becomes two spaces, which is a hint the model can use and a human can read.
    """
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    rows: list[list[dict[str, object]]] = []
    for word in sorted(words, key=lambda w: (float(w["top"]), float(w["x0"]))):
        for row in rows:
            if abs(float(row[0]["top"]) - float(word["top"])) <= LINE_TOLERANCE:
                row.append(word)
                break
        else:
            rows.append([word])

    lines: list[str] = []
    for row in rows:
        row.sort(key=lambda w: float(w["x0"]))
        parts: list[str] = []
        previous: dict[str, object] | None = None
        for word in row:
            if previous is not None:
                parts.append("  " if float(word["x0"]) - float(previous["x1"]) > COLUMN_GAP else " ")
            parts.append(str(word["text"]))
            previous = word
        line = "".join(parts).strip()
        if line:
            lines.append(line)
    return tuple(lines)


def read_pdf(data: bytes) -> Document:
    """Every page of a PDF as printed lines. A page with no text layer comes back empty."""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return Document(
                pages=tuple(Page(number=number, lines=_lines_of(page)) for number, page in enumerate(pdf.pages, start=1))
            )
    except PdfUnreadable:
        raise
    except Exception as exc:  # noqa: BLE001 - every failure to open is the same message here
        raise PdfUnreadable(f"This file could not be opened as a PDF: {exc}") from exc


def _png(image: Image.Image) -> bytes:
    if max(image.size) > MAX_IMAGE_SIDE:
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def render(data: bytes, number: int, *, dpi: int = RENDER_DPI) -> bytes:
    """One page of a PDF as a PNG, for the pages that have to be looked at instead of read."""
    document = pypdfium2.PdfDocument(data)
    try:
        page = document[number - 1]
        return _png(page.render(scale=dpi / 72).to_pil())
    except IndexError as exc:
        raise PdfUnreadable(f"The PDF has no page {number}.") from exc
    finally:
        document.close()


def as_image(data: bytes) -> bytes:
    """A photo as a PNG the model can take, shrunk to `MAX_IMAGE_SIDE` if it is bigger."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            # A phone stores the rotation in EXIF and leaves the pixels sideways; the model
            # would otherwise read a receipt turned by 90 degrees.
            return _png(ImageOps.exif_transpose(image) or image)
    except Exception as exc:  # noqa: BLE001 - a photo we cannot open is one message
        raise PdfUnreadable(f"This image could not be read: {exc}") from exc
