# The three local candidates on the HPI cluster

Gemma 4 E4B, Qwen3.5 9B and Gemma 4 12B, Q4_K_M through llama-cpp with CUDA, one RTX PRO 6000
per job, 32k context, the same wire formats and the same sub-agent paths the laptop runs. The
seconds are seconds on that one GPU, which is not the laptop's: the tokens per second table
below is what the laptop costs.

The SQL and chart tables are the primary numbers: they score the sub-agent, which is where an
adapter attaches. The end-to-end table runs the whole chat turn in front of the sub-agent on 30
training cases, so the gap between the two is routing and phrasing loss.

### sql set

| model | n | figure match | SQL valid | first attempt | median s | total s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 152 | 66 % | 99 % | 75 % | 8.2 | 1431 |
| local:qwen3.5-9b | 152 | 70 % | 97 % | 30 % | 25.4 | 5216 |
| local:gemma-4-12b | 152 | 87 % | 99 % | 82 % | 10.0 | 1871 |


### local:gemma-4-e4b vs local:qwen3.5-9b on the sql set

| | figure match | SQL valid | first attempt | median s | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 66 % | 99 % | 75 % | 8.2 | 152 |
| local:qwen3.5-9b | 70 % | 97 % | 30 % | 25.4 | 152 |

152 datapoints in both runs: 87 right in both, 31 wrong in both, 20 only right in local:qwen3.5-9b, 14 only right in local:gemma-4-e4b.

Only local:qwen3.5-9b gets right:

- `g001-comparison` Compare my spending on Dining between Q1 and Q2 2025.
- `g001-entity` Wie viel habe ich 2025 fuer Fitness First ausgegeben?
- `g003-breakdown` Zeige mir eine Aufschluesselung meiner Einnahmen im Jahr 2025 nach Subkategorie 
- `g003-comparison` Compare my spending on Public transport versus Ride hailing in 2025.
- `g005-entity` How many times did I order from Lieferando in 2025, and what was the average ord
- `g006-trend` How did my monthly spending on dining out develop in the second quarter of 2025?
- `g007-follow-up` Und wie oft war ich dort einkaufen?
- `g008-follow-up` Split that by month.
- `g010-total` What was my total spending on Spotify and Netflix combined in 2025?
- `s06-groceries-per-week-de` Was habe ich 2025 im Schnitt pro Woche fuer Lebensmittel ausgegeben, auf 52 Woch
- `s13-per-category-de` Wie viel habe ich 2025 pro Kategorie ausgegeben?
- `s16-supermarkets-de` Wie verteilen sich meine Lebensmittelausgaben auf die einzelnen Laeden?
- `s18-needs-review-merchants-de` Welche Haendler stecken in 'Needs review', und wie viele Buchungen sind das jewe
- `s19-per-quarter-en` How much did I spend per quarter in 2025?
- `s22-account-months-de` Zeig mir pro Monat, wie viele Ausgaben ich hatte und was sie zusammen gekostet h
- `s29-rent-constant-de` Ist meine Miete im Laufe des Jahres gestiegen?
- `s48-rewe-and-edeka-de` Wie viel bei REWE und wie viel bei EDEKA?
- `s51-anna-de` Wie viel habe ich Anna Weber ueberwiesen?
- `s55-netflix-de` Was kostet mich Netflix im Jahr?
- `s64-just-supermarkets-en` Show me just the supermarkets.

Only local:gemma-4-e4b gets right:

- `g002-period` Wie viel Geld habe ich im Oktober 2025 bei ALDI SÜD gelassen?
- `g004-period` Wie viel habe ich im Dezember 2025 fuer die Subkategorie Supermarket bezahlt?
- `g004-ranking` Which 3 merchants did I spend the most at in Groceries during 2025?
- `g004-trend` Wie hoch waren meine monatlichen Ausgaben fuer Drogerien im Jahr 2025?
- `g006-total` How much did I spend at Aldi in the first quarter of 2025?
- `g007-entity` How much did I spend at Cafe Milchbart in 2025, and when was the last visit?
- `g008-period` Wie hoch waren meine Ausgaben im Zeitraum vom 15. August 2025 bis zum 15. Septem
- `g009-period` How much did I spend in total between 2025-02-01 and 2025-04-30 excluding Housin
- `s09-this-quarter-en` What did I spend this quarter?
- `s31-per-month-en` How much did I spend per month in 2025?
- `s33-groceries-trend-en` Is my grocery spending going up?
- `s47-edeka-en` How much did I spend at Edeka in 2025?
- `s56-all-subscriptions-en` What do all my subscriptions cost me per year?
- `s75-summer-en` How much did I spend over the summer?


