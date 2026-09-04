# ADR 0005: Money as integer cents, read through a split-aware view

Date: 2026-09-04
Status: accepted

## Context

Every number the assistant states comes from SQL it ran (ADR 0004), so the storage of an amount
decides whether that number is exact. SQLite has no decimal type: a `NUMERIC` column round
trips through a float, and `SUM` over it is a float sum. Splits make it worse, because a parent
and its children would both be summed unless queries know the difference.

## Decision

- A transaction stores `amount_cents` as an `INTEGER`. Python arithmetic, the split sum
  constraint and SQL `SUM` are all exact. The API sends cents; the frontend formats EUR.
- Queries and charts never read the `transaction` table. They read the view
  `transaction_view` (`finquery.db.QUERY_VIEW`), which joins account, category and subcategory
  names in, exposes `amount_cents` and a convenience `amount` in euros, and excludes any
  transaction that has children. A split parent is therefore invisible to every query while its
  children are counted once.
- The split sum rule is enforced in code, not by a check constraint: a session-level
  `after_flush` listener registered in `make_session_factory` recomputes the children of every
  parent the unit of work touched and raises `SplitSumError` when they do not sum to it. One
  guard covers the import, the transactions page and changesets.
- Categorization is absent, not empty: `category_id IS NULL` is `Needs review`. `Unknown` is a
  seeded category a human picks, and automation never writes it.

## Consequences

- The SQL guard of ticket 05 allowlists exactly one relation, `transaction_view`, and the query
  sub-agent prompt describes its columns.
- Anything that writes splits gets the sum check for free and has to handle `SplitSumError` as
  a validation error.
- The view is dropped and recreated on every start, so changing its shape is a code change with
  no migration.
