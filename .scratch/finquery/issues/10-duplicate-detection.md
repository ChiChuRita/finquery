# 10: Duplicate detection

**What to build:** When an import would insert a transaction that matches an existing one exactly (same account, date, amount and normalized description) or nearly (same amount within two days and a similar description), nothing is inserted silently. The import result lists every candidate and the assistant asks about each in the chat with Keep both or Remove. The import summary shows how many were kept and removed.

**Blocked by:** 08 Import through chat attachments and text

**Status:** done

- [x] Fingerprint and near-match detection at commit time for every ingestion path
- [x] Candidates held aside, asked one card at a time through `ask_user`, applied per answer
- [x] Import record stores duplicate decisions
- [x] HTTP-seam tests: re-importing the same CSV asks about every row, a near match by date shift is detected, Keep both inserts
- [x] Browser verification of a double import

## Comments

Real data (2026-09-04): the user added their own Trade Republic export under `fixtures/private/` (gitignored, never shipped, never sent to OpenRouter): the full CSV export (1520 rows, 2024-06 to 2026-09, header `datetime,date,account_type,category,type,...,amount,...,description,counterparty_name,counterparty_iban,payment_reference,mcc_code`) and the 102-page German statement PDF. Both are sliced into shorter frames in `fixtures/private/frames/`: one CSV per quarter, two overlapping CSVs (2025-01 to 04 and 2025-03 to 06) for duplicate testing, and seven PDF frames of a few months each, every PDF frame starting with the account overview page. The Trade Republic CSV preset and the Trade Republic PDF layout must be developed against these files, only on the local provider or with the scripted model. The synthetic dataset stays the shipped fixture.

Done 2026-09-04. 8 new tests (`tests/test_duplicates.py`), 131 passed and 1 skipped in total
(2 skipped without `fixtures/private/`). Screenshots: /tmp/finquery-10/.

**The seam is `commit_rows`.** `src/finquery/ingest/duplicates.py` is the whole feature:
`Matcher` loads one account's bookings once and says whether an incoming row matches one
exactly (account, date, amount, normalized description) or nearly (same amount, at most two
days apart, a similar description by containment or a difflib ratio of 0.72), `hold` writes a
`duplicate_candidate` row instead of a transaction, and `apply_decisions` inserts what the user
kept (then categorizes exactly those rows) and marks what they removed. Every existing booking
is matched at most once, so two coffees of the same amount in the same week still both land.
Every ingestion path is covered because they all go through `commit_rows` (Import page,
`import_file`, and ticket 11's extraction when it calls it); typed transactions go through
`add_draft`, which does the same check for its one row and answers with a card of its own.

- **The silent skip is gone.** `commit_rows` used to count a repeated fingerprint and drop it.
  `duplicate_count` now means candidates held aside, and `duplicates_kept` and
  `duplicates_removed` (two new columns, in `NEW_COLUMNS`) are what was decided.
  `import_summary` says both: "Of 433 bookings that looked like duplicates, 2 were kept and 431
  removed." Undecided ones say so instead.
- **Import page:** `GET /api/imports/{id}/duplicates` (counts plus 25 pending candidates) and
  `POST` the same path (`decisions: [{ref, decision}]`, `remove_all_exact`). The page shows
  `components/duplicate-candidates.tsx` after a commit, holds the review conversation back
  until nothing is pending, and the Past imports table turns its Duplicates column amber while
  a decision is missing.
- **Chat:** the new `ApplyKind` is `duplicate_decision` with an applier in `APPLIERS`.
  `import_file` returns `duplicate_card` (and no merchant `questions`, so the transcript never
  shows two cards at once), `review_duplicates` returns the next batch, and the prompt has one
  block: show the card, say the `applied` line back, call `review_duplicates` until `pending`
  is 0, then `review_batch`.
- **`APPLIERS` entries are async now** and take an `ApplyContext` (session, profile, rows,
  answers, `resolve_model`, `model_settings`), because keeping a candidate inserts a booking
  and a booking is categorized. `resolve_answers` is awaited in `api/chat.py`. The
  categorization applier is unchanged behind a two-line wrapper.
- **The shortcut is a row, not a button.** 433 identical rows must not be 87 cards. The card
  carries one row `all-exact` labelled "All 433 exact duplicates" with `bookings: 433` and a
  single Remove button, and the near matches under it are asked about one by one. It started
  as a question-level option and had to move: the fast model copies a card's title, rows and
  apply hint faithfully and drops `note` and `options`. Only Remove is offered for the group;
  keeping is a per-row answer.
- **Two tolerances the browser run forced, both pinned by a test.** The fast model handed the
  card back nested under its own `card` key, twice, with every scalar stringified
  (`"amount_cents": "null"`): `ask_user.unwrap_card` and a `mode="before"` validator read that
  as the card it meant, on the server, and `question-card.tsx` does the same before it renders.
  Without them the card renders empty and, worse, fails validation, so the answers apply
  nothing. `formatDate` also stopped throwing on an unparseable string: one `"null"` date took
  the whole chat page down to the error boundary.
- The Import page's shortcut is scoped to that import; the card's group row is scoped to the
  profile, which is what its own counts say (`review` counts the profile, like `review_batch`).
- **`review_duplicates` is read-only**, so it is not in `preferences.MUTATING_TOOLS` or
  `WRITING_PARTS`; the `ask_user` call it leads to is already in both.
- **The test context budget went from 3400 to 3600 tokens.** Measured: the system prompt is
  2291 tokens with this ticket's block on it and the floor a compressed prompt cannot go below
  is 3199, so 3400 left 6 percent and 3600 leaves 11.
- Requests per turn: a chat import with duplicates costs the chat model twice and the fast slot
  once for the categorizer (the merchant questions are not asked yet, which saves a call);
  answering a card costs one chat request plus one categorizer call when something was kept.

Verified on OpenRouter on port 8085 with a throwaway database. The synthetic CSV imported on the
Import page (433 rows), then imported again: 0 rows added, 433 candidates listed 25 at a time
with "Remove all 433 exact duplicates", and one click removed them all with the table still at
433. A copy with five dates moved by one day gave 428 exact and 5 near candidates; two near ones
were kept and one removed row by row (the kept bookings are in the table, categorized, next to
their twins), and the shortcut then took the exact ones and left the two remaining near matches
still asked about. In the chat, the same file dropped on the composer imported 0 of 433 and
asked with the duplicate card: a first card of five rows (kept 1, removed 2, the `applied` line
in the transcript before the model spoke), then "Remove all 430" on the group row, then a mixed
card (group row, one Keep both, one typed "remove" in the free text field) which came back
"Applied: kept 1 booking and removed 432 duplicates. 2 candidates still waiting." No console
errors after the fixes. Screenshots: /tmp/finquery-10/01 to 13.

Harness notes: `agent-browser eval` was unavailable in this session, so the file drop was done
with `wait --fn`, which runs the same JavaScript (fetch the fixture from `frontend/dist`, build
a `File`, dispatch a synthetic `change` on the input). Clicks below the fold still do nothing
silently: `scrollintoview` first, then click, and re-snapshot before every ref because they
shift after each render.

For ticket 11: extracted rows reach the same duplicate path by calling
`ingest.commit.commit_rows` with the parsed rows (nothing else needed, the candidates and the
card follow), or, for a single bill photo booking, `duplicates.Matcher(...).take(...)` plus
`duplicates.hold(..., source="manual", draft_id=...)` and `duplicates.one_card(...)`, which is
what `ingest/typed.py::add_draft` does.
