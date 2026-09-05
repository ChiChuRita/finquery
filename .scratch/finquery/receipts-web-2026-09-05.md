# Twenty photographed receipts from the web, through the receipt reader

2026-09-05. Twenty real receipts (seventeen German-market, three not) collected from Wikimedia
Commons, every one freely licensed, and run through FinQuery's receipt path on OpenRouter
(`FINQUERY_PROVIDER=openrouter`, fast slot = Gemma 4 26B, subagent settings, reasoning off).

The images live in `fixtures/private/receipts-web/` with a `SOURCES.md` naming the Commons page,
the licence and the author of each. That folder is gitignored; this file holds no image content.

What was run:

- `extract.bill.read_bill_image` + `check_bill` per file, which is exactly what the chat tool
  `import_file` calls for an image attachment (`ingest/chat_import.py:_import_bill`). This is the
  receipt path.
- `POST /api/imports/extract` per file against a private instance on port 8103, which is the
  statement path. A receipt is not a statement, so this is a rejection test.
- Three of them through the real UI (browser, chat composer, preview card).

"Printed" is what I read off the photo myself. "FinQuery read" is the checked extraction.

## Per receipt

| File | Printed: merchant / date / total / items | FinQuery read: merchant / date / total / items | Items add up? | Time |
| --- | --- | --- | --- | --- |
| de-kassenbon-edeka.jpg | E center EDEKA / 08.12.07 / 14,84 / 8 | Ecenter EDEKA / 2007-12-08 / 14,84 / 8 (sum 14,84) | yes | 5,0 s |
| de-rewe-kreiller.png | REWE fragment / none printed / none printed / 3 | Kreiller Str. 81673 München / today / 5,77 / 3 (sum 5,77) | flagged no_total, no_date (correct) | 1,6 s |
| de-lidl-aurich-2019.jpg | Lidl Aurich / 04.05.19 / 18,02 / 7 | LIDL / 2019-05-04 / 18,02 / 8 (sum 18,51) | no, does_not_add_up | 4,1 s |
| de-lidl-2007.jpg | Lidl Thannhausen / 28.06.2007 / 24.22 / 10 | Lidl / today / 24,22 / 9 (sum 14,23) | no, does_not_add_up + no_date | 4,6 s |
| de-aldi-hesel-2019.jpg | ALDI Hesel / 04.05.2019 / 25,74 / 30 | ALDI HESEL, IM BRINK 8 / 2019-05-04 / 25,74 / 32 (sum 52,13) | no, does_not_add_up | 11,7 s |
| de-aldi-2006.jpg | ALDI Ebersberg / 18.12.06 / 57.23 / 14 | ALDI / 2006-12-18 / 57,23 / 15 (sum 58,52) | no, does_not_add_up | 5,8 s |
| de-aldi-leergutbon-2019.jpg | ALDI Leergutbon / 23.03.2019 / 0.25 in / 1 | ALDI Markt / 2019-03-23 / 0,25 out / 1 (sum 0,25) | yes (but booked the wrong way round) | 3,0 s |
| de-rossmann-bunde-2019.jpg | ROSSMANN Bunde / 04.05.2019 / 7,85 / 1 | ROSSMANN Mein Drogeriemarkt / 2019-05-04 / 7,85 / 1 (sum 47,85) | no, does_not_add_up | 2,9 s |
| de-combi-hesel-2019.jpg | Combi Hesel / 04.05.19 / 28,20 / 15 | Combi. Frisch. Nebenan. / 2019-05-04 / 28,20 / 10 (sum 19,70) | no, does_not_add_up | 4,9 s |
| de-fressnapf-2020.png | Fressnapf Köln / 04.12.20 / 34,09 / 3 | Fressnapf Köln-Ehrenfeld / 2020-12-04 / 34,09 / 3 (sum 34,97) | no, does_not_add_up (the receipt itself does not, see below) | 2,7 s |
| de-schlecker-2009.jpg | SCHLECKER / 24.12.2009 / 5,96 / 4 | SCHLÖCKER / 2009-12-24 / 5,96 / 4 (sum 5,96) | yes | 2,3 s |
| de-esso-2020.jpg | ESSO Aschendorf / 28.12.2019 / 143,93 / 1 | Esso Station / 2019-12-28 / 143,93 / 1 (sum 100,02) | no, does_not_add_up | 2,5 s |
| de-tankquittung-hit-2020.jpg | HIT-Tankstelle Rheinbach / 21.11.2020 / 76,64 / 1 | HIT-Tankstelle / 2020-11-21 / 76,64 / 1 (sum 76,64) | yes | 1,9 s |
| de-augustiner-2020.jpg | Neuhauser Augustiner / 10.09.2020 / 23.50 / 2 | NEUHAUSER AUGUSTINER / 2020-09-10 / 23,50 / 2 (sum 23,50) | yes | 1,6 s |
| de-saurusselalm-2024.jpg | Saurüsselalm (photo rotated 90°) / 07.04.2024 / 23,40 / 2 | Saurüsselalm / 2024-04-07 / 23,40 / 2 (sum 23,40) | yes | 2,8 s |
| de-vogtlandbahn-2015.jpg | Vogtlandbahn dining car / 04.06.2015 / 6.60 / 2 | VOGTLANDBAHN-GMBH / 2015-06-04 / 6,60 / 2 (sum 6,60) | yes | 6,7 s |
| de-kassenbons-ralfr-2018.jpg | Three receipts in one photo: Lidl 10,54 + EDEKA 4,74 + REWE 1,88 / 16.02.2018 / 17,16 / 12 | LIDL / 2018-02-16 / 10,54 / 5 (sum 10,54) | yes for the one it saw, two receipts missing | 6,6 s |
| pl-supermarket.jpg | Biedronka Wrocław / 2020-01-09 / 8,27 PLN / 3 | Biedronka / 2020-01-09 / 8,27 (as EUR) / 3 (sum 10,27) | no, does_not_add_up | 2,9 s |
| it-supermarket-iva.jpg | Italian documento commerciale / none on the crop / 11,85 / 6 | DOCUMENTO COMMERCIALE di vendita o prestazione / today / 11,85 / 6 (sum 11,85) | flagged no_date (correct) | 6,1 s |
| us-family-dollar.jpg | Family Dollar, Muskogee OK / none printed / $2.18 / 2 | FAMILY DOLLAR / today / 2,18 / 2 (sum 2,00) | no, does_not_add_up (US pre-tax prices) | 2,3 s |

