# 10: Duplicate detection

**What to build:** When an import would insert a transaction that matches an existing one exactly (same account, date, amount and normalized description) or nearly (same amount within two days and a similar description), nothing is inserted silently. The import result lists every candidate and the assistant asks about each in the chat with Keep both or Remove. The import summary shows how many were kept and removed.

**Blocked by:** 08 Import through chat attachments and text

**Status:** ready-for-agent

- [ ] Fingerprint and near-match detection at commit time for every ingestion path
- [ ] Candidates held aside, asked one card at a time through `ask_user`, applied per answer
- [ ] Import record stores duplicate decisions
- [ ] HTTP-seam tests: re-importing the same CSV asks about every row, a near match by date shift is detected, Keep both inserts
- [ ] Browser verification of a double import

## Comments

Real data (2026-09-04): the user added their own Trade Republic export under `fixtures/private/` (gitignored, never shipped, never sent to OpenRouter): the full CSV export (1520 rows, 2024-06 to 2026-09, header `datetime,date,account_type,category,type,...,amount,...,description,counterparty_name,counterparty_iban,payment_reference,mcc_code`) and the 102-page German statement PDF. Both are sliced into shorter frames in `fixtures/private/frames/`: one CSV per quarter, two overlapping CSVs (2025-01 to 04 and 2025-03 to 06) for duplicate testing, and seven PDF frames of a few months each, every PDF frame starting with the account overview page. The Trade Republic CSV preset and the Trade Republic PDF layout must be developed against these files, only on the local provider or with the scripted model. The synthetic dataset stays the shipped fixture.
