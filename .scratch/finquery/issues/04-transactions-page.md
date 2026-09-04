# 04: Transactions page

**What to build:** A user opens Transactions and sees every row of the profile in a fast virtualized table: date, description, enriched title, amount, category, subcategory, account, source. Filters for text, date range, category, account and Needs review narrow it down. Clicking a cell edits it inline. Expanding a row shows its splits, which can be added, edited and removed while the children always sum to the parent. Selecting many rows offers recategorize and delete. A transaction can be added manually.

**Blocked by:** 03 Data model, synthetic dataset and CSV import page

**Status:** done

- [x] Paginated or virtualized listing endpoint with the filters; table scrolls smoothly with ten thousand rows
- [x] Inline edit of date, description, amount, category, subcategory, account with optimistic update and validation errors shown in place
- [x] Split editor in the expanded row enforcing the sum; parents render with a split badge
- [x] Bulk select with recategorize and delete, with confirmation for delete
- [x] Manual add form
- [x] HTTP-seam tests for filters, inline edit validation, split sum enforcement, bulk operations
- [x] Browser verification with the synthetic dataset loaded

## Comments

Done 2026-09-04. Structure for the next tickets:

- `GET /api/transactions` gained the filters (`q`, `date_from`, `date_to`, `category_id`,
  `account_id`, `needs_review`) plus `include_parents`. Default (false) keeps the split-aware
  row set of `transaction_view`: children, never a parent. The page asks for `include_parents=true`,
  which lists parents with a `split_count` and hides their children, because they are edited
  under the expanded row. Both modes read the base tables, since editing needs the ids the view
  joins away.
- New endpoints in `api/transactions.py`: `POST /api/transactions` (manual, source `manual`),
  `PATCH /api/transactions/{id}` (only the fields sent are applied, so `category_id: null` means
  Needs review), `GET` and `PUT /api/transactions/{id}/splits` (the PUT replaces the whole set of
  legs: with an id it is edited, without one added, a missing id removed, `[]` unsplits),
  `POST /api/transactions/bulk-recategorize` and `POST /api/transactions/bulk-delete`.
- Refusals are 400 with a readable `detail`, mapped once in the app factory for both
  `TransactionEditError` (taxonomy or profile says no) and `SplitSumError` (ADR 0005's session
  guard). No endpoint catches them. The cell that caused one shows it in place.
- Every writer validates before it mutates: a query in between would autoflush a half-written
  split and the guard would judge a state nobody asked for.
- Frontend: `components/transactions-page.tsx` (filters, selection, the optimistic patch,
  bulk actions), `transactions-table.tsx` (TanStack Table v9 `useTable` plus
  `@tanstack/react-virtual`, virtualizing over the whole result with placeholder rows),
  `transaction-cells.tsx` (click to edit, Enter or blur saves, Escape gives up, the refusal
  shows under the cell), `split-editor.tsx`, `transaction-dialogs.tsx` (manual add, delete
  confirmation). Route `/transactions`, sidebar link above Import.
- Ten thousand rows: the listing answers in 7 ms for the first page and 22 ms at offset 9000;
  the table scrolls to the bottom of 9998 rows instantly and fills the pages it lands on
  (500 rows per request) in well under a second.
- Tests: 20 total (`tests/test_transactions.py` adds 5), all at the HTTP seam.
- Screenshots of the verification: /tmp/finquery-04/.
- For ticket 09 (changesets): the mutation endpoints are the apply path. `_resolve_taxonomy`,
  `_resolve_account`, `replace_splits` and the two bulk endpoints are the deterministic code a
  changeset needs, and `TransactionEditError` is the shape a preview should refuse with.
