# 58: XLSX and DOCX ingestion, and the multimodal elective explainer

**What to build:** Excel workbooks (.xlsx) and Word documents (.docx) go through the same chat composer path as CSV, PDF and images: an XLSX sheet becomes rows for the existing CSV mapping engine (the model proposes the mapping, the user confirms in a Question card), a DOCX becomes text for the existing pasted-text and text-layer path (extraction sub-agent with the verbatim guard). The multimodal elective is now claimed, so the explainer and the checklist say what is covered (images, PDF, text, CSV, XLSX, DOCX through inherently multimodal local models) and what is not (audio). Decided by the user on 2026-09-06.

**Blocked by:** 05, 06, 11, 22 (merged)

**Status:** done

Decisions, settled:
- Libraries: `openpyxl` for XLSX (read-only, values not formulas, the first sheet by default and a sheet picker in the mapping card only when there is more than one non-empty sheet), `python-docx` for DOCX (paragraphs and table cells in document order, joined as text). Both are parsing libraries, allowed by the course; add them to `pyproject.toml` and lock.
- XLSX rows feed `ingest/csv_reader` as if they were a delimited file: header detection, preset detection and `mapping_for` reuse; numbers keep their cell type (a float amount is not re-parsed from a string); dates come from cell datetimes when present, otherwise through the existing date parsing. Empty rows and a leading title block above the header are skipped the way the edge-case CSVs are (tickets 31, 32).
- DOCX text takes the pasted-text path: `extract_transaction`-style extraction over the text with the verbatim guard and the extraction review card, and a statement-shaped document (many bookings) goes through the statement extraction with reconciliation when balances appear. Formatting is dropped; tables keep their cell order so an amount stays on its booking's line.
- Composer: the attachment picker accepts `.xlsx` and `.docx`; the attachment chip shows the kind; the Import page's overview lists the new kinds. Size limits as for CSV and PDF. Audio, images inside DOCX and macros are ignored with a one-line note in the answer.
- Fixtures: `fixtures/synthetic/sparkasse-2025.xlsx` generated from the CSV by `scripts/generate_synthetic.py` (deterministic), and `fixtures/synthetic/statement-excerpt.docx` with about fifteen bookings and a balance line; both small, committed.
- Docs: `docs/explainers/16-elective-multimodal-ingestion.md` in the style of the other explainers (claim, how it works with the vision path and the guards, code path, model in and out of the loop, guards, measurements from tickets 22 and 24 and the receipts review, what to say, grader questions, what is not covered: audio), `docs/explainers/README.md` and the checklist row for multimodal set to claimed (the coordinator updates the checklist's preference row), CONTEXT.md if a term is new, demo script step for an XLSX drop.

- [x] XLSX through the mapping engine with the fixture; multi-sheet picker only when needed; tests at the HTTP seam (import, mapping card, confirm, rows in the table, numbers and dates exact)
- [x] DOCX through the text path with the fixture; tests (extraction with the verbatim guard, the review card, a statement-shaped document reconciled)
- [x] Composer and Import page accept and label the two kinds; build clean
- [x] Explainer 16, README index, checklist row, demo step; `uv run pytest` green; headful browser verification (named session, own port above 8100, throwaway database, Qwen on both cloud slots, few turns): the XLSX drop to imported rows, the DOCX drop to a review card, both themes; screenshots in `/tmp/finquery-58/`; Comments

## Comments

**2026-09-06, implementation agent.** Done on branch `worktree-agent-affbd600148b875b1`, seven
commits. `uv run pytest` is 404 passed, 4 skipped, up from 399 passed, 4 skipped (5 new tests, no
existing test rewritten except the one below). `npm run build` clean, oxlint 38 warnings (the
count on `main`, none of them in a file this ticket touched), `check_refs.py` 437 references, 0
failures. The browser check and the two dependencies cost 0.02 USD of the shared credit: five
hosted turns on `qwen/qwen3.5-9b`, the tests cost nothing.

### What changed, by file

`ingest/xlsx.py` (new): `read_xlsx` opens the workbook read-only with `data_only=True`, drops
empty rows and trailing empty cells, picks the header row with the same "most common width, the
first of them" rule `csv_reader.sniff` uses (so a title block above the table is skipped), and
hands back a `Sniffed` the CSV path already knows what to do with. A cell keeps what its type
knows: a date becomes `2025-01-04`, a number becomes `-39.9` with no thousands separator, and the
columns those cells were in are remembered. `with_cell_types` then corrects the mapping's
`date_format` and `decimal_separator` for those columns, which is the whole point of the module:
the Sparkasse preset says "German decimal comma", and reading the float `-39.9` with it would
have booked 3.990,00 EUR. A column that also holds text is left alone (one format has to fit
every cell), and an empty money column does not veto its sibling. `XlsxUnreadable` subclasses
`CsvUnreadable` so every caller that already answers an unreadable CSV answers this too.

`extract/docx.py` (new): `read_docx` walks the document body in order, paragraphs and tables
together, and joins a table row's cells with the two spaces `extract/pdf.py` writes a printed
column boundary as, so an amount stays on its booking's line. It returns a `pdf.Document` with
one page, which is all `extract_statement` needs. `DocxUnreadable` subclasses `PdfUnreadable`
for the same reason as above.

`extract/statement.py`: three lines. A `docx` kind reads its document through `read_docx`, and
only a `pdf` page may be rendered when it has no text layer (a short Word document is a short
document, not a scan). Everything after that is unchanged, which is the reason a DOCX gets the
verbatim guard, the reconciliation guard and the review card for free.

`ingest/chat_import.py`: the router sends `xlsx` to `_import_csv` and `docx` to
`_import_statement`. `_read_rows` reads a workbook one sheet at a time (the one asked for, the
one a previous call settled on, or the first sheet with bookings), `_for_cells` applies
`with_cell_types` wherever a mapping is produced, so the card shows the amounts the cells really
hold. `mapping_card` grows a button per other sheet (`sheet:NAME`), the confirm payload carries
`sheet` and `sheets`, and the commit now passes the attachment's kind through, so the Import
record says `xlsx` or `docx` rather than `csv`.

`attachments.py`: `kind_of` answers `xlsx` and `docx` (suffix first, media type second),
`ACCEPTED_KINDS` is the one sentence naming what may be attached, and the refusal quotes it.
`db.py`: `attachment.sheet_name`, additive, in `NEW_COLUMNS`. `agent.py`: `import_file` takes
`sheet`, and three prompt paragraphs name the two new kinds and what a `sheet:` answer means.

`composer.tsx`: the accept list, the refusal sentence, the attach button's label, and a kind
badge on each chip (`kindOf`, by extension, the way the server decides). `imports-list.tsx`:
`KIND_LABELS` gains Excel workbook and Word document, and the empty state says so.

`scripts/generate_synthetic.py`: `write_sparkasse_xlsx` (the same 433 bookings, the same header,
dates and amounts as typed cells) and `write_statement_docx` (the first 15 bookings with an
opening and a closing balance). Both are byte-for-byte reproducible: `_deterministic` rewrites
the zip entries with a fixed timestamp, and the workbook is written through `ExcelWriter` rather
than `Workbook.save`, because `save` stamps `modified` with the clock of the run. 25 KB and
37 KB, committed.

`tests/test_xlsx_and_docx_import.py` (new, 5 tests, all at the HTTP seam): the shipped workbook
imported by its preset with no model call and the exact cents and days off the cells; an unknown
workbook proposed, confirmed on the card and committed, with the card showing `-40,90 EUR` and
`09.01.2025`; a two-sheet workbook whose card offers the other sheet and whose picked sheet is
the one that lands; the Word excerpt read, reconciled and imported; and one amount rewritten by
the scripted reader, flagged, nothing written until the card was answered.

`tests/test_edge_cases.py`: the "unsupported type" case was a `notes.docx`, which is now a kind
we read. It is a `voice-memo.m4a` instead, which is the kind the elective deliberately does not
cover.

Docs: `docs/explainers/16-elective-multimodal-ingestion.md` (new), the explainers README index
and its elective paragraph, the checklist's multimodal row set to done and claimed (the
preference rows are ticket 59's and were not touched), explainer 08 (the claim, the diagram, the
XLSX and DOCX steps, and the "out of scope" bullet that named XLSX), `CONTEXT.md` (Attachment
kinds, Column mapping, Extraction), the root README, and demo step 31 with two rows in the
timing table.

