### local:gemma-4-e4b+query on the sql set

459 datapoints, 2026-09-07T00:49:52+00:00, 7077.7 s in total, 15.4 s per datapoint, median 14.3 s, p90 20.8 s.

| | n | figure match | SQL valid | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: |
| **all** | 459 | 76 % | 96 % | 90 % | 14.3 |
| breakdown | 59 | 70 % | 95 % | 78 % | 13.9 |
| comparison | 38 | 76 % | 97 % | 87 % | 16.7 |
| entity | 69 | 87 % | 99 % | 94 % | 14.6 |
| follow-up | 77 | 65 % | 96 % | 91 % | 14.8 |
| period | 58 | 81 % | 100 % | 93 % | 13.8 |
| ranking | 39 | 62 % | 85 % | 85 % | 14.8 |
| total | 62 | 82 % | 97 % | 90 % | 12.5 |
| trend | 57 | 86 % | 98 % | 96 % | 13.7 |
| difficulty 1 | 67 | 92 % | 100 % | 97 % | 12.4 |
| difficulty 2 | 211 | 77 % | 97 % | 90 % | 14.3 |
| difficulty 3 | 181 | 70 % | 94 % | 86 % | 15.2 |

Missed (108):

- `s04-rent-total-de` Wie viel Miete habe ich 2025 insgesamt gezahlt? - wrong figures
- `s06-groceries-per-week-de` Was habe ich 2025 im Schnitt pro Woche fuer Lebensmittel ausgegeben, a - wrong figures
- `s16-supermarkets-de` Wie verteilen sich meine Lebensmittelausgaben auf die einzelnen Laeden - wrong figures
- `s18-needs-review-merchants-de` Welche Haendler stecken in 'Needs review', und wie viele Buchungen sin - wrong figures
- `s21-categorized-share-en` How much of my 2025 spending is categorized and how much still needs r - wrong figures
- `s26-groceries-vs-dining-de` Vergleiche meine Ausgaben fuer Lebensmittel und fuers Essengehen, pro  - wrong figures
- `s28-q4-vs-q3-en` How does this quarter compare with the last one? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `s29-rent-constant-de` Ist meine Miete im Laufe des Jahres gestiegen? - wrong figures
- `s30-anna-vs-max-en` Compare what I sent Anna with what I sent Max. - wrong figures
- `s34-cumulative-de` Zeig mir meine kumulierten Ausgaben pro Monat. - wrong figures
- `s41-smallest-recurring-de` Was ist meine kleinste wiederkehrende Zahlung? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `s45-biggest-without-rent-de` Wer hat 2025 am meisten Geld von mir bekommen, ohne die Miete? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `s54-last-rent-en` When was my last rent payment and how much was it? - wrong figures
- `s56-all-subscriptions-en` What do all my subscriptions cost me per year? - wrong figures
- `s62-only-groceries-en` Only groceries. - wrong figures
- `s67-without-rent-de` Und ohne die Miete? - wrong figures
- `g011-total` Wie hoch waren meine Gesamtausgaben bei der BVG im Jahr 2025? - wrong figures
- `g012-total` How much did I spend in November 2025 on dining out? - wrong figures
- `g004-breakdown` Aufschluesselung meiner Ausgaben fuer Subscriptions im Jahr 2025 nach  - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `g005-comparison` Vergleiche meine Gesamteinnahmen mit meinen Gesamtausgaben im Jahr 202 - wrong figures
- `g007-comparison` Habe ich im ersten oder im zweiten Quartal 2025 mehr fuer Transport au - wrong figures
- `g002-trend` Wie haben sich meine Ausgaben fuer Transport monatlich im zweiten Halb - wrong figures
- `g003-ranking` Bei welchen 5 Geschaeften oder Dienstleistern hatte ich 2025 die meist - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `g008-ranking` Was waren meine 3 groessten Ausgaben im November 2025? - wrong figures
- `g009-ranking` What were my top 3 largest supermarket purchases in 2025? - wrong figures
- `g007-entity` How much did I spend at Cafe Milchbart in 2025, and when was the last  - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `g010-entity` Was war mein teuerster und mein guenstigster Einkauf bei Lidl im Jahr  - wrong figures
- `g001-follow-up` Und fuer Fitness? - wrong figures
- `g006-follow-up` What was the single biggest one? - wrong figures
- `g009-period` How much did I spend in total between 2025-02-01 and 2025-04-30 exclud - wrong figures
- `t64-w01-shipped-en-005` where does most of my money go? top 5 please - wrong figures
- `t64-w01-shipped-en-006` and how much of that was just the BVG tickets? - wrong figures
- `t64-w02-shipped-de-002` Was habe ich seit dem Sommer fuer Lebensmittel bezahlt? - wrong figures
- `t64-w03-shipped-en-008` How much lands in the Needs review bucket each month? - wrong figures
- `t64-w03-shipped-en-012` Did I spend more at the supermarket or on takeaway and delivery in 202 - wrong figures
- `t64-w03-shipped-en-014` And which merchants are those uncategorized bookings from? - wrong figures
- `t64-w04-shipped-de-010` Was habe ich im dritten Quartal 2025 fuers Essengehen ausgegeben? - wrong figures
- `t64-w05-shipped-en-002` How much did I spend per week on average in November 2025? - wrong figures
- `t64-w05-shipped-en-004` How did the average size of one grocery booking change from quarter to - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w05-shipped-de-007` Und wie viele Einkaeufe waren das pro Woche? - wrong figures
- `t64-w05-shipped-en-010` Which three merchants did I book with most often in 2025? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w05-shipped-de-013` Wie viele Buchungen entfallen 2025 auf welche Kategorie? - wrong figures
- `t64-w05-shipped-de-014` Aufschluesselung meiner Ausgaben 2025 nach Kategorie, und was ist das  - wrong figures
- `t64-w06-shipped-en-003` Which subscriptions am I actually paying for, and what does each of th - wrong figures
- `t64-w06-shipped-en-005` What did rent, electricity and insurance together cost me last month? - wrong figures
- `t64-w06-shipped-en-007` Of the bills that come off exactly once a month, which three take the  - wrong figures
- `t64-w06-shipped-en-008` Has my Netflix payment gone up since January? - wrong figures
- `t64-w06-shipped-de-013` Was zahle ich pro Monat an Fitness First? - wrong figures
- `t64-w06-shipped-de-014` Welche Zahlungen gehen jeden Monat raus, und wie viel sind das pro Anb - wrong figures
- `t64-w07-shipped-de-005` Woher kam mein Geld 2025? Bitte nach Zahler aufschluesseln. - wrong figures
- `t64-w07-shipped-en-007` Show me month by month what was left over after everything went out. - wrong figures
- `t64-w07-shipped-de-008` Wie verteilt sich mein Gehalt 2025 auf die Monate? - wrong figures
- `t64-w08-shipped-en-003` How much more did I spend on transport in the second half of 2025 than - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w08-shipped-de-003` Und im vierten Quartal, wie sieht das dagegen aus? - wrong figures
- `t64-w08-shipped-en-007` Which three categories went up the most from the first half of the yea - The query was refused 2 times, last reason: SQLite cannot parse this: Invalid expression / Unexpected token. L
- `t64-w08-shipped-de-006` Wie hat sich mein Essengehen ueber die vier Quartale entwickelt? - wrong figures
- `t64-w09-shipped-de-003` Wie verteilen sich meine Ausgaben 2025 prozentual auf die Kategorien? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w09-shipped-en-005` And which three merchants took the least? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w09-shipped-de-006` Welchen Anteil meiner Ausgaben hat 2025 die Miete verschlungen? - wrong figures
- `t64-w09-shipped-de-007` Zeig mir meine Ausgaben Monat fuer Monat. - wrong figures
- `t64-w09-shipped-en-010` And which grocery shop did I spend the least at? - wrong figures
- `t64-w09-shipped-de-013` Und wie teilt sich dieser Monat auf die Kategorien auf? - wrong figures
- `t64-w09-shipped-en-015` How does my grocery spending split across supermarket, bakery and drug - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w10-shipped-de-003` Und wie sieht dieselbe Liste fuer den November aus? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w10-shipped-de-005` Wie viel Geld ist eigentlich ueber PayPal rausgegangen? - wrong figures
- `t64-w10-shipped-en-004` Which payees took the most money off me in the second half of the year - wrong figures
- `t64-w11-shipped-en-004` and how about november, same thing? - wrong figures
- `t64-w11-shipped-en-006` top 3 shops that ate my money in december please - wrong figures
- `t64-w11-shipped-de-008` was is letzten monat so alles weggegangen? - wrong figures
- `t64-w11-shipped-de-010` was zahl ich eigentlich im schnitt pro monat fuer die miete? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w11-shipped-de-012` und wie sah das im august aus? - wrong figures
- `t64-w12-shipped-de-007` Und wie sieht das seit dem Sommer aus, im Restaurant? - wrong figures
- `t64-w13-shipped-de-004` Welche Zahlungsempfaenger stecken hinter den Buchungen, die noch keine - wrong figures
- `t64-w13-shipped-de-010` Welche fuenf Unterkategorien haben mich 2025 am meisten gekostet? - wrong figures
- `t64-w13-shipped-de-014` Und im Dezember, aufgeteilt nach Unterkategorie? - wrong figures
- `t64-w13-shipped-en-015` How much have I spent in cafes? - wrong figures
- `t64-w14-shipped-de-008` An welche Leute habe ich per PayPal ueberwiesen, und wie viel an wen? - wrong figures
- `t64-w14-shipped-en-011` What did the doener and the dean and david bowls add up to in the last - wrong figures
- `t64-w14-shipped-en-013` And how much of that came back as a refund? - wrong figures
- `t64-w14-shipped-de-015` Und wie oft war ich da im ganzen Jahr? - wrong figures
- `t64-w15-shipped-de-005` Wie viel gebe ich eigentlich pro Tag aus? - wrong figures
- `t64-w15-shipped-de-006` Und auf wie viele einzelne Einkaeufe hat sich dieser Betrag verteilt? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w15-shipped-de-008` Und was war das pro Woche in dem Monat? - wrong figures
- `t64-w15-shipped-en-009` How many bookings do I have per category this year? - wrong figures
- `t64-w15-shipped-en-013` On average how many bookings land on my account in a month? - wrong figures
- `t64-w15-shipped-de-014` Wie viele Buchungen habe ich diesen Monat? - wrong figures
- `t64-w16-shipped-de-003` Was zahle ich jeden Monat an die Hausverwaltung? - wrong figures
- `t64-w16-shipped-de-006` Wie verteilen sich meine festen Kosten im Dezember 2025 auf die Katego - wrong figures
- `t64-w16-shipped-en-008` What did my recurring bills cost me last month? - wrong figures
- `t64-w16-shipped-de-013` Und im Dezember, wie hoch waren die festen Kosten da? - wrong figures
- `t64-w16-shipped-en-014` And how much is that one costing me every month? - wrong figures
- `t64-w17-shipped-en-008` Split my 2025 income into the salary and everything else. - wrong figures
- `t64-w18-shipped-de-002` Welche drei Kategorien waren im vierten Quartal 2025 am teuersten? - The query sub-agent did not return a statement: Exceeded maximum output retries (1)
- `t64-w18-shipped-de-004` Und wie viel war es im Quartal davor? - wrong figures
- `t64-w18-shipped-en-008` And how does the second half of the year compare on transport? - wrong figures
- `t64-w19-shipped-de-002` Und welcher von den fuenf war der kleinste Posten? - wrong figures
- `t64-w19-shipped-de-004` Wie gross ist der Anteil der Lebensmittel an meinen Ausgaben? - wrong figures
- `t64-w19-shipped-de-006` Wie verteilen sich meine Abos auf die einzelnen Anbieter? - wrong figures
- `t64-w19-shipped-de-008` Habe ich im Juli mehr im Restaurant und Cafe ausgegeben als im August? - wrong figures
- `t64-w19-shipped-en-009` What did November 2025 add up to for me? - wrong figures
- `t64-w19-shipped-en-011` And what share of my subscriptions does that make? - wrong figures
- `t64-w20-shipped-de-008` Wie viel ist bei mir ueber PayPal rausgegangen? - wrong figures
- `t64-w20-shipped-en-011` Who were my five most expensive merchants in the second half of 2025? - wrong figures
- `t64-w22-shipped-en-002` What have I spent in the last 90 days? - wrong figures
- `t64-w22-shipped-en-007` Which merchants took the most money from me in the last 90 days? Top f - wrong figures
- `t64-w22-shipped-de-010` Und wie sieht das gegen letzten Monat aus? - wrong figures
- `t64-w22-shipped-de-012` Wie teilen sich meine Restaurant- und Essensausgaben seit dem Sommer a - wrong figures
- `t64-w22-shipped-de-015` Wie viel habe ich in den letzten zwei Wochen ausgegeben? - wrong figures
