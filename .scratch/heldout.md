# The held-out cases, and how the candidates did on them

74 held-out datapoints of 225. A model column is the newest run of that model in `bench/results/`, `pass`, `miss` or an empty cell when that run did not cover the datapoint.

| id | set | kind | difficulty | language | google/gemini-3.8-flash | local:fast | local:gemma-4-12b | local:gemma-4-e4b | local:qwen3.5-9b | qwen/qwen3.5-9b |
| --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| `s01-may-total-de` | sql | total | 1 | de | pass | pass | pass | pass | pass | pass |
| `s02-year-total-en` | sql | total | 1 | en | pass | pass | pass | pass | pass | pass |
| `s06-groceries-per-week-de` | sql | total | 3 | de | miss | miss | pass | miss | pass | miss |
| `s09-this-quarter-en` | sql | total | 3 | en | pass | pass | pass | pass | miss | pass |
| `s11-supermarket-october-en` | sql | total | 2 | en | pass | pass | miss | pass | pass | miss |
| `s13-per-category-de` | sql | breakdown | 1 | de | pass | pass | pass | miss | pass | pass |
| `s18-needs-review-merchants-de` | sql | breakdown | 2 | de | pass | pass | pass | miss | pass | miss |
| `s19-per-quarter-en` | sql | breakdown | 2 | en | pass | miss | pass | miss | pass | miss |
| `s20-weekday-de` | sql | breakdown | 3 | de | pass | pass | pass | pass | pass | pass |
| `s25-halves-en` | sql | comparison | 2 | en | pass | pass | pass | pass | pass | pass |
| `s26-groceries-vs-dining-de` | sql | comparison | 3 | de | pass | miss | miss | miss | miss | miss |
| `s34-cumulative-de` | sql | trend | 3 | de | pass | miss | miss | miss | miss | miss |
| `s35-net-per-month-en` | sql | trend | 3 | en | pass | pass | pass | miss | miss | miss |
| `s39-top-ten-de` | sql | ranking | 3 | de | pass | pass | pass | pass | pass | pass |
| `s40-biggest-expense-en` | sql | ranking | 2 | en | pass | miss | pass | miss | miss | miss |
| `s44-most-visited-supermarkets-en` | sql | ranking | 3 | en | pass | miss | pass | miss | miss | pass |
| `s47-edeka-en` | sql | entity | 1 | en | pass | pass | pass | pass | miss | miss |
| `s50-dm-de` | sql | entity | 3 | de | pass | miss | pass | pass | pass | miss |
| `s56-all-subscriptions-en` | sql | entity | 2 | en | pass | pass | pass | pass | miss | miss |
| `s59-bakery-de` | sql | entity | 2 | de | pass | pass | pass | miss | miss | miss |
| `s66-cheapest-month-en` | sql | follow-up | 3 | en | pass | pass | pass | miss | miss | pass |
| `s68-by-merchant-en` | sql | follow-up | 2 | en | pass | miss | pass | miss | miss | miss |
| `s71-last-three-months-en` | sql | period | 2 | en | pass | pass | pass | pass | pass | pass |
| `s74-this-month-de` | sql | period | 2 | de | pass | pass | pass | pass | pass | pass |
| `s75-summer-en` | sql | period | 3 | en | pass | miss | pass | pass | miss | miss |
| `g003-total` | sql | total | 3 | de | pass | pass | pass | pass | pass | miss |
| `g004-total` | sql | total | 3 | en | pass | pass | pass | pass | pass | pass |
| `g005-total` | sql | total | 1 | en | pass | pass | pass | pass | pass | pass |
| `g007-total` | sql | total | 2 | de | pass | pass | pass | pass | pass | miss |
| `g010-total` | sql | total | 2 | en | pass | pass | pass | miss | pass | pass |
| `g001-breakdown` | sql | breakdown | 2 | de | pass | pass | pass | pass | pass | pass |
| `g008-breakdown` | sql | breakdown | 2 | en | pass | pass | pass | pass | pass | pass |
| `g009-breakdown` | sql | breakdown | 3 | en | pass | pass | pass | pass | pass | pass |
| `g001-comparison` | sql | comparison | 2 | en | pass | miss | pass | miss | pass | miss |
| `g007-comparison` | sql | comparison | 2 | de | pass | miss | pass | pass | pass | miss |
| `g008-comparison` | sql | comparison | 3 | en | pass | miss | pass | pass | pass | miss |
| `g006-trend` | sql | trend | 2 | en | pass | miss | pass | miss | pass | miss |
| `g004-ranking` | sql | ranking | 2 | en | pass | pass | pass | pass | miss | pass |
| `g009-ranking` | sql | ranking | 3 | en | pass | miss | pass | miss | miss | pass |
| `g002-entity` | sql | entity | 1 | en | pass | pass | pass | pass | pass | miss |
| `g007-entity` | sql | entity | 2 | en | pass | pass | pass | pass | miss | pass |
| `g008-entity` | sql | entity | 2 | de | pass | pass | pass | pass | pass | pass |
| `g010-entity` | sql | entity | 3 | de | pass | miss | pass | miss | miss | miss |
| `g011-entity` | sql | entity | 3 | en | pass | pass | pass | pass | pass | pass |
| `g002-follow-up` | sql | follow-up | 2 | de | miss | miss | miss | miss | miss | miss |
| `g005-follow-up` | sql | follow-up | 3 | de | pass | miss | miss | miss | miss | miss |
| `g008-follow-up` | sql | follow-up | 2 | en | pass | miss | miss | miss | pass | miss |
| `g003-period` | sql | period | 2 | en | pass | pass | pass | pass | pass | pass |
| `g007-period` | sql | period | 2 | de | pass | pass | pass | pass | pass | pass |
| `g009-period` | sql | period | 3 | en | pass | miss | pass | pass | miss | miss |
| `04-cumulative-area-de` | chart | area | 2 | de | miss | miss | pass | miss | miss | miss |
| `05-category-bars-en` | chart | bar | 1 | en | pass | pass | pass | pass | pass | pass |
| `07-top-merchants-en` | chart | bar_horizontal | 2 | en | pass | pass | pass | pass | pass | miss |
| `16-sankey-income-de` | chart | sankey | 3 | de | pass | miss | pass | pass | miss | miss |
| `17-two-halves-en` | chart | bar | 2 | en | pass | pass | miss | miss | pass | miss |
| `21-groceries-months-en` | chart | line | 2 | en | pass | pass | pass | pass | miss | pass |
| `24-net-per-month-de` | chart | bar | 2 | de | pass | pass | pass | miss | pass | miss |
| `27-needs-review-bar-de` | chart | bar | 2 | de | pass | miss | pass | miss | miss | pass |
| `30-groceries-stacked-quarters-en` | chart | bar_stacked | 3 | en | pass | miss | miss | miss | miss | miss |
| `33-grocery-lines-de` | chart | line | 3 | de |  |  | pass | pass | miss |  |
| `g003-bar` | chart | bar | 2 | en | pass | miss | miss | miss | miss | miss |
| `g005-bar` | chart | bar | 2 | en | pass | pass | pass | miss | pass | miss |
| `g001-line` | chart | line | 2 | en | miss | pass | pass | pass | pass | miss |
| `g005-line` | chart | line | 2 | de | pass | pass | miss | pass | miss | pass |
| `g002-doughnut` | chart | doughnut | 2 | de | pass | pass | pass | pass | miss | miss |
| `g003-doughnut` | chart | doughnut | 3 | en | pass | pass | pass | pass | miss | miss |
| `g001-bar_horizontal` | chart | bar_horizontal | 2 | en | pass | miss | pass | miss | miss | miss |
| `g002-bar_grouped` | chart | bar_grouped | 3 | en | pass | miss | pass | miss | pass | miss |
| `g001-sankey` | chart | sankey | 3 | de | pass | miss | miss | miss | miss | pass |
| `g003-sankey` | chart | sankey | 2 | de | pass | miss | pass | miss | miss | miss |
| `36-this-month-versus-last-de` | chart | bar_grouped | 3 | de | pass |  | pass | miss | miss |  |
| `38-change-per-month-de` | chart | bar | 3 | de | pass |  | pass | miss | miss |  |
| `39-average-line-en` | chart | line | 3 | en | pass |  | pass | pass | pass |  |
| `41-cumulative-halves-en` | chart | area | 3 | en | pass |  | miss | miss | miss |  |

- google/gemini-3.8-flash: 69 of 73 held-out cases, 4 missed
- local:fast: 41 of 69 held-out cases, 28 missed
- local:gemma-4-12b: 62 of 74 held-out cases, 12 missed
- local:gemma-4-e4b: 40 of 74 held-out cases, 34 missed
- local:qwen3.5-9b: 39 of 74 held-out cases, 35 missed
- qwen/qwen3.5-9b: 29 of 69 held-out cases, 40 missed
