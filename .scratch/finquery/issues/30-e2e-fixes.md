# 30: End-to-end test fixes

**What to build:** The comprehensive end-to-end test of 2026-09-05 (../e2e-2026-09-05.md, 57 pass, 4 partial, 2 fail, zero console errors) found three blockers and five majors, plus a receipt date miss. Fix them at the root.

**Blocked by:** 17 (merged)

**Status:** ready-for-agent

- [ ] B1 Stop during a chart turn must never reach the React error boundary: guard the reads on a half-arrived chart data part (the .length on undefined) and any other part that can arrive partially; the partial turn is kept; a test drives a stop mid chart stream at the HTTP seam and a browser check repeats it three times
- [ ] B2 The CSV mapping confirmation card renders with its options and free-text field: the ask_user call must carry the rows and options itself (the stored call had rows: [] while the options sat in the import_file output); a card with nothing to answer is never emitted (server refuses to build it); test with unknown-bank-2025.csv through the chat path
- [ ] B3 A changeset never reports Applied unless the database changed: apply verifies its effect (split_count for splits, category for recategorize, existence for delete) inside the same transaction and fails loudly otherwise; the card reflects the real status; find the intermittent cause of the bill split writing no legs (likely the apply running against a stale or different session, or an exception swallowed after the status flip)
- [ ] M1 review_batch returning a queue is always followed by an ask_user card: when the model narrates the card instead of calling the tool, the server emits the card itself from the review_batch result (same mechanism as the seeded review conversation), so the next card is never missing
- [ ] M2 "Compare a second answer" on a chart turn returns a second answer or a clean 409 with a readable message, never a 500 printed into the transcript; test at the HTTP seam
- [x] M3 Stacked bars: the chart runner's query hint and the plan must group by both the position and the series column when a tail is folded into Other; the self-check already catches duplicates, so the fix is in the prompt and the fold step; the stacked benchmark prompt passes first attempt
- [x] M4 The sentence under a chart comes from that chart's rows: the chart tool summary names the chart and its figures, and the prompt says the answer describes the chart that was just drawn, never an earlier one; test with two chart turns in a row
- [x] M5 Sankey: a self-loop (Income to Income) is folded or refused before the code pass, with a query hint that the source and target columns must differ
- [x] Receipt date: the bill extraction reads the printed date (the real Edeka receipt prints 04.09.26 20:00 and the model fell back to today); prompt the date field explicitly with German short formats and verify against the text spans; the real receipt at fixtures/private/edeka-bill-real.jpeg is the manual check (never commit it)
- [ ] Minors: remember confirms in one line; a deleted memory is not resolved from history; follow-up chips follow the profile's fixed language; the duplicate summary is not a copy of the Applied line; mapping preview uses German dates and decimals; a second Stop keeps the partial tool step; thinking panel order; bulk Recategorize never defaults to Needs review and confirms before applying
- [ ] Suite green, typecheck and build clean; browser verification of every blocker and major in both themes
