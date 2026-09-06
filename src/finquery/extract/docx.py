"""The text of a Word document, as one page the statement reader can read.

A DOCX carries its text already: there is nothing to look at and nothing to render, so it goes
down the text-layer path of `finquery.extract.statement` and gets exactly what a PDF page with
a text layer gets, the verbatim guard included. A figure the extraction sub-agent reports has
to occur literally in these lines or its row is flagged (ADR 0011).

What is read is paragraphs and table cells in document order. A table row becomes one line with
two spaces between its cells, the same separator `extract.pdf` writes a printed column boundary
as, so a booking's amount stays on the booking's line and the sub-agent sees the columns it is
told about. Formatting is dropped. Images inside the document, headers, footers and macros are
not read, and `read_docx` says so in one line for the answer to pass on.
"""

import io
import logging

from docx import Document as open_docx
from docx.document import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from finquery.extract.pdf import Document, Page, PdfUnreadable

logger = logging.getLogger(__name__)

CELL_GAP = "  "
"""What a table cell boundary becomes, the same two spaces `extract.pdf` writes a printed
column boundary as."""

IGNORED = "Pictures, headers and footers in a Word document are not read, only its text."


class DocxUnreadable(PdfUnreadable):
    """The file is not a Word document we can open.

    A subclass, so every caller that already answers an unreadable PDF with one sentence
    answers an unreadable DOCX with one too.
    """


def _lines_of(document: DocxDocument) -> list[str]:
    """Paragraphs and table rows in the order the document prints them."""
    lines: list[str] = []
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            text = Paragraph(child, document).text.strip()
            if text:
                lines.append(text)
        elif child.tag.endswith("}tbl"):
            for row in Table(child, document).rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                line = CELL_GAP.join(cell for cell in cells if cell)
                if line:
                    lines.append(line)
    return lines


def read_docx(data: bytes) -> Document:
    """One Word document as a single page of printed lines.

    A DOCX has no pages of its own until it is laid out, so it is one page. Nothing downstream
    needs more: the page number is what a flagged row points back with, and every line of the
    document is in it.
    """
    try:
        document = open_docx(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - every failure to open is the same message here
        # python-docx's own words ("file ... is not a Word file, content type is ...") are for
        # the log; what the user needs is what to do next.
        logger.warning("a Word document could not be opened", exc_info=True)
        raise DocxUnreadable(
            "This file could not be opened as a Word document. It may be damaged, or it may be "
            "an older .doc file. Save it again as .docx, or attach the CSV export instead."
        ) from exc
    lines = _lines_of(document)
    if not lines:
        raise DocxUnreadable("This Word document has no text in it, so there is nothing to read.")
    return Document(pages=(Page(number=1, lines=tuple(lines)),))