### local:gemma-4-e4b vs local:gemma-4-12b on the sql set

| | figure match | SQL valid | first attempt | median s | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 66 % | 99 % | 75 % | 8.2 | 152 |
| local:gemma-4-12b | 87 % | 99 % | 82 % | 10.0 | 152 |

152 datapoints in both runs: 97 right in both, 16 wrong in both, 35 only right in local:gemma-4-12b, 4 only right in local:gemma-4-e4b.

Only local:gemma-4-12b gets right:

- `g001-comparison` Compare my spending on Dining between Q1 and Q2 2025.
- `g001-entity` Wie viel habe ich 2025 fuer Fitness First ausgegeben?
- `g003-breakdown` Zeige mir eine Aufschluesselung meiner Einnahmen im Jahr 2025 nach Subkategorie 
- `g003-comparison` Compare my spending on Public transport versus Ride hailing in 2025.
- `g003-ranking` Bei welchen 5 Geschaeften oder Dienstleistern hatte ich 2025 die meisten Abbuchu
- `g003-trend` Show my monthly spending across 2025 excluding Housing.
- `g004-comparison` Vergleiche die Supermarkt-Ausgaben im dritten Quartal mit dem vierten Quartal 20
- `g004-follow-up` And on Groceries?
- `g005-entity` How many times did I order from Lieferando in 2025, and what was the average ord
- `g006-follow-up` What was the single biggest one?
- `g006-trend` How did my monthly spending on dining out develop in the second quarter of 2025?
- `g007-ranking` Welche 5 Haendler hatten 2025 den hoechsten Durchschnittsbetrag pro Buchung, bei
- `g009-ranking` What were my top 3 largest supermarket purchases in 2025?
- `g010-entity` Was war mein teuerster und mein guenstigster Einkauf bei Lidl im Jahr 2025?
- `g010-total` What was my total spending on Spotify and Netflix combined in 2025?
- `s04-rent-total-de` Wie viel Miete habe ich 2025 insgesamt gezahlt?
- `s06-groceries-per-week-de` Was habe ich 2025 im Schnitt pro Woche fuer Lebensmittel ausgegeben, auf 52 Woch
- `s13-per-category-de` Wie viel habe ich 2025 pro Kategorie ausgegeben?
- `s16-supermarkets-de` Wie verteilen sich meine Lebensmittelausgaben auf die einzelnen Laeden?
- `s18-needs-review-merchants-de` Welche Haendler stecken in 'Needs review', und wie viele Buchungen sind das jewe
- `s19-per-quarter-en` How much did I spend per quarter in 2025?
- `s22-account-months-de` Zeig mir pro Monat, wie viele Ausgaben ich hatte und was sie zusammen gekostet h
- `s35-net-per-month-en` What is my net per month, income minus spending?
- `s40-biggest-expense-en` What was my biggest single expense in 2025?
- `s44-most-visited-supermarkets-en` Which three supermarkets did I shop at most often?
- `s45-biggest-without-rent-de` Wer hat 2025 am meisten Geld von mir bekommen, ohne die Miete?
- `s51-anna-de` Wie viel habe ich Anna Weber ueberwiesen?
- `s54-last-rent-en` When was my last rent payment and how much was it?
- `s55-netflix-de` Was kostet mich Netflix im Jahr?
- `s57-refunds-en` Did I get any refunds in 2025?
- `s59-bakery-de` Wie oft war ich 2025 beim Baecker und was habe ich dort gelassen?
- `s64-just-supermarkets-en` Show me just the supermarkets.
- `s66-cheapest-month-en` Which of those months was the cheapest?
- `s67-without-rent-de` Und ohne die Miete?
- `s68-by-merchant-en` Break that down by merchant.

Only local:gemma-4-e4b gets right:

