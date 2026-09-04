# FinQuery second review, demo instance at 127.0.0.1:8000 (OpenRouter)

Reviewed 2026-09-04 against `.scratch/finquery/spec.md`, the previous review
`.scratch/finquery/review-2026-09-04.md`, and tickets 08, 14, 15, 20, 21. Headed browser session
`review2`, viewports 1440x900 and 1024x768, both themes, screenshots in `/tmp/finquery-review2/`.
Zero browser console messages on every page for the whole session.

## Verdict

The three blockers of the last review are gone and gone properly: a Question card's answers are now
in the database within a second and a half of pressing Send (20 Needs review rows went to 0 before
the model had spoken, and the card printed its own "Applied:" line), markdown tables open at their
header with no scroll box, and a reload produces exactly the messages I wrote plus the ones the
assistant produced, with every "Thought for N seconds" label identical to the live one. Bulk
recategorization now goes through a real changeset card with a 24-row preview, Apply, Discard and
Undo; the chart thumbs are wired end to end into a pair-and-pick with records on the Feedback page;
the model chips no longer relabel on a switch; the context badge reads 16.5 percent instead of NaN;
money in prose is German in both languages; the tabs survive a profile round trip; and Settings has
grown a taxonomy editor with a preview dialog, a web-lookup switch and an outbound log that shows
one request carrying nothing but the token `karls`. What is left is a different and sharper problem
than last time, and it is concentrated in the query and chart sub-agents. Twice in one session the
query sub-agent wrote its own category classifier into the SQL (`CASE WHEN LOWER(description) LIKE
'%rewe%' THEN 'Groceries'`), so a chart titled "Ausgaben pro Kategorie" showed the model's guesses
next to an answer quoting the real categories, and the two disagreed by two orders of magnitude
(318,86 EUR against 29.472,00 EUR) in the same message. The same UNION of real and guessed
categories produced duplicate rows that crashed the stacked bar chart, and the sankey crashed too;
in both cases the assistant went on to describe the chart it had just failed to draw. Two of the
five chart shapes on the demo script are therefore broken on first attempt, and the one thing a
finance product cannot afford is a confident sentence about a picture that is not there. Fix the
sub-agent SQL, make a failed chart admit it, and this is a strong demo.

## Previous review: status of every finding

