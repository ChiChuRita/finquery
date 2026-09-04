# 09: Changesets and edits in chat

**What to build:** A user asks the assistant to split, recategorize, edit or delete transactions. For anything touching more than one row, or anything not literally requested, the assistant proposes a changeset: a card in the chat lists the exact affected rows with Apply and Discard. Applying is deterministic code. A single obvious edit the user literally asked for ("set this one to Dining") applies immediately with an Undo. Taxonomy changes (add, rename, merge, delete categories and subcategories) work both through the assistant as changesets and in a Settings taxonomy editor.

**Blocked by:** 04 Transactions page, 05 Query sub-agent and the numbers invariant

**Status:** done

- [x] Changeset entity with kinds recategorize, split, edit, delete, taxonomy; preview computed at proposal time; superseded when a newer one arrives or the data changes underneath
- [x] `propose_changeset` tool and the Changeset card with Apply and Discard calling REST endpoints; applied changesets show as applied in the transcript
- [x] `apply_simple_edit` tool for single-row literal requests with an Undo button that reverts
- [x] Split via chat creates children summing to the parent
- [x] Settings taxonomy editor with add, rename, merge, delete and the effect on existing rows previewed
- [x] HTTP-seam tests: proposal preview matches applied result, discard leaves data untouched, stale changeset refuses to apply, undo reverts a simple edit
- [x] Browser verification of a split, a bulk recategorize, an undo and a taxonomy merge

## Comments

Done 2026-09-04. Structure for the next tickets:

- `src/finquery/edits.py` is new and is where the rules about what may be written now live:
  `TransactionEditError`, `resolve_taxonomy`, `resolve_account`, `resolve_names` (a category and
  subcategory by name, refusing with the list of names the profile has), `clean_description`,
  `find_transaction` (the ownership check: a row of another profile is simply not found),
  `listing_conditions` (the filter the transactions page and a changeset selection share) and
  `replace_split_legs`. `api/transactions.py` lost its private copies of all of these and now
  imports them, so the page and a changeset cannot disagree about what is legal. `app.py`
  imports `TransactionEditError` from `finquery.edits`.
- `src/finquery/changesets.py` is the engine. `propose(session, profile_id, intent,
  conversation_id=)` resolves the intent into a payload of ids, computes the preview, hashes the
  affected rows and stores all three; `apply`, `discard`, `undo` and `refresh` are the rest.
  Nothing in it calls a model. Three invariants:
  - The payload freezes `transaction_ids`, so applying touches exactly the rows the preview
    listed.
  - `row_version` is a sha256 over the union of the frozen ids and whatever the selection
    resolves to *today*, each with its state (date, amount, description, category, subcategory,
    account, parent) or `missing`, plus the parent's legs for a split and the taxonomy rows'
    names. So an edited row, a deleted row, a row that left the filter and a row that newly
    matches it all move the hash. A mismatch is `ChangesetStale` (409) and the changeset turns
    `stale` rather than applying to a state nobody saw.
  - `_supersede` retires any `proposed` changeset of the profile whose ids intersect the new
    one's, so two cards can never both apply to the same rows.
- `db.Changeset`: profile_id, conversation_id (`SET NULL`; null for the Settings editor),
  kind, title, status, payload_json, preview_json, row_version, undo_json, created_at,
  applied_at. `applied_at` stays set after an undo, which is what tells an undone edit
  (`discarded` with an applied time) from a discarded proposal. `db.split_sum_error` is the one
  wording for a broken split, used by the ADR 0005 flush guard and by a split proposal.
- `api/changesets.py`: `POST /api/changesets` (propose, 201, body `{profile_id,
  conversation_id?, intent}`), `GET /api/changesets/{id}?profile_id=` (what the card reads after
  a reload; it turns a proposal whose rows moved `stale` on the way out),
  `POST /api/changesets/{id}/apply`, `/discard`, `/undo` (body `{profile_id}`). A changeset of
  another profile is a 404 on every one of them. Refusals are 400 (`ChangesetError`,
  `TransactionEditError`, `SplitSumError`), a stale apply is 409 (`ChangesetStale`), all mapped
  once in the app factory.
- Tool contracts on the chat agent:
  - `propose_changeset(intent: ChangesetIntent) -> Changeset`. `ChangesetIntent` is one flat
    model (pydantic AI flattens a single model argument): `kind`, `title`, `transaction_ids` or
    `where` (a `Selection`: q, date_from, date_to, category, account, needs_review), `category`
    and `subcategory` by name, `description`/`amount_cents`/`booked_on` for an edit, `legs`
    (`SplitLeg`: description, amount_cents, category, subcategory) for a split, and `taxonomy`
    (`TaxonomyChange`: operation add/rename/merge/delete, category, subcategory, new_name,
    into). Every refusal becomes a `ModelRetry` with the readable sentence, and the tool has
    `retries=2`, so the model corrects itself instead of the turn dying.
  - `apply_simple_edit(transaction_id, title, category=, subcategory=, description=,
    amount_cents=, booked_on=) -> Changeset & {undo_token}`. It proposes and applies in one
    session; the `undo_token` is the changeset id the Undo button posts to.
  - Both return the same shape as `GET /api/changesets/{id}`: `id, kind, title, status,
    summary, note, total, fields, rows[{id, before, after}], undoable, created_at, applied_at`.
    Preview values are display strings, so the card never recomputes a number, and `after` is
    null for a row that goes away (deleted, or the booking a split replaces).
