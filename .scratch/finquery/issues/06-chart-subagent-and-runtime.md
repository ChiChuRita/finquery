# 06: Chart sub-agent and chart runtime

**What to build:** A user asks for a chart and gets a house-style TanStack chart inside the answer. The chart sub-agent on the fast slot plans (shape, columns, title) with the plan visible as thinking, gets the SQL through the query sub-agent, writes a chart definition in plain JavaScript against an allowlisted set of globals, checks it in-process with quickjs against a recording stub (compiles, runs, exactly one chart, referenced columns exist, requested shape honoured, data mapped not inlined, house rules) and repairs up to twice with the repairs visible. Only then does a chart data part reach the browser, where a sandboxed iframe hosting React and TanStack Charts renders it with theme palette, EUR axes and tooltips, short month labels, light horizontal grid, legend only for several series, subtle animation, 280px height, responsive.

**Blocked by:** 05 Query sub-agent and the numbers invariant

**Status:** done

- [x] Chart runtime contract documented: allowlisted globals (defineChart, lineY, areaY, barY, barX, polar, pie, radialArc, sankeyDiagram, scaleLinear, scaleBand, scalePoint, scaleOrdinal, tooltip, palette, EUR formatters), the six shapes, house rules
- [x] Iframe runtime built as a separate bundle, receives title, rows and code, renders, reports errors back to the parent
- [x] quickjs self-check with the rule list; failures fed back to the sub-agent as repair instructions; two rounds maximum, then a readable failure message in chat
- [x] Chart data part rendered in the transcript with title, thumbs placeholder and an expandable SQL and rows view
- [x] Dark and light theme switch re-renders charts
- [x] HTTP-seam tests with scripted sub-agent output: a valid chart passes, a chart with an unknown column is repaired, a chart failing twice yields the failure message
- [x] Browser verification of all six shapes on the synthetic dataset with screenshots in both themes

## Comments

Done 2026-09-04. Structure for the next tickets:

- `src/finquery/chart/`: `shapes.py` (the eight shapes and what each one has to look like, read by
  the plan prompt, the code prompt and the check), `subagent.py` (`plan_agent` with the forced
  tool `chart_plan`, `code_agent` with the forced tool `chart_code`, the pure prompt builders
  `plan_prompt` and `code_prompt` and one worked example per shape), `selfcheck.py` (the QuickJS
  stub, `judge` and `check_chart_code`), `runner.py` (`run_chart(...)` returning a
  `ChartOutcome` whose `.payload()` is the tool result).
- `agent.py` gained the `chart` tool and the prompt lines that say when to draw one. `ChatDeps`
  gained `narrate`: a tool calls it and the chat endpoint turns each line into reasoning text, so
  the plan, the row count and every repair round show up in the thinking panel live and after a
  reload. `api/chat.py` merges those lines into the stream through one queue (`Narration`,
  `_pump`) and puts them back after the tool part when the turn is persisted.
- Two things the plan cannot know are decided after the query: a shape the rows cannot carry is
  downgraded (a stacked chart whose query returned one series becomes plain bars, narrated), and
  a chart whose only remaining finding is polish (a legend nobody needs) is shown with a note
  instead of thrown away. Everything else fails after `ATTEMPTS = 3`.
- The result travels as the `chart` tool's output, not as a `data-chart` part: it carries title,
  shape, plan, sql, columns, rows, code and notes, so the card is auditable the same way a number
  is and ticket 15 has the whole record in one place.
- Frontend: `chart-runtime.html` plus `src/chart-runtime/` are a second Vite entry, loaded as
  `<iframe sandbox="allow-scripts">`; `components/chart-tool.tsx` is the card (title, shape badge,
  frame, rating placeholder, expandable request, plan, repairs, SQL and rows).
  `components/query-result.tsx` holds the pieces the query step and the chart card share.
  `lib/chart-frame.ts` is the message protocol. `index.css` gained a real six-colour chart
  palette for both themes (the shadcn default was five greys).
- The app answers `/assets/*` with `access-control-allow-origin: *`: a sandboxed document has an
  opaque origin, so Vite's `crossorigin` entry script is a CORS request. Without it the frame
  stays blank, which is the first thing to check if a chart ever shows nothing.
- Two traps found while verifying, both fixed in the prompts and worth knowing:
  an alias that reuses a view column name (`CASE ... END AS category`) makes SQLite's `GROUP BY`
  bind to the view's own column and silently collapses the result, so `query/subagent.py` now
  forbids it; and a sankey rejects negative or missing link values, so the chart hint asks for
  positive amounts and complete endpoints.
- Tests: 49 total (`tests/test_chart.py` adds 7). The fast slot is scripted per forced tool
  (`chart_plan`, `run_sql`, `chart_code`) plus the follow-up step, so one turn is one chat
  request, one plan, one statement, one code per attempt and one follow-up request.
- Docs: `docs/chart-runtime.md` is the contract (globals, shapes, house rules, the check, the
  message protocol, the payload) and the reference for generating the chart adapter's training
  data. `docs/adr/0009-charts-as-checked-code-in-a-sandboxed-frame.md` records the decision.
- Verified on OpenRouter against the synthetic dataset: monthly line, cumulative area, monthly
  bars, top-ten merchants as horizontal bars, grouped bars per quarter and merchant, stacked bars
  per month and topic, doughnut of the largest merchants with a folded rest slice, and a sankey
  from income into the spending groups. Each in both themes, the plan and the repairs visible in
  the thinking panel, the SQL and rows expandable, and the frame's error path forced once.
  Screenshots: /tmp/finquery-06/.
