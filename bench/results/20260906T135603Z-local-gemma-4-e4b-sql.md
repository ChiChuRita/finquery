### local:gemma-4-e4b on the sql set

152 datapoints, 2026-09-06T13:56:03+00:00, 1430.7 s in total, 9.4 s per datapoint, median 8.2 s, p90 14.7 s.

| | n | figure match | SQL valid | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: |
| **all** | 152 | 66 % | 99 % | 75 % | 8.2 |
| breakdown | 18 | 61 % | 100 % | 78 % | 6.4 |
| comparison | 16 | 62 % | 100 % | 75 % | 13.5 |
| entity | 28 | 68 % | 93 % | 75 % | 9.9 |
| follow-up | 16 | 25 % | 100 % | 69 % | 6.5 |
| period | 18 | 100 % | 100 % | 94 % | 7.7 |
| ranking | 18 | 44 % | 100 % | 56 % | 9.6 |
| total | 24 | 88 % | 100 % | 75 % | 7.5 |
| trend | 14 | 71 % | 100 % | 79 % | 8.2 |
| difficulty 1 | 23 | 83 % | 96 % | 74 % | 7.0 |
| difficulty 2 | 76 | 66 % | 100 % | 82 % | 8.0 |
| difficulty 3 | 53 | 60 % | 98 % | 66 % | 9.6 |

Missed (51):

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
