# 21: Review fixes, frontend side

**What to build:** Frontend findings of the headful review of 2026-09-04 (see ../review-2026-09-04.md). Ticket 20 takes the agent and stream side.

**Blocked by:** 06, 09 (merged)

**Status:** ready-for-agent

- [ ] Markdown tables in answers open at the top: no scroll box that starts scrolled past its header; overflow gets a visible scrollbar or fade
- [ ] The reasoning panel has a height cap while streaming and scrolls internally, so the answer is never pushed off screen
- [ ] Tabs survive a profile round trip: switching profiles and back restores the same open tabs and selection
- [ ] Split editor validates the sum in place (Save disabled while the legs do not sum, one number format in the hint and the error)
- [ ] Import success banner is neutral when 0 rows were imported; past imports table does not clip its When column at 1024 wide; Transactions table shows a column affordance when Account and Source are hidden at 1024 wide
- [ ] Filter bar date inputs styled like the shadcn controls next to them
- [ ] Undo card reflects the restored value after Reverted
- [ ] Empty-state suggestions depend on whether the profile has data
- [ ] Accessibility: date filters named, row selects get distinct names, model listbox aria-selected matches the visible choice, real plurals instead of "answer(s)" and "merchant(s)", one accessible name for the model dialog
- [ ] Adjacent reasoning panels with no tool between them fold into one
- [ ] Typecheck and build clean, existing tests green, browser verification of every item in both themes at 1024 and 1440 wide
