# 50: A line chart with several series

**What to build:** `line` and `area` gain an optional series, so "spending at my five grocery stores per month" draws five lines with a legend instead of one line or sixty bars. Reported by the user on 2026-09-06: asked for five stores over time, the chart came back with one store and then "tried weird things". Root cause: the shape catalogue has no multi-series line; the self-check's "two euro columns with nothing to tell them apart" finding then makes the repair loop drop every store but one, or the planner reaches for grouped bars.

**Blocked by:** 42 (merged); 44 and 45 run in parallel and touch neighbouring files (dashboard defaults, prompt examples), keep the diff tight

**Status:** done

Decisions, settled with the user:
- Optional series on `line` and `area`, not a new shape. One `lineY` (or `areaY`) mark with `color` (or `z`) pointing at the column that names the series; a legend when there is more than one series, none when there is one; the same `MAX_SERIES` ceiling as the bars. `ShapeRule` gets a flag for "may carry a series" distinct from `series` (which means "must"), and `shapes.py`'s docstring and `docs/chart-runtime.md`'s flag list say so.
- Rows for a multi-series line come long (month, series, figure), one row per (month, series) pair, like a grouped bar; the plan and code prompts say so, and the query hint asks for that shape of rows when the request names several entities over time.
- The fold for a series-carrying line or area keeps the largest `MAX_SERIES` series by total and drops the rest, with a note saying which were left out; it never sums them into an "Other" line, because a summed line means nothing. `fold_rows` is shared with the dashboard, so a stored multi-line card behaves the same on load.
- Self-check: the "two marks draw different euro columns" finding must not fire when the mark carries a series channel; a series count above `MAX_SERIES` is a finding for line and area too; more than one series without a legend keeps its finding; the existing single-series checks (domain owns zero, one figure per position) stay.
- Prompt: one worked plan and one code example for a multi-series line in `subagent.EXAMPLES`, in the ticket 42 style (reasoning before the answer), drawn from a new case in the chart benchmark's training half: "Wie viel habe ich 2025 pro Monat bei Rewe, Edeka, Lidl, Aldi und dm ausgegeben, als Linien?" or the English equivalent. Add the case (request, gold shape, rows shape, why) to `bench/chart-benchmark.json` in the training split, one in each language, and re-run `uv run finquery-bench run --set chart --model google/gemini-3.8-flash --n 6` on those and the existing line cases only, if OpenRouter credit allows (a few cents); otherwise say so.
- Frontend: `SHAPE_LABELS` unchanged (still "Line"), the legend already renders; verify the frame draws five lines with the palette and the tooltip names the series.
- Numbers invariant untouched: rows still come from the guarded query; the fold is arithmetic on returned rows and is noted in the card details.

- [x] `ShapeRule` flag, `line` and `area` rows updated, `docs/chart-runtime.md` flag list and shape table updated
- [x] Fold: largest `MAX_SERIES` series kept by total, rest dropped with a note; shared with the dashboard; tests
- [x] Self-check: series allowed on line and area, ceiling finding, no false "two euro columns" finding; tests for a five-line chart that passes, a seven-series one that fails with the ceiling, a two-column no-series line that still fails
- [x] Prompt examples (plan and code) and the two benchmark cases in the training split; `bench/README.md` counts updated
- [x] HTTP-seam test with the scripted FunctionModel: a five-store request renders a line chart with five series and a legend; pinning it to the dashboard and loading the dashboard keeps five series
- [x] `uv run pytest` green, `npm run build` clean; headful browser verification (named session, own port above 8100, throwaway database with the sample year, Gemini 3.8 Flash): the five-store question in chat, the chart with five lines and a legend, the tooltip naming a store, both themes; screenshots in `/tmp/finquery-50/`; a note under Comments with what was built and the benchmark numbers if they were run


## Comments

Done 2026-09-06. `uv run pytest` is 331 passed, 4 skipped, up from 326 passed, 4 skipped: five
tests new, four in `tests/test_chart.py` and one in `tests/test_dashboard.py`. The four skips
are the usual environmental ones. `npm run build` in `frontend/` is clean and no frontend file
is touched: `SHAPE_LABELS` still says "Line", and `lineY`, the `color` channel and `colorLegend`
already did the right thing in the frame.

### What changed

**`chart/shapes.py`.** `ShapeRule` gains `may_series`, and the line and the area set it. It is
apart from `series` (which means the shape must separate its data by colour) and apart from
`crossed` (which means the rows must be complete): a five-shop line needs its (month, shop)
pairs to be unique, but a shop with no booking in March is a gap in one stroke and not a chart
that cannot be drawn. The two purposes the plan menu shows say so, and so does the flag list in
`docs/chart-runtime.md`.