- The system prompt gained a "Changing the data" block: query for the rows and their `id`
  first, `apply_simple_edit` only for one row and a change the user spelled out,
  `propose_changeset` for everything else (and never claim it happened), legs must sum, and
  taxonomy changes go through `propose_changeset`. `data_brief` now lists the subcategories too,
  because a changeset names them and an invented name is refused.
- Frontend: `components/changeset-card.tsx` renders `tool-propose_changeset` and
  `tool-apply_simple_edit` as a card (title, kind badge, status badge, the summary, the note,
  the before/after table, then Apply and Discard or Undo). It reads
  `changesetQuery(profileId, id)` from the server, so the status is right after a reload and
  after another card superseded it; applying invalidates the transactions and categories
  queries. `ChangesetEffect` is exported and reused by `components/taxonomy-card.tsx`, the
  Settings editor: add, rename (click the name), merge (a submenu of the other categories or
  sibling subcategories) and delete, each proposing the same changeset the assistant would and
  showing its effect in a dialog before Apply. Cancel discards the proposal.
- Decisions worth knowing:
  - A proposal that resolves to no row is refused, not stored. Seen in verification: the model's
    first delete attempt matched nothing, and without this it left a dead card behind.
  - `recategorize` and `edit` store the before state, so an applied one of those kinds also
    offers Undo, not only `apply_simple_edit`. `split`, `delete` and `taxonomy` do not, and the
    delete card says so. The upgrade path (recreating deleted rows) is noted in `UNDOABLE`.
  - A merge maps a row's subcategory by name into the target category and drops it otherwise,
    which the preview note states and a test pins.
  - `GET /api/changesets/{id}` has a side effect (marking a proposal stale). That is deliberate:
    the card must be honest about what Apply would do before it is pressed.
- Tests: 68 pass, 2 skipped (`tests/test_changesets.py` adds 13), all at the HTTP seam. Request
  counts per turn are unchanged: the chat model plus the follow-up and distillation steps on
  fast; no changeset path calls a model, so `scripts.resolved == ["fast", "fast", "fast"]` for a
  proposal turn.
- Verified on OpenRouter on port 8090 with the synthetic Sparkasse CSV imported through the
  preset (433 rows), on both slots. Screenshots: /tmp/finquery-09/.
  - Fast: split the 5 January Edeka booking (-52.30) into -45.00 Groceries and -7.30
    Shopping/Home. Query step, then the card, Apply, and the Transactions page shows the split
    badge with both legs adding up to -52.30.
  - Quality: all 12 Netflix bookings to Subscriptions, previewed as `Needs review ->
    Subscriptions` per row, applied; then the most recent Vapiano booking to Dining/Restaurant
    through `apply_simple_edit`, applied at once, Undo put it back to Needs review and the card
    reads Reverted after a reload.
  - Quality: a delete of the 20 ATM withdrawals, discarded; 434 rows still there.
  - Settings: Subscriptions merged into Leisure with the 12 rows shown moving before confirming;
    Subscriptions is gone and the rows are Leisure. A rename of Groceries showed its one
    affected row and Cancel left the name alone.
  - Stale: a proposed split, then the booking's amount changed underneath, then Apply. 409 with
    the reason, the card flips to Out of date, and it still says so after a reload.
  - A split asked for as 10 + 5 euros of a 41.90 booking: the quality model queried, saw the
    mismatch and asked the user instead of proposing it. The refusal path itself
    (`split_sum_error` back to the model) is covered by the HTTP test.
- Known issue, pre-existing: a turn with tool steps shows several "Thought for 1 second" panels
  because `foldReasoning` only folds adjacent reasoning parts. Same as after ticket 05.

For ticket 11 (a bill photo proposes a split changeset): build a `ChangesetIntent(kind="split",
transaction_ids=[matched_id], legs=[SplitLeg(...)])` and call
`finquery.changesets.propose(session, profile_id, intent, conversation_id=...)`. The legs must
sum to the matched booking in cents with the booking's sign, or `propose` raises
`SplitSumError` with the sentence naming both totals. The changeset id and `to_out(changeset)`
are all the card needs; the extraction path does not have to render anything or write any row
itself, because Apply is `POST /api/changesets/{id}/apply`. If the photo matches nothing, that
is a new transaction preview, not a changeset.
