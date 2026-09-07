### local:gemma-4-12b+chart on the chart set

302 datapoints, 2026-09-07T06:39:44+00:00, 15716.8 s in total, 52.0 s per datapoint, median 46.1 s, p90 67.1 s.

| | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 302 | 50 % | 100 % | 84 % | 82 % | 98 % | 86 % | 80 % | 46.1 |
| area | 32 | 47 % | 100 % | 97 % | 81 % | 100 % | 81 % | 75 % | 44.8 |
| bar | 59 | 51 % | 100 % | 81 % | 76 % | 98 % | 88 % | 83 % | 43.6 |
| bar_grouped | 31 | 16 % | 100 % | 77 % | 81 % | 100 % | 94 % | 87 % | 52.8 |
| bar_horizontal | 29 | 72 % | 100 % | 93 % | 90 % | 97 % | 90 % | 90 % | 38.7 |
| bar_stacked | 30 | 33 % | 100 % | 70 % | 83 % | 100 % | 90 % | 83 % | 50.0 |
| doughnut | 36 | 56 % | 100 % | 97 % | 94 % | 94 % | 86 % | 81 % | 44.8 |
| line | 59 | 66 % | 100 % | 70 % | 80 % | 98 % | 85 % | 80 % | 44.5 |
| sankey | 26 | 46 % | 100 % | 100 % | 73 % | 100 % | 69 % | 58 % | 62.6 |
| difficulty 1 | 36 | 69 % | 100 % | 81 % | 81 % | 97 % | 92 % | 86 % | 43.2 |
| difficulty 2 | 137 | 59 % | 100 % | 85 % | 90 % | 98 % | 92 % | 90 % | 44.0 |
| difficulty 3 | 129 | 36 % | 100 % | 84 % | 74 % | 99 % | 78 % | 68 % | 50.9 |

Missed (150):

