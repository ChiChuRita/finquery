# 06: Chart sub-agent and chart runtime

**What to build:** A user asks for a chart and gets a house-style TanStack chart inside the answer. The chart sub-agent on the fast slot plans (shape, columns, title) with the plan visible as thinking, gets the SQL through the query sub-agent, writes a chart definition in plain JavaScript against an allowlisted set of globals, checks it in-process with quickjs against a recording stub (compiles, runs, exactly one chart, referenced columns exist, requested shape honoured, data mapped not inlined, house rules) and repairs up to twice with the repairs visible. Only then does a chart data part reach the browser, where a sandboxed iframe hosting React and TanStack Charts renders it with theme palette, EUR axes and tooltips, short month labels, light horizontal grid, legend only for several series, subtle animation, 280px height, responsive.

**Blocked by:** 05 Query sub-agent and the numbers invariant

**Status:** ready-for-agent

- [ ] Chart runtime contract documented: allowlisted globals (defineChart, lineY, areaY, barY, barX, polar, pie, radialArc, sankeyDiagram, scaleLinear, scaleBand, scalePoint, scaleOrdinal, tooltip, palette, EUR formatters), the six shapes, house rules
- [ ] Iframe runtime built as a separate bundle, receives title, rows and code, renders, reports errors back to the parent
- [ ] quickjs self-check with the rule list; failures fed back to the sub-agent as repair instructions; two rounds maximum, then a readable failure message in chat
- [ ] Chart data part rendered in the transcript with title, thumbs placeholder and an expandable SQL and rows view
- [ ] Dark and light theme switch re-renders charts
- [ ] HTTP-seam tests with scripted sub-agent output: a valid chart passes, a chart with an unknown column is repaired, a chart failing twice yields the failure message
- [ ] Browser verification of all six shapes on the synthetic dataset with screenshots in both themes
