# 09: Changesets and edits in chat

**What to build:** A user asks the assistant to split, recategorize, edit or delete transactions. For anything touching more than one row, or anything not literally requested, the assistant proposes a changeset: a card in the chat lists the exact affected rows with Apply and Discard. Applying is deterministic code. A single obvious edit the user literally asked for ("set this one to Dining") applies immediately with an Undo. Taxonomy changes (add, rename, merge, delete categories and subcategories) work both through the assistant as changesets and in a Settings taxonomy editor.

**Blocked by:** 04 Transactions page, 05 Query sub-agent and the numbers invariant

**Status:** ready-for-agent

- [ ] Changeset entity with kinds recategorize, split, edit, delete, taxonomy; preview computed at proposal time; superseded when a newer one arrives or the data changes underneath
- [ ] `propose_changeset` tool and the Changeset card with Apply and Discard calling REST endpoints; applied changesets show as applied in the transcript
- [ ] `apply_simple_edit` tool for single-row literal requests with an Undo button that reverts
- [ ] Split via chat creates children summing to the parent
- [ ] Settings taxonomy editor with add, rename, merge, delete and the effect on existing rows previewed
- [ ] HTTP-seam tests: proposal preview matches applied result, discard leaves data untouched, stale changeset refuses to apply, undo reverts a simple edit
- [ ] Browser verification of a split, a bulk recategorize, an undo and a taxonomy merge