- `s11-supermarket-october-en` How much did I spend at the supermarket in October?
- `s33-groceries-trend-en` Is my grocery spending going up?
- `s58-friends-total-de` Wie viel Geld habe ich 2025 insgesamt an Freunde per PayPal geschickt?
- `s77-rambling-en` I am trying to work out where the money went last year, so could you tell me wha


### chart set

| model | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | total s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 73 | 45 % | 100 % | 85 % | 89 % | 99 % | 90 % | 77 % | 34.9 | 2991 |
| local:qwen3.5-9b | 73 | 42 % | 100 % | 89 % | 78 % | 94 % | 78 % | 55 % | 45.1 | 4084 |
| local:gemma-4-12b | 73 | 81 % | 100 % | 96 % | 85 % | 99 % | 94 % | 92 % | 46.7 | 3645 |


### local:gemma-4-e4b vs local:qwen3.5-9b on the chart set

| | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | n |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 45 % | 100 % | 85 % | 89 % | 99 % | 90 % | 77 % | 34.9 | 73 |
| local:qwen3.5-9b | 42 % | 100 % | 89 % | 78 % | 94 % | 78 % | 55 % | 45.1 | 73 |

73 datapoints in both runs: 20 right in both, 29 wrong in both, 11 only right in local:qwen3.5-9b, 13 only right in local:gemma-4-e4b.

Only local:qwen3.5-9b gets right:

- `17-two-halves-en` Compare my total spending in the first half of 2025 with the second half in a ch
- `19-quarters-en` Chart my spending per quarter in 2025.
- `24-net-per-month-de` Zeig den monatlichen Saldo 2025, also Einnahmen minus Ausgaben, als Diagramm.
- `29-daily-december-line-de` Zeig meine taeglichen Ausgaben im Dezember 2025 als Liniendiagramm.
- `35-this-month-versus-last-en` Compare this month with last month by category.
- `37-change-per-month-en` Show me for each month of 2025 how much more or less I spent than the month befo
- `g002-bar_grouped` Compare my quarterly expenses for Groceries, Dining, and Transport across 2025 s
- `g002-line` Plot my daily spending in November 2025 as a line chart.
- `g003-line` Zeig mir den Verlauf meiner Fahrt- und Transportkosten pro Quartal im Jahr 2025.
- `g005-bar` Compare my spending across categories in November 2025.
- `g007-bar` Give me a breakdown of my spending across categories in Q3 2025.

Only local:gemma-4-e4b gets right:

- `16-sankey-income-de` Zeig als Sankey, wie mein Einkommen 2025 in die Ausgabenkategorien fliesst.
- `21-groceries-months-en` Show what I spent on groceries per month in 2025.
- `32-top-merchants-half-en` Which five merchants took the most money in the second half of 2025? Show them a
- `33-grocery-lines-de` Wie viel habe ich 2025 pro Monat bei Rewe, Edeka, Lidl, Aldi und dm ausgegeben, 
- `g001-bar` Vergleiche meine Ausgaben in diesem Quartal nach Kategorie als Balkendiagramm.
- `g002-bar_stacked` Stacked bar chart of my Transport spending by subcategory for each month in the 
- `g002-doughnut` Stelle meine Transportausgaben 2025 nach Unterkategorien als Ringdiagramm dar.
- `g003-bar_grouped` Vergleiche meine Barauszahlungen mit den Shopping-Ausgaben in den Monaten von Ok
- `g003-bar_horizontal` Rank my top 5 merchants in November 2025 by total spending.
- `g003-doughnut` How was my spending split across my top categories last month?
- `g004-bar` Vergleiche meine Dining-Ausgaben 2025 nach Subkategorie als Balkendiagramm.
- `g004-doughnut` Show the breakdown of my 2025 grocery spending by subcategory as a doughnut char
- `g005-line` Wie haben sich meine Ausgaben im Oktober 2025 von Tag zu Tag entwickelt?


### local:gemma-4-e4b vs local:gemma-4-12b on the chart set

| | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | n |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 45 % | 100 % | 85 % | 89 % | 99 % | 90 % | 77 % | 34.9 | 73 |
| local:gemma-4-12b | 81 % | 100 % | 96 % | 85 % | 99 % | 94 % | 92 % | 46.7 | 73 |

