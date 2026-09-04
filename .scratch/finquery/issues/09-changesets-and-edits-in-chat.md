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

Merged into main on 2026-09-04 on top of 01, 02, 03, 04, 05, 07, 12, 13, 16, 18 and 19. What
changed in the merge:

- `agent.py` is the union of six tools on one `ChatDeps`: `query`, `propose_changeset`,
  `apply_simple_edit`, `remember`, `set_rule` and `review_batch`, plus the `ask_user` toolset and
  `output_type=[str, DeferredToolRequests]`. `ChatDeps` was already the five-field union
  (`session_factory`, `profile_id`, `conversation_id`, `resolve_model`, `subagent_settings`) on
  this branch's base, so nothing had to be added to it. Prompt order: the query rules, then
  "Changing the data", then the `remember` rule, then the categories and rules block, then the
  two paragraphs that stay last (answer as text after a tool, keep answers short).
- `app.py` imports `TransactionEditError` from `finquery.edits`, not from `api.transactions`
  any more: the shared refused handler and the page's own writes now name the same exception.
  The 409 `conflicted` handler for `ChangesetStale` sits next to it, and `context_budget` from
  ticket 12 stays.
- `api/transactions.py` keeps ticket 04's explicit profile scoping (a read takes `profile_id` as
  a required query parameter, a write carries it in the body, another profile's row is a 404) and
  now gets `resolve_taxonomy`, `resolve_account`, `clean_description`, `find_transaction`,
  `listing_conditions` and `replace_split_legs` from `edits.py`. Every call still passes
  `profile_id` explicitly, so the scoping and the shared rules are the same thing rather than two
  copies.
- `lib/api.ts` is the union of the tool map: `query`, `ask_user`, `set_rule`, `review_batch`,
  `propose_changeset`, `apply_simple_edit`. The part types use main's `ToolUIPart<{...}>` style
  throughout, so `ChangesetToolPart` is one union of the two writing tools rather than an
  `Extract` over the whole map. `chat-view.tsx` renders the changeset branch after the
  `ask_user`, `set_rule` and `review_batch` branches.
- **The test context budget went from 2000 to 2600 tokens.** The system prompt is 1197 tokens
  now (920 before this merge): the "Changing the data" block is about 277 of them. A compressed
  prompt can never go below the system prompt plus the summary plus the last six turns, about
  2100 tokens here, so the old 2000-token budget was under the floor and `used < budget` could
  not hold after compression. Nothing changed in the code; the real default is 32768.
  This is the second time this test's budget had to move for a longer prompt (see ticket 12's
  note), so a ticket that adds a prompt block should expect to touch it.
- `uv run pytest` is 83 passed, 1 skipped (`test_changesets.py` adds 13 to main's 70).
  `npx tsc --noEmit`, `npm run build` and `oxlint` are clean.
- Verified on OpenRouter on port 8076 with a throwaway database and the Sparkasse preset imported
  by REST (433 rows, categorization placed 408 and left 25, the same figures as ticket 07):
  - The quality slot proposed all 12 Netflix bookings to Subscriptions as a card titled "Move
    Netflix bookings to Subscriptions" (Recategorize, Waiting for you, "12 bookings move to
    Subscriptions.", every row as `Needs review -> Subscriptions`), and its answer said it had
    proposed the change rather than made it. Apply turned the card Applied and the Transactions
    page filtered to netflix showed 12 rows in Subscriptions.
  - "Set the PayPal payment to Jonas Keller from 2 October 2025 to Dining" went through
    `apply_simple_edit` after the model found the row, and the card came back Applied with an
    Undo. Undo on it and Undo on the applied recategorize both reverted their rows and both cards
    read Reverted, still after a reload.
  - The Settings taxonomy editor renders the profile's categories with the add, rename, merge and
    delete affordances.
  - Screenshots: /tmp/finquery-merge09/.
- Seen in verification, not caused by the merge: the query sub-agent needed four attempts to find
  the Jonas Keller booking, because "PayPal" is nowhere in the description (`PP.4711.PP . JONAS
  KELLER, Ihre Zahlung`). The turn recovered on its own, but a single-row edit costs four query
  calls when the user names the processor instead of the counterparty.
- Harness note for the next browser verification: `agent-browser`'s click reports success but
  does nothing when the target sits below the fold (the default viewport is 577 px tall and a
  card's Apply button lands past it). Scroll it into view first, or click through
  `eval`. Same family of harness quirk as ticket 19. Also, several cards in one transcript means
  several Undo buttons: `find role button --name Undo` takes the first one, which is not
  necessarily the card you are looking at.
