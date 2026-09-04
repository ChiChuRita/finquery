# 11: PDF and image extraction

**What to build:** A user imports a text PDF bank statement and the transactions appear, with every amount and date literally present in the source text and the statement reconciling (opening balance plus bookings equals closing). Rows that fail a guard are shown in a review step before commit. Scanned PDFs and photos are rendered to images and read by the vision path on the fast slot with the same guards where a total exists. A photo of a bill becomes a new transaction, or, if it matches an existing transaction by amount and date within three days, a proposed split of that transaction into the bill's line items.

**Blocked by:** 08 Import through chat attachments and text, 09 Changesets and edits in chat

**Status:** ready-for-agent

- [ ] Text-layer extraction with pdfplumber; extraction sub-agent points at literal spans; verbatim guard rejects anything not in the text
- [ ] Reconciliation guard when balances are present; flagged rows go to a review card before commit
- [ ] Page rendering with pypdfium2; vision extraction through the fast slot for scans and photos
- [ ] Bill photo flow: line items, total, date, merchant; match to an existing transaction proposes a split changeset, otherwise a new transaction preview
- [ ] Works from the Import page and from chat attachments
- [ ] HTTP-seam tests with the synthetic PDF and bill images and scripted extraction output: verbatim violation is flagged, reconciliation failure is flagged, bill match proposes a split
- [ ] Browser verification with the synthetic PDF and one bill image

## Comments

Real data (2026-09-04): the user added their own Trade Republic export under `fixtures/private/` (gitignored, never shipped, never sent to OpenRouter): the full CSV export (1520 rows, 2024-06 to 2026-09, header `datetime,date,account_type,category,type,...,amount,...,description,counterparty_name,counterparty_iban,payment_reference,mcc_code`) and the 102-page German statement PDF. Both are sliced into shorter frames in `fixtures/private/frames/`: one CSV per quarter, two overlapping CSVs (2025-01 to 04 and 2025-03 to 06) for duplicate testing, and seven PDF frames of a few months each, every PDF frame starting with the account overview page. The Trade Republic CSV preset and the Trade Republic PDF layout must be developed against these files, only on the local provider or with the scripted model. The synthetic dataset stays the shipped fixture.