73 datapoints in both runs: 32 right in both, 13 wrong in both, 27 only right in local:gemma-4-12b, 1 only right in local:gemma-4-e4b.

Only local:gemma-4-12b gets right:

- `03-cumulative-area-en` Chart my cumulative spending over 2025 as an area chart.
- `04-cumulative-area-de` Zeig die kumulierten Ausgaben 2025 als Flaechendiagramm.
- `09-quarter-groups-en` Compare what I spent on groceries and on dining per quarter in 2025 as grouped b
- `10-quarter-groups-de` Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte Balken.
- `15-sankey-income-en` Draw a sankey of my 2025 income flowing into the spending categories.
- `19-quarters-en` Chart my spending per quarter in 2025.
- `23-income-versus-spending-en` Chart my income and my spending per month in 2025 side by side.
- `24-net-per-month-de` Zeig den monatlichen Saldo 2025, also Einnahmen minus Ausgaben, als Diagramm.
- `25-doughnut-supermarkets-de` Zeig als Donut, wie sich meine Lebensmittelausgaben 2025 auf die einzelnen Maerk
- `27-needs-review-bar-de` Zeig mir als Diagramm, wie viel von meinen Ausgaben 2025 kategorisiert ist und w
- `28-friends-doughnut-de` Wie verteilen sich meine PayPal-Zahlungen an Freunde 2025? Zeig es als Donut.
- `29-daily-december-line-de` Zeig meine taeglichen Ausgaben im Dezember 2025 als Liniendiagramm.
- `31-groceries-area-de` Zeig die kumulierten Lebensmittelausgaben 2025 als Flaechendiagramm.
- `36-this-month-versus-last-de` Vergleiche diesen Monat mit dem letzten Monat nach Kategorie.
- `37-change-per-month-en` Show me for each month of 2025 how much more or less I spent than the month befo
- `38-change-per-month-de` Zeig mir für jeden Monat 2025, wie viel mehr oder weniger ich als im Monat davor
- `42-cumulative-halves-de` Vergleiche, wie sich meine Ausgaben im ersten und im zweiten Halbjahr 2025 aufsu
- `g001-bar_horizontal` Show my top 8 merchants by spending in Q4 2025 as a horizontal bar chart.
- `g002-area` Wie haben sich meine Ausgaben im Jahr 2025 Quartal fuer Quartal aufsummiert? Zei
- `g002-bar` Give me a breakdown of what I spent at supermarkets in 2025.
- `g002-bar_grouped` Compare my quarterly expenses for Groceries, Dining, and Transport across 2025 s
- `g002-bar_horizontal` Welche Streaming- und Abo-Dienste haben mich 2025 am meisten gekostet? Zeig mir 
- `g002-line` Plot my daily spending in November 2025 as a line chart.
- `g003-bar_stacked` Zeig meine Restaurant- und Lieferdienstausgaben (Dining) nach Unterkategorie pro
- `g003-line` Zeig mir den Verlauf meiner Fahrt- und Transportkosten pro Quartal im Jahr 2025.
- `g003-sankey` Stelle als Sankey dar, wie sich meine Ausgaben fuer Subscriptions 2025 auf die e
- `g005-bar` Compare my spending across categories in November 2025.

Only local:gemma-4-e4b gets right:

- `g005-line` Wie haben sich meine Ausgaben im Oktober 2025 von Tag zu Tag entwickelt?


### e2e set

| model | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | total s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 30 | 53 % | 87 % | 93 % | 87 % | 100 % | 87 % | 53 % | 34.3 | 926 |
| local:qwen3.5-9b | 30 | 73 % | 97 % | 87 % | 93 % | 87 % | 93 % | 70 % | 50.8 | 2086 |
| local:gemma-4-12b | 30 | 77 % | 97 % | 100 % | 93 % | 100 % | 100 % | 77 % | 46.9 | 1359 |


### local:gemma-4-e4b vs local:qwen3.5-9b on the e2e set

| | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | n |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 53 % | 87 % | 93 % | 87 % | 100 % | 87 % | 53 % | 34.3 | 30 |
| local:qwen3.5-9b | 73 % | 97 % | 87 % | 93 % | 87 % | 93 % | 70 % | 50.8 | 30 |

