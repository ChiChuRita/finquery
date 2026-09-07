### local:gemma-4-12b on the chart set

302 datapoints, 2026-09-07T01:09:23+00:00, 14287.6 s in total, 47.3 s per datapoint, median 42.5 s, p90 65.1 s.

| | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 302 | 62 % | 100 % | 90 % | 86 % | 99 % | 92 % | 88 % | 42.5 |
| area | 32 | 59 % | 100 % | 100 % | 84 % | 97 % | 97 % | 97 % | 42.2 |
| bar | 59 | 76 % | 100 % | 76 % | 81 % | 100 % | 98 % | 95 % | 40.4 |
| bar_grouped | 31 | 45 % | 97 % | 90 % | 97 % | 100 % | 97 % | 84 % | 50.8 |
| bar_horizontal | 29 | 59 % | 100 % | 93 % | 90 % | 100 % | 93 % | 93 % | 36.7 |
| bar_stacked | 30 | 57 % | 100 % | 83 % | 93 % | 100 % | 97 % | 93 % | 43.2 |
| doughnut | 36 | 56 % | 100 % | 94 % | 94 % | 97 % | 89 % | 83 % | 40.9 |
| line | 59 | 75 % | 100 % | 93 % | 81 % | 100 % | 92 % | 92 % | 41.3 |
| sankey | 26 | 38 % | 100 % | 100 % | 73 % | 100 % | 69 % | 58 % | 66.2 |
| difficulty 1 | 36 | 78 % | 100 % | 83 % | 81 % | 100 % | 92 % | 92 % | 38.9 |
| difficulty 2 | 137 | 64 % | 100 % | 91 % | 90 % | 99 % | 92 % | 90 % | 40.6 |
| difficulty 3 | 129 | 54 % | 99 % | 91 % | 84 % | 99 % | 93 % | 86 % | 47.7 |

Missed (116):

