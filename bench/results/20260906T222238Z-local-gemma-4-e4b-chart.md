### local:gemma-4-e4b on the chart set

302 datapoints, 2026-09-06T22:22:38+00:00, 12050.0 s in total, 39.9 s per datapoint, median 35.3 s, p90 59.8 s.

| | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 302 | 38 % | 100 % | 80 % | 80 % | 96 % | 85 % | 79 % | 35.3 |
| area | 32 | 0 % | 100 % | 84 % | 66 % | 94 % | 91 % | 91 % | 33.7 |
| bar | 59 | 46 % | 100 % | 64 % | 73 % | 97 % | 85 % | 73 % | 34.6 |
| bar_grouped | 31 | 26 % | 100 % | 71 % | 84 % | 90 % | 74 % | 55 % | 45.5 |
| bar_horizontal | 29 | 52 % | 100 % | 93 % | 90 % | 100 % | 100 % | 100 % | 29.7 |
| bar_stacked | 30 | 30 % | 100 % | 60 % | 93 % | 100 % | 97 % | 90 % | 35.9 |
| doughnut | 36 | 39 % | 100 % | 86 % | 94 % | 94 % | 78 % | 72 % | 34.1 |
| line | 59 | 64 % | 100 % | 88 % | 78 % | 97 % | 97 % | 97 % | 36.3 |
| sankey | 26 | 12 % | 100 % | 100 % | 62 % | 100 % | 50 % | 42 % | 38.8 |
| difficulty 1 | 36 | 72 % | 100 % | 81 % | 83 % | 97 % | 83 % | 78 % | 34.6 |
| difficulty 2 | 137 | 40 % | 100 % | 78 % | 82 % | 97 % | 92 % | 86 % | 33.3 |
| difficulty 3 | 129 | 26 % | 100 % | 81 % | 76 % | 95 % | 79 % | 72 % | 37.9 |

Missed (188):

