# Elective: multimodal ingestion

**Claim.** The same local vision-language models read statement PDFs, scans and receipt
photos; text files, CSV, Excel and Word go through the same import paths; and no extracted
figure is trusted unless code can find it in the source.

## The flow

1. **Route by what the file is.** A PDF with a text layer is read as text (pdfplumber). A scan or
   a photo is rendered to an image (EXIF-rotated first; the real Edeka receipt was sideways).
   CSV and XLSX become rows for the mapping engine; DOCX becomes text; pasted text is text.
2. **Mapping, for tables.** A preset is detected (Sparkasse, Trade Republic, an unknown bank);
   otherwise the model proposes a column mapping and the user confirms it in a Question card.
   Excel cells keep their types, so a German decimal comma cannot be misread.
3. **Extraction, for text and images.** The extraction sub-agent (Gemma 4 with its vision
   projector) reads one page and returns bookings through a forced schema. Pages run with a
   concurrency of four locally.
4. **Verbatim guard.** Every amount and every date the model returns must literally occur in the
   page's text or, for an image, in what the model quoted from it. The model points at digits;
   it never invents them. The year is added by code.
5. **Reconciliation.** For statements with balances: opening balance plus the sum of bookings
   must equal the closing balance to the cent. A gap flags the page.
6. **Review or import.** Anything flagged becomes a review card with the row, the gap and the
   printed line; nothing is written until the user accepts. Clean pages import, then duplicates
   are asked about one by one, and the categorizer files what it can.
7. **Receipts.** A receipt photo becomes a draft booking with item legs (a split), the store
   resolved from the header through the dictionary or, with the switch on, one web lookup.

## What is not covered

Audio. The sheet lists it; we say plainly it is out of scope. We claim images, PDF, text, CSV,
XLSX and DOCX.

## Decisions

- Text layer first, vision only where there is none: cheaper and more exact.
- Two guards rather than trust: a near-duplicate trap in the old repo produced a model error
  that reconciliation caught; that is why both guards exist.
- Excel and Word through the existing paths, not new ones: the mapping engine and the text path
  already carry the guards.

## Numbers

Receipts: 19 of 19 totals right on the real Edeka receipt and 18 web receipts, items 16 of 20
(`.scratch/finquery/reviews/receipts-web-2026-09-05.md`). The synthetic statement PDF reconciles
to the cent (tests). The XLSX fixture imported 433 of 433 rows with the preset recognized without
a model call (ticket 58).

## Say

"A vision model reads the page, and code verifies every digit it returns against the source.
Anything it cannot point at goes to a review card, never into the database."
