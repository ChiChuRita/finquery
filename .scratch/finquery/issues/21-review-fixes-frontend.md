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

Merged into main on 2026-09-04 on top of 01 to 09, 12 to 16, 18, 19 and 20. What changed in the
merge:

- **`foldReasoning`'s allowlist had to be turned round, and that was the one real bug.** This
  ticket's `DRAWN` set names the nine part types that were renderable on its base, and
  `foldReasoning` filters the message's parts through it, so a part not in the set does not just
  fail to break the fold, it never reaches the renderer. On main there are six more that draw:
  `file` (the attachment chip), `tool-import_file`, `tool-extract_transaction`,
  `tool-add_transaction`, `tool-lookup_merchant`, and `tool-remember`, which ticket 20 gave a
  visible step of its own after this ticket had used it as the example of a part that draws
  nothing. All six would have disappeared from the transcript. It is now a `SILENT` set of the
  four parts that render nothing here (`data-context`, `data-followups`,
  `data-import_progress`, `step-start`) plus an empty text part, with a comment saying why that
  way round: a tool left out of an allowlist vanishes, while a silent part left out of a
  denylist only costs one extra thinking panel, and a tool added later is visible by default.
- `import-page.tsx`'s categorization line is the union: this ticket's neutral sentence when 0
  rows were imported, ticket 14's `by_lookup` and lookup counters, and `merchant(s)` turned into
  a real plural (`lookedUp`) the way the rest of this ticket does it.
- The one Python line survived intact: `categorize/pipeline.py`'s Question card note counts
  merchants properly, next to ticket 20's `apply=AskApply()` on the same card.
  `categorize/subagent.py` still says "merchant(s)", correctly: that string is a prompt to the
  model, not copy.
- `uv run pytest` is 123 passed, 1 skipped. `npx tsc --noEmit`, `npm run build` and `oxlint` are
  clean.
- Verified on OpenRouter on port 8077 with a throwaway database and the Sparkasse preset (433
  rows), in both themes at 1024 and 1440 wide, on one turn that answered with a markdown table
  and a chart:
  - The table opens at its header with no scroll box, at both widths and in both themes.
  - The chart card carries Regenerate and thumbs from ticket 15 and re-rendered in the light
    palette on the theme switch.
  - The thinking panel is capped while the turn runs: `clientHeight` 224 with the cap class on,
    measured mid-stream.
  - Switching to a second profile and back restored the open tab and its selection, and the URL
    with it.
  - The Question card renders with its four merchants, real plurals ("Send answers", "6
    bookings"), and named free-text fields.
  - The Transactions page at 1024 shows the "Scroll for more columns" pill and the date filters
    styled like the selects beside them.
  - Zero console messages and no page errors for the whole session.
  Screenshots: /tmp/finquery-merge21/.
