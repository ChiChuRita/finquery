# 69: Transactions table: what the visual review left open

**What to build:** Smaller things seen during the review of ticket 70 (filed as 68) and not changed there.
Each one a judgement call, so one ticket, decide per item.

**Blocked by:** 70 (done; filed as 68 before the number was taken by the model ticket)

**Status:** done for 1, 2 and 4; 3 and 5 left

Seen on 2026-09-07, 1440x900 and 1024x800, both themes, sample year loaded:

1. [x] **Subcategory clips at 1440.** "Cash withdrawal" and "Public transport" show as
   "Cash withdr…" and "Public trans…" because Category, Subcategory and Account share the
   remaining width at 1fr each. Either give Subcategory `minmax(9rem, 1fr)` or let Description
   give up some of its 1.6fr. Check 1024 keeps the "Scroll for more columns" behaviour.
2. [x] **Recategorize reads as a dead button.** In the selection bar it is disabled until a target
   is picked in "Move them to…", which is right, but a grey button next to a live Delete looks
   broken. Options: hide it until a target is chosen, or make the select itself the action
   (choosing a category opens the confirm dialog). Pick one.
3. [ ] **Header checkbox has no visible column title.** Fine for sighted users, but the accessible
   name is only on the checkbox. Confirm with a screen reader pass or leave.
4. [x] **The split editor's help text is two lines of prose.** "Queries and charts count the legs of
   a split, never the transaction itself. This transaction is one booking in one category. Add a
   leg to spread it over several." Could be one line plus the button. Copy only.
5. [ ] **The theme row in the sidebar keeps its focus ring after a click.** Visible in every
   screenshot taken after switching the theme. Check the `SidebarMenuButton` focus-visible
   handling; it may be a browser focus-after-click and not ours.

Rules for whoever takes this: implementation through an Opus sub-agent, verification headful on
a port the agent owns (never 8000 or 5173), throwaway database, named browser session, before
and after screenshots under `/tmp/finquery-69/`, no new dependency.

## Comments

Done 2026-09-07 for items 1, 2 and 4. Three files, no new dependency.

1. `transactions-table.tsx`: Subcategory `minmax(7rem, 1fr)` to `minmax(9rem, 1fr)`, Description
   keeps its 1.6fr, and the table min width goes from `68rem` to `72.75rem`, the sum of the ten
   column minimums (2.25 + 2 + 7 + 11 + 8.5 + 7.5 + 8.5 + 9 + 11.5 + 5.5). The old 68rem was
   already under the sum, so the grid overflowed past it anyway. Measured at 1440x900: the
   Subcategory column went 130.8px to 144px and the label inside the trigger 87px to 100px.
   That is not enough for the two names in the report: "Cash withdrawal" needs 107px and
   "Public transport" 102px, so both still end in an ellipsis, just later. 9.5rem would clear
   both, 10.5rem would also clear "Online marketplace" (125px). Left at the decided 9rem, flagged
   for whoever wants the clipping gone.
   At 1024x800 the scroller is 1164px against a 768px viewport (was 1132px), so "Scroll for more
   columns" still shows and nothing before Category moved.
2. `transactions-page.tsx`: the `ConfirmRecategorizeDialog` renders only when
   `target !== NOTHING_CHOSEN`, so the selection bar is "N selected, Move them to..., Delete"
   until a category is picked, then Recategorize appears live next to Delete. Checked the dialog
   still opens and says "Move these 2 bookings to Dining?". The component's `disabled` prop is now
   always false at this one call site; left in place rather than changing the dialog's signature.
   Pre-existing and now more visible: the target survives "Clear the selection", so the next
   selection shows a live Recategorize with the old target still in the select.
3. Left. Needs a screen reader pass to decide, not a code change.
4. `split-editor.tsx`: the two prose lines are one line, "One booking, one category. Add a leg to
   spread it over several; queries count the legs, not the booking.", where the empty state was.
   The "Split of -10,10 €" label stays. Nothing under the header line any more.
5. Left, and it is not ours. After a real mouse click on the theme row, `activeElement` is the
   button but `:focus-visible` is false, the computed outline style is `none` and the ring shadow
   is `0 0 #0000`: `SidebarMenuButton` only draws `focus-visible:ring-2`. What the screenshots
   show is `hover:bg-sidebar-accent` with the pointer parked on the row. Move the pointer away
   and the row is plain again (`after/1024-theme-clicked.png` against
   `after/1024-theme-clicked-mouse-away.png`).

`npm run build` clean, `npm run lint` 36 warnings and 0 errors, the same 36 as before the change.
Before and after screenshots in `/tmp/finquery-69/before/` and `/tmp/finquery-69/after/` at
1440x900 and 1024x800, each with a plain table, two rows selected and a split row expanded, plus
`after/1440-two-selected-target-chosen.png` for the button appearing. Server on port 8091 with
`/tmp/finquery-69/verify.db`, seeded through `/api/onboarding/sample` so no model ran, browser
session `ticket69`, both closed after.

Follow-up 2026-09-07, after the note above: 9rem still clipped "Cash withdrawal" and "Public
transport". Subcategory is now `minmax(10.5rem, 1fr)`, Description `minmax(10.75rem, 1.6fr)`,
table minimum 74rem, which is exactly the 1184px a 1440 window leaves next to the sidebar, so
no "Scroll for more columns" badge at 1440 and both names read in full. Checked headful on port
8093, session `vr2`, screenshot `/tmp/finquery-vr2/tx2.png`. Build and lint unchanged.
