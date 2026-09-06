"""One statement file to checked rows: read the pages, ask the sub-agent, run the guards.

This is the PDF, Word and photo reader of the ingestion pipeline, and it ends where the CSV
reader ends: at `ingest.commit.commit_rows`, with a `ParsedRow` per booking. Everything between
is about being able to prove the rows.

The order is always the same. Read the file, recognize the layout, hand each page to the
extraction sub-agent (the text layer where there is one, the rendered page where there is
not), parse the spans it points at, then reconcile. A DOCX is text and nothing else, so it is
one page of the text-layer path and gets the verbatim guard like any printed page
(`finquery.extract.docx`). What comes out is an `Extraction`: the rows, the ones the guards
flagged, and one sentence about the arithmetic that the review step shows and the Import record
keeps.

Pages go out four at a time. A page is one model call, so a 15 page statement is 15 calls on
the fast slot, and doing them one after another would cost minutes of wall clock for nothing.
"""

import asyncio
import logging
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence

from pydantic import BaseModel, Field
from pydantic_ai.settings import ModelSettings
from sqlalchemy.orm import Session

from finquery.db import Import
from finquery.extract import pdf
from finquery.extract.docx import read_docx
from finquery.extract.guards import ExtractedRow, Reconciliation, flag_unverified, reconcile, to_rows
from finquery.extract.layouts import detect_layout, layout_named
from finquery.extract.subagent import StatementPage, read_statement_image, read_statement_text
from finquery.ingest.commit import commit_rows
from finquery.ingest.csv_reader import ParsedRow
from finquery.providers import ModelResolver

logger = logging.getLogger(__name__)

PAGE_CONCURRENCY = 4
"""Pages in flight when nobody says otherwise. `create_app` raises it for a hosted provider
through `settings.page_concurrency`, since only there the pages really run in parallel."""
"""Pages in flight at once. The local provider serializes the slot anyway; on OpenRouter this
is what turns a 15 page statement from minutes into under one."""

_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

Reporter = Callable[..., Awaitable[None]]


async def _silent(stage: str, message: str, **counts: int) -> None:
    return None


class Extraction(BaseModel):
    """What one file came to. Stored as it is between the extraction and the review."""

    file_name: str
    kind: str
    """`pdf`, `docx` or `image`, the attachment kind it was read from."""
    layout: str
    layout_label: str
    account_name: str
    pages: int = 0
    scanned_pages: list[int] = Field(default_factory=list)
    rows: list[ExtractedRow] = Field(default_factory=list)
    reconciliation: Reconciliation
    note: str | None = None
    errors: list[str] = Field(default_factory=list)
    model_calls: int = 0

    @property
    def flagged(self) -> list[ExtractedRow]:
        return [row for row in self.rows if row.flagged]

    @property
    def clean(self) -> list[ExtractedRow]:
        return [row for row in self.rows if not row.flagged and row.committable]

    @property
    def needs_review(self) -> bool:
        """Whether a human has to see this before anything is written.

        A flagged row, obviously. A statement that did not reconcile too, even when every
        single row passed its own checks: the arithmetic then says a booking is missing, and
        importing rows that are known to be incomplete without saying so is the failure this
        guard exists for.
        """
        return bool(self.flagged) or self.reconciliation.status != "ok"


def _refusals(rows: Sequence[ExtractedRow]) -> list[str]:
    """What the verbatim guard refused about these rows, in the words the second reading gets.

    Only the two flags a second reading of the same page can do anything about: a figure that is
    not printed on the page, and a span that is not a date or an amount at all. Reconciliation
    is judged over the whole statement, long after this, and no single page can fix it.
    """
    return [
        f"line {row.line}: {row.reason}"
        for row in rows
        if row.reason and ("verbatim" in row.flags or "unreadable" in row.flags)
    ]


def _year_of(text: str) -> int | None:
    """The year the statement is mostly about, for a date printed as `01.04.` with none."""
    years = Counter(int(match.group()) for match in _YEAR.finditer(text))
    return years.most_common(1)[0][0] if years else None


