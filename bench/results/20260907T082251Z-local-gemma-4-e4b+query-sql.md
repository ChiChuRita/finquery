### local:gemma-4-e4b+query on the sql set

459 datapoints, 2026-09-07T08:22:51+00:00, 8281.7 s in total, 18.0 s per datapoint, median 16.5 s, p90 25.6 s.

| | n | figure match | SQL valid | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: |
| **all** | 459 | 80 % | 100 % | 91 % | 16.5 |
| breakdown | 59 | 76 % | 98 % | 83 % | 17.0 |
| comparison | 38 | 84 % | 100 % | 79 % | 18.4 |
| entity | 69 | 88 % | 100 % | 94 % | 15.8 |
| follow-up | 77 | 74 % | 100 % | 91 % | 17.9 |
| period | 58 | 83 % | 100 % | 95 % | 17.3 |
| ranking | 39 | 64 % | 100 % | 85 % | 16.8 |
| total | 62 | 84 % | 100 % | 95 % | 15.8 |
| trend | 57 | 84 % | 100 % | 96 % | 14.7 |
| difficulty 1 | 67 | 96 % | 100 % | 98 % | 14.8 |
| difficulty 2 | 211 | 83 % | 100 % | 93 % | 16.3 |
| difficulty 3 | 181 | 71 % | 99 % | 84 % | 18.7 |

Missed (91):

