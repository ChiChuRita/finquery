# Chart quality pass, 2026-09-05

Ticket 25. The same twenty-four requests (`fixtures/chart-benchmark.json`) sent through the chat
on OpenRouter, fast slot, one fresh conversation each, against a profile holding
`fixtures/synthetic/sparkasse-2025.csv` imported through the Sparkasse preset (433 bookings) and
categorized (384 by the dictionary, 24 by the model, 25 Needs review). Every card screenshotted
in both themes: `/tmp/finquery-25/before/` and `/tmp/finquery-25/after/`.

## How a chart is scored

The self-check is the written form of the house style (ADR 0009), so the same rules are run over
both sets of generated code and a chart with no finding is a chart that obeys them. Four columns
per chart:

- **shape**: the plan chose the shape the request asks for, or one that answers it as directly;
- **first**: the code passed the self-check on the first attempt, with no repair round;
- **language**: the caption is in the language of the request;
- **findings**: what today's rules say about the code that was drawn.

`clean` is a chart that is on screen, in the right language, with no finding at all. The
checklist items the rules cannot see (colours from the palette, EUR formatting, chart junk, the
tooltip) were read off the screenshots; where a chart failed one of those it is named below.

## Before and after

| | before | after |
| --- | --- | --- |
| on the right shape | 23/24 | 23/24 |
| a chart on screen | 24/24 | 21/24 |
| passed on the first attempt | 22/24 | 19/24 |
| caption in the request's language | 19/24 | 24/24 |
| no house-rule finding | 8/24 | 24/24 |
| clean: drawn, in language, no finding | 6/24 | 21/24 |
| **good on the first attempt: clean and no repair** | **5/24** | **18/24** |
| seconds per chart, mean | 31.0 | 32.0 |

### Before

| # | shape | first pass | language | findings |
| --- | --- | --- | --- | --- |
| 01-monthly-line-en | line | yes | **no** | The euro axis has to start at zero, or a change of a few percent is dr |
| 02-monthly-line-de | line | yes | yes | The euro axis has to start at zero, or a change of a few percent is dr |
| 03-cumulative-area-en | area | yes | **no** | clean |
| 04-cumulative-area-de | area | yes | yes | clean |
| 05-category-bars-en | bar | yes | yes | Every bar is named by its own label and none may be dropped, so `scale |
| 06-category-bars-de | bar | yes | yes | Every bar is named by its own label and none may be dropped, so `scale |
| 07-top-merchants-en | bar_horizontal | yes | yes | Every bar is named by its own label and none may be dropped, so `scale |
| 08-top-merchants-de | bar_horizontal | yes | yes | Every bar is named by its own label and none may be dropped, so `scale |
| 09-quarter-groups-en | bar_grouped | yes | yes | Every bar is named by its own label and none may be dropped, so `scale |
| 10-quarter-groups-de | bar_grouped | yes | yes | clean |
| 11-stacked-months-en | bar_stacked | yes | yes | The palette holds 6 colours and this chart asks for 11, so two groups  |
| 12-stacked-months-de | bar_stacked | yes | yes | The palette holds 6 colours and this chart asks for 11, so two groups  |
| 13-doughnut-categories-en | doughnut | **no** | yes | clean |
| 14-doughnut-merchants-de | doughnut | yes | yes | clean |
| 15-sankey-income-en | sankey | yes | **no** | clean |
| 16-sankey-income-de | sankey | yes | yes | clean |
| 17-two-halves-en | bar | yes | yes | Every bar is named by its own label and none may be dropped, so `scale |
| 18-two-months-de | bar | yes | yes | clean |
| 19-quarters-en | bar | yes | **no** | Every bar is named by its own label and none may be dropped, so `scale |
| 20-daily-march-en | line | yes | yes | The euro axis has to start at zero, or a change of a few percent is dr |
| 21-groceries-months-en | line | yes | yes | The euro axis has to start at zero, or a change of a few percent is dr |
| 22-all-categories-de | bar | yes | yes | Every bar is named by its own label and none may be dropped, so `scale |
| 23-income-versus-spending-en | bar (wanted bar_grouped) | **no** | **no** | Two marks draw different euro columns (income_eur, spending_eur) with ; One series needs no legend. Drop the `color.legend` option. |
| 24-net-per-month-de | line | yes | yes | The euro axis has to start at zero, or a change of a few percent is dr |

### After

