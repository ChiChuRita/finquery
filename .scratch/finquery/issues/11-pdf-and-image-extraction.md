# 11: PDF and image extraction

**What to build:** A user imports a text PDF bank statement and the transactions appear, with every amount and date literally present in the source text and the statement reconciling (opening balance plus bookings equals closing). Rows that fail a guard are shown in a review step before commit. Scanned PDFs and photos are rendered to images and read by the vision path on the fast slot with the same guards where a total exists. A photo of a bill becomes a new transaction, or, if it matches an existing transaction by amount and date within three days, a proposed split of that transaction into the bill's line items.

**Blocked by:** 08 Import through chat attachments and text, 09 Changesets and edits in chat

**Status:** done

- [x] Text-layer extraction with pdfplumber; extraction sub-agent points at literal spans; verbatim guard rejects anything not in the text
- [x] Reconciliation guard when balances are present; flagged rows go to a review card before commit
- [x] Page rendering with pypdfium2; vision extraction through the fast slot for scans and photos
- [x] Bill photo flow: line items, total, date, merchant; match to an existing transaction proposes a split changeset, otherwise a new transaction preview
- [x] Works from the Import page and from chat attachments
- [x] HTTP-seam tests with the synthetic PDF and bill images and scripted extraction output: verbatim violation is flagged, reconciliation failure is flagged, bill match proposes a split
- [x] Browser verification with the synthetic PDF and one bill image

## Comments

Real data (2026-09-04): the user added their own Trade Republic export under `fixtures/private/` (gitignored, never shipped, never sent to OpenRouter): the full CSV export (1520 rows, 2024-06 to 2026-09, header `datetime,date,account_type,category,type,...,amount,...,description,counterparty_name,counterparty_iban,payment_reference,mcc_code`) and the 102-page German statement PDF. Both are sliced into shorter frames in `fixtures/private/frames/`: one CSV per quarter, two overlapping CSVs (2025-01 to 04 and 2025-03 to 06) for duplicate testing, and seven PDF frames of a few months each, every PDF frame starting with the account overview page. The Trade Republic CSV preset and the Trade Republic PDF layout must be developed against these files, only on the local provider or with the scripted model. The synthetic dataset stays the shipped fixture.

Done 2026-09-04. Structure, for ticket 10 and for anything that reads a document later:

- **`src/finquery/extract/` is the reader.** `pdf.py` (pdfplumber words grouped back into the
  printed lines, pypdfium2 rendering a page at 150 dpi, Pillow shrinking a photo to 1600 px),
  `layouts.py` (the Sparkasse and Trade Republic page layouts, their hints and their printed
  balance labels), `subagent.py` (the extraction sub-agent: `read_statement` for a page,
  `read_bill` for a receipt, both forced single tools), `guards.py` (the two guards),
  `statement.py` (the pipeline and `commit_extraction`), `review.py` (the card and its applier),
  `bill.py` (the receipt flow). ADR 0011 is the design.
- **The sub-agent returns spans, never figures.** A row is `date_text`, `amount_text`,
  `direction`, `description`, `counterparty`, `balance_text` and the `line` number it stands on.
  The cents are parsed from those spans in `guards.to_rows`, so the number that lands is the
  number that was printed, and the verbatim guard is a substring check rather than a judgement.
  A date is the one exception: Trade Republic prints the day and the year on different lines, so
  a date passes if the whole span is printed or if every digit group of it appears within two
  lines of the one it was read from.
- **The reconciliation guard walks the running balance** (`guards.reconcile`): row by row, per
  page and over the whole statement, against the printed opening and closing balances only when
  the layout says they cover these pages. Trade Republic declares none, because every frame of
  that export starts with a `KONTOÜBERSICHT` of the whole export. The chain also decides the
  direction where the layout cannot: an amount whose size matches the balance move and whose
  sign does not is corrected in code and counted in `directions_fixed`. A misread balance breaks
  the chain twice and cancels out in the sums, so the "Reconciled" line names any row that is
  still flagged.
