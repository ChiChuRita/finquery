# 19: Transactions page freezes when adding a split leg after an inline edit

**What to build:** On the Transactions page, editing a cell inline and then expanding that row and clicking Add a leg pegs a core and freezes the page with no console error. Reproduced on the ticket 04 commit itself. The likely cause is the virtualizer re-measuring the expanded row while its height changes and oscillating against the offsets it feeds back. The page must stay responsive through inline edits, expansion and leg editing in any order.

**Blocked by:** 04 Transactions page (merged)

**Status:** ready-for-agent

- [ ] Root cause found and fixed (not a debounce); expanded rows and the split editor no longer feed a measure loop
- [ ] Browser verification: inline edit, expand, add and remove legs, save, collapse, repeated in both orders, with CPU staying idle
- [ ] Existing transactions tests still pass; a regression test at the HTTP seam is not possible for a render loop, so the browser check is the check