30 datapoints in both runs: 13 right in both, 5 wrong in both, 9 only right in local:qwen3.5-9b, 3 only right in local:gemma-4-e4b.

Only local:qwen3.5-9b gets right:

- `10-quarter-groups-de` Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte Balken.
- `26-sankey-subcategories-en` Draw a sankey of how my 2025 spending flows from its categories into their subca
- `g001-area` Plot my cumulative income over 2025 month by month as an area chart.
- `g001-doughnut` Wie teilen sich meine Ausgaben fuer Gastronomie im vierten Quartal 2025 auf? Bit
- `g002-breakdown` Break down my transport spending by subcategory in 2025.
- `g002-line` Plot my daily spending in November 2025 as a line chart.
- `g009-entity` How much did I spend at Dean and David per month in 2025?
- `s23-may-vs-april-en` Compare my spending in May 2025 with April 2025.
- `s69-last-month-en` How much did I spend last month?

Only local:gemma-4-e4b gets right:

- `g003-bar_stacked` Zeig meine Restaurant- und Lieferdienstausgaben (Dining) nach Unterkategorie pro
- `g003-ranking` Bei welchen 5 Geschaeften oder Dienstleistern hatte ich 2025 die meisten Abbuchu
- `g004-entity` Wie oft war ich 2025 bei ALDI SÜD einkaufen und was war der Gesammtbetrag?


### local:gemma-4-e4b vs local:gemma-4-12b on the e2e set

| | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | n |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| local:gemma-4-e4b | 53 % | 87 % | 93 % | 87 % | 100 % | 87 % | 53 % | 34.3 | 30 |
| local:gemma-4-12b | 77 % | 97 % | 100 % | 93 % | 100 % | 100 % | 77 % | 46.9 | 30 |

30 datapoints in both runs: 13 right in both, 4 wrong in both, 10 only right in local:gemma-4-12b, 3 only right in local:gemma-4-e4b.

Only local:gemma-4-12b gets right:

- `10-quarter-groups-de` Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte Balken.
- `25-doughnut-supermarkets-de` Zeig als Donut, wie sich meine Lebensmittelausgaben 2025 auf die einzelnen Maerk
- `26-sankey-subcategories-en` Draw a sankey of how my 2025 spending flows from its categories into their subca
- `g001-area` Plot my cumulative income over 2025 month by month as an area chart.
- `g001-doughnut` Wie teilen sich meine Ausgaben fuer Gastronomie im vierten Quartal 2025 auf? Bit
- `g002-breakdown` Break down my transport spending by subcategory in 2025.
- `g002-line` Plot my daily spending in November 2025 as a line chart.
- `g009-entity` How much did I spend at Dean and David per month in 2025?
- `s22-account-months-de` Zeig mir pro Monat, wie viele Ausgaben ich hatte und was sie zusammen gekostet h
- `s23-may-vs-april-en` Compare my spending in May 2025 with April 2025.

Only local:gemma-4-e4b gets right:

- `g003-ranking` Bei welchen 5 Geschaeften oder Dienstleistern hatte ich 2025 die meisten Abbuchu
- `g004-entity` Wie oft war ich 2025 bei ALDI SÜD einkaufen und was war der Gesammtbetrag?
- `s63-per-week-de` Und pro Woche?


## What each pair costs on the laptop

From `bench/results/20260906-local-tokens-per-second.md`, measured on the user's Mac with
Metal. The fast slot is Gemma 4 E4B either way, so the pair is E4B plus the chat model.

| pair | generation | prompt processing | both models at 32k |
| --- | ---: | ---: | ---: |
| E4B alone | 46.7 tok/s | 545 tok/s | 5.9 GB |
| E4B + Qwen3.5 9B | 29.5 tok/s | 329 tok/s | 13.5 GB |
| E4B + Gemma 4 12B | 22.4 tok/s | 205 tok/s | 12.9 GB |

## The decision rule

Accuracy first: the pair is the one with the highest figure match on the SQL set, then on the
chart set. Speed breaks a tie only inside about five points. The pair has to fit in about
13.5 GB, which is what the 24 GB Mac has left for weights and KV cache with both models
resident, so a pair that does not fit is not a candidate whatever it scores.