| Severity | Finding | Status | Evidence |
|---|---|---|---|
| blocker | Question card loops on `set_rule` and applies nothing | **fixed** | 3 answers, 20 Needs review to 0 within 1.5 s, "Applied: ... (7 bookings recategorized)" line on the card, model summary in 5.9 s. `59`, `60`, `61` |
| blocker | Markdown table opens scrolled past its header | **fixed** | 10-row table, `scrollTop 0`, `scrollHeight == clientHeight`, header and all rows visible at 1440 and after reload. `09`, `11` |
| blocker | Fake "Validation feedback" user bubbles after reload | **fixed** | After reload: 4 user bubbles for 4 messages, 0 occurrences of the string in the persisted transcript. `11` |
| major | `<turn\|>` leaks into answer text | **partially fixed** | Gone from answer text and from the persisted transcript; still leaks into live reasoning text (2 sightings). `10` |
| major | Bulk recategorize mutates immediately with no preview | **fixed** | "Recategorize all Netflix rows as Leisure." went to `propose_changeset`: card, 24-row preview with struck-through old values, Apply, Discard, Undo. `50`, `51` |
| major | Answer language sticks to the conversation | **partially fixed** | German, English, German in one conversation is now correct. But an English request after German turns still answers German, and a brand-new conversation answered an English question in German. `07`, `09`, `45` |
| major | Chart thumbs rendered but disabled and unnamed | **fixed** | Enabled, named, plus Regenerate, pair, Pick, "Pair collected" after reload, record on the Feedback page. `19`, `20`, `21`, `94` |
| major | Model chip relabels earlier turns on a model switch | **fixed** | 4 "Fast model" chips stayed Fast after switching the conversation to Quality; only the new turn is "Quality model". `23`, `26` |
| major | Context badge shows NaN | **fixed** | 16.5 / 17.8 / 20.1 / 30.5 percent, popover "5.8K / 33K, Fast slot, Memories in prompt 2". `08` |
| minor | en-US money in prose | **fixed** | 8.907,96 EUR, 27.600,00 EUR, 1.150,00 EUR, 4.401,88 EUR, in German and English answers. `04`, `06`, `07` |
| minor | Split editor error copy in two formats | **fixed** | One format: "Legs add up to -55,00 € · -6,80 € unaccounted for". `80` |
| minor | Import model mapping contradicts its own note | **not verified** | Needs a non-preset CSV dropped on the Import page; `agent-browser upload` is off limits in this harness. |
| minor | Reasoning panel uncapped while streaming | **fixed** | `max-h` class active mid-stream, `clientHeight` 168, scrolls internally, composer never pushed off. `24`, `25` |
| minor | Thinking durations degrade after reload | **fixed** | Identical label set before and after reload: 11, 11, 37, 37, 37, 23, 23, 6, 6. `11` |
| minor | Tabs dropped on a profile round trip | **fixed** | 5 tabs, same order, same selection, same URL after switching away and back. `56`, `62` |
| minor | Only `query` renders a collapsible tool step | **fixed** | `remember` ("Remembered for every chat"), `set_rule` ("Rule · LEA HOFFMANN is Dining"), `review_batch` ("Review queue · 3 merchants"), `import_file` (counters), `lookup_merchant` (token, searches, sources) all render. `36`, `45`, `52`, `58` |
| minor | Chart Y axis starts at 4400 € | **still present** | Monthly line chart 4.400 to 5.600 €, a 25 percent range reads as a cliff. `63`, `68` |
| minor | 1024 drops columns with no affordance | **fixed** | "Scroll for more columns" pill; the Past imports "When" column is intact. `93`, `97` |
| minor | Accessibility of filters, row selects, model listbox | **partially fixed** | Row selects are "Category of X" / "Account of X", the model listbox marks Fast `[selected]` matching the visual check, date inputs are styled and reachable. Still: 11 row checkboxes share "Select SHELL STATION 1204", 3 card fields share "or type an answer", the add dialog reads "Day Day / Month Month / Year Year". `22`, `58`, `75`, `90` |
| minor | Parenthesised plurals and two names for the model dialog | **partially fixed** | "Send 3 answers", "Send 1 answer", "7 bookings", heading "Choose a model" all correct. Still "3 merchant(s) I am not sure about." on the Question card. `22`, `58`, `59` |
| polish | Save split enabled with an invalid sum | **fixed** | Disabled while the legs do not sum, enabled the moment they do. `80`, `81` |
| polish | Green tick over "Imported 0 of 433 rows" | **partially verified** | The chat import path is neutral ("0 of 2 bookings ... 2 were already in this profile and were skipped"). The Import page banner needs an upload to re-check. `36` |
| polish | No delete or rollback on an import | **still present** | Past imports table has no row action. `97` |
| polish | Empty-state suggestions ignore whether there is data | **not verified** | Both profiles have data; I did not create an empty one. |
| polish | Unanswerable answer with no reason or alternative | **not verified** | Not re-asked this session. |
| polish | Settings is only the Models card | **fixed** | Categories editor with a preview-and-apply dialog, Models, Web lookup with the outbound log. Story 71's sanity check button is still missing and "resident" is still odd copy for a hosted provider. `37`, `38`, `47` |
| polish | Undo card still shows the change that no longer applies | **not verified** | No `apply_simple_edit` turn this session. |
| polish | Unstyled native date inputs in the filter bar | **fixed** | dd.mm.yyyy inputs styled like the selects beside them. `69`, `72` |
| polish | German month labels in an English UI | **still present** | Jan 25 ... Dez 25, and chart titles come back German for English questions. `63`, `64`, `66` |
| polish | Two reasoning panels per turn | **partially fixed** | The adjacent-panels case is fixed (the `remember` turn renders one panel, the tool step, one panel). Every turn with a tool still renders a panel before and after it. `52` |
| — | Zero console messages | **still true** | Chat, Transactions, Import, Memory, Feedback, Settings: no console output at all. |

## New findings

