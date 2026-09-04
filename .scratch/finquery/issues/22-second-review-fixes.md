# 22: Second review fixes

**What to build:** The second headful review (../review-2026-09-04-second.md) confirmed the first review's blockers are fixed and found a sharper set concentrated in the query and chart sub-agents. This ticket fixes them.

**Blocked by:** 20, 21 (merged)

**Status:** ready-for-agent

- [ ] The query sub-agent never invents categories in SQL: no CASE WHEN description LIKE ... THEN 'Groceries' classifiers. The guard rejects string-literal category labels derived from description matching, the prompt says category comes only from the category column and that Needs review is shown as its own bucket, and a test covers the refusal
- [ ] A chart that fails to render in the browser is reported back to the turn: the card shows the error, the assistant's text says the chart could not be drawn and gives the numbers instead of describing a chart that is not there. The self-check runs against the real rows (duplicate (x, series) pairs for stacked bars and circular or negative sankey links are caught before the browser), and one automatic retry happens when the render fails
- [ ] The reasoning stream gets the same template-token and retry-feedback filter as the text stream, and a chart turn ends with text on the first pass (no empty-text retry after a tool)
- [ ] Distilled memories are written in the language of the turn they came from, and the answer language rule is verified on a fresh conversation with an English question in a profile whose memories are German
- [ ] An absent subcategory renders as a dash, never the string None; a typed transaction never stores the string "null" as counterparty
- [ ] Regenerate retries until the second chart differs (up to three attempts server-side) and never offers Pick on a failed side
- [ ] Copy: "3 merchants", "1 row matches these filters", "Used 1 source", one number in the delete dialog, one date format in the outbound log, rendered markdown in the import tool step
- [ ] Doughnut Rest slice never holds the majority: regroup so the six largest categories are shown when the rest would dominate, or state the share in the title
- [ ] Web lookup cache hit shows a step saying it came from the cache
- [ ] HTTP-seam tests for the guard, the chart failure path, the reasoning filter and the memory language; suite green; browser verification of a category chart, a stacked bar chart and a sankey on a categorized profile
