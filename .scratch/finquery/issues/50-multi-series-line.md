# 50: A line chart with several series

**What to build:** `line` and `area` gain an optional series, so "spending at my five grocery stores per month" draws five lines with a legend instead of one line or sixty bars. Reported by the user on 2026-09-06: asked for five stores over time, the chart came back with one store and then "tried weird things". Root cause: the shape catalogue has no multi-series line; the self-check's "two euro columns with nothing to tell them apart" finding then makes the repair loop drop every store but one, or the planner reaches for grouped bars.

**Blocked by:** 42 (merged); 44 and 45 run in parallel and touch neighbouring files (dashboard defaults, prompt examples), keep the diff tight

**Status:** ready-for-agent

Decisions, settled with the user:
- Optional series on `line` and `area`, not a new shape. One `lineY` (or `areaY`) mark with `color` (or `z`) pointing at the column that names the series; a legend when there is more than one series, none when there is one; the same `MAX_SERIES` ceiling as the bars. `ShapeRule` gets a flag for "may carry a series" distinct from `series` (which means "must"), and `shapes.py`'s docstring and `docs/chart-runtime.md`'s flag list say so.
- Rows for a multi-series line come long (month, series, figure), one row per (month, series) pair, like a grouped bar; the plan and code prompts say so, and the query hint asks for that shape of rows when the request names several entities over time.
- The fold for a series-carrying line or area keeps the largest `MAX_SERIES` series by total and drops the rest, with a note saying which were left out; it never sums them into an "Other" line, because a summed line means nothing. `fold_rows` is shared with the dashboard, so a stored multi-line card behaves the same on load.
- Self-check: the "two marks draw different euro columns" finding must not fire when the mark carries a series channel; a series count above `MAX_SERIES` is a finding for line and area too; more than one series without a legend keeps its finding; the existing single-series checks (domain owns zero, one figure per position) stay.
- Prompt: one worked plan and one code example for a multi-series line in `subagent.EXAMPLES`, in the ticket 42 style (reasoning before the answer), drawn from a new case in the chart benchmark's training half: "Wie viel habe ich 2025 pro Monat bei Rewe, Edeka, Lidl, Aldi und dm ausgegeben, als Linien?" or the English equivalent. Add the case (request, gold shape, rows shape, why) to `bench/chart-benchmark.json` in the training split, one in each language, and re-run `uv run finquery-bench run --set chart --model google/gemini-3.8-flash --n 6` on those and the existing line cases only, if OpenRouter credit allows (a few cents); otherwise say so.
- Frontend: `SHAPE_LABELS` unchanged (still "Line"), the legend already renders; verify the frame draws five lines with the palette and the tooltip names the series.
- Numbers invariant untouched: rows still come from the guarded query; the fold is arithmetic on returned rows and is noted in the card details.

- [ ] `ShapeRule` flag, `line` and `area` rows updated, `docs/chart-runtime.md` flag list and shape table updated
- [ ] Fold: largest `MAX_SERIES` series kept by total, rest dropped with a note; shared with the dashboard; tests
- [ ] Self-check: series allowed on line and area, ceiling finding, no false "two euro columns" finding; tests for a five-line chart that passes, a seven-series one that fails with the ceiling, a two-column no-series line that still fails
- [ ] Prompt examples (plan and code) and the two benchmark cases in the training split; `bench/README.md` counts updated
- [ ] HTTP-seam test with the scripted FunctionModel: a five-store request renders a line chart with five series and a legend; pinning it to the dashboard and loading the dashboard keeps five series
- [ ] `uv run pytest` green, `npm run build` clean; headful browser verification (named session, own port above 8100, throwaway database with the sample year, Gemini 3.8 Flash): the five-store question in chat, the chart with five lines and a legend, the tooltip naming a store, both themes; screenshots in `/tmp/finquery-50/`; a note under Comments with what was built and the benchmark numbers if they were run
