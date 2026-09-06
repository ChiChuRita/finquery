# 58: XLSX and DOCX ingestion, and the multimodal elective explainer

**What to build:** Excel workbooks (.xlsx) and Word documents (.docx) go through the same chat composer path as CSV, PDF and images: an XLSX sheet becomes rows for the existing CSV mapping engine (the model proposes the mapping, the user confirms in a Question card), a DOCX becomes text for the existing pasted-text and text-layer path (extraction sub-agent with the verbatim guard). The multimodal elective is now claimed, so the explainer and the checklist say what is covered (images, PDF, text, CSV, XLSX, DOCX through inherently multimodal local models) and what is not (audio). Decided by the user on 2026-09-06.

**Blocked by:** 05, 06, 11, 22 (merged)

**Status:** ready-for-agent

Decisions, settled:
- Libraries: `openpyxl` for XLSX (read-only, values not formulas, the first sheet by default and a sheet picker in the mapping card only when there is more than one non-empty sheet), `python-docx` for DOCX (paragraphs and table cells in document order, joined as text). Both are parsing libraries, allowed by the course; add them to `pyproject.toml` and lock.
- XLSX rows feed `ingest/csv_reader` as if they were a delimited file: header detection, preset detection and `mapping_for` reuse; numbers keep their cell type (a float amount is not re-parsed from a string); dates come from cell datetimes when present, otherwise through the existing date parsing. Empty rows and a leading title block above the header are skipped the way the edge-case CSVs are (tickets 31, 32).
- DOCX text takes the pasted-text path: `extract_transaction`-style extraction over the text with the verbatim guard and the extraction review card, and a statement-shaped document (many bookings) goes through the statement extraction with reconciliation when balances appear. Formatting is dropped; tables keep their cell order so an amount stays on its booking's line.
- Composer: the attachment picker accepts `.xlsx` and `.docx`; the attachment chip shows the kind; the Import page's overview lists the new kinds. Size limits as for CSV and PDF. Audio, images inside DOCX and macros are ignored with a one-line note in the answer.
- Fixtures: `fixtures/synthetic/sparkasse-2025.xlsx` generated from the CSV by `scripts/generate_synthetic.py` (deterministic), and `fixtures/synthetic/statement-excerpt.docx` with about fifteen bookings and a balance line; both small, committed.
- Docs: `docs/explainers/16-elective-multimodal-ingestion.md` in the style of the other explainers (claim, how it works with the vision path and the guards, code path, model in and out of the loop, guards, measurements from tickets 22 and 24 and the receipts review, what to say, grader questions, what is not covered: audio), `docs/explainers/README.md` and the checklist row for multimodal set to claimed (the coordinator updates the checklist's preference row), CONTEXT.md if a term is new, demo script step for an XLSX drop.

- [ ] XLSX through the mapping engine with the fixture; multi-sheet picker only when needed; tests at the HTTP seam (import, mapping card, confirm, rows in the table, numbers and dates exact)
- [ ] DOCX through the text path with the fixture; tests (extraction with the verbatim guard, the review card, a statement-shaped document reconciled)
- [ ] Composer and Import page accept and label the two kinds; build clean
- [ ] Explainer 16, README index, checklist row, demo step; `uv run pytest` green; headful browser verification (named session, own port above 8100, throwaway database, Qwen on both cloud slots, few turns): the XLSX drop to imported rows, the DOCX drop to a review card, both themes; screenshots in `/tmp/finquery-58/`; Comments