### The one design decision worth arguing about

The mapping the user confirms describes how a *text* export writes its figures, and a workbook
does not write figures at all: it stores them. Two ways out. Either format the cells into the
German text the mapping expects, or keep the cells' own rendering and correct the mapping. The
first one loses on edge cases (a preset saying `dot` would misread a cell we formatted with a
comma, and the other way round), so `with_cell_types` does the second: one place, two fields,
tested from both directions. The ceiling is a `TODO` in the module: a sheet whose money columns
disagree about their type keeps the declared separator.

### The browser session

Headful, session `ticket58`, port 8137, throwaway database at `/tmp/finquery-58/verify.db`,
`qwen/qwen3.5-9b` on both slots, five turns, screenshots in `/tmp/finquery-58/`. Files were
attached through the chat endpoint the way tickets 22 and 24 did it, never through the file
dialog.

- **XLSX (`01`, `02`, both themes).** `sparkasse-2025.xlsx` dropped with "Import this workbook
  please": read 433 rows, recognized as a Sparkasse export, imported 433, 384 by the merchant
  list, 24 by the categorizer, 25 Needs review, then the merchant card. The same figures as the
  CSV of the same year, which is the point of the fixture. `/import` (`07`) shows the row with
  the **Excel workbook** badge.
- **DOCX (`03`, `04`, both themes).** `statement-excerpt.docx` in a second profile: 1 page read,
  0 read as images, 15 of 15 bookings, 0 flagged, "Reconciled: opening balance plus 15 bookings
  equals the closing balance (4.210,55 + -1.877,97 = 2.332,58)", imported and categorized. The
  hosted Qwen read every span cleanly, so there was no review card to look at.
