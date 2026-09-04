# 24: Headful verification fixes (import page and chart card)

**What to build:** The headful verification of 2026-09-04 (../verification-2026-09-04-watch.md) passed every step but found four things ticket 22 does not cover.

**Blocked by:** 10 (merged)

**Status:** ready-for-agent

- [ ] The Import page resumes pending duplicate decisions: an import with undecided candidates shows them (from GET /api/imports/{id}/duplicates) whenever the page opens or the row in Past imports is clicked, not only right after the commit that produced them; the amber Duplicates cell is a link to that list
- [ ] Reloading /import (or any page) never resets the active profile: the active profile is read from storage before the first query runs, and a missing or deleted profile falls back to the first one explicitly
- [ ] The import banner reflects the state after duplicate decisions (counts update, no stale "0 imported" once rows were kept)
- [ ] A failed chart card never shows the sub-agent's scratch notes or raw code comments: the card shows the error and a one-line note; the code and notes stay behind the details toggle
- [ ] A past import can be deleted with its transactions (confirmation dialog, cascades to its bookings, candidates and decisions), since there is no other way to undo an import into the wrong profile
- [ ] Tests at the HTTP seam for the delete and for pending candidates listing; typecheck and build clean; browser verification of the four items
