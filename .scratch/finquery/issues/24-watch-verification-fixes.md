# 24: Import page becomes an overview, plus verification fixes

**What to build:** The headful verification of 2026-09-04 (../verification-2026-09-04-watch.md) passed every step but found four things ticket 22 does not cover.

**Blocked by:** 10 (merged)

**Status:** ready-for-agent

- [ ] The Import page is an overview only: no drop zone, file input, mapping preview, review table or duplicate decisions on the page. Per past import it shows file, kind, account, when, rows read, imported, duplicates found and undecided, reconciliation, needs review, and a Delete action. Undecided candidates or pending review get a "Continue in chat" link to the conversation the import came from, or a review conversation created through the existing endpoint. Empty state and sidebar copy say to drop a statement into the chat (user decision 2026-09-05, see spec Amendments)
- [ ] Reloading /import (or any page) never resets the active profile: the active profile is read from storage before the first query runs, and a missing or deleted profile falls back to the first one explicitly
- [ ] A failed chart card never shows the sub-agent's scratch notes or raw code comments: the card shows the error and a one-line note; the code and notes stay behind the details toggle
- [ ] A past import can be deleted with its transactions (confirmation dialog, cascades to its bookings, candidates and decisions), since there is no other way to undo an import into the wrong profile
- [ ] Tests at the HTTP seam for the delete and for pending candidates listing; typecheck and build clean; browser verification of the four items