| Severity | Area | What happened | Expected | Screenshot |
|---|---|---|---|---|
| blocker | Query sub-agent / invariant | Asked for spending per category, the query sub-agent wrote a hand-rolled classifier into the SQL (`CASE WHEN LOWER(COALESCE(counterparty, description)) LIKE '%rewe%' THEN 'Groceries' ...`) and the chart came back titled "Gesamtausgaben pro Kategorie im Jahr 2025" with Housing at 29.472,00 EUR. The answer in the same turn quoted the real category query: total 318,86 EUR, largest Subscriptions 311,76 EUR. Two contradictory pictures in one message, and the invented labels are indistinguishable from the profile's own categories. | The SQL groups by the profile's `category`. A model-invented classification is either refused by the guard or labelled as a guess. One turn tells one story. | `26`, `27` |
| blocker | Charts | The stacked bar chart failed at runtime: "This chart could not be drawn: TypeError: A stack requires at most one value for each position and series; duplicate 2025-01 / Groceries". The sankey failed too: "This chart could not be drawn: Error: circular link". Both passed the sub-agent's self-check. Two of the five shapes on the demo script. | Story 49: the self-check and up to two repairs mean a broken chart never reaches the user. The check has to run against the real rows, not a stub. | `65`, `66` |
| blocker | Charts / answer | After each failed chart the assistant described it in full: "The stacked bar chart shows your monthly spending by category throughout 2025. It illustrates how different categories, such as Cash, Groceries, and Shopping, contributed ..." and "The Sankey diagram illustrates the money flow in 2025, showing a Total Income of 68.469,80 EUR and ...". | When the chart data part carries a render error, the assistant says the chart could not be drawn and offers the numbers instead. | `65`, `66` |
| major | Demo data | The profile the app opens on has 634 of 868 bookings in Needs review (841 of 866 at the start of the session). Every "per category" question therefore covers a few percent of the money, which is exactly what pushed the sub-agent into inventing categories. | The demo profile is fully categorized before Monday, or the answer says how much of the data it covers. | `26`, `99` |
| major | Language / memory | A brand-new conversation answered the English question "What is KARLS DANKT on my statement?" with "Das scheint Karls Erlebnis-Dorf zu sein, ein Freizeitpark." The Memory page shows why: distillation stored German facts from English turns ("Präsentiere Listen der Top 10 Händler als Markdown-Tabelle ...", "Alle Netflix-Buchungen sollen als Leisure kategorisiert werden.") and those are injected into every chat. | Distilled memories carry the language of the turn they came from, or are stored language-neutral. The answer follows the newest user message even in a fresh conversation. | `45`, `96` |
| major | Reasoning panel | The panel quotes the framework's retry plumbing verbatim and reasons about it: "The user's previous message 'Validation feedback: Please return text or call a tool. Fix the errors and try again.' is likely a system message ... This caused the 'Validation feedback' error." Seen on three turns. A raw `<turn\|>` marker sits in the same panel. | No framework message and no chat-template token reaches the transcript, reasoning included. The reasoning stream needs the same filter the text stream got. | `10`, `35` |
| major | Latency | The merchants turn took 101.1 s with the first answer token at 98.8 s: the model called `query` then `chart`, emitted no text, was retried by the framework, then answered. 287 KB of stream for two sentences. Every chart turn that forgets its text costs a full extra round. | A chart turn ends with text on the first pass, or the retry is cheap. Under 30 s for a chart turn. | `05`, `06` |
| major | Transactions / bulk | After a bulk recategorize to Transport, all three rows render the literal string "None" in the Subcategory cell instead of a dash. The same happens on a split parent. No such subcategory exists in the taxonomy (checked through the API). | An absent subcategory renders as the em dash used everywhere else. | `70`, `87`, `99` |
| major | Charts / preference | Regenerate needed three presses to produce a different chart: twice it answered "Same chart again" (about 45 s each). On a chart that failed to render it still offers "Both charts drew the rows of the same query. Pick the better one." with a Pick under an error message. | Regenerate retries until the definition differs, or says so once and offers to try again. A failed side is not offered as a choice. | `18`, `19`, `100` |
| minor | Charts | The doughnut of 2025 spending by category put 46.117,62 EUR of about 51.000 EUR into a single "Rest" slice, so the chart carries no information; the answer repeats "the largest portion is in Rest". | With one bucket over about half the total, say so or pick a different grouping. | `64` |
| minor | Web lookup | The cache hit produced no lookup step, no sources and no note: the answer just appears. There is no way to see in the transcript that nothing left the machine. | A cache hit renders the step with a "from the cache of this profile" note, which is the audit story the feature is for. | `48` |
| minor | Web lookup copy | The sources toggle reads "Used 1 sources". | "Used 1 source". | `45`, `46` |
| minor | Question card copy | The card note still reads "3 merchant(s) I am not sure about." Ticket 21 fixed this in `categorize/pipeline.py` but the `review_batch` card builds its own note. | Real plural, as on the same card's "7 bookings" and "Send 3 answers". | `58` |
| minor | Transactions copy | With one match the header reads "1 row match these filters". | "1 row matches these filters". | `74` |
| minor | Transactions copy | The delete dialog mixes number: heading "Delete this transaction?", cancel "Keep them", confirm "Delete 1". | One number throughout, driven by the selection count. | `88` |
| minor | Typed transaction | "I paid 12 EUR cash for lunch today" created the booking correctly (-12,00 €, Cash, source manual) but stored the literal string `"null"` as the counterparty. A transaction added by hand on the Transactions page stores a real null. | The extraction path writes null, not the string "null". | `33` |
| minor | Settings / taxonomy | Renaming a subcategory and clicking elsewhere silently discards the edit and restores the old name with no feedback; only Enter opens the preview dialog. Everywhere else in the app (inline table cells) clicking away is how you save. | Blur either saves, opens the preview, or says the edit was discarded. | `42`, `43` |
| minor | Transactions | The Enriched title column is not editable inline, while Date, Description, Amount, Category and Account all are. | Story 54: click a cell and edit it. Either make it editable or mark it derived. | `76` |
| minor | Accessibility | 11 row checkboxes all read "Select SHELL STATION 1204"; the three Question card free-text fields all read "or type an answer"; the add dialog's date parts read "Day Day", "Month Month", "Year Year". | Names that identify the row and the merchant, and no doubled words. | `58`, `75`, `90` |
| minor | Settings / outbound log | The log entry is timestamped "4 Sept 2026, 20:32" while every other date in the app is `04.09.2026`. | One date format. | `47` |
| minor | Memory | Contradictory rules pile up with no supersede: "Recategorize all Netflix transactions as Subscriptions." (18:36) sits next to "Alle Netflix-Buchungen sollen als Leisure kategorisiert werden." (20:34). One-off commands are stored as durable rules at all. | A new rule about the same merchant replaces the old one, and a command is not a durable fact. | `96` |
| minor | Charts | Chart titles and month labels come back German for English questions ("Ausgaben nach Kategorien im Jahr 2025", "Jan 25 ... Dez 25"). | Chart language follows the answer language. | `63`, `64`, `66` |
| minor | Import tool step | The step body shows raw markdown: "I imported \*\*0 of 2 bookings\*\* from `sparkasse-mini.csv`". | Rendered, like the rest of the transcript. | `36` |
| minor | Transactions | The header select-all checkbox draws a full check while `aria-checked` is `mixed`, so a partial selection looks like "everything is selected". | The indeterminate state draws a dash. | `83` |
| minor | Typed transaction card | The card stacks two confirmations: Confirm/Discard per row, then "Skip these" / "Send 1 answer" for the card, and it never names the account the booking will land in (it chose Cash). | One confirmation, and the target account on the preview. | `31`, `32` |
| polish | Transactions | A split parent shows no enriched title ("—") while its unsplit twin shows "ALDI". | The parent keeps its enrichment. | `70` |
| polish | Charts | The vertical bar chart of 10 categories printed 8 labels; two bars sit under blank space. | Rotate, wrap or thin the labels visibly. | `25` |
| polish | Charts | In a regenerated pair both frames extend the X axis to 40.000 € for a 27.600 € maximum, wasting a third of the plot. | Domain to the data. | `19` |
| polish | Transactions | The Account column truncates without an ellipsis at 1440 ("Sparkasse Girok"). | Ellipsis or a wider column. | `99` |
| polish | Import | Still no delete or rollback on a past import (carried from the last review); the chat-attached CSV now also appears in that list, which makes the missing action more visible. | An import can be reverted, or the copy says it cannot. | `97` |
| polish | Question card | The turn that applies the answers gets no follow-up suggestions, unlike every other turn. | Offer the obvious next step ("show me what changed"). | `61` |

