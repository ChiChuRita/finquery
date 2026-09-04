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
