### local:gemma-4-12b+query on the sql set

459 datapoints, 2026-09-07T05:11:40+00:00, 6799.1 s in total, 14.8 s per datapoint, median 12.7 s, p90 24.7 s.

| | n | figure match | SQL valid | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: |
| **all** | 459 | 80 % | 98 % | 85 % | 12.7 |
| breakdown | 59 | 68 % | 98 % | 86 % | 12.9 |
| comparison | 38 | 79 % | 95 % | 87 % | 14.5 |
| entity | 69 | 88 % | 97 % | 93 % | 12.0 |
| follow-up | 77 | 75 % | 99 % | 83 % | 12.8 |
| period | 58 | 83 % | 100 % | 93 % | 12.1 |
| ranking | 39 | 67 % | 95 % | 74 % | 13.6 |
| total | 62 | 89 % | 100 % | 90 % | 11.1 |
| trend | 57 | 84 % | 98 % | 70 % | 13.1 |
| difficulty 1 | 67 | 91 % | 100 % | 94 % | 11.0 |
| difficulty 2 | 211 | 82 % | 99 % | 86 % | 12.6 |
| difficulty 3 | 181 | 72 % | 97 % | 81 % | 13.5 |

Missed (93):

- `s17-income-vs-spending-en` Show me income and spending for each month of 2025. - wrong figures
- `s18-needs-review-merchants-de` Welche Haendler stecken in 'Needs review', und wie viele Buchungen sin - wrong figures
- `s21-categorized-share-en` How much of my 2025 spending is categorized and how much still needs r - wrong figures
- `s26-groceries-vs-dining-de` Vergleiche meine Ausgaben fuer Lebensmittel und fuers Essengehen, pro  - wrong figures
- `s30-anna-vs-max-en` Compare what I sent Anna with what I sent Max. - wrong figures
- `s33-groceries-trend-en` Is my grocery spending going up? - wrong figures
- `s34-cumulative-de` Zeig mir meine kumulierten Ausgaben pro Monat. - wrong figures
- `s41-smallest-recurring-de` Was ist meine kleinste wiederkehrende Zahlung? - The query was refused 2 times, last reason: misuse of aggregate: COUNT()
- `s62-only-groceries-en` Only groceries. - wrong figures
- `g004-total` What was my total spending on fitness in 2025? - wrong figures
- `g009-total` Was habe ich 2025 fuer Mobilfunk ausgegeben, also reine Handykosten oh - wrong figures
- `g003-comparison` Compare my spending on Public transport versus Ride hailing in 2025. - The query was refused 2 times, last reason: Public transport is a subcategory of Transport, not a category, so
- `g006-comparison` Compare my spending on Restaurant vs Delivery under Dining in 2025. - wrong figures
- `g003-trend` Show my monthly spending across 2025 excluding Housing. - wrong figures
- `g005-ranking` What were my 3 smallest spending transactions in 2025? - wrong figures
- `g008-ranking` Was waren meine 3 groessten Ausgaben im November 2025? - wrong figures
- `g009-ranking` What were my top 3 largest supermarket purchases in 2025? - wrong figures
- `g010-entity` Was war mein teuerster und mein guenstigster Einkauf bei Lidl im Jahr  - The query was refused 2 times, last reason: ORDER BY clause should come after UNION ALL not before
- `g012-entity` Wie viel habe ich im vierten Quartal 2025 bei Baeckerei Steinecke ausg - wrong figures
- `g002-follow-up` Und im Dezember? - wrong figures
- `g007-follow-up` Und wie oft war ich dort einkaufen? - wrong figures
- `g009-period` How much did I spend in total between 2025-02-01 and 2025-04-30 exclud - wrong figures
- `t64-w01-shipped-de-005` was zahl ich eigentlich jeden monat fuer meine abos? - wrong figures
- `t64-w01-shipped-en-005` where does most of my money go? top 5 please - wrong figures
- `t64-w02-shipped-en-003` And in the quarter before that one? - wrong figures
- `t64-w02-shipped-en-007` Which merchants did I spend the most with last month? Top five, please - wrong figures
- `t64-w02-shipped-de-004` Und wie verteilt sich dieser Betrag auf die Unterkategorien? - wrong figures
- `t64-w03-shipped-en-006` What have I left at the bakery all in all? - wrong figures
- `t64-w03-shipped-en-012` Did I spend more at the supermarket or on takeaway and delivery in 202 - wrong figures
- `t64-w03-shipped-en-014` And which merchants are those uncategorized bookings from? - wrong figures
- `t64-w04-shipped-de-010` Was habe ich im dritten Quartal 2025 fuers Essengehen ausgegeben? - wrong figures
- `t64-w04-shipped-en-011` Which merchants did I pay more than 500 euros in 2025? - wrong figures
- `t64-w05-shipped-en-004` How did the average size of one grocery booking change from quarter to - wrong figures
- `t64-w05-shipped-de-005` Wie oft war ich dieses Jahr bei Fitness First und was hat ein Besuch i - The query was refused 2 times, last reason: row value misused
- `t64-w05-shipped-en-008` And how often did I book with that landlord over the same year? - wrong figures
- `t64-w05-shipped-en-010` Which three merchants did I book with most often in 2025? - wrong figures
- `t64-w05-shipped-de-011` Wie viel habe ich letzten Monat pro Woche im Schnitt ausgegeben? - wrong figures
- `t64-w05-shipped-de-013` Wie viele Buchungen entfallen 2025 auf welche Kategorie? - wrong figures
- `t64-w06-shipped-en-005` What did rent, electricity and insurance together cost me last month? - wrong figures
- `t64-w06-shipped-en-007` Of the bills that come off exactly once a month, which three take the  - wrong figures
- `t64-w06-shipped-en-008` Has my Netflix payment gone up since January? - wrong figures
- `t64-w06-shipped-de-013` Was zahle ich pro Monat an Fitness First? - wrong figures
- `t64-w06-shipped-de-014` Welche Zahlungen gehen jeden Monat raus, und wie viel sind das pro Anb - wrong figures
- `t64-w07-shipped-de-001` Wie viel Gehalt habe ich 2025 bekommen? - wrong figures
- `t64-w07-shipped-de-004` Und wie viel davon kam im vierten Quartal an? - wrong figures
- `t64-w07-shipped-de-005` Woher kam mein Geld 2025? Bitte nach Zahler aufschluesseln. - wrong figures
- `t64-w08-shipped-en-003` How much more did I spend on transport in the second half of 2025 than - wrong figures
- `t64-w08-shipped-de-001` Wofuer ist im Dezember 2025 das meiste Geld draufgegangen? - wrong figures
- `t64-w08-shipped-en-007` Which three categories went up the most from the first half of the yea - The query was refused 2 times, last reason: no such column: second_half_eur
- `t64-w08-shipped-de-007` Vergleiche meine Kategorien im ersten und im zweiten Halbjahr 2025. - wrong figures
- `t64-w09-shipped-de-003` Wie verteilen sich meine Ausgaben 2025 prozentual auf die Kategorien? - wrong figures
- `t64-w09-shipped-en-012` Which month was my cheapest one this year? - wrong figures
- `t64-w09-shipped-en-015` How does my grocery spending split across supermarket, bakery and drug - wrong figures
- `t64-w10-shipped-en-001` Over the whole of 2025, what did the food shopping add up to? - wrong figures
- `t64-w10-shipped-de-005` Wie viel Geld ist eigentlich ueber PayPal rausgegangen? - wrong figures
- `t64-w10-shipped-de-006` Zeig mir die Ausgaben im Dezember 2025 nach Kategorie und dazu die Ges - wrong figures
- `t64-w10-shipped-en-004` Which payees took the most money off me in the second half of the year - wrong figures
- `t64-w11-shipped-de-005` wie haben sich meine abos ueber das jahr entwickelt, pro monat? - wrong figures
- `t64-w11-shipped-en-006` top 3 shops that ate my money in december please - wrong figures
- `t64-w11-shipped-de-008` was is letzten monat so alles weggegangen? - wrong figures
- `t64-w12-shipped-de-002` Wie viel Bargeld habe ich in den letzten 30 Tagen abgehoben? - wrong figures
- `t64-w13-shipped-de-001` Was kosten mich meine Streaming-Dienste insgesamt? - wrong figures
- `t64-w13-shipped-de-004` Welche Zahlungsempfaenger stecken hinter den Buchungen, die noch keine - wrong figures
- `t64-w13-shipped-en-011` Compare what I spent at the supermarket in November and in December 20 - wrong figures
- `t64-w14-shipped-de-008` An welche Leute habe ich per PayPal ueberwiesen, und wie viel an wen? - wrong figures
- `t64-w14-shipped-en-011` What did the doener and the dean and david bowls add up to in the last - wrong figures
- `t64-w14-shipped-de-015` Und wie oft war ich da im ganzen Jahr? - wrong figures
- `t64-w15-shipped-de-008` Und was war das pro Woche in dem Monat? - wrong figures
- `t64-w15-shipped-en-009` How many bookings do I have per category this year? - wrong figures
- `t64-w15-shipped-de-012` War ich im November oder im Dezember oefter beim Baecker? - The query was refused 2 times, last reason: no such column: total_eur
- `t64-w16-shipped-en-005` How did my fixed costs move over 2025? Rent, electricity, insurance, p - wrong figures
- `t64-w16-shipped-de-006` Wie verteilen sich meine festen Kosten im Dezember 2025 auf die Katego - wrong figures
- `t64-w16-shipped-en-008` What did my recurring bills cost me last month? - wrong figures
- `t64-w16-shipped-de-013` Und im Dezember, wie hoch waren die festen Kosten da? - The query was refused 2 times, last reason: This statement matches 9 merchant patterns, which is every merchan
- `t64-w17-shipped-en-008` Split my 2025 income into the salary and everything else. - The query was refused 2 times, last reason: A CASE over description or counterparty that returns a label of it
- `t64-w18-shipped-de-006` Wie haben sich meine Lebensmittelausgaben von Quartal zu Quartal entwi - The query was refused 2 times, last reason: SQLite cannot parse this: Expected END after CASE. Line 1, Col: 17
- `t64-w19-shipped-de-002` Und welcher von den fuenf war der kleinste Posten? - wrong figures
- `t64-w19-shipped-de-004` Wie gross ist der Anteil der Lebensmittel an meinen Ausgaben? - wrong figures
- `t64-w19-shipped-de-006` Wie verteilen sich meine Abos auf die einzelnen Anbieter? - wrong figures
- `t64-w19-shipped-en-011` And what share of my subscriptions does that make? - wrong figures
- `t64-w19-shipped-en-012` Break my October spending down by category, biggest first. - wrong figures
- `t64-w20-shipped-de-008` Wie viel ist bei mir ueber PayPal rausgegangen? - wrong figures
- `t64-w20-shipped-de-010` Was ist in diesem Quartal bei mir alles vom Konto gegangen? - wrong figures
- `t64-w20-shipped-en-013` And what was the Netflix share of that? - wrong figures
- `t64-w20-shipped-en-015` Same question for the whole quarter, please. - wrong figures
- `t64-w21-shipped-en-004` split my grocery spend for 2025 into the subcategories, and give me th - wrong figures
- `t64-w21-shipped-de-015` und im juli dann, war das mehr? - wrong figures
- `t64-w22-shipped-en-006` And what was the same thing in the quarter before that? - wrong figures
- `t64-w22-shipped-en-007` Which merchants took the most money from me in the last 90 days? Top f - wrong figures
- `t64-w22-shipped-de-010` Und wie sieht das gegen letzten Monat aus? - wrong figures
- `t64-w22-shipped-de-011` Und wie viel davon war beim Baecker? - wrong figures
- `t64-w22-shipped-de-012` Wie teilen sich meine Restaurant- und Essensausgaben seit dem Sommer a - wrong figures
- `t64-w22-shipped-de-015` Wie viel habe ich in den letzten zwei Wochen ausgegeben? - wrong figures