## What worked well

- **The Question card is now the strongest moment in the product.** Three answers (two buttons, one
  free text "Leisure"), Send, and the rules were in the database in under 1.5 s, before the model
  spoke. The card then printed its own line, "Applied: Jonas Keller (via PayPal) -> Dining (7
  bookings recategorized), Max Schulz (via PayPal) -> Transfers > Friends and family (7 bookings
  recategorized), Anna Weber (via PayPal) -> Leisure (6 bookings recategorized)", and the model only
  summarized it, in 5.9 s. Needs review went 20 to 0.
- **The changeset card does exactly what story 58 asks.** "Netflix rows as Leisure", badge
  Recategorize, status "Waiting for you", "24 bookings move to Leisure.", a row-by-row table with
  `Subscriptions` struck through and `Leisure` beside it, Apply and Discard, then Applied with an
  Undo. Verified in the API.
- **Numbers still come from queries.** Every figure I checked matched a row I could expand: 8.907,96
  for groceries 2025, 27.600,00 and 4.800,00 for the top two merchants against 12 rows, 1.150,00 for
  the largest single booking, 5.521,60 July peak and 4.401,88 October low against 12 rows. SQL shown
  with line numbers, copy and download, `LIMIT` applied, the sub-agent's request quoted above it.
- **Stop and continue is flawless.** Stop kept the partial reasoning, the finished chart and a
  "Stopped" chip next to "Quality model"; "Mach weiter." resumed the same analysis with the same
  numbers in 22 s.
