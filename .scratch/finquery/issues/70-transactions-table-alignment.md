# 70: Transactions table: checkboxes, headers and text size off (micro-ticket)

**What to build:** The user saw the Transactions table looking odd on 2026-09-07, the checkboxes
first. Visual review on a throwaway database with the sample year found four things, all in
`frontend/src/components/transactions-table.tsx`: the row checkbox sits above the middle of its
row, the header labels are not over their columns, the cell text is 16px while the rest of the
app and the inline editors are 14px, and the Account column clips "Sparkasse Girokonto" at
1440 wide.

**Blocked by:** nothing

**Status:** done

Decisions:
- The table stays TanStack Table v9 (headless `useTable`) plus TanStack Virtual, rendered as a
  CSS grid with `items-start` so the error line under an input can grow a cell. Keep that. Give
  the 16px checkbox the same 28px box every other control has instead of centring the row.
- Header cells pad like row cells (`px-1`) and inset the label like a read cell (`px-1.5`), so
  header text and the header checkbox line up with the column under them.
- `text-sm` on the table root: the inputs already were, so a cell shrank when clicked.
- Account `minmax(11.5rem, 1fr)`, Enriched title `minmax(8.5rem, 0.8fr)`, table min width 68rem.

- [x] Before and after screenshots in `/tmp/finquery-vr/` (1440 and 1024, dark and light,
      selected rows, an open editor, an expanded split)
- [x] `npm run build` clean, `oxlint` unchanged, geometry measured in the page (see Comments)

## Comments

Done 2026-09-07. Measured with `getBoundingClientRect` on the first rows: before, the row was
36px (28px control plus 4px padding each side) and the checkbox cell 24px, top aligned, so the
box centre sat 6px above the row centre; the header text started 5px left of the cell text
(header `px-1.5` against cell `px-1` plus read button `px-1.5`). After: every cell child is
28px tall at the same top, header and cell left edges match. Checked on 1440x900 and 1024x800,
both themes, with two rows selected, the description editor open, and a split row expanded.
Server on port 8087 with `/tmp/finquery-vr/verify.db`, browser session `vr`, both closed after.
