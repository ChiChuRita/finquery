# FinQuery headful watch run, 2026-09-04

Demo instance http://127.0.0.1:8000 (never restarted). Session `watch`, headful Chrome for
Testing (visible window, no `--headless` flag on pid 7831; the daemon printed
"--headed ignored" only because it was already up from the `open` that started it headed).
Profile "Watch" created for the run. Screenshots in `/tmp/finquery-watch/`.

## Pass / fail

| # | Step | Result | Evidence | Screenshot |
|---|---|---|---|---|
| 1a | New profile "Watch" | pass | Profile switcher > New profile, `f501c8a0…` in `GET /api/profiles` | `01-profile-watch.png` |
| 1b | Import sparkasse-2025.csv by REST, Sparkasse preset | pass | `POST /api/imports` returned 433/433, preset `sparkasse`; Import page after reload lists 433 / 433 / 0 duplicates | `02-import-433.png` |
| 1c | Categorization | pass | 384 by dictionary, 24 by model, 25 Needs review, 4 merchants uncertain (identical to tickets 07/09/20) | `02-import-433.png` |
| 1d | Review conversation, answer one Question card | pass | Jonas Keller -> Dining, card printed "Applied: Jonas Keller (via PayPal) -> Dining (7 bookings recategorized). Left for later: …" ~4 s after Send, next card with the 3 remaining merchants right under it | `03`, `04`, `05` |
| 2a | Second import of the same file | pass | `imported_count 0`, `duplicate_count 433`; Past imports shows the Duplicates cell amber (`text-amber-600`) while undecided | `06-import-page-after-rest-dup.png` |
| 2b | Duplicate candidates list + "Remove all N exact duplicates" | pass (with a caveat, see F1) | Panel: "433 bookings may already be in this profile", "433 exact, 0 near", button "Remove all 433 exact duplicates"; one click set `duplicates_removed: 433` and cleared the panel | `08`, `09` |
| 2c | Shifted copy (5 dates +1 day) | pass | 428 exact + 5 near = 433 candidates, exactly the figures ticket 10 documents; each near row reads "Similar booking 1 day apart (01.01.2025)" | `11-shifted-near.png` |
| 2d | Decide two near matches individually | pass | Keep both on MITGLIEDSBEITRAG, Remove on MIETE WOHNUNG, "Apply 2 decisions" -> import record `imported_count 1, duplicates_kept 1, duplicates_removed 1`, list dropped to 428 exact + 3 near | `12`, `13` |
| 2e | Shortcut leaves near matches alone | pass | "Remove all 428 exact duplicates" left "0 exact, 3 near" still asked about | `14-only-near-left.png` |
| 2f | Transactions count | pass | 434 rows in the profile (433 imported + 1 kept near match), API total 434 | `15-transactions-count.png` |
| 3a | "How much did I spend on groceries in May 2025?" | pass | "In May 2025, you spent 440,72 EUR on groceries.", query step `category = 'Groceries'`, context badge 7.9 percent (no NaN) | `16`, `18` |
| 3b | "Und im Vergleich zum April?" | pass | "Im Vergleich zum April (252,70 EUR) haben Sie im Mai 440,72 EUR für Lebensmittel ausgegeben." German money format, German answer to the German turn | `17-query-expanded.png` |
| 3c | Expand the Query step | pass, with finding F2 | SQL, request line and the 2 result rows all shown; the SQL contains a hand-rolled classifier (`OR LOWER(...) LIKE '%rewe%' … '%dm drogerie%'`) next to `category = 'Groceries'` | `17-query-expanded.png` |
| 3d | "recategorize all Netflix rows to Subscriptions" | pass (changeset card, not `set_rule`) | Card "Netflix zu Abonnements verschieben", kind Recategorize, "Waiting for you", 12-row preview, Apply/Discard; after Apply the status reads "Applied" with Undo | `19`, `20` |
| 3e | Doughnut per category | pass on the second attempt, finding F3 | First chart card came back as an ERROR card, second rendered a 6-slice doughnut with an answer quoting 14.736,00 EUR and 4.474,95 EUR | `21-doughnut.png` |
| 3f | Stacked bars by month and category | pass | 120 rows, 12 months x 10 categories drawn, no runtime error (the review's "duplicate 2025-01 / Groceries" crash did not reproduce); SQL groups by the real `category` | `22-stacked-bar-reasoning-leak.png` |
| 4a | Stop mid-generation, then continue | pass | "Stopped" chip on the interrupted turn, "Mach bitte weiter." resumed and produced the full table plus the three largest items | `25`, `26` |
| 4b | Switch to Quality for one turn, then back | pass | Only the new turn is chipped "Quality model"; the 7 earlier ones stayed "Fast model"; composer back to Fast afterwards | `27`, `28`, `29` |
| 4c | Thumbs up an answer | pass | `aria-pressed="true"` on the last answer's thumb, record on /feedback as "quality slot · Useful" | `30`, `33` |
| 4d | Regenerate a chart | pass | One press produced the pair ("The first chart" / "Drawn again", "Both charts drew the rows of the same query. Pick the better one."), Pick this one -> "Picked" and "Stored as a preference pair" | `31`, `32` |
| 4e | /feedback | pass | "2 records, 1 with both sides", chart pair "chosen and rejected", Export JSONL present | `33-feedback.png` |
| 5 | Web lookup on, "what is Karls dankt", sources, outbound log, off | pass | Lookup step "karls · 1 search · Leisure > Events · 90%", 2 sources (Wikipedia, karls-shop.de), outbound log "1 request · karls was ist Unternehmen · merchant token karls · ok", switch back to off | `35`, `36`, `37`, `38` |
| 6 | Console | pass | 0 console messages for the whole session (`agent-browser console --json` at the end) | — |

## What failed or looked wrong

- **F1 (major, new): the Import page cannot resume a pending duplicate decision.** The
  candidates panel lives in page state only. An import committed anywhere else (REST, chat,
  or the same page before a reload) shows 433 undecided duplicates in the amber column of
  Past imports and there is no way to decide them from that page: reloading /import gives the
  table and nothing else. On stage this is one accidental refresh away. `06`.
- **F2 (blocker, unchanged from the second review): the query sub-agent still writes its own
  merchant classifier into the SQL.** The April/May comparison ran
  `category = 'Groceries' OR LOWER(COALESCE(counterparty, description)) LIKE '%rewe%' … '%aldi%'
  … '%dm drogerie%'`. It happened to return the same totals as the clean query here (April
  252,70 both ways, checked against the database), so no wrong number reached the screen this
  time, but the leak the review flagged is present and `'%dm drogerie%'` is a category the
  profile calls Groceries only by luck. `17`.
- **F3 (major): a failed chart shows the sub-agent's raw scratch notes.** The first doughnut
  attempt rendered an ERROR card reading "The query was refused 2 times, last reason: SQLite
  cannot parse this: Failed to parse any statement following CTE. Line 1, Col: 318. ,
  top_categories AS (… LIMIT 1) -- This is wrong, I want top spenders … -- Let's try aga".
  Internal SQL comments and a truncated sentence in front of the user. The turn recovered on
  the retry, so both cards sit in the transcript, the broken one first. `21`.
- **F4 (major, unchanged): the reasoning panel quotes pydantic AI's retry prompt.** The stacked
  bar turn rendered a full paragraph of "the user provided 'Validation feedback: Please return
  text or call a tool' … in these simulated environments …", quoted the system prompt's chart
  rules verbatim, and the panel is not height capped once streaming ends (one 440 px paragraph,
  taller than the viewport). Visible on screen, not just in the DOM. `23`.
- **F5 (major, unchanged): "None" in the Subcategory cell.** After the Netflix changeset was
  applied, all 12 rows render the literal string "None" where every other empty cell uses a
  dash. `39`.
- **F6 (minor, unchanged): the answer language follows the conversation, not an English
  command.** "recategorize all Netflix rows to Subscriptions" got a German changeset title
  ("Netflix zu Abonnements verschieben") and a German answer. The fresh English conversation
  ("what is Karls dankt") answered in English, so the review's worse case is fixed. `19`, `20`,
  `36`.
- **F7 (minor): the import banner goes stale after duplicate decisions.** After keeping one
  near match the banner still read "No new rows for Sparkasse Girokonto / 433 rows look like
  bookings you already have, so nothing was added for them until you decide below", while the
  import record already said `imported_count 1`. `13`.
- **F8 (nit): mixed date formats.** The outbound log stamps "4 Sept 2026, 21:46" while the
  Import table and the transaction rows use "04.09.2026". `37`.
- **F9 (nit, unchanged): two reasoning panels per turn** on every turn with a tool call
  ("Thought for 14 seconds" before and after). `25`.

## Notes on the run itself

- `agent-browser upload` was not used. The Import page commits were driven by an `eval` that
  builds a `File` from the fixture bytes and dispatches a synthetic `change` on the file input,
  which is the ticket 10 harness trick.
- One reload of /import landed with the profile reset to **Default** and the shifted CSV was
  committed there before I noticed. Cleaned up through the API: all 431 candidates decided as
  Remove and the 2 rows that had been inserted deleted (`bulk-delete`, `deleted: 2`), so the
  Default profile's data is back to what it was. What cannot be undone is the **`sparkasse-2025-shifted.csv`
  row in Default's Past imports table** (0 rows added, 431 duplicates, all decided): there is
  no delete or rollback for an import, which is the review's own open polish item.
- Left behind in the **Watch** scratch profile on purpose: the second REST import
  (`81fd3d5f…`) still has 433 undecided candidates, which is the F1 evidence.