- **Memory across chats.** `remember` renders as its own step, a brand-new conversation answered
  from it in 5.6 s with "5 memories used", and the Memory page shows every fact with a Rule/Fact/
  Preference badge and honest provenance ("you asked for it" / "picked up in a chat").
- **Preference optimization is complete and honest.** Thumbs up stored a record with the prompt; a
  thumbs down offered "Compare a second answer", ran a second answer at temperature 1.2 side by
  side with a Pick under each, stored an `answer/pick` with both sides, and showed "Stored as a
  preference pair"; the chart pair stored a `chart/pick`; a reload showed "Pair collected"; the
  Feedback page read "2 records, 2 with both sides" and the Export served a valid two-line NDJSON
  attachment with `chosen` and `rejected`.
- **Web lookup does what ticket 14 promised.** One request left, carrying the token `karls` and the
  query "was ist karls", logged in Settings with a status; the answer carried "Leisure > Events ·
  90%", a summary and "Karls Tourismus - Wikipedia · de.wikipedia.org"; asking again added no log
  entry.
- **Composer attachments work end to end.** A CSV attached through the file input showed as a chip
  on the user bubble, ran `import_file` with a live counter panel (2 rows read, 0 imported, 2
  already there, 0 unreadable) and appeared in the Import page's Past imports list.
- **The taxonomy editor's preview dialog is the right shape**: "Rename Bakery to Bäckerei · This is
  what it does to the bookings you already have · Renames the subcategory ... · No existing booking
  is affected", Cancel and Apply.
- **The Transactions page holds up.** Filters narrow correctly (866 to 34 to 6 to 0) with a good
  empty state; inline edit saves on click-away and keeps umlauts; the split editor disables Save
  while the legs do not sum, shows "-6,80 € unaccounted for" and saves the moment they do; bulk
  recategorize and delete both work with honest dialogs; manual add is one small form with good
  copy ("For cash and anything else no statement knows about").
- **Zero console messages** across every page, including the chart iframes and the two that failed
  to render.

## Turn timings (OpenRouter, measured on the chat stream itself)