- `03-cumulative-area-en` Chart my cumulative spending over 2025 as an area chart. - wrong figures
- `15-sankey-income-en` Draw a sankey of my 2025 income flowing into the spending categories. - The chart could not be drawn from these rows: One row carries no positive figure in amount_eur. Every flow is 
- `18-two-months-de` Vergleiche meine Ausgaben im Januar 2025 mit denen im Juli 2025 als Di - wrong figures
- `27-needs-review-bar-de` Zeig mir als Diagramm, wie viel von meinen Ausgaben 2025 kategorisiert - wrong figures
- `28-friends-doughnut-de` Wie verteilen sich meine PayPal-Zahlungen an Freunde 2025? Zeig es als - The query behind the chart returned no rows, so there is nothing to draw.
- `31-groceries-area-de` Zeig die kumulierten Lebensmittelausgaben 2025 als Flaechendiagramm. - wrong figures
- `g002-bar` Give me a breakdown of what I spent at supermarkets in 2025. - wrong figures
- `g007-bar` Give me a breakdown of my spending across categories in Q3 2025. - wrong figures
- `g002-area` Wie haben sich meine Ausgaben im Jahr 2025 Quartal fuer Quartal aufsum - wrong figures
- `g003-area` Zeig die aufgelaufenen Ausgaben fuer Wohnen ueber das Jahr 2025 als Fl - wrong figures
- `g001-bar_horizontal` Show my top 8 merchants by spending in Q4 2025 as a horizontal bar cha - wrong figures
- `g002-sankey` Where did my income go in November 2025? Give me a visual breakdown of - wrong figures
- `g003-sankey` Stelle als Sankey dar, wie sich meine Ausgaben fuer Subscriptions 2025 - wrong figures
- `35-this-month-versus-last-en` Compare this month with last month by category. - wrong figures
- `36-this-month-versus-last-de` Vergleiche diesen Monat mit dem letzten Monat nach Kategorie. - wrong figures
- `t64-c01-shipped-en-004` whats my money actually going to? donut by category please - wrong figures
- `t64-c01-shipped-en-008` sankey pls: where does my salary end up - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c01-shipped-de-009` kaufland, rewe und aldi pro monat - jeweils eine linie - wrong figures
- `t64-c01-shipped-de-005` vergleich mal diesen monat mit dem letzten, aufgeteilt nach kategorie  - wrong figures
- `t64-c02-shipped-en-002` What did my spending this quarter split into by category? Draw a dough - wrong figures
- `t64-c02-shipped-en-003` Draw my spending per category since the summer as bars. - wrong figures
- `t64-c02-shipped-en-004` Which merchants took the most of my money in the last 90 days? Draw a  - wrong figures
- `t64-c02-shipped-de-006` Zeig mir, wie sich meine Ausgaben seit dem Sommer aufsummiert haben. - wrong figures
- `t64-c02-shipped-de-007` Was hat sich je Kategorie zwischen letztem und diesem Monat getan? Bei - wrong figures
- `t64-c03-shipped-de-001` Zeig mir meine Supermarkt-Ausgaben pro Monat 2025 als Linie. - wrong figures
- `t64-c03-shipped-de-005` Wie setzen sich meine Abos Monat fuer Monat zusammen? - wrong figures
- `t64-c03-shipped-en-006` How does the money in Needs review add up over the year? - wrong figures
- `t64-c03-shipped-en-008` Draw supermarket, drugstore and bakery spending per month as three lin - wrong figures
- `t64-c04-shipped-de-006` Vergleiche als gruppierte Balken, was ich im ersten und im zweiten Hal - wrong figures
- `t64-c04-shipped-en-007` Stack up per month what the takeaway costs me: Doener Haus Kreuzberg,  - wrong figures
- `t64-c04-shipped-de-002` Was habe ich 2025 pro Supermarkt ausgegeben? Auf dem Auszug stehen die - wrong figures
- `t64-c05-shipped-de-001` Wie viel gebe ich im Schnitt pro Woche aus, Monat fuer Monat? - wrong figures
- `t64-c05-shipped-en-002` How much does one grocery run cost me on average, month by month? Draw - wrong figures
- `t64-c05-shipped-de-003` Was war 2025 mein groesster einzelner Lebensmitteleinkauf pro Monat? - The chart could not be drawn from these rows: The 76 rows carry only 12 different values in month, because 12 
- `t64-c05-shipped-en-008` How does what I pay for eating out add up over the year? - wrong figures
- `t64-c05-shipped-de-009` Was kostet mich ein Tag im Monat, und welche Kategorien machen den Tag - wrong figures
- `t64-c05-shipped-en-006` Of the places my money goes to at least a dozen times a year, which on - wrong figures
- `t64-c06-shipped-de-007` Was habe ich 2025 in jedem Monat an Miete gezahlt? - wrong figures
- `t64-c06-shipped-en-005` Draw the flow of my fixed monthly costs in 2025: from Fixed costs into - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c07-shipped-de-001` Zeig mir mein Gehalt von Mustermann Systems Monat fuer Monat 2025 als  - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c07-shipped-en-004` Show what was left of my salary each month in 2025 and where my averag - wrong figures
- `t64-c07-shipped-en-008` Stack each month of 2025 into what I spent and what stayed on the acco - wrong figures
- `t64-c07-shipped-de-009` Welche Kategorien haben 2025 am meisten von meinem Gehalt aufgebraucht - The chart could not be drawn from these rows: 10 rows carry no positive figure in amount_eur. Every flow is a 
- `t64-c08-shipped-en-005` Which shops took the most of my money in the second half of 2025? - wrong figures
- `t64-c08-shipped-de-006` Zeig als Flussdiagramm, wohin mein Geld im vierten Quartal 2025 geflos - The chart could not be drawn from these rows: 11 rows carry no positive figure in amount_eur. Every flow is a 
- `t64-c09-shipped-de-005` Wohin fliesst mein Einkommen 2025? Zeig die sechs groessten Ausgabenka - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c09-shipped-en-006` Compare December 2025 with November across the categories I spend the  - wrong figures
- `t64-c09-shipped-en-010` Of everything I spent in December 2025, what share did each category t - wrong figures
- `t64-c09-shipped-de-001` Welchen Anteil hat jeder meiner Supermaerkte an meinen Lebensmittelaus - wrong figures
- `t64-c10-shipped-de-006` Erst ging es um Lebensmittel im Oktober, dann um das ganze Jahr. Jetzt - wrong figures
- `t64-c10-shipped-de-007` Wir hatten die Monatslinie und die Kategorien. Zeig mir jetzt, wie sic - wrong figures
- `t64-c10-shipped-en-004` We looked at December, then at November on its own. Put the two months - wrong figures
- `t64-c11-shipped-en-004` what is my money split into? donut pls - wrong figures
- `t64-c11-shipped-de-005` wo liegen wir grad hoeher als im monat davor? bitte kategorie fuer kat - wrong figures
- `t64-c11-shipped-en-006` stack my monthly spending by category for the whole year - wrong figures
- `t64-c11-shipped-en-008` where does my salary actually go? sankey plz - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c12-shipped-de-002` Zeig mir als Linie, was ich in den letzten 30 Tagen Tag fuer Tag ausge - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c12-shipped-de-004` Bin ich seit dem Sommer Monat fuer Monat teurer oder billiger geworden - wrong figures
- `t64-c12-shipped-de-008` Stell diesen Monat und den letzten Monat nebeneinander, Kategorie fuer - wrong figures
- `t64-c12-shipped-en-009` Stack what I spent by category for each of the last six months. - wrong figures
- `t64-c12-shipped-en-010` Which shops took the most of my money in the last 90 days? - wrong figures
- `t64-c12-shipped-de-007` Wie verteilen sich meine Supermarkt-Einkaeufe seit dem Sommer auf die  - wrong figures
- `t64-c13-shipped-de-007` Vergleiche die Unterkategorien von Essengehen im ersten und im zweiten - wrong figures
- `t64-c13-shipped-en-010` Show how my 2025 spending flows from each category into its subcategor - wrong figures
- `t64-c14-shipped-de-004` Wie haben sich meine Amazon-Bestellungen (AMZN Mktp) 2025 aufsummiert? - wrong figures
- `t64-c14-shipped-en-008` Draw me a flow of where my 2025 income ended up. - wrong figures
- `t64-c15-shipped-de-001` Wie viel gebe ich eigentlich pro Tag aus? Zeig mir den Tagesschnitt Mo - wrong figures
- `t64-c15-shipped-en-002` Show me the largest single payment of each month in 2025. - wrong figures
- `t64-c15-shipped-en-004` How does an average week of my spending split up by category? Draw a d - wrong figures
- `t64-c15-shipped-en-006` Break my average daily spending down by category, month by month. - wrong figures
- `t64-c15-shipped-de-007` Bei welchen Haendlern ist mein Durchschnittsbon am hoechsten? Nur die, - wrong figures
- `t64-c15-shipped-en-008` Where does an average week of my money go? Show it as a flow. - wrong figures
- `t64-c15-shipped-en-010` What does an average shopping day cost me, per weekday? - wrong figures
- `t64-c16-shipped-en-001` Show me what I paid in rent every month in 2025. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c16-shipped-en-003` Draw my recurring fixed costs of 2025 by category as bars. - wrong figures
- `t64-c16-shipped-en-005` Show me how my rent added up over 2025. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c16-shipped-de-006` Wie verteilen sich meine Fixkosten 2025 auf die Kategorien? - wrong figures
- `t64-c16-shipped-en-007` Put this month's fixed costs next to last month's, one group of bars p - wrong figures
- `t64-c16-shipped-de-008` Zeig mir meine monatlichen Fixkosten 2025 gestapelt nach Kategorie. - wrong figures
- `t64-c16-shipped-en-009` Which payments come off my account every single month? Show a ranking. - wrong figures
- `t64-c16-shipped-de-010` Zeig mir als Sankey, wohin mein Einkommen in die Fixkosten fliesst. - wrong figures
- `t64-c17-shipped-de-001` Zeig mir mein Gehalt Monat fuer Monat 2025 als Linie und wo der Durchs - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c17-shipped-en-008` Show me month by month which categories my salary went to. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c17-shipped-de-009` Wohin fliesst mein Gehalt? Zeig die Kategorien als liegende Balken. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c17-shipped-en-010` Draw a flow from my income into the categories it is spent on. - The chart could not be drawn from these rows: 11 rows carry no positive figure in total_eur. Every flow is a p
- `t64-c18-shipped-en-001` Draw two lines, January to June of 2025 and July to December, so I can - wrong figures
- `t64-c18-shipped-de-002` Stell die Ausgaben aus dem dritten und dem vierten Quartal 2025 je Kat - wrong figures
- `t64-c18-shipped-de-004` Wie haben sich meine Ausgaben im vierten Quartal 2025 auf die Kategori - wrong figures
- `t64-c18-shipped-en-005` Draw the running total of each half of 2025 as two bands over the six  - wrong figures
- `t64-c18-shipped-en-007` Which categories did I spend more on this month than last month? Rank  - wrong figures
- `t64-c19-shipped-en-002` Which shops take the biggest share of my grocery money in 2025? Draw i - wrong figures
- `t64-c19-shipped-en-004` Take the three categories I spend most on and show each of them per mo - wrong figures
- `t64-c19-shipped-de-005` Wo landet mein Gehalt eigentlich? Zeig den Fluss vom Einkommen in die  - The query was refused 2 times, last reason: SQLite cannot parse this: Invalid expression / Unexpected token. L
- `t64-c19-shipped-en-008` Stack my four biggest spending categories per quarter of 2025 so I see - wrong figures
- `t64-c19-shipped-de-009` Wie summieren sich meine Lebensmittelausgaben 2025 ueber das Jahr auf? - wrong figures
- `t64-c20-shipped-en-005` We looked at December and then at November. Now compare the two months - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-c20-shipped-de-001` Wir hatten erst die Ausgaben pro Monat und danach die vier groessten K - wrong figures
- `t64-c20-shipped-de-002` Du hast mir das Jahreseinkommen genannt und danach die Ausgaben pro Ka - wrong figures
- `t64-c21-shipped-en-004` donut plz: which supermarkets eat my grocery money? - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c21-shipped-de-005` wo geht die kohle 2025 hin? als donut nach kategorie - wrong figures
- `t64-c21-shipped-en-008` compare december with november, by category - wrong figures
- `t64-c22-shipped-en-001` Show me how my spending has run month by month year to date. - wrong figures
- `t64-c22-shipped-en-003` Show how my spending has piled up since the summer. - wrong figures
- `t64-c22-shipped-de-004` Wie verteilen sich meine Ausgaben in diesem Quartal auf die Kategorien - wrong figures
- `t64-c22-shipped-en-005` Set this quarter against last quarter, category by category. - wrong figures
- `t64-c22-shipped-de-006` Zeig mir die letzten sechs Monate gestapelt nach Kategorie. - wrong figures
- `t64-c22-shipped-de-010` Wie viel mehr oder weniger habe ich seit dem Sommer in jedem Monat geg - wrong figures
- `t64-c23-shipped-de-004` Wie verteilen sich meine Restaurant-, Cafe- und Lieferausgaben 2025? A - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c23-shipped-en-005` Compare Supermarket, Drugstore and Bakery per quarter of 2025 as group - wrong figures
- `t64-c23-shipped-en-007` Rank my subcategories of 2025 by what they cost me, top eight, horizon - wrong figures
- `t64-c24-shipped-en-001` My statement is full of things like 'AMZN Mktp DE' and 'PP.4711.PP'. W - wrong figures
- `t64-c24-shipped-en-004` Where does my salary go? Draw the flow from my income into the spendin - wrong figures
- `t64-c24-shipped-de-007` Stell November und Dezember pro Kategorie nebeneinander. - wrong figures
- `t64-c24-shipped-en-008` Stack what I leave at each supermarket per quarter. - wrong figures
- `t64-c24-shipped-de-009` Was habe ich pro Monat ueber PayPal an Freunde ueberwiesen? - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c24-shipped-en-010` My PayPal lines all read 'PP.4711.PP'. Split those payments by who act - The query behind the chart returned no rows, so there is nothing to draw.