- `03-cumulative-area-en` Chart my cumulative spending over 2025 as an area chart. - wrong figures
- `04-cumulative-area-de` Zeig die kumulierten Ausgaben 2025 als Flaechendiagramm. - wrong figures
- `09-quarter-groups-en` Compare what I spent on groceries and on dining per quarter in 2025 as - wrong figures
- `10-quarter-groups-de` Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte - wrong figures
- `15-sankey-income-en` Draw a sankey of my 2025 income flowing into the spending categories. - The chart could not be drawn from these rows: 11 rows flow from a name into itself (Cash, Communication, Dinin
- `16-sankey-income-de` Zeig als Sankey, wie mein Einkommen 2025 in die Ausgabenkategorien fli - The chart could not be drawn from these rows: One row carries no positive figure in amount_eur. Every flow is 
- `17-two-halves-en` Compare my total spending in the first half of 2025 with the second ha - wrong figures
- `18-two-months-de` Vergleiche meine Ausgaben im Januar 2025 mit denen im Juli 2025 als Di - wrong figures
- `19-quarters-en` Chart my spending per quarter in 2025. - wrong figures
- `20-daily-march-en` Show my spending per day in March 2025 as a line chart. - wrong figures
- `23-income-versus-spending-en` Chart my income and my spending per month in 2025 side by side. - wrong figures
- `25-doughnut-supermarkets-de` Zeig als Donut, wie sich meine Lebensmittelausgaben 2025 auf die einze - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `27-needs-review-bar-de` Zeig mir als Diagramm, wie viel von meinen Ausgaben 2025 kategorisiert - wrong figures
- `28-friends-doughnut-de` Wie verteilen sich meine PayPal-Zahlungen an Freunde 2025? Zeig es als - The query behind the chart returned no rows, so there is nothing to draw.
- `30-groceries-stacked-quarters-en` Show my grocery spending per quarter in 2025, split into supermarket,  - wrong figures
- `31-groceries-area-de` Zeig die kumulierten Lebensmittelausgaben 2025 als Flaechendiagramm. - wrong figures
- `g001-bar` Vergleiche meine Ausgaben in diesem Quartal nach Kategorie als Balkend - wrong figures
- `g002-bar` Give me a breakdown of what I spent at supermarkets in 2025. - wrong figures
- `g003-bar` Show how much each subscription service cost me in 2025. - wrong figures
- `g004-bar` Vergleiche meine Dining-Ausgaben 2025 nach Subkategorie als Balkendiag - wrong figures
- `g007-bar` Give me a breakdown of my spending across categories in Q3 2025. - wrong figures
- `g003-line` Zeig mir den Verlauf meiner Fahrt- und Transportkosten pro Quartal im  - wrong figures
- `g004-line` Stelle meine Monatsausgaben bei Amazon 2025 als Liniengrafik dar. - wrong figures
- `g005-line` Wie haben sich meine Ausgaben im Oktober 2025 von Tag zu Tag entwickel - wrong figures
- `g001-area` Plot my cumulative income over 2025 month by month as an area chart. - wrong figures
- `g002-area` Wie haben sich meine Ausgaben im Jahr 2025 Quartal fuer Quartal aufsum - wrong figures
- `g003-area` Zeig die aufgelaufenen Ausgaben fuer Wohnen ueber das Jahr 2025 als Fl - wrong figures
- `g002-bar_horizontal` Welche Streaming- und Abo-Dienste haben mich 2025 am meisten gekostet? - wrong figures
- `g002-bar_grouped` Compare my quarterly expenses for Groceries, Dining, and Transport acr - wrong figures
- `g001-bar_stacked` Show what I spent on Housing and Subscriptions per quarter in 2025 as  - wrong figures
- `g003-bar_stacked` Zeig meine Restaurant- und Lieferdienstausgaben (Dining) nach Unterkat - wrong figures
- `g001-sankey` Zeig mir fuer Q4 2025 als Sankey-Diagramm, wie mein Einkommen in die e - wrong figures
- `g002-sankey` Where did my income go in November 2025? Give me a visual breakdown of - The query behind the chart returned no rows, so there is nothing to draw.
- `35-this-month-versus-last-en` Compare this month with last month by category. - The query was refused 2 times, last reason: misuse of aliased aggregate total_eur
- `36-this-month-versus-last-de` Vergleiche diesen Monat mit dem letzten Monat nach Kategorie. - The query was refused 2 times, last reason: misuse of aggregate function SUM()
- `37-change-per-month-en` Show me for each month of 2025 how much more or less I spent than the  - wrong figures
- `38-change-per-month-de` Zeig mir für jeden Monat 2025, wie viel mehr oder weniger ich als im M - The query was refused 2 times, last reason: no such column: T2.booked_on
- `41-cumulative-halves-en` Compare how my spending added up over the first half of 2025 and over  - wrong figures
- `42-cumulative-halves-de` Vergleiche, wie sich meine Ausgaben im ersten und im zweiten Halbjahr  - wrong figures
- `t64-c01-shipped-en-002` which months did i blow more than usual on food shopping? bars with my - wrong figures
- `t64-c01-shipped-de-003` zeig mal wie sich meine ausgaben ueber 2025 aufsummiert haben - wrong figures
- `t64-c01-shipped-en-004` whats my money actually going to? donut by category please - wrong figures
- `t64-c01-shipped-en-008` sankey pls: where does my salary end up - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c01-shipped-en-010` each month, how much more or less did i spend than the month before? b - The query was refused 2 times, last reason: SQLite cannot parse this: Invalid expression / Unexpected token. L
- `t64-c01-shipped-de-005` vergleich mal diesen monat mit dem letzten, aufgeteilt nach kategorie  - wrong figures
- `t64-c02-shipped-en-002` What did my spending this quarter split into by category? Draw a dough - wrong figures
- `t64-c02-shipped-en-003` Draw my spending per category since the summer as bars. - wrong figures
- `t64-c02-shipped-en-004` Which merchants took the most of my money in the last 90 days? Draw a  - wrong figures
- `t64-c02-shipped-en-005` Where did my income go this quarter? Draw it as a flow. - wrong figures
- `t64-c02-shipped-de-006` Zeig mir, wie sich meine Ausgaben seit dem Sommer aufsummiert haben. - wrong figures
- `t64-c02-shipped-de-007` Was hat sich je Kategorie zwischen letztem und diesem Monat getan? Bei - wrong figures
- `t64-c02-shipped-de-009` Stapel Lebensmittel, Transport und Essengehen pro Monat im letzten hal - wrong figures
- `t64-c03-shipped-en-002` What share of my groceries went to supermarkets, drugstores and bakeri - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c03-shipped-de-005` Wie setzen sich meine Abos Monat fuer Monat zusammen? - wrong figures
- `t64-c03-shipped-en-006` How does the money in Needs review add up over the year? - wrong figures
- `t64-c03-shipped-de-007` Zeig mir als Fluss, wohin mein Geld geht, mit den unkategorisierten Bu - wrong figures
- `t64-c03-shipped-en-008` Draw supermarket, drugstore and bakery spending per month as three lin - wrong figures
- `t64-c03-shipped-de-009` Vergleich meine Lebensmittel-Unterkategorien diesen Monat mit dem letz - wrong figures
- `t64-c04-shipped-en-005` Show me how the PayPal payments add up over 2025. - wrong figures
- `t64-c04-shipped-de-006` Vergleiche als gruppierte Balken, was ich im ersten und im zweiten Hal - wrong figures
- `t64-c04-shipped-de-008` Zeig als Sankey, wie das Gehalt von Mustermann Systems GmbH in meine A - wrong figures
- `t64-c04-shipped-de-010` Die Baeckerei steht als Baeckerei Steinecke auf dem Auszug. Was hat di - wrong figures
- `t64-c04-shipped-de-002` Was habe ich 2025 pro Supermarkt ausgegeben? Auf dem Auszug stehen die - wrong figures
- `t64-c05-shipped-de-001` Wie viel gebe ich im Schnitt pro Woche aus, Monat fuer Monat? - wrong figures
- `t64-c05-shipped-en-002` How much does one grocery run cost me on average, month by month? Draw - wrong figures
- `t64-c05-shipped-de-003` Was war 2025 mein groesster einzelner Lebensmitteleinkauf pro Monat? - wrong figures
- `t64-c05-shipped-en-008` How does what I pay for eating out add up over the year? - wrong figures
- `t64-c05-shipped-de-009` Was kostet mich ein Tag im Monat, und welche Kategorien machen den Tag - wrong figures
- `t64-c05-shipped-en-006` Of the places my money goes to at least a dozen times a year, which on - wrong figures
- `t64-c06-shipped-en-001` Which of my subscriptions cost me the most in 2025? Draw it as a horiz - wrong figures
- `t64-c06-shipped-en-004` Compare what I paid for insurance, my phone contracts and my subscript - wrong figures
- `t64-c06-shipped-de-007` Was habe ich 2025 in jedem Monat an Miete gezahlt? - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c06-shipped-de-008` Stapel mir pro Monat, was 2025 auf Strom, Versicherung, Handy und Abos - wrong figures
- `t64-c06-shipped-de-010` Wie verteilen sich meine Abokosten 2025 auf die einzelnen Dienste? - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c06-shipped-en-005` Draw the flow of my fixed monthly costs in 2025: from Fixed costs into - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c06-shipped-de-006` Zeig mir, wie sich meine Fixkosten 2025 Monat fuer Monat aufsummiert h - wrong figures
- `t64-c06-shipped-de-009` Zeig meine monatlichen Fixkosten 2025 und wo mein Durchschnitt liegt. - wrong figures
- `t64-c07-shipped-en-002` Show my income and my spending per month in 2025 as two lines. - wrong figures
- `t64-c07-shipped-en-004` Show what was left of my salary each month in 2025 and where my averag - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c07-shipped-de-005` Wie haben sich meine Einnahmen 2025 aufsummiert? - wrong figures
- `t64-c07-shipped-en-006` Which quarter of 2025 brought in what share of my income? Draw it as a - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c07-shipped-en-008` Stack each month of 2025 into what I spent and what stayed on the acco - wrong figures
- `t64-c07-shipped-en-010` Show me where my 2025 income went, from my income into the spending gr - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c07-shipped-de-007` Vergleiche Einnahmen und Ausgaben pro Quartal 2025 nebeneinander. - wrong figures
- `t64-c07-shipped-de-009` Welche Kategorien haben 2025 am meisten von meinem Gehalt aufgebraucht - wrong figures
- `t64-c08-shipped-de-003` In welchen Monaten 2025 habe ich mehr ausgegeben als eingenommen? - wrong figures
- `t64-c08-shipped-de-004` Wie verteilen sich meine Ausgaben im zweiten Halbjahr 2025 auf die Kat - wrong figures
- `t64-c08-shipped-en-005` Which shops took the most of my money in the second half of 2025? - wrong figures
- `t64-c08-shipped-de-006` Zeig als Flussdiagramm, wohin mein Geld im vierten Quartal 2025 geflos - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c08-shipped-en-007` Show me how my spending piled up over 2025. - wrong figures
- `t64-c08-shipped-de-008` Stapel mir Lebensmittel, Transport und Essengehen pro Quartal 2025 ueb - wrong figures
- `t64-c08-shipped-de-010` Vergleiche meine Ausgaben Quartal fuer Quartal 2025. - wrong figures
- `t64-c09-shipped-de-005` Wohin fliesst mein Einkommen 2025? Zeig die sechs groessten Ausgabenka - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c09-shipped-en-006` Compare December 2025 with November across the categories I spend the  - wrong figures
- `t64-c09-shipped-de-007` Vergleiche, wie sich meine Lebensmittel- und meine Transportausgaben 2 - wrong figures
- `t64-c09-shipped-en-010` Of everything I spent in December 2025, what share did each category t - wrong figures
- `t64-c09-shipped-de-001` Welchen Anteil hat jeder meiner Supermaerkte an meinen Lebensmittelaus - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c09-shipped-de-003` Zeig mir die sechs kleinsten Ausgabenkategorien 2025 und wo ihr Durchs - The query was refused 2 times, last reason: ORDER BY clause should come after UNION ALL not before
- `t64-c10-shipped-en-005` After the category bars and the two-month comparison, show me the whol - wrong figures
- `t64-c10-shipped-de-007` Wir hatten die Monatslinie und die Kategorien. Zeig mir jetzt, wie sic - wrong figures
- `t64-c10-shipped-de-009` Vorher ging es um Kategorien und um die Supermaerkte. Jetzt die Haendl - wrong figures
- `t64-c10-shipped-en-004` We looked at December, then at November on its own. Put the two months - wrong figures
- `t64-c10-shipped-de-010` Wir hatten die aufsummierte Kurve und die Monatslinie. Jetzt bitte pro - wrong figures
- `t64-c11-shipped-de-003` wie viel hab ich dieses jahr schon verbraten, so aufaddiert? - wrong figures
- `t64-c11-shipped-en-004` what is my money split into? donut pls - wrong figures
- `t64-c11-shipped-de-005` wo liegen wir grad hoeher als im monat davor? bitte kategorie fuer kat - The query was refused 2 times, last reason: no such column: T1.topic
- `t64-c11-shipped-en-006` stack my monthly spending by category for the whole year - wrong figures
- `t64-c11-shipped-de-007` wo lass ich am meisten geld? top 10 bitte quer - wrong figures
- `t64-c11-shipped-en-008` where does my salary actually go? sankey plz - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c11-shipped-en-010` each month, did i spend more or less than the month before? - wrong figures
- `t64-c12-shipped-de-002` Zeig mir als Linie, was ich in den letzten 30 Tagen Tag fuer Tag ausge - wrong figures
- `t64-c12-shipped-de-004` Bin ich seit dem Sommer Monat fuer Monat teurer oder billiger geworden - wrong figures
- `t64-c12-shipped-de-008` Stell diesen Monat und den letzten Monat nebeneinander, Kategorie fuer - wrong figures
- `t64-c12-shipped-en-009` Stack what I spent by category for each of the last six months. - wrong figures
- `t64-c12-shipped-en-010` Which shops took the most of my money in the last 90 days? - wrong figures
- `t64-c12-shipped-de-007` Wie verteilen sich meine Supermarkt-Einkaeufe seit dem Sommer auf die  - wrong figures
- `t64-c13-shipped-de-003` Vergleiche die Unterkategorien meiner Abos im Jahresverlauf. - wrong figures
- `t64-c13-shipped-de-005` Wie summieren sich meine Stromkosten ueber 2025 auf? - wrong figures
- `t64-c13-shipped-en-010` Show how my 2025 spending flows from each category into its subcategor - wrong figures
- `t64-c14-shipped-de-002` Bei welchem Supermarkt habe ich 2025 wie viel gelassen? Die Buchungen  - wrong figures
- `t64-c14-shipped-en-003` Which grocery shops take the biggest share of my 2025 food money? Doug - wrong figures
- `t64-c14-shipped-de-004` Wie haben sich meine Amazon-Bestellungen (AMZN Mktp) 2025 aufsummiert? - wrong figures
- `t64-c14-shipped-de-006` Stelle Lebensmittel, Verkehr und Wohnen pro Quartal 2025 nebeneinander - wrong figures
- `t64-c14-shipped-en-007` Stack what I spent per quarter of 2025 on groceries, eating out, trans - wrong figures
- `t64-c14-shipped-en-008` Draw me a flow of where my 2025 income ended up. - wrong figures
- `t64-c15-shipped-de-001` Wie viel gebe ich eigentlich pro Tag aus? Zeig mir den Tagesschnitt Mo - wrong figures
- `t64-c15-shipped-en-002` Show me the largest single payment of each month in 2025. - wrong figures
- `t64-c15-shipped-de-003` Zeig mir aufsummiert, wie schnell sich meine Ausgaben ueber das Jahr a - The query was refused 2 times, last reason: misuse of aggregate function SUM()
- `t64-c15-shipped-en-004` How does an average week of my spending split up by category? Draw a d - wrong figures
- `t64-c15-shipped-en-006` Break my average daily spending down by category, month by month. - wrong figures
- `t64-c15-shipped-de-007` Bei welchen Haendlern ist mein Durchschnittsbon am hoechsten? Nur die, - wrong figures
- `t64-c15-shipped-en-008` Where does an average week of my money go? Show it as a flow. - wrong figures
- `t64-c15-shipped-en-010` What does an average shopping day cost me, per weekday? - The chart could not be drawn: 3 attempts failed the self-check, last reason: - `scales.x` is a configured scal
- `t64-c16-shipped-en-001` Show me what I paid in rent every month in 2025. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c16-shipped-en-003` Draw my recurring fixed costs of 2025 by category as bars. - wrong figures
- `t64-c16-shipped-en-005` Show me how my rent added up over 2025. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c16-shipped-de-006` Wie verteilen sich meine Fixkosten 2025 auf die Kategorien? - wrong figures
- `t64-c16-shipped-en-007` Put this month's fixed costs next to last month's, one group of bars p - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A bar_grouped chart separates i
- `t64-c16-shipped-de-008` Zeig mir meine monatlichen Fixkosten 2025 gestapelt nach Kategorie. - wrong figures
- `t64-c16-shipped-en-009` Which payments come off my account every single month? Show a ranking. - wrong figures
- `t64-c16-shipped-de-010` Zeig mir als Sankey, wohin mein Einkommen in die Fixkosten fliesst. - The chart could not be drawn from these rows: 2 rows carry no positive figure in amount_eur. Every flow is a p
- `t64-c17-shipped-de-001` Zeig mir mein Gehalt Monat fuer Monat 2025 als Linie und wo der Durchs - wrong figures
- `t64-c17-shipped-en-002` Put what came in and what went out on one chart, month by month in 202 - wrong figures
- `t64-c17-shipped-de-005` Zeig mir aufsummiert, wie viel 2025 auf mein Konto geflossen ist. - wrong figures
- `t64-c17-shipped-en-006` Which share of this year's income arrived in which quarter? - wrong figures
- `t64-c17-shipped-de-007` Vergleiche Einnahmen und Ausgaben pro Quartal 2025 als gruppierte Balk - wrong figures
- `t64-c17-shipped-en-008` Show me month by month which categories my salary went to. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c17-shipped-de-009` Wohin fliesst mein Gehalt? Zeig die Kategorien als liegende Balken. - wrong figures
- `t64-c17-shipped-en-010` Draw a flow from my income into the categories it is spent on. - wrong figures
- `t64-c18-shipped-en-001` Draw two lines, January to June of 2025 and July to December, so I can - wrong figures
- `t64-c18-shipped-en-003` Quarter by quarter in 2025, plot the swing up or down against the quar - The query was refused 2 times, last reason: misuse of aggregate: SUM()
- `t64-c18-shipped-en-005` Draw the running total of each half of 2025 as two bands over the six  - The chart could not be drawn from these rows: The rows carry 2 pairs of month_of_half and half more than once 
- `t64-c18-shipped-de-006` Zeig mir pro Quartal 2025 gestapelt, wie sich Lebensmittel, Transport, - wrong figures
- `t64-c18-shipped-en-007` Which categories did I spend more on this month than last month? Rank  - wrong figures
- `t64-c18-shipped-en-009` Show what I spent in each quarter of 2025. - wrong figures
- `t64-c19-shipped-en-002` Which shops take the biggest share of my grocery money in 2025? Draw i - wrong figures
- `t64-c19-shipped-en-004` Take the three categories I spend most on and show each of them per mo - wrong figures
- `t64-c19-shipped-de-005` Wo landet mein Gehalt eigentlich? Zeig den Fluss vom Einkommen in die  - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c19-shipped-de-007` Welchen Anteil hat jeder Ausgabenbereich an meinem Jahr 2025? Als Ring - wrong figures
- `t64-c19-shipped-en-008` Stack my four biggest spending categories per quarter of 2025 so I see - wrong figures
- `t64-c19-shipped-de-009` Wie summieren sich meine Lebensmittelausgaben 2025 ueber das Jahr auf? - wrong figures
- `t64-c20-shipped-en-004` We had the monthly spending and then the yearly total. Now put the two - wrong figures
- `t64-c20-shipped-en-005` We looked at December and then at November. Now compare the two months - The query was refused 2 times, last reason: misuse of aggregate function SUM()
- `t64-c20-shipped-de-001` Wir hatten erst die Ausgaben pro Monat und danach die vier groessten K - wrong figures
- `t64-c20-shipped-de-002` Du hast mir das Jahreseinkommen genannt und danach die Ausgaben pro Ka - wrong figures
- `t64-c20-shipped-de-005` Nach der Jahressumme und den Lebensmitteln pro Monat: zeig mir, wie si - wrong figures
- `t64-c21-shipped-en-002` how much cash did i pull out each month, and wheres my average? - wrong figures
- `t64-c21-shipped-en-004` donut plz: which supermarkets eat my grocery money? - wrong figures
- `t64-c21-shipped-en-006` show me how my spending piles up over the year - wrong figures
- `t64-c21-shipped-en-008` compare december with november, by category - wrong figures
- `t64-c22-shipped-en-003` Show how my spending has piled up since the summer. - wrong figures
- `t64-c22-shipped-de-004` Wie verteilen sich meine Ausgaben in diesem Quartal auf die Kategorien - wrong figures
- `t64-c22-shipped-en-005` Set this quarter against last quarter, category by category. - The query was refused 2 times, last reason: misuse of aggregate: SUM()
- `t64-c22-shipped-de-006` Zeig mir die letzten sechs Monate gestapelt nach Kategorie. - wrong figures
- `t64-c22-shipped-de-008` Wohin ist mein Einkommen seit dem Sommer geflossen? - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c22-shipped-de-010` Wie viel mehr oder weniger habe ich seit dem Sommer in jedem Monat geg - wrong figures
- `t64-c23-shipped-en-003` Show how the spending that is still in Needs review piles up over 2025 - wrong figures
- `t64-c23-shipped-de-004` Wie verteilen sich meine Restaurant-, Cafe- und Lieferausgaben 2025? A - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c23-shipped-en-005` Compare Supermarket, Drugstore and Bakery per quarter of 2025 as group - wrong figures
- `t64-c23-shipped-de-006` Stapelbalken: meine Transportausgaben pro Monat 2025 nach Unterkategor - wrong figures
- `t64-c23-shipped-en-007` Rank my subcategories of 2025 by what they cost me, top eight, horizon - wrong figures
- `t64-c24-shipped-en-002` Per month, what goes to AMZN Mktp DE against what goes to Kaufland and - wrong figures
- `t64-c24-shipped-de-003` Zeig als Ring, wie sich meine Supermarkt-Ausgaben auf die Maerkte vert - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c24-shipped-en-004` Where does my salary go? Draw the flow from my income into the spendin - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c24-shipped-de-005` Was wurde pro Monat bei AMZN Mktp DE abgebucht? - wrong figures
- `t64-c24-shipped-en-006` How does everything I ordered from Amazon add up over the year? - wrong figures
- `t64-c24-shipped-en-008` Stack what I leave at each supermarket per quarter. - wrong figures
- `t64-c24-shipped-de-009` Was habe ich pro Monat ueber PayPal an Freunde ueberwiesen? - The query behind the chart returned no rows, so there is nothing to draw.
