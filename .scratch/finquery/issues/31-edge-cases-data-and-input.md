# 31: Edge cases, data and input

**What to build:** Hunt for edge cases in everything that takes data or input, fix each at the root with a test, and polish the message the user sees when something is refused. Requested 2026-09-05 after the end-to-end run.

**Blocked by:** 30 (merged)

**Status:** done

Cases to cover at least (add what you find):
- CSV: empty file, header only, 10k rows, duplicate header names, semicolon and comma and tab, cp1252 and utf-8 with BOM, quoted fields with line breaks, thousands separators, plus and minus and parentheses for sign, separate debit and credit both filled, dates at year boundaries and two-digit years, zero amounts, very long descriptions, emoji and control characters, a description that looks like SQL or a prompt injection
- Chat input: empty message, whitespace only, 20k characters pasted, a message during a running turn (409 and what the UI shows), Stop pressed immediately after send, two tabs sending at once
- Attachments: over the size limit, unsupported type, a renamed file with the wrong extension, a corrupted PDF, a PDF with no text layer (scanned) forcing the vision path, an image that is not a receipt, a non-EUR receipt, a photo of several receipts
- Data operations: deleting a category in use (rows fall back to Needs review), merging a category into itself, splitting a split parent, splitting into one leg, undo twice, applying a stale changeset, applying a discarded one, deleting a profile with open conversations and tabs, deleting the last profile, deleting an import whose rows were split or recategorized
- Web lookup: a merchant that is a person's name (refused whole), a merchant with digits only, rate limit or network failure from the search backend (clean message, no crash, logged), the switch flipped off mid-loop
- Every refusal reaches the user as one plain sentence saying what to do; nothing surfaces as a raw exception, a 500 or an empty card

- [x] Each case above tried through the real product (browser or the HTTP seam) and recorded in a table with outcome before and after
- [x] Every defect fixed at the root with an HTTP-seam test; refusal copy polished; suite green; typecheck and build clean; zero console errors during the browser runs

## Comments

Done 2026-09-05. `uv run pytest` is 232 passed, 4 skipped (the four are environmental: the two
private Trade Republic fixtures, the private statement PDF and the opt-in local smoke suite).
`npx tsc --noEmit`, `npm run build` and `oxlint` are clean (34 warnings, the pre-existing set,
none in a touched file). Zero browser console messages and zero 4xx or 5xx responses that were
not a refusal being asserted. Screenshots: `/tmp/finquery-31/shots/`.

Fourteen defects, ten of them found by driving the case rather than by reading the code. Three
of the ten could lose or corrupt data without saying so, which is why the CSV reader is the
biggest change in the ticket.

### The table

Every row was tried through the real product: `B` for the browser, `H` for the HTTP seam. Where
both are marked the seam test is the one that pins it and the browser is where the copy was
read.

