### local:gemma-4-12b on the chart set

73 datapoints, 2026-09-06T15:17:12+00:00, 3645.0 s in total, 49.9 s per datapoint, median 46.7 s, p90 64.1 s.

| | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 73 | 81 % | 100 % | 96 % | 85 % | 99 % | 94 % | 92 % | 46.7 |
| area | 8 | 62 % | 100 % | 100 % | 62 % | 88 % | 88 % | 88 % | 52.2 |
| bar | 17 | 76 % | 100 % | 88 % | 82 % | 100 % | 100 % | 94 % | 45.9 |
| bar_grouped | 8 | 88 % | 100 % | 100 % | 100 % | 100 % | 100 % | 88 % | 60.0 |
| bar_horizontal | 6 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 40.4 |
| bar_stacked | 6 | 67 % | 100 % | 83 % | 83 % | 100 % | 83 % | 83 % | 41.8 |
| doughnut | 8 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 50.2 |
| line | 14 | 86 % | 100 % | 100 % | 86 % | 100 % | 100 % | 100 % | 40.8 |
| sankey | 6 | 67 % | 100 % | 100 % | 67 % | 100 % | 67 % | 67 % | 63.7 |
| difficulty 1 | 4 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 38.3 |
| difficulty 2 | 39 | 80 % | 100 % | 95 % | 90 % | 100 % | 100 % | 95 % | 46.2 |
| difficulty 3 | 30 | 80 % | 100 % | 97 % | 77 % | 97 % | 87 % | 87 % | 51.1 |

Missed (14):

- `17-two-halves-en` Compare my total spending in the first half of 2025 with the second ha - wrong figures
- `18-two-months-de` Vergleiche meine Ausgaben im Januar 2025 mit denen im Juli 2025 als Di - wrong figures
- `30-groceries-stacked-quarters-en` Show my grocery spending per quarter in 2025, split into supermarket,  - wrong figures
- `g003-bar` Show how much each subscription service cost me in 2025. - wrong figures
- `g007-bar` Give me a breakdown of my spending across categories in Q3 2025. - wrong figures
- `g004-line` Stelle meine Monatsausgaben bei Amazon 2025 als Liniengrafik dar. - wrong figures
- `g005-line` Wie haben sich meine Ausgaben im Oktober 2025 von Tag zu Tag entwickel - wrong figures
- `g001-area` Plot my cumulative income over 2025 month by month as an area chart. - The query behind the chart returned no rows, so there is nothing to draw.
- `g003-area` Zeig die aufgelaufenen Ausgaben fuer Wohnen ueber das Jahr 2025 als Fl - wrong figures
- `g001-bar_stacked` Show what I spent on Housing and Subscriptions per quarter in 2025 as  - wrong figures
- `g001-sankey` Zeig mir fuer Q4 2025 als Sankey-Diagramm, wie mein Einkommen in die e - wrong figures
- `g002-sankey` Where did my income go in November 2025? Give me a visual breakdown of - The chart could not be drawn from these rows: 11 rows carry no positive figure in total_eur. Every flow is a p
- `35-this-month-versus-last-en` Compare this month with last month by category. - wrong figures
- `41-cumulative-halves-en` Compare how my spending added up over the first half of 2025 and over  - wrong figures
