### local:gemma-4-12b+query on the sql set

459 datapoints, 2026-09-07T05:11:40+00:00, 7755.4 s in total, 16.9 s per datapoint, median 15.2 s, p90 25.1 s.

| | n | figure match | SQL valid | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: |
| **all** | 459 | 82 % | 99 % | 89 % | 15.2 |
| breakdown | 59 | 71 % | 97 % | 80 % | 15.6 |
| comparison | 38 | 90 % | 100 % | 92 % | 18.2 |
| entity | 69 | 91 % | 100 % | 93 % | 15.1 |
| follow-up | 77 | 75 % | 100 % | 86 % | 15.3 |
| period | 58 | 84 % | 100 % | 95 % | 13.9 |
| ranking | 39 | 74 % | 100 % | 95 % | 16.3 |
| total | 62 | 90 % | 100 % | 94 % | 13.4 |
| trend | 57 | 82 % | 98 % | 84 % | 14.6 |
| difficulty 1 | 67 | 97 % | 100 % | 94 % | 12.9 |
| difficulty 2 | 211 | 84 % | 100 % | 90 % | 15.1 |
| difficulty 3 | 181 | 75 % | 99 % | 87 % | 15.9 |

Missed (81):

- `s04-rent-total-de` Wie viel Miete habe ich 2025 insgesamt gezahlt? - wrong figures
- `s18-needs-review-merchants-de` Welche Haendler stecken in 'Needs review', und wie viele Buchungen sin - wrong figures
- `s21-categorized-share-en` How much of my 2025 spending is categorized and how much still needs r - wrong figures
- `s26-groceries-vs-dining-de` Vergleiche meine Ausgaben fuer Lebensmittel und fuers Essengehen, pro  - wrong figures
- `s33-groceries-trend-en` Is my grocery spending going up? - wrong figures
- `s34-cumulative-de` Zeig mir meine kumulierten Ausgaben pro Monat. - wrong figures
- `s35-net-per-month-en` What is my net per month, income minus spending? - wrong figures
- `s41-smallest-recurring-de` Was ist meine kleinste wiederkehrende Zahlung? - wrong figures
- `s54-last-rent-en` When was my last rent payment and how much was it? - wrong figures
- `s62-only-groceries-en` Only groceries. - wrong figures
- `g003-total` Was habe ich im gesamten Jahr 2025 fuer oeffentliche Verkehrsmittel au - wrong figures
- `g006-comparison` Compare my spending on Restaurant vs Delivery under Dining in 2025. - wrong figures
- `g002-follow-up` Und im Dezember? - wrong figures
- `t64-w01-shipped-de-005` was zahl ich eigentlich jeden monat fuer meine abos? - wrong figures
- `t64-w01-shipped-en-005` where does most of my money go? top 5 please - wrong figures
- `t64-w02-shipped-en-003` And in the quarter before that one? - wrong figures
- `t64-w02-shipped-en-007` Which merchants did I spend the most with last month? Top five, please - wrong figures
- `t64-w02-shipped-en-008` How does my eating out this month compare with last month? - wrong figures
- `t64-w02-shipped-de-003` Und wie sieht das diesen Monat aus? - wrong figures
- `t64-w02-shipped-de-004` Und wie verteilt sich dieser Betrag auf die Unterkategorien? - wrong figures
- `t64-w03-shipped-en-014` And which merchants are those uncategorized bookings from? - wrong figures
- `t64-w04-shipped-de-006` Was kostet mich jedes einzelne Abo im Jahr 2025? - wrong figures
- `t64-w04-shipped-en-007` What did I spend at the supermarket each month? - wrong figures
- `t64-w05-shipped-en-002` How much did I spend per week on average in November 2025? - wrong figures
- `t64-w05-shipped-en-004` How did the average size of one grocery booking change from quarter to - wrong figures
- `t64-w05-shipped-en-010` Which three merchants did I book with most often in 2025? - wrong figures
- `t64-w05-shipped-de-011` Wie viel habe ich letzten Monat pro Woche im Schnitt ausgegeben? - wrong figures
- `t64-w05-shipped-de-014` Aufschluesselung meiner Ausgaben 2025 nach Kategorie, und was ist das  - wrong figures
- `t64-w06-shipped-en-003` Which subscriptions am I actually paying for, and what does each of th - wrong figures
- `t64-w06-shipped-en-007` Of the bills that come off exactly once a month, which three take the  - wrong figures
- `t64-w06-shipped-en-008` Has my Netflix payment gone up since January? - wrong figures
- `t64-w06-shipped-de-013` Was zahle ich pro Monat an Fitness First? - wrong figures
- `t64-w06-shipped-de-015` Wie viel Versicherungsbeitrag ist im letzten Quartal abgebucht worden? - wrong figures
- `t64-w06-shipped-de-014` Welche Zahlungen gehen jeden Monat raus, und wie viel sind das pro Anb - wrong figures
- `t64-w07-shipped-en-001` What was my total income in 2025, including anything that was not sala - wrong figures
- `t64-w08-shipped-en-003` How much more did I spend on transport in the second half of 2025 than - wrong figures
- `t64-w08-shipped-de-001` Wofuer ist im Dezember 2025 das meiste Geld draufgegangen? - wrong figures
- `t64-w09-shipped-de-003` Wie verteilen sich meine Ausgaben 2025 prozentual auf die Kategorien? - wrong figures
- `t64-w09-shipped-en-012` Which month was my cheapest one this year? - The query was refused 2 times, last reason: no such column: total_eur
- `t64-w09-shipped-de-013` Und wie teilt sich dieser Monat auf die Kategorien auf? - wrong figures
- `t64-w09-shipped-en-015` How does my grocery spending split across supermarket, bakery and drug - wrong figures
- `t64-w10-shipped-de-003` Und wie sieht dieselbe Liste fuer den November aus? - wrong figures
- `t64-w10-shipped-de-005` Wie viel Geld ist eigentlich ueber PayPal rausgegangen? - wrong figures
- `t64-w10-shipped-de-007` Wie viel habe ich in den letzten drei Monaten des Jahres ausgegeben? - wrong figures
- `t64-w11-shipped-de-005` wie haben sich meine abos ueber das jahr entwickelt, pro monat? - wrong figures
- `t64-w11-shipped-en-006` top 3 shops that ate my money in december please - wrong figures
- `t64-w11-shipped-de-008` was is letzten monat so alles weggegangen? - wrong figures
- `t64-w12-shipped-de-007` Und wie sieht das seit dem Sommer aus, im Restaurant? - wrong figures
- `t64-w13-shipped-de-002` Wie teilen sich meine Abos auf die Unterkategorien auf? - wrong figures
- `t64-w13-shipped-de-004` Welche Zahlungsempfaenger stecken hinter den Buchungen, die noch keine - wrong figures
- `t64-w13-shipped-en-007` Per month, how much money went through bookings that are still uncateg - wrong figures
- `t64-w13-shipped-de-010` Welche fuenf Unterkategorien haben mich 2025 am meisten gekostet? - wrong figures
- `t64-w14-shipped-de-008` An welche Leute habe ich per PayPal ueberwiesen, und wie viel an wen? - wrong figures
- `t64-w14-shipped-en-011` What did the doener and the dean and david bowls add up to in the last - wrong figures
- `t64-w14-shipped-de-015` Und wie oft war ich da im ganzen Jahr? - wrong figures
- `t64-w15-shipped-de-005` Wie viel gebe ich eigentlich pro Tag aus? - wrong figures
- `t64-w15-shipped-de-008` Und was war das pro Woche in dem Monat? - wrong figures
- `t64-w15-shipped-en-013` On average how many bookings land on my account in a month? - wrong figures
- `t64-w16-shipped-de-003` Was zahle ich jeden Monat an die Hausverwaltung? - wrong figures
- `t64-w16-shipped-de-006` Wie verteilen sich meine festen Kosten im Dezember 2025 auf die Katego - wrong figures
- `t64-w16-shipped-en-008` What did my recurring bills cost me last month? - wrong figures
- `t64-w16-shipped-en-010` Which of my subscriptions is the most expensive per month? - wrong figures
- `t64-w16-shipped-en-014` And how much is that one costing me every month? - wrong figures
- `t64-w17-shipped-en-008` Split my 2025 income into the salary and everything else. - The query was refused 2 times, last reason: Salary is a subcategory of Income, not a category, so `category = 
- `t64-w17-shipped-de-013` Und wie viel davon kam im ersten Halbjahr? - wrong figures
- `t64-w18-shipped-de-007` Zeig mir je Kategorie, wie sich der Dezember gegen den November schlae - The query was refused 2 times, last reason: no such column: total_eur
- `t64-w19-shipped-de-002` Und welcher von den fuenf war der kleinste Posten? - wrong figures
- `t64-w19-shipped-de-004` Wie gross ist der Anteil der Lebensmittel an meinen Ausgaben? - wrong figures
- `t64-w19-shipped-de-006` Wie verteilen sich meine Abos auf die einzelnen Anbieter? - wrong figures
- `t64-w19-shipped-de-007` Was ist im laufenden Quartal bei mir zusammengekommen? - wrong figures
- `t64-w19-shipped-en-011` And what share of my subscriptions does that make? - wrong figures
- `t64-w20-shipped-de-008` Wie viel ist bei mir ueber PayPal rausgegangen? - wrong figures
- `t64-w20-shipped-en-011` Who were my five most expensive merchants in the second half of 2025? - wrong figures
- `t64-w20-shipped-en-013` And what was the Netflix share of that? - wrong figures
- `t64-w21-shipped-en-004` split my grocery spend for 2025 into the subcategories, and give me th - wrong figures
- `t64-w21-shipped-de-015` und im juli dann, war das mehr? - wrong figures
- `t64-w22-shipped-en-006` And what was the same thing in the quarter before that? - wrong figures
- `t64-w22-shipped-en-007` Which merchants took the most money from me in the last 90 days? Top f - wrong figures
- `t64-w22-shipped-de-010` Und wie sieht das gegen letzten Monat aus? - wrong figures
- `t64-w22-shipped-de-012` Wie teilen sich meine Restaurant- und Essensausgaben seit dem Sommer a - wrong figures
- `t64-w22-shipped-de-015` Wie viel habe ich in den letzten zwei Wochen ausgegeben? - wrong figures
