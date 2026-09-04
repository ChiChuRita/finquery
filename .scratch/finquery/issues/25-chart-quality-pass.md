# 25: Chart quality pass

**What to build:** Generate many charts through the real product in a browser, review each one as a data visualization and against the house style, then improve the chart sub-agent prompt, the runtime and the self-check until the charts are consistently good on the first attempt. Measured before and after.

**Blocked by:** 06, 22 (merged)

**Status:** ready-for-agent

Known findings to start from (reviews of 2026-09-04): a Y axis starting at 4400 EUR made a 25 percent range look tenfold; German titles and month labels for English questions; 10 bars with 8 labels and two bars under blank space; pair frames running the axis to 40.000 EUR for a 27.600 EUR maximum; a doughnut with a Rest slice holding the majority; a doughnut that errored on the first attempt and drew on the second; the assistant describing a chart that failed.

- [ ] A chart request set of at least 20 prompts covering the eight shapes, German and English, periods (month, quarter, year), comparisons (two periods, category versus category), rankings (top merchants), flows (income to categories), and edge cases (one series, many categories, a single month of data, negative and positive together); stored in the repo as the chart benchmark set with the expected shape per prompt
- [ ] Every prompt run through the chat on OpenRouter with the fast slot, screenshots of every card in both themes, and a written review per chart: shape right, axis honest (zero baseline for bars and areas, explicit truncation note for lines that do not start at zero), labels readable (no overlap, thinned or rotated), legend only for several series, colours from the palette in a stable order, title in the answer language, EUR formatting, no chart junk, tooltip works
- [ ] Improvements landed for what the review found: prompt and few-shot changes in the sub-agent, runtime defaults (axis domains, label thinning, margins, colour order, title language), self-check rules (label count versus width, zero baseline for bars), and any fix to the shapes table
- [ ] The failed-chart text problem is closed: when the chart tool returns rendered false, the assistant's text never describes the chart (re-verified after ticket 22's change, and fixed if it still happens)
- [ ] Measured: first-attempt pass rate and visual score before and after on the same prompt set, reported as a small table; docs/chart-runtime.md updated where the contract changed
- [ ] Tests: the prompt example test still covers every worked example; new self-check rules have a test each; suite green; typecheck and build clean
