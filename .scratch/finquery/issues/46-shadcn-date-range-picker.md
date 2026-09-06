# 46: A shadcn date range picker for the Transactions filters (micro-ticket)

**What to build:** The From and to fields in the Transactions filter bar are two native `<input type="date">`. Replace them with the shadcn date picker pattern: a Popover holding a Calendar in range mode, opened from one button that reads the range ("1 Mar 2025 to 31 Mar 2025", "Any date" when empty), with a clear action. Requested by the user on 2026-09-06.

**Blocked by:** none

**Status:** ready-for-agent

Decisions:
- Add the shadcn `calendar` and `popover` components through the repo-local shadcn skill (`npx shadcn add calendar popover` in `frontend/`), which brings `react-day-picker` and `date-fns`. These are the shadcn way and count as the one dependency this ticket may add.
- One reusable component, `frontend/src/components/date-range-picker.tsx`, exporting `DateRangePicker({ from, to, onChange, ... })` over ISO `YYYY-MM-DD` strings (empty string for open ends), so the filter state in `transactions-page.tsx` (`filters.date_from`, `filters.date_to`) does not change shape and the dashboard's range bar (ticket 44) can use the same component later.
- Labels are English, dates are shown the way the rest of the UI shows them (check `lib/format.ts` for the existing date formatter and reuse it), weeks start on Monday, the calendar shows two months side by side at 1024 and up.
- Keyboard and screen reader: the trigger is a button with a name that includes the current range; Escape closes; the clear action is a button.
- The inline date cell in the table and the New transaction dialog keep their native inputs (the cell's Enter and blur behaviour is tuned and the dialog is a single date); the `input[type="date"]` rule in `index.css` stays for them.
- Style stays within the existing filter bar height and tokens; no layout redesign (ticket 45 owns the UI pass).

- [ ] `calendar` and `popover` added through shadcn; `DateRangePicker` component; the filter bar uses it and the filter state, the URL search params (if the filters live there) and the request to the API are unchanged
- [ ] Both themes look right at 1024 and 1440; a headful browser check (named session, own port above 8100, throwaway database with the sample year) shows: open, pick a range, the table filters, clear, reload keeps whatever the filters kept before; screenshots in `/tmp/finquery-46/`
- [ ] `npm run build` clean, oxlint at baseline, `uv run pytest` untouched and green; a short note under Comments