- **The review step.** `Extraction.needs_review` is any flagged row or a reconciliation that is
  not `ok`. On the Import page that is `components/extraction-review.tsx` (accept, edit and drop
  per flagged row, the verdict banner, a preview of what would be imported). In a chat it is
  `extract.review.review_card`, an `ask_user` card with `ApplyKind` `extraction_review`: up to
  four flagged rows with Accept and Drop, one more row standing for the rest, and a single
  "import it anyway" row when the statement did not add up but no single row did.
- **`finquery.answers.resolve_answers` is async now**, and an applier takes one `Answered`
  (session, profile, conversation, rows, answers, `resolve_model`, `model_settings`) instead of
  four positional arguments. It had to be: committing an extraction categorizes what it wrote.
  **Ticket 10 adds its duplicate applier as `APPLIERS["duplicate_decision"]` taking that same
  `Answered`**, and its duplicate step belongs inside `ingest.commit.commit_rows`, which is the
  single commit every reader now ends at (CSV, statement PDF, the accepted rows of a review).
- **Two endpoints**, because reading a PDF costs a model call per page and must not happen
  twice: `POST /api/imports/extract` (multipart, returns the rows with their flags, the layout
  and the verdict) and `POST /api/imports/extracted` (JSON, commits the reviewed rows). The
  second one recomputes the reconciliation over exactly the rows it was given, so
  `Import.reconciliation` is always the server's arithmetic and never a client's claim: a row
  the user dropped leaves a hole in the running balance and the record says so.
- **In chat, `import_file` routes on the attachment kind**: CSV as before, PDF to the statement
  reader, image to the bill reader. A photo dropped into a chat is a till receipt; a photo of a
  statement page belongs on the Import page, where it is read as a page. The extraction is
  stored on `Attachment.extraction_json` (new column) between the card and its answer, exactly
  as a proposed CSV mapping is, so the rows that are committed are the rows the user saw.
- **The bill flow.** `check_bill` adds the line items up and holds them to the printed total.
  `find_match` looks for money out of the same amount within three days that is neither a leg of
  a split nor already split. A match becomes `ChangesetIntent(kind="split", ...)` whose legs are
  the line items grouped by the categorizer sub-agent's guess (one leg per item when they all
  land in one category), proposed through `changesets.propose` and rendered by the existing
  changeset card inside the `import_file` step (`ChangesetProposal` is exported for that). No
  match becomes a `transaction_draft` and the same preview card ticket 08 built.
- **Statuses `import_file` can now return**: `imported`, `extraction_review`, `bill_split`,
  `bill_draft`, `bill_matched`, `nothing_found`, `extraction_failed`, plus the ones it had.
  `extraction_not_ready` is gone. `lib/api.ts` and `import-tool.tsx` render them; no new chat
  tool was needed, so `ChatTools`, the `chat-view.tsx` branch, `SILENT`, `MUTATING_TOOLS` and
  `WRITING_PARTS` needed no change.
- **New dependencies**: `pdfplumber` (text and words with positions), `pypdfium2` (rendering,
  already a dependency of pdfplumber) and `pillow`, which moved from the dev group into the
  runtime dependencies because pypdfium2's bitmap needs it to become a PNG. `pymupdf` stays out:
  it is AGPL.
- **Requests per turn**: one fast-slot call per page of a statement, four in flight at once,
  then the categorizer and the usual follow-up and distillation steps. A receipt is one vision
  call plus one categorizer call for its line items. An answered review card costs one chat
  request, because the commit and the categorization happen in the applier.
- **The test context budget went from 3400 to 3600 tokens.** The system prompt is 2300 tokens
  with the two paragraphs this ticket adds, and the floor a compressed prompt cannot go below,
  measured the way ticket 20 measured it, is 3208. Fourth ticket to move this constant.