- `09-quarter-groups-en` Compare what I spent on groceries and on dining per quarter in 2025 as - wrong figures
- `10-quarter-groups-de` Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte - wrong figures
- `18-two-months-de` Vergleiche meine Ausgaben im Januar 2025 mit denen im Juli 2025 als Di - wrong figures
- `23-income-versus-spending-en` Chart my income and my spending per month in 2025 side by side. - wrong figures
- `27-needs-review-bar-de` Zeig mir als Diagramm, wie viel von meinen Ausgaben 2025 kategorisiert - wrong figures
- `28-friends-doughnut-de` Wie verteilen sich meine PayPal-Zahlungen an Freunde 2025? Zeig es als - wrong figures
- `30-groceries-stacked-quarters-en` Show my grocery spending per quarter in 2025, split into supermarket,  - The query was refused 2 times, last reason: ORDER BY clause should come after UNION ALL not before
- `33-grocery-lines-de` Wie viel habe ich 2025 pro Monat bei Rewe, Edeka, Lidl, Aldi und dm au - wrong figures
- `g002-bar` Give me a breakdown of what I spent at supermarkets in 2025. - wrong figures
- `g003-bar` Show how much each subscription service cost me in 2025. - wrong figures
- `g007-bar` Give me a breakdown of my spending across categories in Q3 2025. - wrong figures
- `g005-line` Wie haben sich meine Ausgaben im Oktober 2025 von Tag zu Tag entwickel - wrong figures
- `g002-area` Wie haben sich meine Ausgaben im Jahr 2025 Quartal fuer Quartal aufsum - wrong figures
- `g003-doughnut` How was my spending split across my top categories last month? - wrong figures
- `g002-bar_grouped` Compare my quarterly expenses for Groceries, Dining, and Transport acr - wrong figures
- `g001-bar_stacked` Show what I spent on Housing and Subscriptions per quarter in 2025 as  - wrong figures
- `g002-bar_stacked` Stacked bar chart of my Transport spending by subcategory for each mon - wrong figures
- `g003-bar_stacked` Zeig meine Restaurant- und Lieferdienstausgaben (Dining) nach Unterkat - wrong figures
- `g002-sankey` Where did my income go in November 2025? Give me a visual breakdown of - wrong figures
- `35-this-month-versus-last-en` Compare this month with last month by category. - wrong figures
- `36-this-month-versus-last-de` Vergleiche diesen Monat mit dem letzten Monat nach Kategorie. - wrong figures
- `37-change-per-month-en` Show me for each month of 2025 how much more or less I spent than the  - The query was refused 2 times, last reason: misuse of window function LAG()
- `41-cumulative-halves-en` Compare how my spending added up over the first half of 2025 and over  - wrong figures
- `42-cumulative-halves-de` Vergleiche, wie sich meine Ausgaben im ersten und im zweiten Halbjahr  - The query was refused 2 times, last reason: no such column: half
- `t64-c01-shipped-de-003` zeig mal wie sich meine ausgaben ueber 2025 aufsummiert haben - wrong figures
- `t64-c01-shipped-en-004` whats my money actually going to? donut by category please - wrong figures
- `t64-c01-shipped-en-008` sankey pls: where does my salary end up - wrong figures
- `t64-c01-shipped-de-009` kaufland, rewe und aldi pro monat - jeweils eine linie - The query was refused 2 times, last reason: no such column: merchant
- `t64-c01-shipped-en-010` each month, how much more or less did i spend than the month before? b - The query was refused 2 times, last reason: no such column: added_on
- `t64-c03-shipped-en-004` Which merchants are still sitting in Needs review, by how much money? - wrong figures
- `t64-c03-shipped-de-005` Wie setzen sich meine Abos Monat fuer Monat zusammen? - wrong figures
- `t64-c03-shipped-de-007` Zeig mir als Fluss, wohin mein Geld geht, mit den unkategorisierten Bu - The query was refused 2 times, last reason: ORDER BY clause should come after UNION ALL not before
- `t64-c03-shipped-en-008` Draw supermarket, drugstore and bakery spending per month as three lin - wrong figures
- `t64-c03-shipped-de-009` Vergleich meine Lebensmittel-Unterkategorien diesen Monat mit dem letz - wrong figures
- `t64-c04-shipped-en-001` How much do I pay AMAZON EU S.A R.L. each month in 2025? AMAZON PRIME  - wrong figures
- `t64-c04-shipped-en-005` Show me how the PayPal payments add up over 2025. - wrong figures
- `t64-c04-shipped-de-006` Vergleiche als gruppierte Balken, was ich im ersten und im zweiten Hal - wrong figures
- `t64-c04-shipped-en-007` Stack up per month what the takeaway costs me: Doener Haus Kreuzberg,  - wrong figures
- `t64-c04-shipped-de-008` Zeig als Sankey, wie das Gehalt von Mustermann Systems GmbH in meine A - The chart could not be drawn from these rows: 2 rows carry no positive figure in amount_eur. Every flow is a p
- `t64-c04-shipped-de-002` Was habe ich 2025 pro Supermarkt ausgegeben? Auf dem Auszug stehen die - wrong figures
- `t64-c05-shipped-de-001` Wie viel gebe ich im Schnitt pro Woche aus, Monat fuer Monat? - wrong figures
- `t64-c05-shipped-en-002` How much does one grocery run cost me on average, month by month? Draw - The query was refused 2 times, last reason: aggregate functions are not allowed in the GROUP BY clause
- `t64-c05-shipped-de-003` Was war 2025 mein groesster einzelner Lebensmitteleinkauf pro Monat? - The query was refused 2 times, last reason: no such column: month
- `t64-c05-shipped-en-004` Which weekday do my card payments cost the most on average? - The chart could not be drawn from these rows: The 200 rows carry only 52 different values in week, because 51 
- `t64-c05-shipped-de-009` Was kostet mich ein Tag im Monat, und welche Kategorien machen den Tag - The query was refused 2 times, last reason: SQLite cannot parse this: Expecting ). Line 1, Col: 99.
  SELECT m
