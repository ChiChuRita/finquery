### local:gemma-4-12b+chart on the chart set

302 datapoints, 2026-09-07T06:39:44+00:00, 16127.1 s in total, 53.4 s per datapoint, median 47.1 s, p90 72.0 s.

| | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **all** | 302 | 46 % | 100 % | 85 % | 82 % | 98 % | 85 % | 79 % | 47.1 |
| area | 32 | 25 % | 100 % | 97 % | 69 % | 100 % | 72 % | 69 % | 46.1 |
| bar | 59 | 48 % | 100 % | 81 % | 70 % | 97 % | 80 % | 71 % | 43.5 |
| bar_grouped | 31 | 32 % | 100 % | 81 % | 87 % | 100 % | 97 % | 81 % | 53.7 |
| bar_horizontal | 29 | 38 % | 100 % | 93 % | 93 % | 100 % | 97 % | 97 % | 39.7 |
| bar_stacked | 30 | 27 % | 100 % | 67 % | 83 % | 100 % | 90 % | 83 % | 48.7 |
| doughnut | 36 | 67 % | 100 % | 97 % | 92 % | 97 % | 92 % | 86 % | 47.1 |
| line | 59 | 61 % | 100 % | 78 % | 86 % | 98 % | 90 % | 83 % | 47.6 |
| sankey | 26 | 54 % | 100 % | 100 % | 77 % | 96 % | 62 % | 62 % | 63.0 |
| difficulty 1 | 36 | 78 % | 100 % | 81 % | 92 % | 94 % | 92 % | 89 % | 43.6 |
| difficulty 2 | 137 | 45 % | 100 % | 85 % | 81 % | 98 % | 85 % | 77 % | 44.0 |
| difficulty 3 | 129 | 38 % | 100 % | 87 % | 79 % | 100 % | 84 % | 78 % | 50.3 |

Missed (163):

