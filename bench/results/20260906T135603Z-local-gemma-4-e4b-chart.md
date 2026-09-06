### local:gemma-4-e4b on the chart set

73 datapoints, 2026-09-06T13:56:03+00:00, 2990.9 s in total, 41.0 s per datapoint, median 34.9 s, p90 61.6 s.

| | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 73 | 45 % | 100 % | 85 % | 89 % | 99 % | 90 % | 77 % | 34.9 |
| area | 8 | 0 % | 100 % | 75 % | 75 % | 88 % | 88 % | 88 % | 34.7 |
| bar | 17 | 35 % | 100 % | 88 % | 88 % | 100 % | 88 % | 76 % | 31.6 |
| bar_grouped | 8 | 25 % | 100 % | 50 % | 88 % | 100 % | 88 % | 38 % | 55.8 |
| bar_horizontal | 6 | 67 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 29.4 |
| bar_stacked | 6 | 50 % | 100 % | 50 % | 100 % | 100 % | 83 % | 67 % | 38.0 |
| doughnut | 8 | 75 % | 100 % | 100 % | 88 % | 100 % | 75 % | 75 % | 31.5 |
| line | 14 | 71 % | 100 % | 100 % | 86 % | 100 % | 100 % | 86 % | 34.9 |
| sankey | 6 | 33 % | 100 % | 100 % | 100 % | 100 % | 100 % | 83 % | 53.0 |
| difficulty 1 | 4 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 29.5 |
| difficulty 2 | 39 | 44 % | 100 % | 85 % | 90 % | 100 % | 95 % | 80 % | 31.6 |
| difficulty 3 | 30 | 40 % | 100 % | 83 % | 87 % | 97 % | 83 % | 70 % | 41.5 |

Missed (40):

- `03-cumulative-area-en` Chart my cumulative spending over 2025 as an area chart. - wrong figures
- `04-cumulative-area-de` Zeig die kumulierten Ausgaben 2025 als Flaechendiagramm. - wrong figures
- `09-quarter-groups-en` Compare what I spent on groceries and on dining per quarter in 2025 as - wrong figures
- `10-quarter-groups-de` Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte - wrong figures
- `15-sankey-income-en` Draw a sankey of my 2025 income flowing into the spending categories. - wrong figures
- `17-two-halves-en` Compare my total spending in the first half of 2025 with the second ha - wrong figures
- `18-two-months-de` Vergleiche meine Ausgaben im Januar 2025 mit denen im Juli 2025 als Di - The query was refused 2 times, last reason: no such column: T.topic
- `19-quarters-en` Chart my spending per quarter in 2025. - wrong figures
- `23-income-versus-spending-en` Chart my income and my spending per month in 2025 side by side. - wrong figures
- `24-net-per-month-de` Zeig den monatlichen Saldo 2025, also Einnahmen minus Ausgaben, als Di - wrong figures
- `25-doughnut-supermarkets-de` Zeig als Donut, wie sich meine Lebensmittelausgaben 2025 auf die einze - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `27-needs-review-bar-de` Zeig mir als Diagramm, wie viel von meinen Ausgaben 2025 kategorisiert - wrong figures
- `28-friends-doughnut-de` Wie verteilen sich meine PayPal-Zahlungen an Freunde 2025? Zeig es als - The query behind the chart returned no rows, so there is nothing to draw.
- `29-daily-december-line-de` Zeig meine taeglichen Ausgaben im Dezember 2025 als Liniendiagramm. - wrong figures
- `30-groceries-stacked-quarters-en` Show my grocery spending per quarter in 2025, split into supermarket,  - wrong figures
- `31-groceries-area-de` Zeig die kumulierten Lebensmittelausgaben 2025 als Flaechendiagramm. - wrong figures
- `g002-bar` Give me a breakdown of what I spent at supermarkets in 2025. - wrong figures
- `g003-bar` Show how much each subscription service cost me in 2025. - wrong figures
- `g005-bar` Compare my spending across categories in November 2025. - wrong figures
- `g007-bar` Give me a breakdown of my spending across categories in Q3 2025. - wrong figures
- `g002-line` Plot my daily spending in November 2025 as a line chart. - wrong figures
- `g003-line` Zeig mir den Verlauf meiner Fahrt- und Transportkosten pro Quartal im  - wrong figures
- `g004-line` Stelle meine Monatsausgaben bei Amazon 2025 als Liniengrafik dar. - wrong figures
- `g001-area` Plot my cumulative income over 2025 month by month as an area chart. - wrong figures
- `g002-area` Wie haben sich meine Ausgaben im Jahr 2025 Quartal fuer Quartal aufsum - The chart could not be drawn: 3 attempts failed the self-check, last reason: - `barY` reads the column "dummy_
- `g003-area` Zeig die aufgelaufenen Ausgaben fuer Wohnen ueber das Jahr 2025 als Fl - wrong figures
- `g001-bar_horizontal` Show my top 8 merchants by spending in Q4 2025 as a horizontal bar cha - wrong figures
- `g002-bar_horizontal` Welche Streaming- und Abo-Dienste haben mich 2025 am meisten gekostet? - wrong figures
- `g002-bar_grouped` Compare my quarterly expenses for Groceries, Dining, and Transport acr - wrong figures
- `g001-bar_stacked` Show what I spent on Housing and Subscriptions per quarter in 2025 as  - wrong figures
- `g003-bar_stacked` Zeig meine Restaurant- und Lieferdienstausgaben (Dining) nach Unterkat - The chart sub-agent did not return code: Exceeded maximum output retries (1)
- `g001-sankey` Zeig mir fuer Q4 2025 als Sankey-Diagramm, wie mein Einkommen in die e - wrong figures
- `g002-sankey` Where did my income go in November 2025? Give me a visual breakdown of - wrong figures
- `g003-sankey` Stelle als Sankey dar, wie sich meine Ausgaben fuer Subscriptions 2025 - wrong figures
- `35-this-month-versus-last-en` Compare this month with last month by category. - wrong figures
- `36-this-month-versus-last-de` Vergleiche diesen Monat mit dem letzten Monat nach Kategorie. - The query was refused 2 times, last reason: no such column: T1.topic
- `37-change-per-month-en` Show me for each month of 2025 how much more or less I spent than the  - wrong figures
- `38-change-per-month-de` Zeig mir für jeden Monat 2025, wie viel mehr oder weniger ich als im M - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The code does not compile: Synt
- `41-cumulative-halves-en` Compare how my spending added up over the first half of 2025 and over  - wrong figures
- `42-cumulative-halves-de` Vergleiche, wie sich meine Ausgaben im ersten und im zweiten Halbjahr  - wrong figures
