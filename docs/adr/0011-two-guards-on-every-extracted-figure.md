# ADR 0011: Two guards on every extracted figure, and a review step for what fails them

Date: 2026-09-04
Status: accepted

## Context

ADR 0004 says every number the assistant states comes from a query it ran. That pushes the
problem one step back: the numbers in the database have to be right too. A CSV is safe, because
a column is parsed rather than read. A PDF statement and a photo are not: the only thing that
can turn a printed page into rows is a model, and a model that misreads `-1.150,00` as
`-1.155,00`, or skips a booking at a page break, produces a plausible number nobody can
distinguish from a real one. "The model is usually right" is not a story a finance app can tell.

Two properties of a bank statement make this checkable without another model. The figures are
printed in the source text, so a figure that is not in that text was not read. And a statement
carries its own arithmetic: an opening balance, a running balance per row and a closing balance.

## Decision

- **The extraction sub-agent returns spans, not figures.** `read_statement` answers with
  `date_text`, `amount_text` and `balance_text` copied out of the page, plus a `line` number and
  a direction. The cents are parsed from those spans in `finquery.extract.guards`, so the number
  that lands is the number that was printed, and the model's job is to point rather than to
  compute. `read_bill` does the same for a receipt.
- **The verbatim guard** checks that each span occurs literally in the source text, the page
  first and then the whole document. A date is the one exception to a plain substring check:
  Trade Republic prints the day and the year on different lines, so for a date every digit group
  of the span has to appear within two printed lines of the one it was read from.
- **The reconciliation guard** holds the rows to the statement's own arithmetic. Row by row, the
  balance of a row minus the balance of the row before it must be that row's amount. Per page,
  the first row's balance minus its own amount plus the page's bookings must be the last row's
  balance. Over the whole statement the same sum has to close, against the printed opening and
  closing balances where the layout says they cover these pages.
- **Printed balances are used only when they belong to the rows.** Every frame of the user's
  Trade Republic export begins with a `KONTOÜBERSICHT` whose figures are the whole export, so
  reconciling a slice against them would fail for a correct extraction. The Trade Republic layout
  therefore declares no balance labels at all and is checked on its running balance alone
  (`finquery.extract.layouts`).
- **The balance also decides the direction** where the layout cannot. Trade Republic's money-in
  and money-out columns are indistinguishable once the page is text, so an amount whose size
  matches the balance move and whose sign does not is corrected in code and counted, rather than
  taken from the model's guess.
- **A row that fails either guard is flagged, never dropped and never trusted.** A statement
  whose whole-statement sum does not close needs a decision even when no single row is flagged,
  because that is what a missing booking looks like. Flagged rows go to a review step before
  anything is written: on the Import page a table with accept, edit and drop per row; in a chat an
  `ask_user` card of kind `extraction_review` whose answers `finquery.answers` applies in code
  (ADR 0008), committing the accepted rows plus the verified ones through the same
  `ingest.commit.commit_rows` a CSV import uses.
- **The vision path gets the same guards where they can apply.** A rendered page or a photo has
  no source text, so the verbatim guard cannot run and the balances or the total are the only
  proof there is: a row from an image with neither is flagged as unverified. A receipt is checked
  by adding its line items up and holding them to the printed total, and a receipt with no total
  says so.
- **The verdict is one sentence, produced in code**, stored on the Import record
  (`Import.reconciliation`) and shown wherever the import is: the review card's note, the tool
  step in the transcript, the past imports list. The endpoint that commits a reviewed extraction
  recomputes it from the rows it was given, so the line is never a client's claim.

## Consequences

- A perfect extraction of the shipped 15 page statement imports 433 bookings with no questions
  asked; one misread amount or one missed booking turns the same import into a card with that row
  on it. Both are tested at the HTTP seam with a scripted extraction over the real fixture.
- An amount the model reformats (`-1150.00` for `-1.150,00`) is flagged even though its value is
  right. That is deliberate: the guard cannot tell a helpful rewrite from an invention, and the
  cost of the strict rule is one click on a card.
- A statement with no balances anywhere reconciles to `not_checkable`, which is a decision the
  user makes rather than a silent import.
- The guards are the reason the extraction sub-agent's output schema looks unusual (spans and a
  line number instead of a date and an integer). Any future reader of a document has to keep
  that shape to keep the guards.