async def extract_statement(
    data: bytes,
    *,
    file_name: str,
    kind: str,
    resolve_model: ModelResolver,
    model_settings: ModelSettings | None = None,
    report: Reporter = _silent,
    concurrency: int | None = None,
) -> Extraction:
    """Read one statement file into checked rows. Writes nothing.

    `kind` is the attachment kind: a `pdf` is read page by page from its text layer, or as an
    image for the pages that have none; a `docx` is its own text as one page; an `image` is one
    page read by the vision path.
    """
    photo = await asyncio.to_thread(pdf.as_image, data) if kind == "image" else None
    if photo is not None:
        document = pdf.Document(pages=(pdf.Page(number=1, lines=()),))
    elif kind == "docx":
        document = await asyncio.to_thread(read_docx, data)
    else:
        document = await asyncio.to_thread(pdf.read_pdf, data)
    if not document.pages:
        raise pdf.PdfUnreadable("This PDF has no pages.")

    layout = detect_layout(document.text)
    year = _year_of(document.text)
    await report(
        "read",
        f"Read {len(document.pages)} page(s) of {file_name}, recognized {layout.label}",
        pages=len(document.pages),
    )

    semaphore = asyncio.Semaphore(max(1, concurrency or PAGE_CONCURRENCY))
    answers: list[StatementPage | None] = [None] * len(document.pages)
    per_page: list[list[ExtractedRow]] = [[] for _ in document.pages]
    errors: list[str] = []
    done = 0
    rereads = 0

    async def one(index: int, page: pdf.Page) -> None:
        nonlocal done, rereads
        async with semaphore:
            try:
                model = resolve_model("extraction")
                image = photo if photo is not None else None
                # Only a PDF page can be rasterized, so only a PDF page is looked at instead
                # of read. A DOCX with almost no text is a short document, not a scan.
                if image is None and page.scanned and kind == "pdf":
                    image = await asyncio.to_thread(pdf.render, data, page.number)
                if image is not None:
                    answer = await read_statement_image(
                        model,
                        image,
                        page=page.number,
                        pages=len(document.pages),
                        layout_hint=layout.hint,
                        year=year,
                        model_settings=model_settings,
                    )
                    rows = to_rows(answer.rows, page=page.number, source_text=None, year=year)
                else:

                    async def read(
                        previous: StatementPage | None = None, findings: list[str] | None = None
                    ) -> tuple[StatementPage, list[ExtractedRow]]:
                        answer = await read_statement_text(
                            model,
                            page=page.number,
                            pages=len(document.pages),
                            layout_hint=layout.hint,
                            year=year,
                            lines=page.numbered(),
                            previous=previous,
                            findings=findings,
                            model_settings=model_settings,
                        )
                        return answer, to_rows(
                            answer.rows,
                            page=page.number,
                            lines=page.lines,
                            source_text=page.text,
                            document_text=document.text,
                            year=year,
                        )

                    answer, rows = await read()
                    # A figure the verbatim guard refused was written rather than read, and the
                    # printed line it belongs to is in the prompt already: one second reading
                    # with the refusal in it is cheaper than a review card per row (ticket 42).
                    if refused := _refusals(rows):
                        rereads += 1
                        second_answer, second_rows = await read(answer, refused)
                        if len(_refusals(second_rows)) < len(refused):
                            answer, rows = second_answer, second_rows
            except Exception as exc:  # noqa: BLE001 - one page failing is a flag, not a crash
                logger.warning("page %s of %s could not be extracted: %s", page.number, file_name, exc)
                errors.append(f"Page {page.number} could not be read: {exc}")
                return
            answers[index] = answer
            per_page[index] = rows
        done += 1
        await report(
            "extracting",
            f"Read page {done} of {len(document.pages)}, {sum(len(rows) for rows in per_page)} bookings so far",
            pages_done=done,
            rows=sum(len(rows) for rows in per_page),
        )

    await asyncio.gather(*(one(index, page) for index, page in enumerate(document.pages)))

    rows = [row for page_rows in per_page for row in page_rows]
    scanned = [page.number for page in document.pages if page.scanned]
    flag_unverified(rows, scanned)
    result = reconcile(
        rows,
        opening_cents=layout.opening(document.text),
        closing_cents=layout.closing(document.text),
    )
    await report("checking", result.line, rows=len(rows), flagged=sum(1 for row in rows if row.flagged))
    notes = [answer.note for answer in answers if answer is not None and answer.note]
    return Extraction(
        file_name=file_name,
        kind=kind,
        layout=layout.name,
        layout_label=layout.label,
        account_name=layout.account_name,
        pages=len(document.pages),
        scanned_pages=scanned,
        rows=rows,
        reconciliation=result,
        # Only worth passing on when there is nothing else to show: it is the sub-agent saying
        # the page was not a statement at all.
        note=notes[0] if notes and not rows else None,
        errors=errors,
        model_calls=len(document.pages) + rereads,
    )


def to_parsed(rows: Sequence[ExtractedRow]) -> list[ParsedRow]:
    """The extracted rows as the commit takes them. A row with no date or amount is left out."""
    return [
        ParsedRow(
            booked_on=row.booked_on,
            amount_cents=row.amount_cents,
            description=row.description,
            counterparty=row.counterparty,
        )
        for row in rows
        if row.booked_on is not None and row.amount_cents is not None
    ]


def commit_extraction(
    session: Session,
    profile_id: str,
    *,
    rows: Sequence[ExtractedRow],
    file_name: str,
    kind: str,
    layout: str,
    account_name: str,
    reconciliation: Reconciliation,
    dropped: int = 0,
) -> Import:
    """Write the rows the user accepted, through the same commit the CSV import uses.

    The same function on purpose: the duplicate step and the categorization that follow a CSV
    import are then the same code for a statement PDF, and the Import record of a PDF reads
    like any other, plus the one line the reconciliation guard produced.
    """
    known = layout_named(layout)
    parsed = to_parsed(rows)
    record = commit_rows(
        session,
        profile_id,
        rows=parsed,
        mapping=known.columns,
        account_name=account_name,
        file_name=file_name,
        kind=kind,
        preset=known.name if known.name != "unknown" else None,
        skipped_count=dropped + len(rows) - len(parsed),
    )
    record.reconciliation = reconciliation.line[:200]
    session.commit()
    return record
