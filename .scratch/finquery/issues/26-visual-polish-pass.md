# 26: Visual polish pass across every page and component

**What to build:** Walk every page and every component state in a real browser and fix everything that looks off: margins and paddings, alignment, spacing rhythm, typography scale, borders and radii, colour usage, empty and loading states, focus rings, hover states, truncation, dark and light parity, 1024 and 1440 widths. The result is one product where every screen looks designed by the same hand. Requested by the user on 2026-09-05 as a Fable 5.1 job.

**Blocked by:** 24 (merged)

**Status:** ready-for-agent

- [ ] Inventory: a checklist of every route (chat empty state, conversation with every part type: reasoning, query step, chart card, changeset card, question card, import step, lookup step, memory step, follow-ups, thumbs and compare; Transactions with filters, inline edit, split editor, bulk bar, dialogs; Imports overview with cards, Continue in chat, Delete dialog; Memory; Feedback; Settings with models, taxonomy, web lookup and log cards; sidebar with profile switcher, tabs, dialogs; model selector; composer with attachments), screenshotted in both themes at 1024 and 1440 before any change
- [ ] Every finding fixed at the source: shared spacing and typography tokens in index.css, component-level fixes in the shadcn and AI Elements primitives where the fault is theirs, page-level fixes otherwise; no one-off pixel hacks
- [ ] Consistent spacing rhythm (one scale), consistent card padding and radius, consistent page header and section spacing, consistent table density, aligned baselines in toolbars and footers, no clipped or overflowing text, no orphaned margins at container edges
- [ ] Dark and light parity: every surface, border and text colour reads correctly in both themes; charts follow the theme (do not change chart internals, ticket 25 owns them; only the card's outer spacing)
- [ ] Focus visible on every interactive element, hover states consistent, disabled states legible
- [ ] After screenshots of the same inventory in both themes at both widths; a before and after contact sheet per route
- [ ] Typecheck and build clean; existing tests green; zero console messages
