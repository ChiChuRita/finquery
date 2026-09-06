# 46: A shadcn date range picker for the Transactions filters (micro-ticket)

**What to build:** The From and to fields in the Transactions filter bar are two native `<input type="date">`. Replace them with the shadcn date picker pattern: a Popover holding a Calendar in range mode, opened from one button that reads the range ("1 Mar 2025 to 31 Mar 2025", "Any date" when empty), with a clear action. Requested by the user on 2026-09-06.

**Blocked by:** none

**Status:** done

Decisions:
- Add the shadcn `calendar` and `popover` components through the repo-local shadcn skill (`npx shadcn add calendar popover` in `frontend/`), which brings `react-day-picker` and `date-fns`. These are the shadcn way and count as the one dependency this ticket may add.
- One reusable component, `frontend/src/components/date-range-picker.tsx`, exporting `DateRangePicker({ from, to, onChange, ... })` over ISO `YYYY-MM-DD` strings (empty string for open ends), so the filter state in `transactions-page.tsx` (`filters.date_from`, `filters.date_to`) does not change shape and the dashboard's range bar (ticket 44) can use the same component later.
- Labels are English, dates are shown the way the rest of the UI shows them (check `lib/format.ts` for the existing date formatter and reuse it), weeks start on Monday, the calendar shows two months side by side at 1024 and up.
- Keyboard and screen reader: the trigger is a button with a name that includes the current range; Escape closes; the clear action is a button.
- The inline date cell in the table and the New transaction dialog keep their native inputs (the cell's Enter and blur behaviour is tuned and the dialog is a single date); the `input[type="date"]` rule in `index.css` stays for them.
- Style stays within the existing filter bar height and tokens; no layout redesign (ticket 45 owns the UI pass).

- [x] `calendar` and `popover` added through shadcn; `DateRangePicker` component; the filter bar uses it and the filter state, the URL search params (if the filters live there) and the request to the API are unchanged
- [x] Both themes look right at 1024 and 1440; a headful browser check (named session, own port above 8100, throwaway database with the sample year) shows: open, pick a range, the table filters, clear, reload keeps whatever the filters kept before; screenshots in `/tmp/finquery-46/`
- [x] `npm run build` clean, oxlint at baseline, `uv run pytest` untouched and green; a short note under Comments

## Comments

Done 2026-09-06. `npx shadcn add calendar popover` brought `react-day-picker` 10 and
`date-fns` 4; nothing else was added. `DateRangePicker` takes and returns ISO strings, so
`filters.date_from` and `filters.date_to` keep their shape, `lib/api.ts` builds the same
request, and the filters still live in component state (the page has no search params, so a
reload drops them, exactly as the two native inputs did).

The trigger reads the range through `formatDate`, which is German (`01.12.2025 to
24.12.2025`), not the `1 Mar 2025` spelling the ticket's opening line sketched: the decision
below it says to reuse the existing formatter, and the table's date column reads the same way.
Labels around it stay English, weeks start on Monday, two months side by side, and the clear
action is a "Clear dates" button inside the popover, disabled when there is nothing to clear.
The bar's own Clear button still resets every filter.

Browser check on ports 8177 (API) and 8178 (Vite) against a throwaway database with the sample
year, headful, session `ticket46`: the popover opens, 1 December then 24 December 2025 filters
the table to 33 rows, "Clear dates" puts the trigger back to "Any date", Escape closes it, and
a reload leaves the filters empty as before. Screenshots in `/tmp/finquery-46/`, both themes at
1024 and 1440; at 1024 the bar wraps the way it already did and the two months still fit. No
console errors.

One thing worth knowing: react-day-picker returns `{ from, to }` with both ends on the first
click, so the range is briefly a single day and the table refetches once before the second
click widens it.

`npm run build` clean, oxlint unchanged at 41 warnings with nothing from the new or edited
files, `uv run pytest` 326 passed and 4 skipped.
