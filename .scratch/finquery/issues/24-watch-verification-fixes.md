# 24: Import page becomes an overview, plus verification fixes

**What to build:** The headful verification of 2026-09-04 (../verification-2026-09-04-watch.md) passed every step but found four things ticket 22 does not cover.

**Blocked by:** 10 (merged)

**Status:** done

- [x] The Import page is an overview only: no drop zone, file input, mapping preview, review table or duplicate decisions on the page. Per past import it shows file, kind, account, when, rows read, imported, duplicates found and undecided, reconciliation, needs review, and a Delete action. Undecided candidates or pending review get a "Continue in chat" link to the conversation the import came from, or a review conversation created through the existing endpoint. Empty state and sidebar copy say to drop a statement into the chat (user decision 2026-09-05, see spec Amendments)
- [x] Reloading /import (or any page) never resets the active profile: the active profile is read from storage before the first query runs, and a missing or deleted profile falls back to the first one explicitly
- [x] A failed chart card never shows the sub-agent's scratch notes or raw code comments: the card shows the error and a one-line note; the code and notes stay behind the details toggle
- [x] A past import can be deleted with its transactions (confirmation dialog, cascades to its bookings, candidates and decisions), since there is no other way to undo an import into the wrong profile
- [x] Tests at the HTTP seam for the delete and for pending candidates listing; typecheck and build clean; browser verification of the four items

## Comments

Scope changed mid-ticket (2026-09-05, spec Amendments): the Import page is an overview and every
import happens in the chat. What was already built for the old scope and is now gone: resuming
duplicate decisions on the page and the page's import banner. What survived from it: the delete
endpoint with its tests, the profile fix, the chart card fix.

Done 2026-09-05. 133 passed and 3 skipped (4 new tests in `tests/test_duplicates.py`).

**The page.** `components/import-page.tsx` is a header and `components/imports-list.tsx`, which
is a card per import: file name, kind, preset, account, when, then rows read, imported,
duplicates (with `N undecided` in amber, or `kept, removed` once decided) and needs review, plus
the reconciliation sentence when the record has one. A card list rather than a table: ten columns
do not fit 1024 wide and the reconciliation verdict is a sentence, not a cell.
`duplicate-candidates.tsx` and `mapping-editor.tsx` are deleted, and with them `previewImport`,
`commitImport`, `categorizeImport`, `decideDuplicates` and the duplicates query in `lib/api.ts`.
The REST endpoints behind them stay: `tests/` and `scripts/measure_categorization.py` drive them,
and they are the same pipeline the chat tool uses, one HTTP door further out.

**Continue in chat.** `GET /api/imports` gained two fields: `needs_review` (bookings of that
import with no category) and `conversation_id`, which is the conversation the file was dropped
into, read through the attachment that carries the import id. With one, the link opens that
conversation; without one (an import committed over REST) it calls
`POST /api/imports/{id}/review-conversation`, which now seeds the **duplicate** card when the
import has pending candidates and the categorization card otherwise. Without that branch the
endpoint answered 409 for exactly the case the watch run found (F1: 433 undecided candidates, no
conversation), so an old import would have been stranded. Both cards resume through the same
`ask_user` deferred path and the same appliers; no model call is made for the duplicate branch.

**Delete.** `DELETE /api/imports/{id}?profile_id=...` answers `{transactions, candidates}` and
takes the record, its bookings (split children follow their parent through the foreign key) and
its candidates with the decisions on them. `Transaction.import_id` is `ON DELETE SET NULL`, so
deleting the record alone would leave bookings nobody can account for. A booking a Keep both
inserted belongs to the import and goes with it; the booking it matched came in earlier and
stays. Ownership is `_import_or_404`, so another profile's import is a 404 and nothing is
touched.

**The profile.** `WorkspaceProvider` already read storage in the state initializer; what was
missing is that the fallback was implicit. It now writes the resolved profile back, so a storage
that is empty (a first visit, or the other of `127.0.0.1` and `localhost`, which have separate
storage and is the likeliest reading of the watch run's one reset) resolves once and sticks.

**The failed chart card.** `failureLine` in `chart-tool.tsx` cuts the reason where quoted code
starts (a newline, `--`, `/*`, a fence, `WITH`, `SELECT`, `AS (`), ends it on the last finished
sentence and caps it at 160 characters. The whole reason, comments and all, is a new "Why it
failed" section under the details toggle, next to the plan and the SQL. Nothing on the server
changed: the reason is still the query runner's own sentence, so ticket 22's query work is
untouched.

Verified headful on port 8089 against a throwaway database, session `fq24`, the fixture imported
twice by curl into a second profile: the overview lists three imports with the undecided one
amber; a reload keeps the second profile (and a storage pointing at a deleted profile falls back
to the first and is written back); "Continue in chat" on the REST import opens a seeded
conversation whose card is "All 431 exact duplicates", answering it says "Applied: removed 431
duplicates" and the overview counts follow; deleting the 433 row import through the confirmation
takes the Transactions page from 434 rows to 1. A forced chart failure (the runner replaced with
one canned reason carrying the sub-agent's `-- This is wrong, I want top spenders` comment)
renders as one clean line ending at "Line 1, Col: 318." with the raw text under Details. 0 console
messages. Screenshots: /tmp/finquery-24/01 to 18.

Two things seen on the way that belong to other tickets: a tool that narrates nothing makes the
stream send a `reasoning-end` for a narration part that was never started (the browser shows
"Received reasoning-end for missing reasoning part"), which the real `run_chart` only hits when it
fails before its first narration (an empty profile, an unavailable provider); and one answer
rendered with a literal `thought ` in front of it.