Totals: 1,6 s to 11,7 s per receipt, median about 3 s, one model call each.

### The score in one paragraph

The **printed total was read correctly on 19 of 19 receipts that print one**, to the cent, including
`zu zahlen`, `SUMME`, `Summe`, `Total`, `TOTAL`, `Gesamt`, `Gesamtbetrag`, `Preis`, `SUMA PLN` and
`TOTALE COMPLESSIVO`, and including the Fressnapf receipt that prints two totals (it took the
final 34,09 and not the 34,97 above the VAT-cut line). The twentieth is a cropped fragment with no
total, correctly flagged `no_total`. **Dates: 16 of the 17 printed dates correct**, in every format
that turned up (`08.12.07`, `04.05.19`, `04.05.2019`, `21.11.2020`, `2020-01-09`, and one buried in
a `Datum Uhrzeit Filiale` column block); the three receipts with no printed date were correctly
flagged `no_date`. **Line items: clean on 9 of 20.** Eight of the eleven flagged ones are real
misreads, all caught by the total guard; the amount that would be booked was still the printed
total in every single case. The merchant name is usable on all twenty (one dot-matrix typo,
`SCHLÖCKER` for `SCHLECKER`).

### The three through the UI

Composer attach, one message, preview card, screenshotted (screenshots in /tmp, not committed).

- `de-kassenbon-edeka.jpg`: card headed "Ecenter EDEKA: a receipt with no booking to match",
  eight item rows with amounts, "8 line items add up to the printed total of 14,84 EUR", then
  "Add this transaction?" with `Ecenter EDEKA / Cash / -14,84 €` and Confirm/Discard. Correct.
- `de-fressnapf-2020.png`: same shape, three item rows, "The line items do not add up to the
  printed total.", draft `-34,09 €`. The user sees the warning and the right amount.