- Tests: `tests/test_extraction.py` adds 7. The scripted fast slot there is not a canned answer:
  it reads the numbered lines out of the prompt the sub-agent was given and answers with the
  bookings it finds, so the tests run the real shipped statement through the real pipeline, and a
  guard is tested by asking that reader to misread one specific booking (an amount rendering that
  is not on the page, a row left out). The Trade Republic test skips when `fixtures/private/` is
  absent. `uv run pytest` is 130 passed, 1 skipped. `npx tsc --noEmit`, `npm run build` and
  `oxlint` are clean.
- One ticket 08 test changed: the PDF attachment no longer answers with the "not ready" sentence,
  so it now pins the half that is still that ticket's (the bytes are stored, the chip links to
  them, the file reaches the reader).

Verified on OpenRouter on port 8086 and 8087 with a throwaway database, on the real fast model:

- **The synthetic PDF on the Import page**: 15 pages, 433 of 433 bookings, **131 seconds** with
  four pages in flight at once, 0 flagged. Every date and amount matches the shipped CSV of the
  same year exactly (433 of 433, no missing row, no extra one, no misread figure), and the
  statement reconciles: "opening balance plus 433 bookings equals the closing balance (4.210,55 +
  5.699,01 = 9.909,56)". Committing wrote 433 rows into Sparkasse Girokonto, the Import record
  keeps that line, the past imports list shows it, and the merchants categorization was unsure
  about opened a review conversation, the same as after a CSV import.
- **A bill photo in chat**: `bill-edeka-2025-03-14.png` dropped on the composer with "here is the
  receipt for this payment". The vision path read all seven line items and the printed total,
  they add up, and it matched the -20,73 EUR EDEKA booking of 14.03.2025. The categorizer grouped
  the items into three legs (Groceries > Supermarket -6,97, Groceries > Bakery -2,49, Groceries >
  Drugstore -11,27) and the changeset card came up inside the import step with Apply and Discard.
  The model's answer said it had proposed the split, not made it. Apply wrote the three legs, and
  the transactions view shows them instead of the parent, summing to -20,73.
- **A bill that matches nothing**: the same receipt dropped again in a new chat. The booking it
  matched is now split, so `find_match` passes it over, and the receipt became a preview card
  ("Add this transaction? EDEKA Sander, Cash, -20,73 EUR"). Confirm wrote it as a manual booking
  and categorized it Groceries > Supermarket.
- **The vision path on a page with no text layer**: page 1 of the same statement rendered to PNG
  and dropped on the Import page. 22 seconds, read as an image, 28 bookings with their running
  balances, and the opening the guard used was the first row's balance minus its own amount
  (4.210,55, correct) rather than anything printed. An earlier run of the same page read only 12
  of the bookings, and the guard caught it: the chain broke, the row after the hole was flagged
  and the verdict named the 500,86 EUR difference. A deliberately bad 70 dpi render misread one
  balance and produced the review table with two flagged rows, each with its reason ("The balance
  moves by -1.145,00 but the amount reads -1.150,00") and Accept, Edit and Drop.
- Screenshots: /tmp/finquery-11/.

Real data on the local provider (Gemma 4 E4B through llama.cpp, nothing left the machine): the
layout detector recognizes a Trade Republic frame from its page header with no model at all, and
the columns mapping and hints are the ones the OpenRouter runs used. The extraction itself did
not produce rows locally: three pages of a frame took 6 minutes and ended with "Prompt exceeds
n_ctx: 25035 > 16384", although the page prompt itself is only 1.438 tokens by the model's own
tokenizer (2.268 for a denser Sparkasse page, measured with `llama.tokenize`). So it is not the
page that does not fit, it is what the model generates plus the retry that follows: the same
runaway generation ticket 20 saw at the Question card boundary. What this means for ticket 17:
**the demo's PDF import runs on OpenRouter, or on local only after that generation is bounded**
(a `max_tokens` for this sub-agent, or fewer lines per call). An extraction that comes back empty
now says why, because the page's own error is passed through instead of "it may not be a bank
statement".
