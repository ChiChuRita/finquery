# 31: Edge cases, data and input

**What to build:** Hunt for edge cases in everything that takes data or input, fix each at the root with a test, and polish the message the user sees when something is refused. Requested 2026-09-05 after the end-to-end run.

**Blocked by:** 30 (merged)

**Status:** ready-for-agent

Cases to cover at least (add what you find):
- CSV: empty file, header only, 10k rows, duplicate header names, semicolon and comma and tab, cp1252 and utf-8 with BOM, quoted fields with line breaks, thousands separators, plus and minus and parentheses for sign, separate debit and credit both filled, dates at year boundaries and two-digit years, zero amounts, very long descriptions, emoji and control characters, a description that looks like SQL or a prompt injection
- Chat input: empty message, whitespace only, 20k characters pasted, a message during a running turn (409 and what the UI shows), Stop pressed immediately after send, two tabs sending at once
- Attachments: over the size limit, unsupported type, a renamed file with the wrong extension, a corrupted PDF, a PDF with no text layer (scanned) forcing the vision path, an image that is not a receipt, a non-EUR receipt, a photo of several receipts
- Data operations: deleting a category in use (rows fall back to Needs review), merging a category into itself, splitting a split parent, splitting into one leg, undo twice, applying a stale changeset, applying a discarded one, deleting a profile with open conversations and tabs, deleting the last profile, deleting an import whose rows were split or recategorized
- Web lookup: a merchant that is a person's name (refused whole), a merchant with digits only, rate limit or network failure from the search backend (clean message, no crash, logged), the switch flipped off mid-loop
- Every refusal reaches the user as one plain sentence saying what to do; nothing surfaces as a raw exception, a 500 or an empty card

- [ ] Each case above tried through the real product (browser or the HTTP seam) and recorded in a table with outcome before and after
- [ ] Every defect fixed at the root with an HTTP-seam test; refusal copy polished; suite green; typecheck and build clean; zero console errors during the browser runs