| Turn | Slot | Tools | First token | Complete |
|---|---|---|---|---|
| "Wie viel habe ich 2025 für Lebensmittel ausgegeben?" | Fast | 1 query | 2.2 s reasoning, 18.3 s text | 31.7 s |
| "Which merchants took the most money in 2025?" | Fast | query + chart, then a retry | 2.4 s reasoning, 98.8 s text | 101.1 s |
| "Und was war meine größte einzelne Ausgabe 2025?" | Fast | 1 query | 11.7 s reasoning, 44.4 s text | 56.2 s |
| Top 10 merchants as a markdown table | Fast | 1 query | 2.1 s reasoning, 10.8 s text | 21.9 s |
| Spending per category (Quality) | Quality | query + chart | 2.3 s reasoning, 29.5 s text | 32.2 s |
| Long explanation, stopped by me | Quality | query + chart | 1.8 s reasoning | stopped at 15.0 s |
| "Mach weiter." | Quality | none | 1.1 s reasoning, 14.2 s text | 22.0 s |
| Clicked follow-up | Quality | 1 query | 1.3 s reasoning, 7.3 s text | 10.9 s |
| "I paid 12 EUR cash for lunch today" | Quality | extract_transaction | 1.6 s reasoning | 12.9 s |
| Confirm the draft | Quality | add_transaction | 5.5 s text | 5.7 s |
| CSV attached in the composer | Quality | import_file | 6.7 s reasoning, 24.4 s text | 36.3 s |
| "What is KARLS DANKT on my statement?" (lookup) | Fast | lookup_merchant, 1 search | 0.8 s reasoning, 6.9 s text | 14.6 s |
| "Was ist KARLS DANKT?" (cache hit) | Fast | none | 1.5 s reasoning, 3.0 s text | 13.5 s |
| "Recategorize all Netflix rows as Leisure." | Fast | query + propose_changeset | 0.6 s reasoning, 5.7 s text | 11.7 s |
| `remember` the KARLS rule | Fast | remember | 1.6 s reasoning, 8.6 s text | 16.1 s |
| Same fact asked in a new conversation | Fast | none | 0.9 s reasoning, 2.1 s text | 5.6 s |
| "Ask me about the merchants that are still left." | Fast | review_batch + ask_user | 0.8 s reasoning | 16.3 s |
| Send 3 Question card answers | Fast | applied in code | 3.7 s text | 5.9 s (rules in the database inside 1.5 s) |
| Line chart | Fast | chart | 0.6 s reasoning, 10.9 s text | 12.4 s |
| Doughnut | Fast | chart | 0.7 s reasoning, 18.6 s text | 21.7 s |
| Stacked bars (failed to render) | Fast | chart | 0.6 s reasoning, 24.1 s text | 25.7 s |
| Sankey (failed to render) | Fast | chart | 0.8 s reasoning, 35.7 s text | 40.7 s |

Chart Regenerate is about 45 s per press and was needed three times before it produced a different
chart.

## Top five fixes before Monday

1. **Stop the query sub-agent inventing categories in SQL.** The `CASE WHEN description LIKE
   '%rewe%' THEN 'Groceries'` classifier is the single root cause of three findings: a chart whose
   labels are model guesses shown as the user's own categories, an answer contradicting its own
   chart by two orders of magnitude, and the duplicate `(month, category)` rows that crash the
   stacked bar chart. Constrain the generated SQL to group by the real `category` column and let a
   "Needs review" bucket be visible instead of guessed away.
2. **Make a chart that fails at runtime say so, and stop the assistant narrating it.** The render
   error already reaches the card. Feed it back to the turn so the answer reads "the chart could not
   be drawn, here are the numbers", and run the self-check against the real rows rather than a stub
   so duplicate keys and circular links are caught before the user sees them. Regenerate proved the
   shapes are drawable, so one automatic retry would have saved both charts.
3. **Categorize the demo profile.** 634 of 868 bookings are Needs review, which is what makes every
   category answer look absurd and what tempts the model into guessing. Run the categorizer over the
   profile, or demo on a freshly imported one.
4. **Give the reasoning stream the filter the text stream already has.** "Validation feedback:
   Please return text or call a tool" and `<turn|>` are both visible in expanded panels, and the
   retry behind them is also what turned a chart turn into 101 seconds. Filter the markers, and stop
   the empty-text-after-tool retry by making the chart tool's contract explicit.
5. **Make distilled memories carry the language of the turn.** German memories from English turns
   are injected into every later chat and are why a brand-new conversation answered an English
   question in German. One line in the distillation prompt fixes the last language complaint from
   both reviews.

Runners-up: render an absent subcategory as a dash instead of the string "None" (it appears the
instant you demo a bulk recategorize), and fix the three copy slips a German audience will notice,
"3 merchant(s)", "1 row match these filters" and "Used 1 sources".
