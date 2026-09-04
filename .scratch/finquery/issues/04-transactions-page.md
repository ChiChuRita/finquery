# 04: Transactions page

**What to build:** A user opens Transactions and sees every row of the profile in a fast virtualized table: date, description, enriched title, amount, category, subcategory, account, source. Filters for text, date range, category, account and Needs review narrow it down. Clicking a cell edits it inline. Expanding a row shows its splits, which can be added, edited and removed while the children always sum to the parent. Selecting many rows offers recategorize and delete. A transaction can be added manually.

**Blocked by:** 03 Data model, synthetic dataset and CSV import page

**Status:** ready-for-agent

- [ ] Paginated or virtualized listing endpoint with the filters; table scrolls smoothly with ten thousand rows
- [ ] Inline edit of date, description, amount, category, subcategory, account with optimistic update and validation errors shown in place
- [ ] Split editor in the expanded row enforcing the sum; parents render with a split badge
- [ ] Bulk select with recategorize and delete, with confirmation for delete
- [ ] Manual add form
- [ ] HTTP-seam tests for filters, inline edit validation, split sum enforcement, bulk operations
- [ ] Browser verification with the synthetic dataset loaded
