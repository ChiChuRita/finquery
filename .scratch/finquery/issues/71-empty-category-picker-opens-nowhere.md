# 71: Category picker of a Needs review row opens nowhere (micro-ticket)

**What to build:** The user reported on 2026-09-07 that clicking "Needs review" in a row's
Category cell offers nothing to select. Reproduced on the sample year: the list is in the DOM
with all categories, but it is positioned below the viewport (y = 900 on a 900px window), so
the user sees only the trigger focus and nothing to click. Rows with a category work.

**Blocked by:** nothing

**Status:** done

Decisions:
- Root cause: Radix Select's default `position="item-aligned"` anchors the open list on the
  trigger's value node (`SelectValue`). `PickerCell` renders the placeholder in that slot when
  the value is null (so an empty cell reads "Needs review" or a dash instead of the clear
  item's words), so there is no value node and the list is never placed.
- Fix: `position="popper"` on the `SelectContent` of `PickerCell` (`transaction-cells.tsx`),
  the list anchors to the trigger. One line plus a comment. The placeholder rendering stays,
  and every other Select in the app renders `SelectValue` and is not affected.
- Not the chat's job: the chat can recategorize too, but the table cell is meant to work.

- [x] Reproduced and fixed headful (port 8093, session `vr3`), screenshots in
      `/tmp/finquery-vr3/` (`open.png` before: nothing visible; `open-fixed.png` after)
- [x] Picking "Health" on a Needs review row sends one PATCH and the cell shows Health
- [x] `npm run build` clean, lint unchanged

## Comments

Done 2026-09-07. Measured with `getBoundingClientRect` on the open list wrapper: before
`[0, 900, 144, 485]` with no top or left set, after `[860, 544, 144, 288]` under the trigger.
Categorized rows were never affected because their trigger carries a value node.