- `de-aldi-hesel-2019.jpg`: 32 rows including two `ZWI.SUMME` rows the reader took for articles,
  "The line items do not add up to the printed total.", draft `-25,74 €`. The wrong itemisation is
  visible on the card, and because it does not add up no split is proposed.

Nothing was confirmed, so nothing was written.

## Findings

**1. Subtotal lines are read as articles.** German tills print running subtotals into the item
list: `ZWI.SUMME` (ALDI, twice on one receipt), `Summe 1 Pos. / Summe 9 Pos.` (Lidl 2007),
`SUB TOTAL`, `Zwischensumme` (Saurüsselalm). ALDI Hesel is the bad case: it kept both `ZWI.SUMME`
labels as articles, gave the first one the *next* article's price (0,75 instead of the printed
7,49), and from there description and amount drifted one row apart for the rest of the receipt,
while the closing `ZWI.SUMME 25,74` double-counted the whole basket. Lidl 2007 stopped at the
second subtotal and never picked up the `BÜROBOX 9.99` printed after it, returning 14,23 of a
24,22 receipt. `STATEMENT_INSTRUCTIONS` has a "what is not a booking" list; `BILL_INSTRUCTIONS`
has no equivalent.

**2. Quantity and multiplier lines are read as prices.** `2 x 0,49` under Gemüsemais (Lidl Aurich,
+0,49), `4 x 1.29` under Müsli Riegel (ALDI 2006, +1,29), and worst, the Esso fuel receipt where
`Säule 01 100,02 l 1,439 EUR/l` made the single article cost 100,02 instead of 143,93. Weight lines
(`0,208 KG x 19,90 EP`, `0,5484kg x E 2,79/kg`) were handled correctly, so the model knows the
pattern; it just needs telling that the number on such a line is never the price.

**3. Discount lines are dropped, and then nothing adds up.** Biedronka prints `Rabat -2,00` under a
4,99 article; Fressnapf prints `MwSt.-Senkung -0,88` between the item sum (34,97) and the final
total (34,09). Both totals were read right, both item lists were read right, and both were flagged
`does_not_add_up` purely because the negative line was left out. The prompt currently says "leave
out discounts you cannot read", which is the wrong default: a discount is the difference between
the item sum and the total, so leaving it out guarantees the guard fires.

**4. Dense, crumpled thermal paper gets invented.** Combi Hesel (15 items, weight lines, creased,
photographed on a table) came back with 10 items, several of them made up: `Mihanband`,
`Ollaphan Bio Rührei-Mix` twice, `Gemüse Tomate Bio Feigen Bio` merging three articles, and
amounts that are not on the paper (1,69 for a printed 1,99). This is the only receipt where the
reader invented text rather than skipping it. The total was still right and the guard fired.

**5. A currency glyph in front of the amount can become a digit.** Rossmann prints `€7,85`; the
reader returned `47,85` for the one article while getting the total `€7,85` right. Single-item
receipts are the case where a wrong item is most dangerous, because a one-item split is not
proposed but the number is shown to the user.

**6. Rotation is not a problem, faded print is not much of one.** The Saurüsselalm receipt is
photographed a full 90° on its side and came back perfect. The dot-matrix Schlecker receipt from
2009 and the marker-scribbled ALDI 2006 scan both read cleanly apart from one letter. The one
date that was missed (Lidl 2007) is the one a previous owner covered with a pink highlighter, and
that one was flagged rather than guessed.

**7. Several receipts in one photo: only the first is read.** The RalfR photo shows a Lidl, an
EDEKA and a REWE receipt side by side, 17,16 EUR together. The reader returned the Lidl one, read
it perfectly, and said nothing about the other two. `Bill` has no `note` field, so it has no way to
say "there are three here" the way `StatementPage.note` can.

**8. A deposit refund is booked as a spend.** The ALDI `Leergutbon` (0,25 EUR back for a can) was
read correctly and would be booked as `-0,25` money out, because `bill_outcome` always drafts
`direction="out"`. Pfand lines inside a normal receipt are fine (ALDI 2006 read both `Pfand 6 x
0,25 EUR` lines as items, correctly, since they are part of the total).

