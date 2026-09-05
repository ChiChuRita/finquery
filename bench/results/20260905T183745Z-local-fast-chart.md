### local:fast on the chart set

63 datapoints, 2026-09-05T18:37:45+00:00, 2527.5 s in total, 40.1 s per datapoint, median 36.0 s, p90 60.1 s.

| | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 63 | 48 % | 100 % | 86 % | 86 % | 92 % | 73 % | 46 % | 36.0 |
| area | 6 | 0 % | 100 % | 100 % | 83 % | 83 % | 50 % | 0 % | 46.8 |
| bar | 15 | 67 % | 100 % | 87 % | 87 % | 93 % | 87 % | 80 % | 29.8 |
| bar_grouped | 6 | 17 % | 100 % | 33 % | 100 % | 100 % | 100 % | 17 % | 44.5 |
| bar_horizontal | 6 | 83 % | 100 % | 100 % | 100 % | 100 % | 83 % | 67 % | 30.2 |
| bar_stacked | 6 | 33 % | 100 % | 50 % | 100 % | 83 % | 83 % | 33 % | 42.4 |
| doughnut | 8 | 38 % | 100 % | 100 % | 62 % | 75 % | 12 % | 12 % | 57.3 |
| line | 10 | 90 % | 100 % | 100 % | 90 % | 100 % | 90 % | 60 % | 30.4 |
| sankey | 6 | 0 % | 100 % | 100 % | 67 % | 100 % | 67 % | 50 % | 44.5 |
| difficulty 1 | 4 | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 100 % | 29.8 |
| difficulty 2 | 39 | 51 % | 100 % | 85 % | 87 % | 90 % | 69 % | 41 % | 36.2 |
| difficulty 3 | 20 | 30 % | 100 % | 85 % | 80 % | 95 % | 75 % | 45 % | 42.4 |

Missed (33):

- `03-cumulative-area-en` Chart my cumulative spending over 2025 as an area chart. - The chart could not be drawn: 3 attempts failed the self-check, last reason: - This mark rests on zero by itse
- `04-cumulative-area-de` Zeig die kumulierten Ausgaben 2025 als Flaechendiagramm. - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The code threw TypeError: not a
- `09-quarter-groups-en` Compare what I spent on groceries and on dining per quarter in 2025 as - wrong figures
- `10-quarter-groups-de` Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte - wrong figures
- `14-doughnut-merchants-de` Zeig den Anteil der groessten Haendler an meinen Ausgaben 2025 als Don - The chart could not be drawn: 3 attempts failed the self-check, last reason: - `radialArc` reads the column "m
- `15-sankey-income-en` Draw a sankey of my 2025 income flowing into the spending categories. - The query behind the chart returned no rows, so there is nothing to draw.
- `16-sankey-income-de` Zeig als Sankey, wie mein Einkommen 2025 in die Ausgabenkategorien fli - wrong figures
- `18-two-months-de` Vergleiche meine Ausgaben im Januar 2025 mit denen im Juli 2025 als Di - wrong figures
- `23-income-versus-spending-en` Chart my income and my spending per month in 2025 side by side. - wrong figures
- `25-doughnut-supermarkets-de` Zeig als Donut, wie sich meine Lebensmittelausgaben 2025 auf die einze - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `26-sankey-subcategories-en` Draw a sankey of how my 2025 spending flows from its categories into t - wrong figures
- `27-needs-review-bar-de` Zeig mir als Diagramm, wie viel von meinen Ausgaben 2025 kategorisiert - wrong figures
- `28-friends-doughnut-de` Wie verteilen sich meine PayPal-Zahlungen an Freunde 2025? Zeig es als - The query behind the chart returned no rows, so there is nothing to draw.
- `30-groceries-stacked-quarters-en` Show my grocery spending per quarter in 2025, split into supermarket,  - wrong figures
- `31-groceries-area-de` Zeig die kumulierten Lebensmittelausgaben 2025 als Flaechendiagramm. - wrong figures
- `g002-bar` Give me a breakdown of what I spent at supermarkets in 2025. - wrong figures
- `g003-bar` Show how much each subscription service cost me in 2025. - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The code does not compile: Synt
- `g007-bar` Give me a breakdown of my spending across categories in Q3 2025. - wrong figures
- `g003-line` Zeig mir den Verlauf meiner Fahrt- und Transportkosten pro Quartal im  - The query was refused 2 times, last reason: near ".3": syntax error
- `g001-area` Plot my cumulative income over 2025 month by month as an area chart. - wrong figures
- `g002-area` Wie haben sich meine Ausgaben im Jahr 2025 Quartal fuer Quartal aufsum - The query was refused 2 times, last reason: SQLite cannot parse this: Error tokenizing 'AND '2025-12-31' GROUP
- `g003-area` Zeig die aufgelaufenen Ausgaben fuer Wohnen ueber das Jahr 2025 als Fl - wrong figures
- `g001-doughnut` Wie teilen sich meine Ausgaben fuer Gastronomie im vierten Quartal 202 - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `g004-doughnut` Show the breakdown of my 2025 grocery spending by subcategory as a dou - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `g001-bar_horizontal` Show my top 8 merchants by spending in Q4 2025 as a horizontal bar cha - wrong figures
- `g002-bar_grouped` Compare my quarterly expenses for Groceries, Dining, and Transport acr - wrong figures
- `g003-bar_grouped` Vergleiche meine Barauszahlungen mit den Shopping-Ausgaben in den Mona - wrong figures
- `g001-bar_stacked` Show what I spent on Housing and Subscriptions per quarter in 2025 as  - wrong figures
- `g002-bar_stacked` Stacked bar chart of my Transport spending by subcategory for each mon - The chart could not be drawn: 3 attempts failed the self-check, last reason: - This mark rests on zero by itse
- `g003-bar_stacked` Zeig meine Restaurant- und Lieferdienstausgaben (Dining) nach Unterkat - wrong figures
- `g001-sankey` Zeig mir fuer Q4 2025 als Sankey-Diagramm, wie mein Einkommen in die e - wrong figures
- `g002-sankey` Where did my income go in November 2025? Give me a visual breakdown of - wrong figures
- `g003-sankey` Stelle als Sankey dar, wie sich meine Ausgaben fuer Subscriptions 2025 - The chart could not be drawn from these rows: One row carries no positive figure in amount_eur. Every flow is 