**`chart/selfcheck.py`.** The root cause. "Two marks draw different euro columns with nothing to
tell them apart" fired on a mark that carries a series, and the repair loop obeyed it by
dropping every store but one. It now fires only where it was written for, two marks and fewer
than two series between them. The palette ceiling is a finding for the line and the area too,
in its own words (`TOO_MANY_LINES`): a line has no tail to sum into, so the instruction is to
draw the six largest and leave the rest out. Both ceilings still start with the same sentence,
so `is_cosmetic` keeps them polish and a seventh colour is shown with a note rather than thrown
away. `data_findings` judges a series-carrying line by the pair rule instead of by "one row per
position", which the long rows would have failed outright, and the pair finding's wording is no
longer only a bar's.

**`chart/fold.py`.** `_keep_largest_series`, the one fold that drops instead of summing: the
six largest series by total are drawn and the rest are named in the note. Nobody spends money
at 'Sonstige', so a seventh line holding the tail is a stroke a reader takes for a shop. It
runs from `fold_rows`, so `dashboard.run_card` folds a stored multi-line card the same way on
every load (ticket 39). A series column that holds figures is handed back untouched, because
"income_eur, spending_eur" is two euro columns in one row and the check says that in its own
words rather than losing twelve months here.

**`chart/runner.py`.** `_euro_last` puts the euro column last for a series-carrying line as it
does for a stack. The trend downgrade counts points along the axis and not rows, so five stores
over two months are still two points and become bars. The query hint asks for the long rows and
splits: a stack's group still comes from the `category` column, a line's series are the names
the request asked about, and the app's own fold is described as it really behaves for each.

**`chart/subagent.py`.** The plan rules gain the line-with-a-series bullet and a third worked
plan; the contract gains one line; `EXAMPLES["line"]` gains the multi-series example, one
`lineY` with `z` and `color` on the name column and a legend. No `radius` and no `cornerRadius`
in it, and `dashboard.py` and the doughnut and bar examples are untouched, for tickets 44 and 45.
Only the shapes that may carry a series are shown the new example beside their own, so a
doughnut's prompt did not grow.

**`bench/`.** `33-grocery-lines-de` and `34-grocery-lines-en`, difficulty 3, roles position,
series, value. Gold rebuilt (`build_gold.py`), split rewritten (`split.py`), README counts and
the validation page's sample with them. The hash held the German twin out and kept the English
one in, so the worked plan in the prompt is the English one: an example drawn from a held-out
datapoint teaches the model the answer to a question it is then scored on. Adding to the line
stratum also swapped `20-daily-march-en` and `29-daily-december-line-de`, which is what the
splitter does inside a stratum that grows.

### The benchmark, line datapoints only

`--n` takes a seed and not a list of ids, so the run filtered `load("chart")` to the twelve
line datapoints and called `run_points` exactly as `command_run` does. OpenRouter had 4,58 USD
left, so it was run. Before is the ticket 42 run of the ten line datapoints of that day.

| google/gemini-3.8-flash, line only | n | figure match | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| before (ticket 42) | 10 | 100 % | 100 % | 100 % | 100 % | 100 % | 90 % | 6.5 |
| after | 12 | 92 % | 100 % | 92 % | 100 % | 92 % | 83 % | 7.6 |

Both new datapoints pass on the first attempt, figure, shape, columns and language, in 8.7 s
and 8.2 s. The one miss is `g001-line` ("Show my monthly income across 2025 as a line chart"),
whose statement came back with no rows, was rewritten once and still got none. It is the query
sub-agent's variance on an income filter, the habit the bench README already names as Gemini's,
and it passed on the same prompt the day before. The table and the result files are in
`bench/README.md` and `bench/results/20260906T101920Z-google-gemini-3.8-flash-lines-chart.*`.

### The browser

Headful, own session, port 8137, throwaway database with the shipped year imported and
categorized, Gemini 3.8 Flash on both slots. Screenshots in `/tmp/finquery-50/`.

Asked in German: "Wie viel habe ich 2025 pro Monat bei Rewe, Edeka, Lidl, Aldi und dm
ausgegeben? Zeig es als Linien." What came back, in two seconds and with no repair round: a
line chart titled "Monatliche Ausgaben nach Händler" with **five strokes and a legend** naming
EDEKA, Lidl, REWE, ALDI and dm, 49 rows, German month labels, the euro axis from zero. The code
is one `lineY` with `z: 'merchant'` and `color: 'merchant'`, which is the worked example's own
shape. The tooltip reads "ALDI (Jun 25) 70,00 €" with the series swatch in front of it. The
prose under it quotes REWE in May at 181,10 EUR from the rows.

Both themes (01 and 03), the tooltip (02). Add to dashboard, then the Dashboard page: the card
draws the same five lines with the same legend under "SQL and 49 rows / Queried on this load",
in light (05) and in dark (06), which is the statement re-run and folded again on load.

### What is left

- The area with a series has no worked example of its own. It is shown the line's, which is the
  same one mark and the same channels, and the check treats the two identically. Write one when
  a request asks for stacked bands over time and the shown example is not enough.
- The Qwen number for the line datapoints. The key has credit for it now, but a twelve-datapoint
  run on a model that noisy would say nothing the bench README does not already say about it.
