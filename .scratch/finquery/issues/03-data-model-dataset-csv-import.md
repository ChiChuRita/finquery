# 03: Data model, synthetic dataset and CSV import page

**What to build:** A user opens the Import page, drops a CSV export from a German bank, sees the first parsed rows in a preview with the column mapping and formats editable, confirms, and the transactions appear in the profile. Known banks (Sparkasse, DKB, ING, N26, comdirect, Trade Republic) map instantly by header; anything else gets a mapping proposed by the fast slot from the header and five sample rows. The profile starts with about fifteen default categories with subcategories. A generator produces the shipped synthetic German household year (CSV, a Sparkasse-layout text PDF, a few bill images) that tests and the demo use.

**Blocked by:** 01 Walking skeleton

**Status:** ready-for-agent

- [ ] Schema: accounts, transactions (with fingerprint, enrichment fields, source, optional parent for splits), categories and subcategories, category rules, imports; every table profile-scoped; split children must sum to the parent and a query view excludes split parents
- [ ] Default taxonomy seeded on profile creation
- [ ] Synthetic dataset generator producing one canonical year with salary, rent, groceries at several chains, transport, subscriptions, PayPal to friends, Amazon, plus the PDF and bill images; committed output in fixtures
- [ ] CSV reader handles German decimal commas, DD.MM.YYYY, separate debit and credit columns, semicolon separators and encodings; presets for the six named banks
- [ ] Mapping proposal by the fast slot through a forced single tool, shown in the Import page preview and editable before commit
- [ ] Import record stores mapping, counts and file name; the Import page lists past imports
- [ ] HTTP-seam tests: preset import of the synthetic CSV, model-proposed mapping with a scripted model, rejection of a malformed file
- [ ] Browser verification of the full Import page flow