- `s04-rent-total-de` Wie viel Miete habe ich 2025 insgesamt gezahlt? - wrong figures
- `s06-groceries-per-week-de` Was habe ich 2025 im Schnitt pro Woche fuer Lebensmittel ausgegeben, a - wrong figures
- `s18-needs-review-merchants-de` Welche Haendler stecken in 'Needs review', und wie viele Buchungen sin - wrong figures
- `s21-categorized-share-en` How much of my 2025 spending is categorized and how much still needs r - wrong figures
- `s26-groceries-vs-dining-de` Vergleiche meine Ausgaben fuer Lebensmittel und fuers Essengehen, pro  - wrong figures
- `s30-anna-vs-max-en` Compare what I sent Anna with what I sent Max. - wrong figures
- `s34-cumulative-de` Zeig mir meine kumulierten Ausgaben pro Monat. - wrong figures
- `s41-smallest-recurring-de` Was ist meine kleinste wiederkehrende Zahlung? - wrong figures
- `s43-worst-grocery-month-de` In welchem Monat habe ich am meisten fuer Lebensmittel ausgegeben? - wrong figures
- `s45-biggest-without-rent-de` Wer hat 2025 am meisten Geld von mir bekommen, ohne die Miete? - wrong figures
- `s59-bakery-de` Wie oft war ich 2025 beim Baecker und was habe ich dort gelassen? - wrong figures
- `s62-only-groceries-en` Only groceries. - wrong figures
- `s71-last-three-months-en` What did I spend in total in the last three months of the year? - wrong figures
- `g011-total` Wie hoch waren meine Gesamtausgaben bei der BVG im Jahr 2025? - wrong figures
- `g012-total` How much did I spend in November 2025 on dining out? - wrong figures
- `g003-trend` Show my monthly spending across 2025 excluding Housing. - wrong figures
- `g006-trend` How did my monthly spending on dining out develop in the second quarte - wrong figures
- `g005-ranking` What were my 3 smallest spending transactions in 2025? - wrong figures
- `g008-ranking` Was waren meine 3 groessten Ausgaben im November 2025? - wrong figures
- `g009-ranking` What were my top 3 largest supermarket purchases in 2025? - wrong figures
- `g005-follow-up` Welche drei Haendler waren da am teuersten? - wrong figures
- `g009-period` How much did I spend in total between 2025-02-01 and 2025-04-30 exclud - wrong figures
- `t64-w01-shipped-en-005` where does most of my money go? top 5 please - wrong figures
- `t64-w01-shipped-en-006` and how much of that was just the BVG tickets? - wrong figures
- `t64-w02-shipped-en-008` How does my eating out this month compare with last month? - wrong figures
- `t64-w02-shipped-de-003` Und wie sieht das diesen Monat aus? - wrong figures
- `t64-w02-shipped-de-004` Und wie verteilt sich dieser Betrag auf die Unterkategorien? - wrong figures
- `t64-w03-shipped-en-014` And which merchants are those uncategorized bookings from? - wrong figures
- `t64-w04-shipped-de-010` Was habe ich im dritten Quartal 2025 fuers Essengehen ausgegeben? - wrong figures
- `t64-w05-shipped-en-002` How much did I spend per week on average in November 2025? - wrong figures
- `t64-w05-shipped-en-004` How did the average size of one grocery booking change from quarter to - wrong figures
- `t64-w05-shipped-en-008` And how often did I book with that landlord over the same year? - wrong figures
- `t64-w05-shipped-en-010` Which three merchants did I book with most often in 2025? - wrong figures
- `t64-w05-shipped-de-011` Wie viel habe ich letzten Monat pro Woche im Schnitt ausgegeben? - wrong figures
- `t64-w05-shipped-de-014` Aufschluesselung meiner Ausgaben 2025 nach Kategorie, und was ist das  - The query was refused 2 times, last reason: ORDER BY clause should come after UNION ALL not before
- `t64-w05-shipped-en-015` Did I book more often in December 2025 than in November, and what did  - wrong figures
- `t64-w06-shipped-en-003` Which subscriptions am I actually paying for, and what does each of th - wrong figures
- `t64-w06-shipped-en-005` What did rent, electricity and insurance together cost me last month? - wrong figures
- `t64-w06-shipped-en-007` Of the bills that come off exactly once a month, which three take the  - wrong figures
- `t64-w06-shipped-en-008` Has my Netflix payment gone up since January? - wrong figures
- `t64-w06-shipped-de-013` Was zahle ich pro Monat an Fitness First? - wrong figures
- `t64-w06-shipped-de-014` Welche Zahlungen gehen jeden Monat raus, und wie viel sind das pro Anb - wrong figures
- `t64-w07-shipped-en-002` Did Amazon ever pay me money back? - wrong figures
- `t64-w07-shipped-de-004` Und wie viel davon kam im vierten Quartal an? - wrong figures
- `t64-w07-shipped-de-005` Woher kam mein Geld 2025? Bitte nach Zahler aufschluesseln. - wrong figures
- `t64-w07-shipped-de-008` Wie verteilt sich mein Gehalt 2025 auf die Monate? - wrong figures
- `t64-w08-shipped-en-003` How much more did I spend on transport in the second half of 2025 than - wrong figures
- `t64-w08-shipped-de-003` Und im vierten Quartal, wie sieht das dagegen aus? - wrong figures
- `t64-w08-shipped-de-006` Wie hat sich mein Essengehen ueber die vier Quartale entwickelt? - wrong figures
- `t64-w09-shipped-de-003` Wie verteilen sich meine Ausgaben 2025 prozentual auf die Kategorien? - wrong figures
- `t64-w09-shipped-de-006` Welchen Anteil meiner Ausgaben hat 2025 die Miete verschlungen? - wrong figures
- `t64-w09-shipped-de-013` Und wie teilt sich dieser Monat auf die Kategorien auf? - wrong figures
- `t64-w09-shipped-en-015` How does my grocery spending split across supermarket, bakery and drug - wrong figures
- `t64-w10-shipped-de-001` Was haben mich meine Abos 2025 insgesamt gekostet? - wrong figures
- `t64-w10-shipped-de-004` Wie viel ist pro Quartal fuer Transport draufgegangen? - wrong figures
- `t64-w10-shipped-de-005` Wie viel Geld ist eigentlich ueber PayPal rausgegangen? - wrong figures
- `t64-w10-shipped-en-004` Which payees took the most money off me in the second half of the year - wrong figures
- `t64-w11-shipped-en-006` top 3 shops that ate my money in december please - wrong figures
- `t64-w11-shipped-de-008` was is letzten monat so alles weggegangen? - wrong figures
- `t64-w11-shipped-de-010` was zahl ich eigentlich im schnitt pro monat fuer die miete? - wrong figures
- `t64-w13-shipped-de-004` Welche Zahlungsempfaenger stecken hinter den Buchungen, die noch keine - wrong figures
- `t64-w13-shipped-de-010` Welche fuenf Unterkategorien haben mich 2025 am meisten gekostet? - wrong figures
- `t64-w14-shipped-de-008` An welche Leute habe ich per PayPal ueberwiesen, und wie viel an wen? - wrong figures
- `t64-w14-shipped-en-011` What did the doener and the dean and david bowls add up to in the last - wrong figures
- `t64-w14-shipped-de-015` Und wie oft war ich da im ganzen Jahr? - wrong figures
- `t64-w15-shipped-de-005` Wie viel gebe ich eigentlich pro Tag aus? - wrong figures
- `t64-w15-shipped-de-008` Und was war das pro Woche in dem Monat? - wrong figures
- `t64-w15-shipped-en-009` How many bookings do I have per category this year? - wrong figures
- `t64-w15-shipped-en-013` On average how many bookings land on my account in a month? - wrong figures
- `t64-w15-shipped-en-015` How often has Netflix charged me and what is the average charge? - wrong figures
- `t64-w16-shipped-de-003` Was zahle ich jeden Monat an die Hausverwaltung? - wrong figures
- `t64-w16-shipped-en-005` How did my fixed costs move over 2025? Rent, electricity, insurance, p - wrong figures
- `t64-w16-shipped-de-006` Wie verteilen sich meine festen Kosten im Dezember 2025 auf die Katego - wrong figures
- `t64-w16-shipped-en-008` What did my recurring bills cost me last month? - wrong figures
- `t64-w16-shipped-de-013` Und im Dezember, wie hoch waren die festen Kosten da? - wrong figures
- `t64-w16-shipped-en-014` And how much is that one costing me every month? - wrong figures
- `t64-w17-shipped-de-013` Und wie viel davon kam im ersten Halbjahr? - wrong figures
- `t64-w17-shipped-en-014` And how much of that April money was not the salary? - wrong figures
- `t64-w18-shipped-de-006` Wie haben sich meine Lebensmittelausgaben von Quartal zu Quartal entwi - wrong figures
- `t64-w19-shipped-de-002` Und welcher von den fuenf war der kleinste Posten? - wrong figures
- `t64-w19-shipped-de-004` Wie gross ist der Anteil der Lebensmittel an meinen Ausgaben? - wrong figures
- `t64-w19-shipped-de-006` Wie verteilen sich meine Abos auf die einzelnen Anbieter? - wrong figures
- `t64-w19-shipped-de-008` Habe ich im Juli mehr im Restaurant und Cafe ausgegeben als im August? - wrong figures
- `t64-w19-shipped-en-011` And what share of my subscriptions does that make? - wrong figures
- `t64-w20-shipped-de-008` Wie viel ist bei mir ueber PayPal rausgegangen? - wrong figures
- `t64-w20-shipped-de-010` Was ist in diesem Quartal bei mir alles vom Konto gegangen? - wrong figures
- `t64-w20-shipped-en-011` Who were my five most expensive merchants in the second half of 2025? - wrong figures
- `t64-w20-shipped-en-013` And what was the Netflix share of that? - wrong figures
- `t64-w20-shipped-en-015` Same question for the whole quarter, please. - wrong figures
- `t64-w22-shipped-en-007` Which merchants took the most money from me in the last 90 days? Top f - wrong figures
- `t64-w22-shipped-de-012` Wie teilen sich meine Restaurant- und Essensausgaben seit dem Sommer a - wrong figures