**9. No currency anywhere in the receipt path.** `Bill` has `total_text` but no currency span, and
`check_bill` produces cents with no unit. The Biedronka receipt would be booked as 8,27 EUR
instead of 8,27 PLN, and Family Dollar as 2,18 EUR instead of $2.18. Nothing flags it.

**10. US-style tax-exclusive receipts always fail the guard.** Family Dollar: 1.00 + 1.00 =
subtotal 2.00, tax 0.18, total 2.18. The items are right, the total is right, and the guard says
the receipt does not add up. Any US or Canadian receipt behaves this way.

**11. `POST /api/imports/extract` is not receipt-aware.** All twenty were posted to it. Eighteen
were correctly refused with 422 and a sentence ("This is a receipt from Rossmann, not a bank
statement."), which is the extraction sub-agent's `note` doing its job. Two were not:
`de-lidl-2007.jpg` returned **200** with nine "bookings" (Rucolasauce -0,99, VISU PENCIL SET -2,99
...) and `de-schlecker-2009.jpg` returned **200** with four. Every row came back flagged and the
reconciliation said `not_checkable`, so the review would catch it, but the REST door will hand a
caller a receipt dressed as a statement. The chat tool never has this problem because it routes by
attachment kind (`kind == "image"` goes to the bill reader).

## The fixes I would make, in order

1. **Give `BILL_INSTRUCTIONS` a "what is not a line item" list**, the way the statement prompt has
   one: `ZWI.SUMME`, `Zwischensumme`, `Summe N Pos.`, `SUB TOTAL`, `Posten`, `SUMME NETTO`, the VAT
   table, the payment lines (`Bar`, `Karte`, `EC-Abbuchung`, `Rückgeld`, `Geg. BAR`), and the
   total itself. Cheapest fix, and it alone accounts for three of the eight real misreads.
2. **Say that a quantity line carries no price.** One sentence: a line like `2 x 0,49`,
   `4 x 1.29`, `0,208 KG x 19,90 EP` or `Säule 01 100,02 l` belongs to the article line under or
   over it; never return its number as an `amount_text`. Two more misreads, including the 143,93
   fuel receipt that is off by 43 EUR in its itemisation.
3. **Ask for discounts as negative items instead of telling the model to drop them.** Replace
   "leave out discounts you cannot read" with "a discount, coupon, `Rabat` or `MwSt.-Senkung` line
   is a line item with a negative `amount_text`, exactly as printed". `check_bill` already sums
   signed cents; only `abs()` in the `BillLine` construction would have to go. Fixes Biedronka and
   Fressnapf, and makes the split legs right instead of merely unflagged.
4. **Let the guard accept "items + tax = total".** Add the printed tax total as an optional span
   (`tax_text`) and treat `summed + tax == total` as adding up. Otherwise every non-European
   receipt is permanently flagged.
5. **Add `currency_text` to `Bill` and refuse a non-EUR receipt loudly**, or carry the currency
   into the draft. Booking 8,27 PLN as 8,27 EUR is the one failure in this set that is silently
   wrong rather than flagged.
6. **Do not book today's date when the date could not be read.** `check_bill` sets
   `booked_on = today` with a `no_date` flag; the preview card then shows a real-looking date the
   receipt never carried. Better: leave the date out of the draft and make the Question card ask
   for it.
7. **A `note` field on `Bill`**, mirroring `StatementPage.note`, so the reader can say "this photo
   holds three receipts" or "this is not a receipt", and a second flag `several_receipts` that
   sends the user to crop and re-attach.
8. **Recognise a refund receipt.** A `Leergutbon`, `Retoure` or `Gutschrift` header, or a total
   printed as a credit, should draft `direction="in"`. Right now every receipt is money out.
9. **Route by kind at `/api/imports/extract`**, or re-check the result: an image extraction whose
   rows carry no dates and no balances and whose reconciliation is `not_checkable` is a receipt,
   not a statement, and should come back 422 like the other eighteen.

None of this was implemented. Nothing in `src/` or `frontend/` was touched.