- **The review card (`05`, `06`, both themes).** So one was produced honestly: the same document
  with one printed amount changed from `-25,00` to `-95,10` (`/tmp/finquery-58`, not committed).
  The card says "The balance moves by -25,00 but the amount reads -95,10, so a booking is missing
  or misread here. Page 1, line 9" with the printed line quoted under it, Accept as read and Drop
  it, and nothing was written. The reconciliation guard on a Word document, in a real turn.
- **`/import` (`07`, `08`, both themes).** Excel workbook and Word document badges, and the
  reconciliation sentence on the Word row.

### What is left

- The chip's kind badge was verified by `npm run build` and by reading, not in the browser: a
  file only reaches the composer chip through the file dialog, and `agent-browser upload` is off
  limits while the `eval` route the drop would need is blocked in this sandbox. The transcript
  chip (the file name after a reload) is in every screenshot.
- The extraction sub-agent copies the whole printed line into `description` for the Word excerpt,
  so one booking reads "10.01.25 ONLINE-UEBERWEISUNG PayPal Europe S.a.r.l. 10.01.25 -31,50".
  Every figure it points at is verified and the amount is right; it is the same prompt behaviour
  a PDF has and it belongs to the sub-agent prompt work (ticket 42), not here.
- A workbook whose header a preset knows imports its first sheet without asking, because the
  sheet picker lives on the mapping card and a preset never shows that card. Written up in
  explainer 16 under "what is not finished".
- The REST endpoints still take CSV, PDF and images only. No screen calls them for a workbook.
