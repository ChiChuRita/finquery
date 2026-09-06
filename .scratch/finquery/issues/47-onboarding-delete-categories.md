# 47: Delete categories and subcategories in onboarding (micro-ticket)

**What to build:** The onboarding categories step lets the user rename and add, and turn a category off with a switch, but a subcategory cannot be removed there at all, and it is not clear that "off" deletes the category. Make deletion explicit and complete: every subcategory pill can be removed, every category (including one the user just added) can be deleted, and the copy says what happens. Requested by the user on 2026-09-06: "you can only add ones, not delete them".

**Blocked by:** 28 (merged)

**Status:** ready-for-agent

Decisions:
- Same path as Settings: every change goes through `proposeTaxonomyChange` plus `applyChangeset` with `operation: 'delete'` (category or category plus subcategory), exactly as `taxonomy-card.tsx` does, so bookings move to Needs review the same way and the two editors stay one implementation. Reuse the taxonomy card's pill menu (Rename, Merge into, Delete) for the onboarding pills if it can be shared without a redesign; otherwise a remove control on the pill (an X, keyboard reachable, named "Remove <subcategory> from <category>").
- The category switch stays as the fast way to turn a default off and back on (it restores the shape). Add a Delete entry for a category in the same menu the Settings card uses (`CategoryMenu`), so a category the user added by mistake can go without pretending it is a toggled default. Copy under the title: "Off removes a category from this profile; Delete does the same for one you added."
- A delete that would move bookings out of a category shows the count in a one-line confirmation before it runs; in onboarding the profile is usually empty and the confirmation then does not appear (check the changeset preview the proposal returns for the count, do not add a new endpoint if it is already there).
- No new dependency, no layout redesign (ticket 45 owns the UI pass), English copy, both themes.

- [ ] Subcategory removal and category delete in onboarding through the changeset path; Unknown stays undeletable; the list stays in order after a delete
- [ ] Confirmation with the booking count when bookings are affected; none when zero
- [ ] `npm run build` clean, oxlint at baseline, `uv run pytest` green (add an HTTP-seam test only if the backend changed); headful browser check (named session, own port above 8100, throwaway database): add a category, add a subcategory, remove the subcategory, delete the category, toggle a default off and on, both themes; screenshots in `/tmp/finquery-47/`; a short note under Comments