| # | shape | first pass | language | findings |
| --- | --- | --- | --- | --- |
| 01-monthly-line-en | line | yes | yes | clean |
| 02-monthly-line-de | line | yes | yes | clean |
| 03-cumulative-area-en | area | yes | yes | clean |
| 04-cumulative-area-de | area | yes | yes | clean |
| 05-category-bars-en | bar | yes | yes | clean |
| 06-category-bars-de | bar | yes | yes | clean |
| 07-top-merchants-en | bar_horizontal | yes | yes | clean |
| 08-top-merchants-de | bar_horizontal | **no** | yes | clean |
| 09-quarter-groups-en | bar_grouped | yes | yes | clean |
| 10-quarter-groups-de | bar_grouped | yes | yes | clean |
| 11-stacked-months-en | bar_stacked | **no** | yes | **no chart drawn** |
| 12-stacked-months-de | bar_stacked | yes | yes | clean |
| 13-doughnut-categories-en | doughnut | **no** | yes | clean |
| 14-doughnut-merchants-de | doughnut | yes | yes | clean |
| 15-sankey-income-en | sankey | yes | yes | clean |
| 16-sankey-income-de | sankey | yes | yes | **no chart drawn** |
| 17-two-halves-en | bar | yes | yes | clean |
| 18-two-months-de | bar_stacked (wanted bar) | **no** | yes | **no chart drawn** |
| 19-quarters-en | bar | yes | yes | clean |
| 20-daily-march-en | line | **no** | yes | clean |
| 21-groceries-months-en | line | yes | yes | clean |
| 22-all-categories-de | bar | yes | yes | clean |
| 23-income-versus-spending-en | bar_grouped | yes | yes | clean |
| 24-net-per-month-de | line | yes | yes | clean |

## What the pictures showed, before

Read off the forty-eight screenshots in `/tmp/finquery-25/before/`, in the order the checklist
puts them:

- **axis**: the monthly line ran from 2.200 to 2.800 EUR over the whole card, so a range of
  25 percent read as a cliff (`01`, `02`, `21`, `24`). Bars and areas were already honest,
  because the mark contributes its own zero.
- **labels**: eleven bars with eight labels, three bars standing under blank space (`05`, `06`,
  `22`), and the same on `17` and `19`. A daily line printed "2025-03" nineteen times, because
  every tick was formatted as its month (`20`).
- **colours**: the stacked bars asked for eleven series out of a six-colour palette, so Housing
  and Communication were both green and Groceries and Subscriptions both blue (`11`, `12`).
  Eleven legend items ate three of the card's rows and squeezed the plot.
- **legend**: the doughnut of the largest merchants overlapped its own labels, because the raw
  booking text ("Hausverwaltung Bergmann GmbH") is longer than a legend column (`14`).
- **language**: five English questions came back with German captions (`01`, `03`, `15`, `19`,
  `23`) and every chart wrote German month labels whatever the question was.
- **junk**: two bars filling half a card each (`17`), and income drawn on top of spending as a
  stack, with an empty legend, which is a total nobody asked for (`23`).
- **money and tooltip**: correct throughout, both themes, before and after.

## What the pictures show, after

- Every drawn chart obeys every rule the check knows (24/24 with no finding).
- The three that did not draw are honest about it, and two of them are now caught earlier than
  they were on the day:
  - `11` the code pass never read `data` three rounds running. The finding now names the
    columns and shows the call, which is the instruction it was missing.
  - `16` the query put a total row into the flow (Einkommen to Einkommen), refused by the row
    rules before any code was written. The sankey hint now forbids a self link outright.
  - `18` folded its groups by relabelling them rather than by summing them, so the array the
    code built carried 2025-01 / Sonstiges twice and the browser threw. The check now judges
    the mark's own rows and not only the query's.
- `18` is also the one case where the answer text still describes a chart that is not there: the
  tool returned `rendered: true`, the browser refused afterwards, and the sentence was already
  written. The card now says so under the error rather than leaving the two to contradict each
  other.

## What is left

- **A Regenerate pair still rounds its euro axis up hard**: 0 to 20.000 EUR for a 13.800 EUR
  maximum, because a 300 pixel frame asks for three ticks and `nice` has nowhere else to land.
  The full width card is unaffected (0 to 14.000 EUR). Forcing a tick count would make the
  common case worse to make the rare one better, so it stays as it is.
- **Month labels are sometimes rotated** where they would fit flat. The contract says a period
  axis is never rotated; nothing refuses it, because a repair round costs more than the tidiness
  is worth.
- Two lines landed after the measured run and are therefore not in its numbers: the plan asks
  for the period the request named (a chart captioned by quarter had months along its axis), and
  a sankey names one source in the request's language (an English flow came back with an
  "Einkommen" component beside an "Income" one).
