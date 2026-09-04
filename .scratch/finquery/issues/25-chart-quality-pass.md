# 25: Chart quality pass

**What to build:** Generate many charts through the real product in a browser, review each one as a data visualization and against the house style, then improve the chart sub-agent prompt, the runtime and the self-check until the charts are consistently good on the first attempt. Measured before and after.

**Blocked by:** 06, 22 (merged)

**Status:** done

Known findings to start from (reviews of 2026-09-04): a Y axis starting at 4400 EUR made a 25 percent range look tenfold; German titles and month labels for English questions; 10 bars with 8 labels and two bars under blank space; pair frames running the axis to 40.000 EUR for a 27.600 EUR maximum; a doughnut with a Rest slice holding the majority; a doughnut that errored on the first attempt and drew on the second; the assistant describing a chart that failed.

- [x] A chart request set of at least 20 prompts covering the eight shapes, German and English, periods (month, quarter, year), comparisons (two periods, category versus category), rankings (top merchants), flows (income to categories), and edge cases (one series, many categories, a single month of data, negative and positive together); stored in the repo as the chart benchmark set with the expected shape per prompt
- [x] Every prompt run through the chat on OpenRouter with the fast slot, screenshots of every card in both themes, and a written review per chart: shape right, axis honest (zero baseline for bars and areas, explicit truncation note for lines that do not start at zero), labels readable (no overlap, thinned or rotated), legend only for several series, colours from the palette in a stable order, title in the answer language, EUR formatting, no chart junk, tooltip works
- [x] Improvements landed for what the review found: prompt and few-shot changes in the sub-agent, runtime defaults (axis domains, label thinning, margins, colour order, title language), self-check rules (label count versus width, zero baseline for bars), and any fix to the shapes table
- [x] The failed-chart text problem is closed: when the chart tool returns rendered false, the assistant's text never describes the chart (re-verified after ticket 22's change, and fixed if it still happens)
- [x] Measured: first-attempt pass rate and visual score before and after on the same prompt set, reported as a small table; docs/chart-runtime.md updated where the contract changed
- [x] Tests: the prompt example test still covers every worked example; new self-check rules have a test each; suite green; typecheck and build clean

## Comments

Done 2026-09-05. `uv run pytest` is 167 passed, 4 skipped (the four are environmental: the
private Trade Republic export and the opt-in local smoke suite). `npx tsc --noEmit`,
`npm run build` and `oxlint` are clean. Screenshots: `/tmp/finquery-25/before/` and
`/tmp/finquery-25/after/`. The full review, with a line per chart, is
`.scratch/finquery/chart-review-2026-09-05.md`.

### Measured

Twenty-four requests (`fixtures/chart-benchmark.json`), OpenRouter, fast slot, a fresh
conversation each, against the shipped synthetic year imported and categorized. Both runs are
scored by the same rules, which are today's rules, so a chart with no finding is a chart that
obeys the house style.

| | before | after |
| --- | --- | --- |
| on the right shape | 23/24 | 23/24 |
| a chart on screen | 24/24 | 21/24 |
| passed the check on the first attempt | 22/24 | 19/24 |
| caption in the request's language | 19/24 | 24/24 |
| no house-rule finding | 8/24 | 24/24 |
| clean: drawn, in language, no finding | 6/24 | 21/24 |
| **good on the first attempt: clean and no repair** | **5/24** | **18/24** |
| seconds per chart, mean | 31.0 | 32.0 |

The two columns that went down are the price of the rules that made the others go up: the check
now refuses things it used to draw. Of the three charts that did not reach the screen, two are
rows no definition could carry (a total row inside a flow, and a fold that relabelled rather
than summed, which the browser threw on and the check now catches first), and one is a code pass
that never read `data` three rounds running.

### What changed

**Prompt and few-shot** (`chart/subagent.py`). `ChartPlan` gained `language`, decided first and
from the request alone, and the caption is written in it. A merchant is named by its enriched
`title`. A grouped chart's third column holds names and never a second euro column. Six groups
is a ceiling and not an instruction to fold: a request that names its categories gets them by
name. The contract learned the difference between `scaleLinear` the factory and `scaleLinear()`
the configured scale, that only a line names a euro domain, that a period axis may thin its
labels and a name axis may not, and `maxThickness: 32`. All eight worked examples were rewritten
to match, so the example test is the contract's own regression test.

**Runtime** (`chart-runtime/globals.ts`, `lib/chart-frame.ts`, `components/chart-tool.tsx`).
`monthShort` is built per render from the chart's `language` and labels a day with its day, so
nineteen daily ticks no longer all read "2025-03". Money stays `de-DE` in both languages. The
render message and `ChartToolOutput` carry `language`. A chart that passed the check and then
failed in the browser says on the card that the answer under it was already written.

**Self-check** (`chart/selfcheck.py`), ten new rules, one test each: a configured scale with no
domain (which drew every bar full width against an axis reading 0 to 1 EUR); a domain inside a
zero-argument factory, which is thrown away; a line whose euro axis does not name a zero
crossing domain; a domain that cuts zero off; a domain on a shape whose mark rests on zero
(which capped a stack below its own total); every named category gets a label; more series than
the palette has colours (cosmetic, so the chart is still shown); two marks over two different
euro columns; a legend labelled by index instead of by name; and, on the rows, a flow with fewer
than three columns, rows that name one position many times, and duplicate (position, group)
pairs in the array the code itself builds. Findings are deduplicated per round.

**Shapes table** (`chart/shapes.py`). `series` (tells its data apart by colour, so a doughnut is
one) is now separate from `crossed` (needs two dimensions that really cross, so a doughnut is
not). That split is what stopped the doughnut oscillating between "drop the legend" and "add the
legend" for two rounds. `zero_from_mark` says which marks bring their own baseline, and
`MAX_SERIES` is the palette's length.

**Runner** (`chart/runner.py`). The tool result carries `language`. A failed chart's `summary`
ends with `NO_PICTURE`, so the last thing the model reads is "no picture, no shape, no axis, no
colour, the figures instead". The grouped query hint carries the six-group ceiling. A line or an
area over fewer than three points is downgraded to bars, because a stroke from January to July
says something about the five months the query did not return.

### The failed-chart text

Verified on three failures in this session. When the tool returns `rendered: false` the answer
opens with the failure and gives figures from a follow-up query, in both languages; no answer
named a shape, an axis or a trend. The one remaining case is the one ticket 22 left: a chart that
passed the check and failed in the browser *after* the answer was written. Re-running the turn is
still a bigger change than this ticket, so the card now says so under the error instead.

### Seen and left

- A Regenerate pair still rounds its euro axis up hard (0 to 20.000 EUR for a 13.800 EUR
  maximum) because a 300 pixel frame asks for three ticks. The full width card is unaffected.
- Month labels are sometimes rotated where they would fit flat. The contract says not to;
  nothing refuses it, because a repair round costs more than the tidiness is worth.
- Two prompt lines landed after the measured run, so its numbers do not include them: ask for
  the period the request named, and give a sankey one source named in the request's language.