| Case | Where | Before | After |
| --- | --- | --- | --- |
| CSV, empty file | B, H | `{"detail":"leer.csv is empty."}` printed as JSON in the transcript | "leer.csv is empty, so there is nothing to read in it." |
| CSV, header only | B, H | "The file has a header but no data rows." | "The file has a header row but no bookings under it." |
| CSV, 10k rows | H | untried | 10.000 imported, the page answers, a second import is 10.000 candidates and no silent insert |
| CSV, duplicate header names | H | **the amount was read out of the second `Betrag` while the mapping named the first** | the first column, the one the card shows |
| CSV, semicolon / comma / tab | H | worked | unchanged, pinned |
| CSV, cp1252 and a UTF-8 BOM | H | worked | unchanged, pinned, with a preamble above the header |
| CSV, quoted field with a line break | H | stored with the newline in it | one line, the break becomes a space |
| CSV, thousands separators | H | worked | unchanged, pinned |
| CSV, plus and minus for the sign | H | worked | unchanged, pinned |
| CSV, parentheses for the sign | H | **`(4,90)` was read as money in** | money out |
| CSV, debit and credit both filled | H | refused as a conflict | still refused when both carry a figure |
| CSV, `0,00` in the unused money column | H | **every row of the file refused, nothing imported** | the zero is not a figure; the file imports |
| CSV, dates at a year boundary, two-digit years | H | worked | unchanged, pinned (99 to 1999, 00 to 2000) |
| CSV, zero amounts | H | worked | unchanged, pinned |
| CSV, very long descriptions | H | a 4.500 character line stored whole into a 500 character column | capped at the column, once, for every path that writes one |
| CSV, emoji and control characters | H | a bare BEL stored and printed | emoji kept, control characters gone |
| CSV, a description that reads as SQL | B, H | **the whole file refused, or the row silently dropped** | the row is one issue and one skipped row, and the count adds up |
| CSV, a description that reads as a prompt injection | H | stored as data | unchanged, pinned |
| Chat, empty message | B, H | a model call on nothing | 422, "Type a question about your transactions, or drop a file in to import it." |
| Chat, whitespace only | H | a model call on nothing | the same sentence |
| Chat, a request with no parts | H | the framework's "Processed history cannot be empty." in the stream | the same sentence |
| Chat, 20k characters pasted | H | worked | unchanged, pinned, and the title stays inside its column |
| Attachment over the size limit | B, H | "All files exceed the maximum size." | "A file has to be under 20 MB. Export a shorter date range from your bank and attach that." |
| Attachment of an unsupported type | B, H | "No files match the accepted types." | "FinQuery reads a CSV export, a statement PDF or a photo. That file is none of the three." |
| A file renamed to `.csv` | H | "This looks like a binary file, not a CSV export." | unchanged, pinned |
| A corrupted PDF | B, H | **"This file could not be opened as a PDF: No /Root object! - Is this really a PDF?"** | one sentence saying what to try; pypdf's words go to the log |
| A PDF with no text layer | H | untried | the page is rendered and looked at, the row is flagged `unverified` |
| An image that is not a receipt | B, H | "No total and no line item could be read from that photo." | the same, plus what to do instead |
| A non-EUR receipt | B, H | refused with a sentence (ticket 30) | unchanged, verified in the browser (PLN) |
| A photo of several receipts | H | flagged (ticket 30) | unchanged |
| Deleting a category in use | B, H | worked | unchanged, pinned: 139 bookings to Needs review, none deleted |
| Merging a category into itself | H | refused | unchanged, pinned |
| Renaming a category to its own name | H | **a card proposing a no-op** | refused with the reason |
| Splitting a split parent | B, H | the card said what it becomes, not what it replaces | "This booking is already split, so its 2 current legs are replaced." |
| Splitting into one leg | B, H | the changeset refused, **the split editor and the receipt path did not** | one rule in `replace_split_legs`, and Save is disabled with the reason |
| Undo twice | B, H | worked | unchanged, pinned, including that the rows do not move a second time |
| Applying a stale changeset | B, H | worked | unchanged, pinned |
| Applying a discarded one | H | worked | unchanged, pinned, all four states |
| Deleting a profile with open conversations and tabs | B | worked | unchanged, verified with eight open tabs |
| Deleting the last profile | H | 409 | unchanged, pinned |
| Deleting an import whose rows were split or recategorized | H | worked | unchanged, pinned, legs go with the parent |
| Web lookup of a person's name | B, H | refused, but the sentence was a lower-case fragment | a whole sentence, and the outbound log stays empty |
| Web lookup of a merchant with digits only | H | refused, same fragment | a whole sentence |
| Web lookup, the search backend refusing every time | H | **"The lookup spent its budget without reaching a conclusion."** | "No web search went through: the search backends are rate limiting us right now." |
| Web lookup, the switch flipped off mid-loop | H | **three more requests left the machine** | the loop stops where it sends, with a sentence |
| An unexpected exception inside a tool | H | **the turn died with the exception's text as a stream error** | one sentence in that tool's step, logged whole |

### The root causes

**The CSV reader had three ways to be wrong about data.** All three were invisible: none of them
raises, and each one produces a file that looks imported.

- A header that repeats a column name (`Betrag` twice, which a bank export does when it prints a
  figure in two currencies) was resolved by the preset to its *first* column and parsed from its
  *last*. `parse` builds its index with `setdefault` now, so both halves mean the same column.
- A row with more fields than the header, which is what an unquoted `;` inside a Verwendungszweck
  produces, was dropped in `sniff` before parsing ever saw it. The import then reported "4 of 4"
  over a file that had five bookings in it. It is kept, becomes an issue, and is counted into
  the record's skipped rows: `ragged.csv` now reads "3 of 4 bookings" with "1 unreadable".
- The header vote preferred the *widest* row when two widths were equally common, so a small file
  whose one data row carried a stray delimiter made that row the header and the whole file came
  back "header but no data rows". The earliest of the equally common widths wins now, and a
  one-column row (a preamble line) is not a candidate at all, which is what the old rule was
  really for.

Two more in the same file are wrong arithmetic rather than lost rows: `(4,90)` is accounting
notation for money out and was read as money in, and an export that writes `0,00` into the
money column it is not using had every row refused as "both are filled".

**`edits.clean_text` is the sixth**, and it is where the ticket's "very long descriptions, emoji
and control characters" all land. The column is 500 characters and SQLite does not enforce that,
so a 4.500 character line reached the table, the card and the prompt as it came. One function in
the module that already owns what a description has to look like, used by `clean_description`
and by the CSV reader, so a manual add, an inline edit, a changeset, a split leg and an imported
row all store the same shape.

**A tool that raised something nobody had written copy for ended the whole turn.** The web
client was the easy way to reach it (a search library raising a new exception type), and what
the browser got was a stream error carrying the exception's text and no step to show for the
work. `agent.guarded` wraps all twelve tools: it logs the exception whole and answers
`{tool_failed, error}`. `ModelRetry` still travels, and `Cancelled` is a `BaseException`, so
Stop cuts a tool short exactly as it did. `chat-view` judges that result in the same place a
stopped tool is judged, before any per-tool renderer reads a field it has not got.

