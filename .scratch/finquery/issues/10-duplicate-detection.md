# 10: Duplicate detection

**What to build:** When an import would insert a transaction that matches an existing one exactly (same account, date, amount and normalized description) or nearly (same amount within two days and a similar description), nothing is inserted silently. The import result lists every candidate and the assistant asks about each in the chat with Keep both or Remove. The import summary shows how many were kept and removed.

**Blocked by:** 08 Import through chat attachments and text

**Status:** ready-for-agent

- [ ] Fingerprint and near-match detection at commit time for every ingestion path
- [ ] Candidates held aside, asked one card at a time through `ask_user`, applied per answer
- [ ] Import record stores duplicate decisions
- [ ] HTTP-seam tests: re-importing the same CSV asks about every row, a near match by date shift is detected, Keep both inserts
- [ ] Browser verification of a double import
