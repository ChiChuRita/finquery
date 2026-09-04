# 21: Review fixes, frontend side

**What to build:** Frontend findings of the headful review of 2026-09-04 (see ../review-2026-09-04.md). Ticket 20 takes the agent and stream side.

**Blocked by:** 06, 09 (merged)

**Status:** done

- [x] Markdown tables in answers open at the top: no scroll box that starts scrolled past its header; overflow gets a visible scrollbar or fade
- [x] The reasoning panel has a height cap while streaming and scrolls internally, so the answer is never pushed off screen
- [x] Tabs survive a profile round trip: switching profiles and back restores the same open tabs and selection
- [x] Split editor validates the sum in place (Save disabled while the legs do not sum, one number format in the hint and the error)
- [x] Import success banner is neutral when 0 rows were imported; past imports table does not clip its When column at 1024 wide; Transactions table shows a column affordance when Account and Source are hidden at 1024 wide
- [x] Filter bar date inputs styled like the shadcn controls next to them
- [x] Undo card reflects the restored value after Reverted
- [x] Empty-state suggestions depend on whether the profile has data
- [x] Accessibility: date filters named, row selects get distinct names, model listbox aria-selected matches the visible choice, real plurals instead of "answer(s)" and "merchant(s)", one accessible name for the model dialog
- [x] Adjacent reasoning panels with no tool between them fold into one
- [x] Typecheck and build clean, existing tests green, browser verification of every item in both themes at 1024 and 1440 wide

## Comments

Verified against OpenRouter on `127.0.0.1:8084` with `fixtures/synthetic/sparkasse-2025.csv`
imported through the Sparkasse preset. Every finding was reproduced first, then fixed, then
re-checked in both themes at 1024 and 1440 wide. Screenshots in `/tmp/finquery-21/`
(`repro-*` before, `fix-*` after). Zero console messages and no page errors across the session.

Root causes worth remembering:

- **The table scroll box.** Not our CSS and not the conversation container: streamdown 2.6
  defaults `tableMaxHeight` to 300px, which turns on `overflow-y-auto` on its table body, and
  its own hook pins that box to the bottom on every content change while `isAnimating` is true
  (we pass `isAnimating` for the typing animation). So an answer's table ended its stream parked
  at the bottom, header and top rows out of view. `tableMaxHeight={0}` in `MessageResponse`
  removes the cap and with it the auto-scroll.
- **The dropped tab.** `openTab` derived the new list from React state, which is still empty on
  the render that opens a conversation of a freshly loaded page (the child effect runs before the
  provider effect that hydrates from local storage), and wrote that list back. Every direct load
  of `/c/<id>` therefore wiped the profile's other tabs. Local storage is now the list: each
  change reads it, edits it and writes it back.
- **The second reasoning panel.** A tool part with no card (`remember`) sits between the two
  reasoning parts of one pause and draws nothing, which broke the fold. The fold now skips every
  part that draws nothing, including an empty text part.
- **The model listbox.** cmdk marks its own cursor item `aria-selected`, which starts on the
  first option. The dialog now opens with the cursor on the slot in use (`defaultValue`).

One line outside `frontend/`: `categorize/pipeline.py` built the Question card note with
"merchant(s)". That string is user-visible copy in the card, so it became a real plural there.