**"Off" did not mean "off" once a lookup was running.** The switch is read per turn, so flipping
it off in Settings while a loop was in flight left three more requests to go out. The check is
in `OutboundJournal.before`, which is the loop's only route to the outside world and therefore
the only place where this can be made a property of the code rather than a promise.

**A refused request reached the transcript as its own response body.** `useChat` puts the body
of a non-2xx response into `error.message`, and every refusal this app writes is a FastAPI
`{"detail": ...}`, so the first thing the browser check showed was a JSON object in a red box.

### Refusal copy

Every refusal in this ticket's scope is one sentence that says what to do next. The three the
composer writes itself were the library's, written for many files at once ("All files exceed
the maximum size.") where the case is one file to swap, and they now match what the server
answers for the same three refusals. `extract/pdf.py` stops quoting pypdf ("No /Root object! -
Is this really a PDF?") and says what to try. The two the merchant scrubber writes were
fragments starting in lower case, which is fine embedded in a sentence and wrong on their own in
a step, which is where they are printed. `attachments.ACCEPTED` is deleted: nothing read it and
its docstring claimed to be the one place the accepted kinds are written, which the composer's
own list had not been true of for some time.

### Tests

`tests/test_edge_cases.py` is new: sixteen tests over the CSV door, the composer and the chat
endpoint. The awkward exports are committed under `fixtures/edge/` and written by
`fixtures/edge/generate.py`, because half of what makes them awkward is bytes a string literal
hides (a BOM, cp1252, a bare BEL, an unquoted delimiter inside a field); the ten thousand row
one is built inside its test. Six more in `test_changesets.py` (the four states of a card, a
taxonomy change that would do nothing, a split of a split, a one-leg split, an import deleted
after its rows were worked on), two in `test_web_lookup.py` (the switch mid-loop, a tool that
raises), two in `test_extraction.py` (the vision path, which had none, and a photo that is not
a receipt), and one changed in `test_transactions.py` (its single-leg refusal now proves the
sum guard with two legs, because one leg is refused earlier).

**The budget was re-measured, not assumed.** The two sentences about a `tool_failed` result cost
47 tokens: the system prompt is 3192 (was 3145) and the floor a compressed prompt cannot go
below is 4110 (was 4063). `BUDGET = 4800` stays where it is with about 17 percent of headroom,
and both numbers are in the comment in `tests/test_context.py`.

### Verified in the browser, port 8104, throwaway database, session `fq31`

The sample year imported and categorized by curl (433 rows, 384 by the dictionary, 24 by the
model, 25 Needs review), then every file dropped on the real composer through a synthetic change
event on the hidden input.

- **An empty CSV** (`01`, `19`), **a file over the size limit** (`02`), **an unsupported type**
  (`03`), each one sentence and no turn started.
- **A corrupted PDF** (`04`, `24`) as a tool step reading "Nothing was imported", with the
  sentence and no `/Root` anywhere on the page.
- **A CSV with only a header** (`05`), **a photo that is not a receipt** (`06`), **a receipt in
  PLN** (`07`, "This receipt is in PLN, not euros ... add the booking yourself with the amount
  your account was charged").
- **`ragged.csv`** (`08`): "I imported **3 of 4 bookings**", 4 rows read, 1 unreadable. Before
  the fix this file refused outright or reported 3 of 3.
- **The split editor** (`09` to `12`): one leg leaves Save disabled with "A split needs at least
  two legs." on it even when the leg adds up, two legs save, and the badge reads 2.
- **Deleting Groceries** (`13`, `14`): "139 bookings lose it and become Needs review", the fifty
  rows previewed, and after Apply the bookings are Needs review rather than gone.
- **A stale apply** (`15`): a Netflix row moved underneath the card by another door, then Apply
  reads "Those bookings changed after this preview was made, so it will not be applied."
- **Undo** (`16`): the card flips to Reverted, the sentence changes to "Undone. The bookings are
  back as they were." and the button is gone, so a second press is not offered at all.
- **A person's name in a web lookup** (`17`, `18`): "That booking names a person, and a person's
  name never leaves this machine, so nothing was looked up.", with `GET /api/outbound-log`
  empty.
- **Deleting a profile with eight open tabs** (`20` to `23`): the confirmation names what goes,
  the app falls back to the other profile, the tab bar is cleared and no tab is left pointing at
  something that is gone.
- Both themes at 1440x577; the light half is `18`, `19`, `20` to `24`.

### Left, seen in passing

- A re-import of ten thousand rows that are all duplicates takes 3,5 s, most of it one
  `SELECT count(*)` per candidate in `duplicates.next_ref`. It is correct and it is fast enough
  for a local app at this size; a counter carried through the commit is the upgrade path if a
  bigger file ever turns up.
- The ticket's "a message during a running turn (409)", "Stop pressed immediately after send"
  and "two tabs sending at once" are conversation flow and belong to ticket 32, which owns them.
  The 409 exists and carries a sentence; what the UI does with it is that ticket's call.