- `03-cumulative-area-en` Chart my cumulative spending over 2025 as an area chart. - The query was refused 2 times, last reason: no such column: booked_on
- `04-cumulative-area-de` Zeig die kumulierten Ausgaben 2025 als Flaechendiagramm. - wrong figures
- `06-category-bars-de` Ausgaben pro Kategorie 2025 als Balkendiagramm. - wrong figures
- `07-top-merchants-en` Which merchants took the most money in 2025? Show the top ten as a hor - wrong figures
- `08-top-merchants-de` Zeig die zehn groessten Haendler 2025 als liegendes Balkendiagramm. - wrong figures
- `09-quarter-groups-en` Compare what I spent on groceries and on dining per quarter in 2025 as - wrong figures
- `10-quarter-groups-de` Vergleiche Lebensmittel und Essengehen pro Quartal 2025 als gruppierte - wrong figures
- `16-sankey-income-de` Zeig als Sankey, wie mein Einkommen 2025 in die Ausgabenkategorien fli - The chart could not be drawn from these rows: One row carries no positive figure in amount_eur. Every flow is 
- `17-two-halves-en` Compare my total spending in the first half of 2025 with the second ha - The chart could not be drawn from these rows: The 22 rows carry only 11 different values in topic, because 11 
- `18-two-months-de` Vergleiche meine Ausgaben im Januar 2025 mit denen im Juli 2025 als Di - wrong figures
- `19-quarters-en` Chart my spending per quarter in 2025. - wrong figures
- `20-daily-march-en` Show my spending per day in March 2025 as a line chart. - wrong figures
- `23-income-versus-spending-en` Chart my income and my spending per month in 2025 side by side. - wrong figures
- `27-needs-review-bar-de` Zeig mir als Diagramm, wie viel von meinen Ausgaben 2025 kategorisiert - wrong figures
- `28-friends-doughnut-de` Wie verteilen sich meine PayPal-Zahlungen an Freunde 2025? Zeig es als - The query was refused 2 times, last reason: no such column: total_eur
- `29-daily-december-line-de` Zeig meine taeglichen Ausgaben im Dezember 2025 als Liniendiagramm. - wrong figures
- `30-groceries-stacked-quarters-en` Show my grocery spending per quarter in 2025, split into supermarket,  - wrong figures
- `33-grocery-lines-de` Wie viel habe ich 2025 pro Monat bei Rewe, Edeka, Lidl, Aldi und dm au - The query behind the chart returned no rows, so there is nothing to draw.
- `g003-bar` Show how much each subscription service cost me in 2025. - wrong figures
- `g005-bar` Compare my spending across categories in November 2025. - wrong figures
- `g007-bar` Give me a breakdown of my spending across categories in Q3 2025. - wrong figures
- `g004-line` Stelle meine Monatsausgaben bei Amazon 2025 als Liniengrafik dar. - wrong figures
- `g005-line` Wie haben sich meine Ausgaben im Oktober 2025 von Tag zu Tag entwickel - The chart could not be drawn from these rows: The 34 rows carry only 18 different values in month, because 8 n
- `g001-area` Plot my cumulative income over 2025 month by month as an area chart. - wrong figures
- `g002-area` Wie haben sich meine Ausgaben im Jahr 2025 Quartal fuer Quartal aufsum - wrong figures
- `g003-area` Zeig die aufgelaufenen Ausgaben fuer Wohnen ueber das Jahr 2025 als Fl - wrong figures
- `g003-doughnut` How was my spending split across my top categories last month? - wrong figures
- `g002-bar_grouped` Compare my quarterly expenses for Groceries, Dining, and Transport acr - wrong figures
- `g001-bar_stacked` Show what I spent on Housing and Subscriptions per quarter in 2025 as  - wrong figures
- `g002-bar_stacked` Stacked bar chart of my Transport spending by subcategory for each mon - wrong figures
- `g003-sankey` Stelle als Sankey dar, wie sich meine Ausgaben fuer Subscriptions 2025 - The query was refused 2 times, last reason: no such column: total_eur
- `35-this-month-versus-last-en` Compare this month with last month by category. - wrong figures
- `36-this-month-versus-last-de` Vergleiche diesen Monat mit dem letzten Monat nach Kategorie. - wrong figures
- `37-change-per-month-en` Show me for each month of 2025 how much more or less I spent than the  - The query was refused 2 times, last reason: misuse of window function LAG()
- `38-change-per-month-de` Zeig mir für jeden Monat 2025, wie viel mehr oder weniger ich als im M - The chart could not be drawn: 3 attempts failed the self-check, last reason: - `barY` reads the column "change
- `41-cumulative-halves-en` Compare how my spending added up over the first half of 2025 and over  - The query was refused 2 times, last reason: no such column: month_of_half
- `42-cumulative-halves-de` Vergleiche, wie sich meine Ausgaben im ersten und im zweiten Halbjahr  - wrong figures
- `t64-c01-shipped-en-002` which months did i blow more than usual on food shopping? bars with my - wrong figures
- `t64-c01-shipped-en-004` whats my money actually going to? donut by category please - wrong figures
- `t64-c01-shipped-de-007` wo hab ich am meisten geld gelassen? die top 8 laeden - wrong figures
- `t64-c01-shipped-de-009` kaufland, rewe und aldi pro monat - jeweils eine linie - wrong figures
- `t64-c01-shipped-en-010` each month, how much more or less did i spend than the month before? b - wrong figures
- `t64-c01-shipped-de-005` vergleich mal diesen monat mit dem letzten, aufgeteilt nach kategorie  - wrong figures
- `t64-c02-shipped-en-003` Draw my spending per category since the summer as bars. - wrong figures
- `t64-c02-shipped-en-004` Which merchants took the most of my money in the last 90 days? Draw a  - wrong figures
- `t64-c02-shipped-de-006` Zeig mir, wie sich meine Ausgaben seit dem Sommer aufsummiert haben. - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The values read as periods (202
- `t64-c02-shipped-de-007` Was hat sich je Kategorie zwischen letztem und diesem Monat getan? Bei - wrong figures
- `t64-c03-shipped-en-004` Which merchants are still sitting in Needs review, by how much money? - wrong figures
- `t64-c03-shipped-de-005` Wie setzen sich meine Abos Monat fuer Monat zusammen? - wrong figures
- `t64-c03-shipped-en-008` Draw supermarket, drugstore and bakery spending per month as three lin - wrong figures
- `t64-c04-shipped-en-003` Every PayPal line on my statement reads PP.4711.PP and then a name. Ra - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c04-shipped-en-005` Show me how the PayPal payments add up over 2025. - wrong figures
- `t64-c04-shipped-de-006` Vergleiche als gruppierte Balken, was ich im ersten und im zweiten Hal - wrong figures
- `t64-c04-shipped-en-007` Stack up per month what the takeaway costs me: Doener Haus Kreuzberg,  - wrong figures
- `t64-c04-shipped-de-008` Zeig als Sankey, wie das Gehalt von Mustermann Systems GmbH in meine A - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c04-shipped-de-010` Die Baeckerei steht als Baeckerei Steinecke auf dem Auszug. Was hat di - The query was refused 2 times, last reason: SQLite cannot parse this: Expected AS after CAST. Line 1, Col: 55.
- `t64-c04-shipped-de-002` Was habe ich 2025 pro Supermarkt ausgegeben? Auf dem Auszug stehen die - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c05-shipped-de-001` Wie viel gebe ich im Schnitt pro Woche aus, Monat fuer Monat? - wrong figures
- `t64-c05-shipped-en-002` How much does one grocery run cost me on average, month by month? Draw - wrong figures
- `t64-c05-shipped-en-004` Which weekday do my card payments cost the most on average? - wrong figures
- `t64-c05-shipped-de-009` Was kostet mich ein Tag im Monat, und welche Kategorien machen den Tag - wrong figures
- `t64-c06-shipped-en-004` Compare what I paid for insurance, my phone contracts and my subscript - wrong figures
- `t64-c06-shipped-de-007` Was habe ich 2025 in jedem Monat an Miete gezahlt? - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c06-shipped-de-008` Stapel mir pro Monat, was 2025 auf Strom, Versicherung, Handy und Abos - wrong figures
- `t64-c06-shipped-en-005` Draw the flow of my fixed monthly costs in 2025: from Fixed costs into - The query was refused 2 times, last reason: no such column: total_eur
- `t64-c06-shipped-de-006` Zeig mir, wie sich meine Fixkosten 2025 Monat fuer Monat aufsummiert h - wrong figures
- `t64-c07-shipped-en-002` Show my income and my spending per month in 2025 as two lines. - wrong figures
- `t64-c07-shipped-de-003` Zeig meine Einnahmen pro Quartal 2025 als Balken. - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The code does not compile: Synt
- `t64-c07-shipped-en-004` Show what was left of my salary each month in 2025 and where my averag - wrong figures
- `t64-c07-shipped-de-005` Wie haben sich meine Einnahmen 2025 aufsummiert? - wrong figures
- `t64-c07-shipped-en-008` Stack each month of 2025 into what I spent and what stayed on the acco - wrong figures
- `t64-c07-shipped-de-007` Vergleiche Einnahmen und Ausgaben pro Quartal 2025 nebeneinander. - wrong figures
- `t64-c07-shipped-de-009` Welche Kategorien haben 2025 am meisten von meinem Gehalt aufgebraucht - wrong figures
- `t64-c08-shipped-en-001` Which categories got dearer for me from the first half of 2025 to the  - wrong figures
- `t64-c08-shipped-de-004` Wie verteilen sich meine Ausgaben im zweiten Halbjahr 2025 auf die Kat - wrong figures
- `t64-c08-shipped-en-007` Show me how my spending piled up over 2025. - wrong figures
- `t64-c08-shipped-de-008` Stapel mir Lebensmittel, Transport und Essengehen pro Quartal 2025 ueb - wrong figures
- `t64-c08-shipped-de-010` Vergleiche meine Ausgaben Quartal fuer Quartal 2025. - wrong figures
- `t64-c09-shipped-en-002` Which five merchants did I spend the least at in 2025? Draw it as a ho - wrong figures
- `t64-c09-shipped-en-006` Compare December 2025 with November across the categories I spend the  - wrong figures
- `t64-c09-shipped-de-007` Vergleiche, wie sich meine Lebensmittel- und meine Transportausgaben 2 - The query was refused 2 times, last reason: no such column: topic
- `t64-c09-shipped-en-008` Show me month by month how my three biggest categories stack up. - wrong figures
- `t64-c09-shipped-en-010` Of everything I spent in December 2025, what share did each category t - The query was refused 2 times, last reason: SQLite cannot parse this: Invalid expression / Unexpected token. L
- `t64-c09-shipped-de-001` Welchen Anteil hat jeder meiner Supermaerkte an meinen Lebensmittelaus - wrong figures
- `t64-c09-shipped-de-003` Zeig mir die sechs kleinsten Ausgabenkategorien 2025 und wo ihr Durchs - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c10-shipped-en-001` We started with what I spent in October, then you broke that month dow - wrong figures
- `t64-c10-shipped-en-003` Those grocery bars were one block. We had October and then the year; n - wrong figures
- `t64-c10-shipped-de-007` Wir hatten die Monatslinie und die Kategorien. Zeig mir jetzt, wie sic - wrong figures
- `t64-c10-shipped-en-004` We looked at December, then at November on its own. Put the two months - wrong figures
- `t64-c10-shipped-de-010` Wir hatten die aufsummierte Kurve und die Monatslinie. Jetzt bitte pro - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The code does not compile: Synt
- `t64-c11-shipped-de-003` wie viel hab ich dieses jahr schon verbraten, so aufaddiert? - wrong figures
- `t64-c11-shipped-en-004` what is my money split into? donut pls - wrong figures
- `t64-c11-shipped-en-006` stack my monthly spending by category for the whole year - wrong figures
- `t64-c11-shipped-de-007` wo lass ich am meisten geld? top 10 bitte quer - wrong figures
- `t64-c11-shipped-en-008` where does my salary actually go? sankey plz - wrong figures
- `t64-c11-shipped-de-009` geb ich grad mehr aus als sonst? linie mit meinem schnitt drin - wrong figures
- `t64-c11-shipped-en-010` each month, did i spend more or less than the month before? - wrong figures
- `t64-c12-shipped-de-002` Zeig mir als Linie, was ich in den letzten 30 Tagen Tag fuer Tag ausge - wrong figures
- `t64-c12-shipped-de-004` Bin ich seit dem Sommer Monat fuer Monat teurer oder billiger geworden - wrong figures
- `t64-c12-shipped-en-009` Stack what I spent by category for each of the last six months. - wrong figures
- `t64-c12-shipped-en-010` Which shops took the most of my money in the last 90 days? - wrong figures
- `t64-c13-shipped-de-009` Welche Unterkategorien haben mich 2025 am meisten gekostet? Bitte als  - wrong figures
- `t64-c13-shipped-en-010` Show how my 2025 spending flows from each category into its subcategor - wrong figures
- `t64-c14-shipped-de-002` Bei welchem Supermarkt habe ich 2025 wie viel gelassen? Die Buchungen  - wrong figures
- `t64-c14-shipped-de-004` Wie haben sich meine Amazon-Bestellungen (AMZN Mktp) 2025 aufsummiert? - wrong figures
- `t64-c14-shipped-en-005` Rank the ten counterparties I paid the most in 2025, horizontal bars,  - wrong figures
- `t64-c14-shipped-de-006` Stelle Lebensmittel, Verkehr und Wohnen pro Quartal 2025 nebeneinander - wrong figures
- `t64-c14-shipped-en-007` Stack what I spent per quarter of 2025 on groceries, eating out, trans - wrong figures
- `t64-c14-shipped-en-008` Draw me a flow of where my 2025 income ended up. - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The code threw Error: the link 
- `t64-c15-shipped-de-001` Wie viel gebe ich eigentlich pro Tag aus? Zeig mir den Tagesschnitt Mo - wrong figures
- `t64-c15-shipped-en-002` Show me the largest single payment of each month in 2025. - wrong figures
- `t64-c15-shipped-de-003` Zeig mir aufsummiert, wie schnell sich meine Ausgaben ueber das Jahr a - The query was refused 2 times, last reason: no such column: a.month
- `t64-c15-shipped-de-005` Vergleich bitte: was kostet eine einzelne Buchung im Schnitt pro Kateg - wrong figures
- `t64-c15-shipped-en-006` Break my average daily spending down by category, month by month. - The chart could not be drawn from these rows: The 132 rows carry only 12 different values in month, because 12
- `t64-c15-shipped-de-007` Bei welchen Haendlern ist mein Durchschnittsbon am hoechsten? Nur die, - wrong figures
- `t64-c15-shipped-de-009` Was kostet ein einzelner Lebensmitteleinkauf bei mir im Schnitt, Monat - The query was refused 2 times, last reason: no such column: month
- `t64-c15-shipped-en-010` What does an average shopping day cost me, per weekday? - The chart could not be drawn: 3 attempts failed the self-check, last reason: - The code does not compile: Synt
- `t64-c16-shipped-en-003` Draw my recurring fixed costs of 2025 by category as bars. - wrong figures
- `t64-c16-shipped-en-005` Show me how my rent added up over 2025. - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c16-shipped-de-006` Wie verteilen sich meine Fixkosten 2025 auf die Kategorien? - wrong figures
- `t64-c16-shipped-en-007` Put this month's fixed costs next to last month's, one group of bars p - wrong figures
- `t64-c16-shipped-de-008` Zeig mir meine monatlichen Fixkosten 2025 gestapelt nach Kategorie. - wrong figures
- `t64-c16-shipped-en-009` Which payments come off my account every single month? Show a ranking. - wrong figures
- `t64-c16-shipped-de-010` Zeig mir als Sankey, wohin mein Einkommen in die Fixkosten fliesst. - The query was refused 2 times, last reason: no such column: target
- `t64-c17-shipped-de-001` Zeig mir mein Gehalt Monat fuer Monat 2025 als Linie und wo der Durchs - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c17-shipped-en-002` Put what came in and what went out on one chart, month by month in 202 - wrong figures
- `t64-c17-shipped-de-005` Zeig mir aufsummiert, wie viel 2025 auf mein Konto geflossen ist. - wrong figures
- `t64-c17-shipped-de-007` Vergleiche Einnahmen und Ausgaben pro Quartal 2025 als gruppierte Balk - The query was refused 2 times, last reason: no such column: quarter
- `t64-c17-shipped-en-008` Show me month by month which categories my salary went to. - The query was refused 2 times, last reason: no such column: topic
- `t64-c17-shipped-en-010` Draw a flow from my income into the categories it is spent on. - wrong figures
- `t64-c18-shipped-en-001` Draw two lines, January to June of 2025 and July to December, so I can - wrong figures
- `t64-c18-shipped-en-003` Quarter by quarter in 2025, plot the swing up or down against the quar - The query was refused 2 times, last reason: no such column: quarter_num
- `t64-c18-shipped-de-004` Wie haben sich meine Ausgaben im vierten Quartal 2025 auf die Kategori - wrong figures
- `t64-c18-shipped-en-005` Draw the running total of each half of 2025 as two bands over the six  - wrong figures
- `t64-c18-shipped-de-006` Zeig mir pro Quartal 2025 gestapelt, wie sich Lebensmittel, Transport, - The query was refused 2 times, last reason: SQLite cannot parse this: Expected AS after CAST. Line 1, Col: 80.
- `t64-c18-shipped-en-007` Which categories did I spend more on this month than last month? Rank  - wrong figures
- `t64-c19-shipped-de-003` Bei welchen fuenf Haendlern habe ich 2025 am wenigsten gelassen? Als l - wrong figures
- `t64-c19-shipped-en-004` Take the three categories I spend most on and show each of them per mo - wrong figures
- `t64-c19-shipped-de-005` Wo landet mein Gehalt eigentlich? Zeig den Fluss vom Einkommen in die  - The query was refused 2 times, last reason: no such column: target
- `t64-c19-shipped-en-008` Stack my four biggest spending categories per quarter of 2025 so I see - wrong figures
- `t64-c19-shipped-de-009` Wie summieren sich meine Lebensmittelausgaben 2025 ueber das Jahr auf? - The query was refused 2 times, last reason: no such column: signed_amount
- `t64-c19-shipped-en-010` Put this month next to last month for the six categories I spend most  - wrong figures
- `t64-c20-shipped-en-004` We had the monthly spending and then the yearly total. Now put the two - wrong figures
- `t64-c20-shipped-en-005` We looked at December and then at November. Now compare the two months - wrong figures
- `t64-c20-shipped-de-001` Wir hatten erst die Ausgaben pro Monat und danach die vier groessten K - wrong figures
- `t64-c20-shipped-de-004` Wir hatten die Lebensmittel pro Monat, dann Rewe allein. Jetzt bitte R - wrong figures
- `t64-c21-shipped-en-004` donut plz: which supermarkets eat my grocery money? - The chart could not be drawn: 3 attempts failed the self-check, last reason: - A doughnut chart separates its 
- `t64-c21-shipped-de-007` top 8 laeden wo ich am meisten gelassen hab, quer bitte - wrong figures
- `t64-c21-shipped-en-008` compare december with november, by category - wrong figures
- `t64-c22-shipped-en-001` Show me how my spending has run month by month year to date. - wrong figures
- `t64-c22-shipped-de-006` Zeig mir die letzten sechs Monate gestapelt nach Kategorie. - wrong figures
- `t64-c22-shipped-de-008` Wohin ist mein Einkommen seit dem Sommer geflossen? - The chart could not be drawn from these rows: One row carries no positive figure in amount_eur. Every flow is 
- `t64-c22-shipped-de-010` Wie viel mehr oder weniger habe ich seit dem Sommer in jedem Monat geg - The query was refused 2 times, last reason: no such column: booked_on
- `t64-c23-shipped-en-003` Show how the spending that is still in Needs review piles up over 2025 - The query was refused 2 times, last reason: no such column: booked_on
- `t64-c23-shipped-de-006` Stapelbalken: meine Transportausgaben pro Monat 2025 nach Unterkategor - wrong figures
- `t64-c23-shipped-en-007` Rank my subcategories of 2025 by what they cost me, top eight, horizon - wrong figures
- `t64-c23-shipped-en-008` Draw a sankey from my spending categories of 2025 into their subcatego - The query was refused 2 times, last reason: no such column: total_eur
- `t64-c24-shipped-en-002` Per month, what goes to AMZN Mktp DE against what goes to Kaufland and - wrong figures
- `t64-c24-shipped-de-005` Was wurde pro Monat bei AMZN Mktp DE abgebucht? - wrong figures
- `t64-c24-shipped-en-006` How does everything I ordered from Amazon add up over the year? - The query was refused 2 times, last reason: no such column: cumulative_eur
- `t64-c24-shipped-en-008` Stack what I leave at each supermarket per quarter. - wrong figures
- `t64-c24-shipped-de-009` Was habe ich pro Monat ueber PayPal an Freunde ueberwiesen? - The query behind the chart returned no rows, so there is nothing to draw.
- `t64-c24-shipped-en-010` My PayPal lines all read 'PP.4711.PP'. Split those payments by who act - wrong figures