- `t64-c05-shipped-en-006` Of the places my money goes to at least a dozen times a year, which on - The query was refused 2 times, last reason: no such column: merchant
- `t64-c06-shipped-de-007` Was habe ich 2025 in jedem Monat an Miete gezahlt? - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c06-shipped-de-010` Wie verteilen sich meine Abokosten 2025 auf die einzelnen Dienste? - wrong figures
- `t64-c06-shipped-en-005` Draw the flow of my fixed monthly costs in 2025: from Fixed costs into - The query was refused 2 times, last reason: no such column: target
- `t64-c06-shipped-de-006` Zeig mir, wie sich meine Fixkosten 2025 Monat fuer Monat aufsummiert h - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c06-shipped-de-009` Zeig meine monatlichen Fixkosten 2025 und wo mein Durchschnitt liegt. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c07-shipped-en-002` Show my income and my spending per month in 2025 as two lines. - wrong figures
- `t64-c07-shipped-de-003` Zeig meine Einnahmen pro Quartal 2025 als Balken. - wrong figures
- `t64-c07-shipped-en-004` Show what was left of my salary each month in 2025 and where my averag - wrong figures
- `t64-c07-shipped-en-008` Stack each month of 2025 into what I spent and what stayed on the acco - wrong figures
- `t64-c07-shipped-de-007` Vergleiche Einnahmen und Ausgaben pro Quartal 2025 nebeneinander. - wrong figures
- `t64-c08-shipped-en-001` Which categories got dearer for me from the first half of 2025 to the  - wrong figures
- `t64-c08-shipped-en-005` Which shops took the most of my money in the second half of 2025? - The query was refused 2 times, last reason: no such column: amount
- `t64-c08-shipped-de-006` Zeig als Flussdiagramm, wohin mein Geld im vierten Quartal 2025 geflos - The query was refused 2 times, last reason: no such column: total_eur
- `t64-c08-shipped-de-008` Stapel mir Lebensmittel, Transport und Essengehen pro Quartal 2025 ueb - The query was refused 2 times, last reason: SQLite cannot parse this: Expected AS after CAST. Line 1, Col: 80.
- `t64-c08-shipped-de-010` Vergleiche meine Ausgaben Quartal fuer Quartal 2025. - wrong figures
- `t64-c09-shipped-de-005` Wohin fliesst mein Einkommen 2025? Zeig die sechs groessten Ausgabenka - The query was refused 2 times, last reason: no such column: topic
- `t64-c09-shipped-en-006` Compare December 2025 with November across the categories I spend the  - wrong figures
- `t64-c09-shipped-de-007` Vergleiche, wie sich meine Lebensmittel- und meine Transportausgaben 2 - wrong figures
- `t64-c09-shipped-en-008` Show me month by month how my three biggest categories stack up. - wrong figures
- `t64-c09-shipped-en-010` Of everything I spent in December 2025, what share did each category t - The query was refused 2 times, last reason: SQLite cannot parse this: Invalid expression / Unexpected token. L
- `t64-c09-shipped-de-001` Welchen Anteil hat jeder meiner Supermaerkte an meinen Lebensmittelaus - wrong figures
- `t64-c09-shipped-de-003` Zeig mir die sechs kleinsten Ausgabenkategorien 2025 und wo ihr Durchs - wrong figures
- `t64-c10-shipped-en-002` Before the grocery line I had asked for October. Now just show my 2025 - wrong figures
- `t64-c10-shipped-de-007` Wir hatten die Monatslinie und die Kategorien. Zeig mir jetzt, wie sic - wrong figures
- `t64-c10-shipped-en-004` We looked at December, then at November on its own. Put the two months - wrong figures
- `t64-c10-shipped-de-010` Wir hatten die aufsummierte Kurve und die Monatslinie. Jetzt bitte pro - wrong figures
- `t64-c11-shipped-de-003` wie viel hab ich dieses jahr schon verbraten, so aufaddiert? - wrong figures
- `t64-c11-shipped-en-004` what is my money split into? donut pls - wrong figures
- `t64-c11-shipped-de-005` wo liegen wir grad hoeher als im monat davor? bitte kategorie fuer kat - wrong figures
- `t64-c11-shipped-en-006` stack my monthly spending by category for the whole year - wrong figures
- `t64-c11-shipped-en-010` each month, did i spend more or less than the month before? - wrong figures
- `t64-c12-shipped-de-004` Bin ich seit dem Sommer Monat fuer Monat teurer oder billiger geworden - wrong figures
- `t64-c12-shipped-de-008` Stell diesen Monat und den letzten Monat nebeneinander, Kategorie fuer - wrong figures
- `t64-c12-shipped-en-009` Stack what I spent by category for each of the last six months. - wrong figures
- `t64-c12-shipped-en-010` Which shops took the most of my money in the last 90 days? - wrong figures
- `t64-c12-shipped-de-007` Wie verteilen sich meine Supermarkt-Einkaeufe seit dem Sommer auf die  - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c13-shipped-en-004` Which months of 2025 still have money sitting in Needs review, and how - wrong figures
- `t64-c13-shipped-de-005` Wie summieren sich meine Stromkosten ueber 2025 auf? - wrong figures
- `t64-c13-shipped-de-007` Vergleiche die Unterkategorien von Essengehen im ersten und im zweiten - wrong figures
- `t64-c13-shipped-de-009` Welche Unterkategorien haben mich 2025 am meisten gekostet? Bitte als  - wrong figures
- `t64-c13-shipped-en-010` Show how my 2025 spending flows from each category into its subcategor - The query was refused 2 times, last reason: no such column: target
- `t64-c14-shipped-de-002` Bei welchem Supermarkt habe ich 2025 wie viel gelassen? Die Buchungen  - wrong figures
- `t64-c14-shipped-en-003` Which grocery shops take the biggest share of my 2025 food money? Doug - wrong figures
- `t64-c14-shipped-de-004` Wie haben sich meine Amazon-Bestellungen (AMZN Mktp) 2025 aufsummiert? - The query was refused 2 times, last reason: SQLite cannot parse this: Required keyword: 'this' missing for <cl
- `t64-c14-shipped-de-006` Stelle Lebensmittel, Verkehr und Wohnen pro Quartal 2025 nebeneinander - wrong figures
- `t64-c14-shipped-en-009` Month by month in 2025, what went to dm, to Lidl and to the Steinecke  - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c15-shipped-de-001` Wie viel gebe ich eigentlich pro Tag aus? Zeig mir den Tagesschnitt Mo - wrong figures
- `t64-c15-shipped-en-002` Show me the largest single payment of each month in 2025. - wrong figures
- `t64-c15-shipped-en-004` How does an average week of my spending split up by category? Draw a d - wrong figures
- `t64-c15-shipped-de-005` Vergleich bitte: was kostet eine einzelne Buchung im Schnitt pro Kateg - The query was refused 2 times, last reason: no such column: topic
- `t64-c15-shipped-en-006` Break my average daily spending down by category, month by month. - wrong figures
- `t64-c15-shipped-de-007` Bei welchen Haendlern ist mein Durchschnittsbon am hoechsten? Nur die, - wrong figures
- `t64-c15-shipped-en-008` Where does an average week of my money go? Show it as a flow. - wrong figures
- `t64-c15-shipped-en-010` What does an average shopping day cost me, per weekday? - wrong figures
- `t64-c16-shipped-en-001` Show me what I paid in rent every month in 2025. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c16-shipped-en-003` Draw my recurring fixed costs of 2025 by category as bars. - wrong figures
- `t64-c16-shipped-de-006` Wie verteilen sich meine Fixkosten 2025 auf die Kategorien? - wrong figures
- `t64-c16-shipped-en-007` Put this month's fixed costs next to last month's, one group of bars p - wrong figures
- `t64-c16-shipped-de-008` Zeig mir meine monatlichen Fixkosten 2025 gestapelt nach Kategorie. - wrong figures
- `t64-c16-shipped-de-010` Zeig mir als Sankey, wohin mein Einkommen in die Fixkosten fliesst. - wrong figures
- `t64-c17-shipped-de-001` Zeig mir mein Gehalt Monat fuer Monat 2025 als Linie und wo der Durchs - wrong figures
- `t64-c17-shipped-en-002` Put what came in and what went out on one chart, month by month in 202 - wrong figures
- `t64-c17-shipped-de-005` Zeig mir aufsummiert, wie viel 2025 auf mein Konto geflossen ist. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c17-shipped-en-006` Which share of this year's income arrived in which quarter? - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c17-shipped-de-007` Vergleiche Einnahmen und Ausgaben pro Quartal 2025 als gruppierte Balk - The query was refused 2 times, last reason: no such column: topic
- `t64-c17-shipped-en-008` Show me month by month which categories my salary went to. - wrong figures
- `t64-c17-shipped-en-010` Draw a flow from my income into the categories it is spent on. - The query was refused 2 times, last reason: ORDER BY clause should come after UNION ALL not before
- `t64-c18-shipped-en-001` Draw two lines, January to June of 2025 and July to December, so I can - wrong figures
- `t64-c18-shipped-de-002` Stell die Ausgaben aus dem dritten und dem vierten Quartal 2025 je Kat - wrong figures
- `t64-c18-shipped-en-003` Quarter by quarter in 2025, plot the swing up or down against the quar - The query was refused 2 times, last reason: no such column: prev.booked_on
- `t64-c18-shipped-de-004` Wie haben sich meine Ausgaben im vierten Quartal 2025 auf die Kategori - wrong figures
- `t64-c18-shipped-en-005` Draw the running total of each half of 2025 as two bands over the six  - The query was refused 2 times, last reason: ROUND() may not be used as a window function
- `t64-c18-shipped-de-006` Zeig mir pro Quartal 2025 gestapelt, wie sich Lebensmittel, Transport, - wrong figures
- `t64-c18-shipped-en-007` Which categories did I spend more on this month than last month? Rank  - wrong figures
- `t64-c18-shipped-en-009` Show what I spent in each quarter of 2025. - wrong figures
- `t64-c19-shipped-en-004` Take the three categories I spend most on and show each of them per mo - wrong figures
- `t64-c19-shipped-de-007` Welchen Anteil hat jeder Ausgabenbereich an meinem Jahr 2025? Als Ring - wrong figures
- `t64-c19-shipped-en-008` Stack my four biggest spending categories per quarter of 2025 so I see - wrong figures
- `t64-c19-shipped-de-009` Wie summieren sich meine Lebensmittelausgaben 2025 ueber das Jahr auf? - wrong figures
- `t64-c19-shipped-en-010` Put this month next to last month for the six categories I spend most  - wrong figures
- `t64-c20-shipped-en-002` First you gave me the 2025 total, then you listed the categories behin - wrong figures
- `t64-c20-shipped-en-005` We looked at December and then at November. Now compare the two months - wrong figures
- `t64-c20-shipped-de-001` Wir hatten erst die Ausgaben pro Monat und danach die vier groessten K - wrong figures
- `t64-c20-shipped-de-002` Du hast mir das Jahreseinkommen genannt und danach die Ausgaben pro Ka - wrong figures
- `t64-c20-shipped-de-004` Wir hatten die Lebensmittel pro Monat, dann Rewe allein. Jetzt bitte R - The query was refused 2 times, last reason: no such column: merchant
- `t64-c20-shipped-de-005` Nach der Jahressumme und den Lebensmitteln pro Monat: zeig mir, wie si - wrong figures
- `t64-c21-shipped-de-003` was lass ich pro monat beim baecker? - wrong figures
- `t64-c21-shipped-en-004` donut plz: which supermarkets eat my grocery money? - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The code does not compile: Synt
- `t64-c21-shipped-en-008` compare december with november, by category - wrong figures
- `t64-c22-shipped-en-001` Show me how my spending has run month by month year to date. - wrong figures
- `t64-c22-shipped-en-003` Show how my spending has piled up since the summer. - The query was refused 2 times, last reason: ROUND() may not be used as a window function
- `t64-c22-shipped-en-005` Set this quarter against last quarter, category by category. - wrong figures
- `t64-c22-shipped-de-006` Zeig mir die letzten sechs Monate gestapelt nach Kategorie. - wrong figures
- `t64-c22-shipped-de-008` Wohin ist mein Einkommen seit dem Sommer geflossen? - The query was refused 2 times, last reason: no such column: total_eur
- `t64-c22-shipped-de-010` Wie viel mehr oder weniger habe ich seit dem Sommer in jedem Monat geg - The query was refused 2 times, last reason: no such column: booked_on
- `t64-c23-shipped-en-005` Compare Supermarket, Drugstore and Bakery per quarter of 2025 as group - wrong figures
- `t64-c24-shipped-en-001` My statement is full of things like 'AMZN Mktp DE' and 'PP.4711.PP'. W - The query was refused 2 times, last reason: no such function: COERCE
- `t64-c24-shipped-en-004` Where does my salary go? Draw the flow from my income into the spendin - wrong figures
- `t64-c24-shipped-de-005` Was wurde pro Monat bei AMZN Mktp DE abgebucht? - wrong figures
- `t64-c24-shipped-en-006` How does everything I ordered from Amazon add up over the year? - wrong figures
- `t64-c24-shipped-de-007` Stell November und Dezember pro Kategorie nebeneinander. - wrong figures
- `t64-c24-shipped-en-008` Stack what I leave at each supermarket per quarter. - wrong figures
- `t64-c24-shipped-de-009` Was habe ich pro Monat ueber PayPal an Freunde ueberwiesen? - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c24-shipped-en-010` My PayPal lines all read 'PP.4711.PP'. Split those payments by who act - The query behind the chart returned no rows, so there is nothing to draw.
