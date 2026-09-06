# 47: Delete categories and subcategories in onboarding (micro-ticket)

**What to build:** The onboarding categories step lets the user rename and add, and turn a category off with a switch, but a subcategory cannot be removed there at all, and it is not clear that "off" deletes the category. Make deletion explicit and complete: every subcategory pill can be removed, every category (including one the user just added) can be deleted, and the copy says what happens. Requested by the user on 2026-09-06: "you can only add ones, not delete them".

**Blocked by:** 28 (merged)

**Status:** done

Decisions:
- Same path as Settings: every change goes through `proposeTaxonomyChange` plus `applyChangeset` with `operation: 'delete'` (category or category plus subcategory), exactly as `taxonomy-card.tsx` does, so bookings move to Needs review the same way and the two editors stay one implementation. Reuse the taxonomy card's pill menu (Rename, Merge into, Delete) for the onboarding pills if it can be shared without a redesign; otherwise a remove control on the pill (an X, keyboard reachable, named "Remove <subcategory> from <category>").
- The category switch stays as the fast way to turn a default off and back on (it restores the shape). Add a Delete entry for a category in the same menu the Settings card uses (`CategoryMenu`), so a category the user added by mistake can go without pretending it is a toggled default. Copy under the title: "Off removes a category from this profile; Delete does the same for one you added."
- A delete that would move bookings out of a category shows the count in a one-line confirmation before it runs; in onboarding the profile is usually empty and the confirmation then does not appear (check the changeset preview the proposal returns for the count, do not add a new endpoint if it is already there).
- No new dependency, no layout redesign (ticket 45 owns the UI pass), English copy, both themes.

- [x] Subcategory removal and category delete in onboarding through the changeset path; Unknown stays undeletable; the list stays in order after a delete
- [x] Confirmation with the booking count when bookings are affected; none when zero
- [x] `npm run build` clean, oxlint at baseline, `uv run pytest` green (add an HTTP-seam test only if the backend changed); headful browser check (named session, own port above 8100, throwaway database): add a category, add a subcategory, remove the subcategory, delete the category, toggle a default off and on, both themes; screenshots in `/tmp/finquery-47/`; a short note under Comments

## Comments

Done 2026-09-06. `npm run build` clean, oxlint at baseline (41 warnings, all pre-existing
`only-export-components`), `uv run pytest` 326 passed, 4 skipped. No backend change, so no new
test: the seam the confirmation reads (`total` on a taxonomy proposal, the `note` naming Needs
review, `total` 0 for an add) is already asserted in
`tests/test_changesets.py::test_add_rename_and_delete_of_a_category_show_their_effect_first`.

### What it is

The Settings card's two menus were the only place that knew what can be done to a name, so they
moved out of `taxonomy-card.tsx` into `frontend/src/components/taxonomy-menus.tsx` as
`SubcategoryPill` and `CategoryMenu`. Onboarding renders those same two, so a pill in step 1 now
offers Rename, Merge into and Delete, and every category row has the menu beside its switch.
Nothing forked: the Settings card behaves as it did.

Every change is still the changeset path (`proposeTaxonomyChange` then `applyChangeset`), so a
booking moves to Needs review the same way in both editors. What is new in step 1 is that a
change which takes a name away (a delete, and a merge, which does the same thing to the old name)
is proposed first and only applied once the preview's `total` is known: zero bookings applies
straight away, more than zero opens the existing `ConfirmDialog` with the preview's own line
("Deletes the category Leisure. 7 bookings lose it and become Needs review."). Cancel discards
the proposal, so it cannot be applied later. A row that is off is not in the taxonomy any more,
so its menu is not rendered until the switch brings it back, and `Unknown` is still filtered out
of the list entirely.

One order fix: a ghost row (a default turned off, kept in place) used to slip one place down when
a category above it was deleted for real. `closeGap` moves the kept rows up with it.

### Verified headful, port 8137, throwaway database, session `ticket47`

Fresh profile straight into `/onboarding`. Added "Pets", added the subcategory "Vet", removed Vet
from its pill menu and deleted Pets from its category menu (both gone from `GET /api/categories`,
neither asked, because nothing used them). Health toggled off (really gone from the taxonomy, row
greyed in place, pills and menu unreachable) and back on with its three subcategories.

For the count: the shipped year imported over `POST /api/imports` (preset mapping, no model) and
bookings put in a category with `bulk-recategorize`. Deleting Leisure then said "7 bookings lose
it and become Needs review". Cancel discarded the proposal and left Leisure alone; Delete applied
once (one apply in the log, no discard after it) and the profile was back to 433 Needs review.
The switch takes the same route: turning Dining off with five bookings under it asked first, and
Cancel snapped the switch back on. Deleting Groceries above the Dining ghost left the ghost where
it was. Both themes, zero console messages, zero page errors. Settings' own editor still opens
its preview dialog for the same delete. Screenshots: `/tmp/finquery-47/` (01 to 12).

### Seen in passing

A category turned back on lands at the end of the list rather than in its old place (the taxonomy
appends it and the kept position is dropped once it is real again). That is ticket 28's behaviour,
unchanged here; ticket 45 owns the step's UI pass if it should be preserved.
