### local:gemma-4-e4b on the sql set

459 datapoints, 2026-09-07T01:43:57+00:00, 4262.1 s in total, 9.3 s per datapoint, median 7.8 s, p90 15.4 s.

| | n | figure match | SQL valid | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: |
| **all** | 459 | 62 % | 99 % | 76 % | 7.8 |
| breakdown | 59 | 56 % | 98 % | 75 % | 7.6 |
| comparison | 38 | 68 % | 97 % | 68 % | 12.8 |
| entity | 69 | 62 % | 97 % | 87 % | 8.0 |
| follow-up | 77 | 44 % | 100 % | 64 % | 8.1 |
| period | 58 | 83 % | 100 % | 88 % | 7.3 |
| ranking | 39 | 49 % | 100 % | 67 % | 8.5 |
| total | 62 | 77 % | 100 % | 86 % | 7.0 |
| trend | 57 | 63 % | 100 % | 74 % | 7.1 |
| difficulty 1 | 67 | 76 % | 98 % | 88 % | 6.8 |
| difficulty 2 | 211 | 68 % | 100 % | 79 % | 7.4 |
| difficulty 3 | 181 | 51 % | 99 % | 69 % | 8.5 |

Missed (172):

- `s04-rent-total-de` Wie viel Miete habe ich 2025 insgesamt gezahlt? - wrong figures
- `s06-groceries-per-week-de` Was habe ich 2025 im Schnitt pro Woche fuer Lebensmittel ausgegeben, a - wrong figures
- `s13-per-category-de` Wie viel habe ich 2025 pro Kategorie ausgegeben? - wrong figures
- `s16-supermarkets-de` Wie verteilen sich meine Lebensmittelausgaben auf die einzelnen Laeden - wrong figures
- `s18-needs-review-merchants-de` Welche Haendler stecken in 'Needs review', und wie viele Buchungen sin - wrong figures
- `s19-per-quarter-en` How much did I spend per quarter in 2025? - wrong figures
- `s21-categorized-share-en` How much of my 2025 spending is categorized and how much still needs r - wrong figures
- `s22-account-months-de` Zeig mir pro Monat, wie viele Ausgaben ich hatte und was sie zusammen  - wrong figures
- `s26-groceries-vs-dining-de` Vergleiche meine Ausgaben fuer Lebensmittel und fuers Essengehen, pro  - wrong figures
- `s29-rent-constant-de` Ist meine Miete im Laufe des Jahres gestiegen? - wrong figures
- `s30-anna-vs-max-en` Compare what I sent Anna with what I sent Max. - wrong figures
- `s34-cumulative-de` Zeig mir meine kumulierten Ausgaben pro Monat. - wrong figures
- `s35-net-per-month-en` What is my net per month, income minus spending? - wrong figures
- `s40-biggest-expense-en` What was my biggest single expense in 2025? - wrong figures
- `s41-smallest-recurring-de` Was ist meine kleinste wiederkehrende Zahlung? - wrong figures
- `s44-most-visited-supermarkets-en` Which three supermarkets did I shop at most often? - wrong figures
- `s45-biggest-without-rent-de` Wer hat 2025 am meisten Geld von mir bekommen, ohne die Miete? - wrong figures
- `s46-top-expenses-en` What are the five largest single bookings that are neither rent nor a  - wrong figures
- `s48-rewe-and-edeka-de` Wie viel bei REWE und wie viel bei EDEKA? - wrong figures
- `s51-anna-de` Wie viel habe ich Anna Weber ueberwiesen? - wrong figures
- `s54-last-rent-en` When was my last rent payment and how much was it? - wrong figures
- `s55-netflix-de` Was kostet mich Netflix im Jahr? - wrong figures
- `s57-refunds-en` Did I get any refunds in 2025? - wrong figures
- `s59-bakery-de` Wie oft war ich 2025 beim Baecker und was habe ich dort gelassen? - wrong figures
- `s62-only-groceries-en` Only groceries. - wrong figures
- `s64-just-supermarkets-en` Show me just the supermarkets. - wrong figures
- `s66-cheapest-month-en` Which of those months was the cheapest? - wrong figures
- `s67-without-rent-de` Und ohne die Miete? - wrong figures
- `s68-by-merchant-en` Break that down by merchant. - wrong figures
- `g010-total` What was my total spending on Spotify and Netflix combined in 2025? - wrong figures
- `g003-breakdown` Zeige mir eine Aufschluesselung meiner Einnahmen im Jahr 2025 nach Sub - wrong figures
- `g001-comparison` Compare my spending on Dining between Q1 and Q2 2025. - wrong figures
- `g003-comparison` Compare my spending on Public transport versus Ride hailing in 2025. - wrong figures
- `g004-comparison` Vergleiche die Supermarkt-Ausgaben im dritten Quartal mit dem vierten  - wrong figures
- `g003-trend` Show my monthly spending across 2025 excluding Housing. - wrong figures
- `g006-trend` How did my monthly spending on dining out develop in the second quarte - wrong figures
- `g003-ranking` Bei welchen 5 Geschaeften oder Dienstleistern hatte ich 2025 die meist - wrong figures
- `g005-ranking` What were my 3 smallest spending transactions in 2025? - wrong figures
- `g007-ranking` Welche 5 Haendler hatten 2025 den hoechsten Durchschnittsbetrag pro Bu - wrong figures
- `g008-ranking` Was waren meine 3 groessten Ausgaben im November 2025? - wrong figures
- `g009-ranking` What were my top 3 largest supermarket purchases in 2025? - wrong figures
- `g001-entity` Wie viel habe ich 2025 fuer Fitness First ausgegeben? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `g005-entity` How many times did I order from Lieferando in 2025, and what was the a - wrong figures
- `g010-entity` Was war mein teuerster und mein guenstigster Einkauf bei Lidl im Jahr  - The query was refused 2 times, last reason: ORDER BY clause should come after UNION ALL not before
- `g002-follow-up` Und im Dezember? - wrong figures
- `g003-follow-up` Break it down by subcategory. - wrong figures
- `g004-follow-up` And on Groceries? - wrong figures
- `g005-follow-up` Welche drei Haendler waren da am teuersten? - wrong figures
- `g006-follow-up` What was the single biggest one? - wrong figures
- `g007-follow-up` Und wie oft war ich dort einkaufen? - wrong figures
- `g008-follow-up` Split that by month. - wrong figures
- `t64-w01-shipped-de-004` wofuer ist letzten monat mein ganzes geld draufgegangen? - wrong figures
- `t64-w01-shipped-de-005` was zahl ich eigentlich jeden monat fuer meine abos? - wrong figures
- `t64-w01-shipped-de-008` und wieviel davon war im supermarkt? - wrong figures
- `t64-w01-shipped-en-001` Lidle, what has all that added up to? - wrong figures
- `t64-w01-shipped-en-003` do i spend more on takeaway or in restaurants? - wrong figures
- `t64-w01-shipped-en-005` where does most of my money go? top 5 please - wrong figures
- `t64-w02-shipped-en-001` How much did I spend in the last 90 days? - wrong figures
- `t64-w02-shipped-en-003` And in the quarter before that one? - wrong figures
- `t64-w02-shipped-en-004` What have I spent per month since the summer? - wrong figures
- `t64-w02-shipped-en-006` Break my spending of the last 90 days down by category, please. - wrong figures
- `t64-w02-shipped-en-007` Which merchants did I spend the most with last month? Top five, please - wrong figures
- `t64-w02-shipped-de-002` Was habe ich seit dem Sommer fuer Lebensmittel bezahlt? - wrong figures
- `t64-w02-shipped-de-003` Und wie sieht das diesen Monat aus? - wrong figures
- `t64-w02-shipped-de-004` Und wie verteilt sich dieser Betrag auf die Unterkategorien? - wrong figures
- `t64-w03-shipped-en-008` How much lands in the Needs review bucket each month? - wrong figures
- `t64-w03-shipped-en-014` And which merchants are those uncategorized bookings from? - wrong figures
- `t64-w04-shipped-en-003` How much did the AMZN Mktp bookings cost me in 2025? - wrong figures
- `t64-w04-shipped-en-005` Which grocery shops did my money go to, and how much each? - wrong figures
- `t64-w04-shipped-de-006` Was kostet mich jedes einzelne Abo im Jahr 2025? - wrong figures
- `t64-w04-shipped-en-011` Which merchants did I pay more than 500 euros in 2025? - wrong figures
- `t64-w05-shipped-en-004` How did the average size of one grocery booking change from quarter to - wrong figures
- `t64-w05-shipped-de-005` Wie oft war ich dieses Jahr bei Fitness First und was hat ein Besuch i - wrong figures
- `t64-w05-shipped-de-007` Und wie viele Einkaeufe waren das pro Woche? - wrong figures
- `t64-w05-shipped-de-014` Aufschluesselung meiner Ausgaben 2025 nach Kategorie, und was ist das  - wrong figures
- `t64-w05-shipped-en-015` Did I book more often in December 2025 than in November, and what did  - wrong figures
- `t64-w06-shipped-en-002` How much rent did I pay to Hausverwaltung Bergmann? - wrong figures
- `t64-w06-shipped-en-003` Which subscriptions am I actually paying for, and what does each of th - wrong figures
- `t64-w06-shipped-en-005` What did rent, electricity and insurance together cost me last month? - wrong figures
- `t64-w06-shipped-en-006` And how much of that was the Adobe subscription? - wrong figures
- `t64-w06-shipped-en-007` Of the bills that come off exactly once a month, which three take the  - wrong figures
- `t64-w06-shipped-en-008` Has my Netflix payment gone up since January? - wrong figures
- `t64-w06-shipped-de-010` Hat sich meine Miete im Laufe des Jahres irgendwann geaendert? - wrong figures
- `t64-w06-shipped-de-013` Was zahle ich pro Monat an Fitness First? - wrong figures
- `t64-w06-shipped-de-014` Welche Zahlungen gehen jeden Monat raus, und wie viel sind das pro Anb - wrong figures
- `t64-w07-shipped-de-001` Wie viel Gehalt habe ich 2025 bekommen? - wrong figures
- `t64-w07-shipped-de-004` Und wie viel davon kam im vierten Quartal an? - wrong figures
- `t64-w07-shipped-de-005` Woher kam mein Geld 2025? Bitte nach Zahler aufschluesseln. - wrong figures
- `t64-w07-shipped-de-008` Wie verteilt sich mein Gehalt 2025 auf die Monate? - wrong figures
- `t64-w08-shipped-en-003` How much more did I spend on transport in the second half of 2025 than - wrong figures
- `t64-w08-shipped-de-001` Wofuer ist im Dezember 2025 das meiste Geld draufgegangen? - wrong figures
- `t64-w08-shipped-de-002` Und wie war das im Dezember? - wrong figures
- `t64-w08-shipped-de-003` Und im vierten Quartal, wie sieht das dagegen aus? - wrong figures
- `t64-w08-shipped-en-005` Did I leave more money at Kaufland or at Rewe this year? - wrong figures
- `t64-w08-shipped-en-007` Which three categories went up the most from the first half of the yea - wrong figures
- `t64-w08-shipped-de-006` Wie hat sich mein Essengehen ueber die vier Quartale entwickelt? - wrong figures
- `t64-w09-shipped-de-003` Wie verteilen sich meine Ausgaben 2025 prozentual auf die Kategorien? - wrong figures
- `t64-w09-shipped-de-006` Welchen Anteil meiner Ausgaben hat 2025 die Miete verschlungen? - wrong figures
- `t64-w09-shipped-en-010` And which grocery shop did I spend the least at? - wrong figures
- `t64-w09-shipped-de-011` Was ist bei Aldi ueber das Jahr zusammengekommen? - wrong figures
- `t64-w09-shipped-en-012` Which month was my cheapest one this year? - wrong figures
- `t64-w09-shipped-de-013` Und wie teilt sich dieser Monat auf die Kategorien auf? - wrong figures
- `t64-w09-shipped-en-015` How does my grocery spending split across supermarket, bakery and drug - The query was refused 2 times, last reason: A join without a condition multiplies the bookings by each other, 
- `t64-w10-shipped-en-005` Add up everything that has gone to ALDI, please. - wrong figures
- `t64-w10-shipped-de-003` Und wie sieht dieselbe Liste fuer den November aus? - wrong figures
- `t64-w10-shipped-de-004` Wie viel ist pro Quartal fuer Transport draufgegangen? - wrong figures
- `t64-w10-shipped-de-005` Wie viel Geld ist eigentlich ueber PayPal rausgegangen? - wrong figures
- `t64-w10-shipped-en-004` Which payees took the most money off me in the second half of the year - wrong figures
- `t64-w11-shipped-de-005` wie haben sich meine abos ueber das jahr entwickelt, pro monat? - wrong figures
- `t64-w11-shipped-de-010` was zahl ich eigentlich im schnitt pro monat fuer die miete? - wrong figures
- `t64-w12-shipped-de-001` Wie viel habe ich seit dem Sommer fuer Lebensmittel ausgegeben? - wrong figures
- `t64-w12-shipped-de-003` Wie viel habe ich seit dem Sommer pro Monat am Geldautomaten abgehoben - wrong figures
- `t64-w12-shipped-de-005` Was habe ich seit dem Sommer bei Aldi gelassen? - wrong figures
- `t64-w12-shipped-de-006` Bin ich diesen Monat teurer unterwegs als im Monat davor? - The query was refused 2 times, last reason: misuse of aggregate function SUM()
- `t64-w12-shipped-de-007` Und wie sieht das seit dem Sommer aus, im Restaurant? - wrong figures
- `t64-w13-shipped-de-002` Wie teilen sich meine Abos auf die Unterkategorien auf? - wrong figures
- `t64-w13-shipped-de-004` Welche Zahlungsempfaenger stecken hinter den Buchungen, die noch keine - wrong figures
- `t64-w13-shipped-de-010` Welche fuenf Unterkategorien haben mich 2025 am meisten gekostet? - wrong figures
- `t64-w13-shipped-en-013` And which part of that has no subcategory on it? - wrong figures
- `t64-w13-shipped-de-014` Und im Dezember, aufgeteilt nach Unterkategorie? - wrong figures
- `t64-w14-shipped-en-007` How did my PayPal payments move from month to month? - wrong figures
- `t64-w14-shipped-de-008` An welche Leute habe ich per PayPal ueberwiesen, und wie viel an wen? - wrong figures
- `t64-w14-shipped-en-011` What did the doener and the dean and david bowls add up to in the last - wrong figures
- `t64-w14-shipped-de-014` Und wie verteilt sich das auf die Monate? - wrong figures
- `t64-w14-shipped-de-015` Und wie oft war ich da im ganzen Jahr? - wrong figures
- `t64-w15-shipped-de-005` Wie viel gebe ich eigentlich pro Tag aus? - wrong figures
- `t64-w15-shipped-de-006` Und auf wie viele einzelne Einkaeufe hat sich dieser Betrag verteilt? - wrong figures
- `t64-w15-shipped-en-007` And what does that work out to per shopping trip? - wrong figures
- `t64-w15-shipped-de-008` Und was war das pro Woche in dem Monat? - wrong figures
- `t64-w15-shipped-en-015` How often has Netflix charged me and what is the average charge? - wrong figures
- `t64-w16-shipped-de-002` Was habe ich 2025 fuer mein Netflix-Abo abgebucht bekommen? - wrong figures
- `t64-w16-shipped-de-003` Was zahle ich jeden Monat an die Hausverwaltung? - wrong figures
- `t64-w16-shipped-en-005` How did my fixed costs move over 2025? Rent, electricity, insurance, p - wrong figures
- `t64-w16-shipped-de-006` Wie verteilen sich meine festen Kosten im Dezember 2025 auf die Katego - wrong figures
- `t64-w16-shipped-en-008` What did my recurring bills cost me last month? - wrong figures
- `t64-w16-shipped-en-010` Which of my subscriptions is the most expensive per month? - wrong figures
- `t64-w16-shipped-de-013` Und im Dezember, wie hoch waren die festen Kosten da? - wrong figures
- `t64-w16-shipped-en-014` And how much is that one costing me every month? - wrong figures
- `t64-w16-shipped-de-015` Was ist 2025 insgesamt an die Hausverwaltung fuer die Miete gegangen? - wrong figures
- `t64-w17-shipped-de-004` Wie viel hat mir Mustermann Systems im zweiten Halbjahr ueberwiesen? - wrong figures
- `t64-w17-shipped-en-006` How did the money coming in develop from quarter to quarter in 2025? - wrong figures
- `t64-w17-shipped-en-008` Split my 2025 income into the salary and everything else. - wrong figures
- `t64-w17-shipped-en-011` Which five categories ate the most of my salary in 2025? - wrong figures
- `t64-w17-shipped-de-012` Habe ich im Dezember mehr eingenommen oder mehr ausgegeben? - wrong figures
- `t64-w17-shipped-de-013` Und wie viel davon kam im ersten Halbjahr? - wrong figures
- `t64-w18-shipped-de-001` Was ist bei mir ueber die ganze Zeit an Versicherungsbeitraegen zusamm - wrong figures
- `t64-w18-shipped-de-003` Kaufland oder Rewe, wo ist bei mir mehr Geld geblieben? - wrong figures
- `t64-w18-shipped-de-004` Und wie viel war es im Quartal davor? - wrong figures
- `t64-w18-shipped-en-005` Take the month before this one, what did it come to? - wrong figures
- `t64-w18-shipped-de-006` Wie haben sich meine Lebensmittelausgaben von Quartal zu Quartal entwi - wrong figures
- `t64-w18-shipped-en-008` And how does the second half of the year compare on transport? - wrong figures
- `t64-w19-shipped-de-002` Und welcher von den fuenf war der kleinste Posten? - wrong figures
- `t64-w19-shipped-de-004` Wie gross ist der Anteil der Lebensmittel an meinen Ausgaben? - wrong figures
- `t64-w19-shipped-de-006` Wie verteilen sich meine Abos auf die einzelnen Anbieter? - wrong figures
- `t64-w19-shipped-de-007` Was ist im laufenden Quartal bei mir zusammengekommen? - wrong figures
- `t64-w19-shipped-en-009` What did November 2025 add up to for me? - wrong figures
- `t64-w19-shipped-en-011` And what share of my subscriptions does that make? - wrong figures
- `t64-w19-shipped-en-013` How does my spending compare quarter by quarter? - wrong figures
- `t64-w20-shipped-de-004` Zeig mir meine Lebensmittelausgaben im dritten Quartal 2025 nach Unter - wrong figures
- `t64-w20-shipped-de-006` Wie viel habe ich pro Quartal fuer Lebensmittel ausgegeben? - wrong figures
- `t64-w20-shipped-de-008` Wie viel ist bei mir ueber PayPal rausgegangen? - wrong figures
- `t64-w20-shipped-de-012` Habe ich im November mehr fuer Lebensmittel ausgegeben als im Oktober? - wrong figures
- `t64-w20-shipped-en-015` Same question for the whole quarter, please. - wrong figures
- `t64-w21-shipped-de-009` was hab ich 2025 an die hausverwaltung ueberwiesen? - wrong figures
- `t64-w22-shipped-en-001` What did the whole of last month add up to for me? - wrong figures
- `t64-w22-shipped-en-002` What have I spent in the last 90 days? - wrong figures
- `t64-w22-shipped-en-004` How has my grocery spending moved month by month since the summer? - wrong figures
- `t64-w22-shipped-en-007` Which merchants took the most money from me in the last 90 days? Top f - wrong figures
- `t64-w22-shipped-de-010` Und wie sieht das gegen letzten Monat aus? - wrong figures
- `t64-w22-shipped-de-011` Und wie viel davon war beim Baecker? - wrong figures
- `t64-w22-shipped-de-012` Wie teilen sich meine Restaurant- und Essensausgaben seit dem Sommer a - wrong figures
- `t64-w22-shipped-de-015` Wie viel habe ich in den letzten zwei Wochen ausgegeben? - wrong figures
