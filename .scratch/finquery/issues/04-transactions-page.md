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

Merged into main on 2026-09-04 on top of 01, 02, 03, 05, 13 and 16. What changed in the merge:

- 04 branched before 02's profile scoping landed, so every endpoint in `api/transactions.py`
  was rescoped from the ambient profile (`app.state.profile_id`, which no longer exists) to an
  explicit one, the same convention conversations and imports use: reads take `profile_id` as a
  required query parameter (`GET /api/transactions`, `GET /api/transactions/{id}/splits`,
  `GET /api/accounts`), writes carry it in the body (`profile_id` is a required field on
  `TransactionIn`, `TransactionPatch`, `SplitsIn`, `BulkRecategorize`, `BulkDelete`). An unknown
  profile is a 404 through `get_profile_or_404`, and a transaction of another profile is a 404
  too, because `_get` already looks the row up by `(profile_id, id)`. The bulk endpoints filter
  by profile, so ids outside it are simply not there: `{"updated": 0}`, `{"deleted": 0}`.
  `profile_id` is stripped from the patch dump (`exclude={"profile_id"}`), so it can never be
  mistaken for a field to write.
- The listing is 04's filtered version over the base tables, not 02's `transaction_view` query.
  `include_parents=false` still answers with the view's row set (children, never a parent), so
  ticket 03's import test and ticket 05's sub-agent see what they saw before.
- The app factory is the union: every router (profiles, conversations, chat, memories, imports,
  transactions, taxonomy, models) plus 04's one handler for `TransactionEditError` and
  `SplitSumError`, registered before the routers.
- Frontend: `lib/api.ts` is the union of 13's `ChatMetadata`/`ChatDataParts`/`ChatTools` typing,
  the memory and import queries and 04's transaction queries and mutations, all profile-scoped
  after `importsQuery(profileId)`: the query key carries the profile, the query is enabled once
  it is known, and mutations take it as their first argument. One error helper survived, 04's
  `problem()`, because it also unwraps FastAPI's validation list into the sentence a cell shows,
  and it kept HEAD's 204 handling for the deletes. `transactions-page.tsx`, `split-editor.tsx`
  and `transaction-dialogs.tsx` read the active profile from `useWorkspace()` the way
  `import-page.tsx` and `memory-page.tsx` do. `routes.tsx` and `app-sidebar.tsx` keep every
  route and link of both sides: index, conversation, transactions, import, memory, settings,
  with Transactions above Import in the nav and Settings in the footer over the profile switcher.
- `tests/test_transactions.py` threads `conftest`'s `profile_id` fixture through: `scoped(...)`
  builds a write body, `listing`/`splits`/`first_account`/`taxonomy` take the profile. One test
  was added for the boundary itself: a second profile lists nothing, its patch, split, bulk
  recategorize and bulk delete of another profile's row change nothing, and an unknown profile
  is a 404 on both a read and a write. `uv run pytest` is 56 passed, 1 skipped. Frontend
  `npx tsc --noEmit` and `npm run build` are clean.
- Verified on port 8073 with the synthetic Sparkasse statement imported through the preset: 433
  rows listed for the active profile, the text filter narrowed them to 14, an inline description
  edit saved and the listing endpoint answered with the new text, a two-leg split saved with its
  legs stored against the parent and the row picked up its split badge, and the second profile's
  table is empty with the manual add disabled because it has no account.
  Screenshots: /tmp/finquery-merge04/.
- Known issue, not caused by this merge: an inline edit followed by expanding that row and
  clicking Add a leg pegs the render loop and freezes the page (no console error, so it is the
  virtualizer re-measuring an expanded row whose height changed, oscillating with the row
  offsets it feeds back). Reproduced on 04's own commit (534ca03) built and run on its own
  server, so it predates the merge. It needs its own ticket; the likely fix is to stop measuring
  the expanded row through `virtualizer.measureElement` and give the split editor its own
  scroll box instead.
- Correction from ticket 19: that reading was wrong. There is no measure loop and no render loop.
  The freeze is `agent-browser press Enter` never stopping when the focused input calls `blur()`
  in its keydown handler, which a static HTML page with no React reproduces. Nothing in the page
  needed fixing. Verify inline cells by clicking away to save, not by sending Enter.
- For ticket 09 (changesets): the mutation endpoints are still the apply path, and they are now
  profile-scoped, so a changeset carries the profile it applies to and every leg of it
  (`_resolve_taxonomy`, `_resolve_account`, `replace_splits`, the two bulk endpoints) takes the
  profile id explicitly. `_get` is the ownership check to reuse: a row outside the profile is a
  404, never a silent no-op, while a bulk id outside it is counted as untouched.
