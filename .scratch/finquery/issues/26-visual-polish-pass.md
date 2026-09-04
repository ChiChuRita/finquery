# 26: Visual polish pass across every page and component

**What to build:** Walk every page and every component state in a real browser and fix everything that looks off: margins and paddings, alignment, spacing rhythm, typography scale, borders and radii, colour usage, empty and loading states, focus rings, hover states, truncation, dark and light parity, 1024 and 1440 widths. The result is one product where every screen looks designed by the same hand. Requested by the user on 2026-09-05 as a Fable 5.1 job.

**Blocked by:** 24 (merged)

**Status:** done

- [x] Inventory: a checklist of every route (chat empty state, conversation with every part type: reasoning, query step, chart card, changeset card, question card, import step, lookup step, memory step, follow-ups, thumbs and compare; Transactions with filters, inline edit, split editor, bulk bar, dialogs; Imports overview with cards, Continue in chat, Delete dialog; Memory; Feedback; Settings with models, taxonomy, web lookup and log cards; sidebar with profile switcher, tabs, dialogs; model selector; composer with attachments), screenshotted in both themes at 1024 and 1440 before any change
- [x] Every finding fixed at the source: shared spacing and typography tokens in index.css, component-level fixes in the shadcn and AI Elements primitives where the fault is theirs, page-level fixes otherwise; no one-off pixel hacks
- [x] Consistent spacing rhythm (one scale), consistent card padding and radius, consistent page header and section spacing, consistent table density, aligned baselines in toolbars and footers, no clipped or overflowing text, no orphaned margins at container edges
- [x] Dark and light parity: every surface, border and text colour reads correctly in both themes; charts follow the theme (do not change chart internals, ticket 25 owns them; only the card's outer spacing)
- [x] Focus visible on every interactive element, hover states consistent, disabled states legible
- [x] After screenshots of the same inventory in both themes at both widths; a before and after contact sheet per route
- [x] Typecheck and build clean; existing tests green; zero console messages

## Comments

### Findings, 2026-09-05, grouped by root cause

Before screenshots: `/tmp/finquery-26/before/<route>-<state>-<theme>-<width>.png` (270 files, both
themes, 1440x900 and 1024x768). Inventory: chat empty (with and without data), review conversation
with the Question card (open, applied), query turn (collapsed, expanded, reasoning open,
streaming), chart card (plain, details, regenerated pair, picked), answer compare (open, picked),
changeset card (proposed, applied), memory step, lookup step (with sources), composer with an
attachment, import step (collapsed, open) with the duplicates card, stopped turn, model picker;
Transactions default, filters, inline edit, split editor (with legs), bulk bar, delete dialog, add
dialog, open picker, empty filter, empty profile; Imports list (one and two cards), delete dialog,
empty; Memory list, edit, delete dialog, empty; Feedback list, empty; Settings top, category menu,
subcategory menu, rename input, preview dialog, add dialog, models card, web lookup card with the
log; sidebar conversation menu, rename, delete dialog, profile menu, new and delete profile
dialogs; focus after Tab presses. Not reachable without a behaviour change: the summary divider
(needs a compressed conversation).

**Tokens (index.css)**

- No semantic status colour: 31 raw palette utilities (`amber`, `emerald`, `green`, `red`,
  `yellow`, `blue`, `orange`) in six files, each with a hand-written `dark:` pair, and the AI
  Elements tool status icons with none, so they do not follow the theme.
- `text-[11px]` in 19 places across 13 files: an off-scale size for every caption.
- Focus: every hand-rolled link and button (sidebar nav and recent list, conversation tabs,
  taxonomy pills and names, memory text, table expand chevron, read-mode cells) falls back to the
  browser's `outline: auto 1px` in `ring/50`, which is close to invisible, while every Button and
  input gets the 3px ring. Confirmed with computed styles after Tab presses.
- The `@layer base` block has inconsistent indentation.

**Primitives (components/ui, components/ai-elements)**

- AI Elements `MessageContent` is `w-fit` for the assistant, so every block is only as wide as
  its widest sibling: the query step is a 315px pill collapsed and 680px open, the chart card
  jumps from 560px to 640px when a pair appears, the changeset card is a third width.
- Four radii inside one transcript: `Tool` and the changeset shell `rounded-md`, `Step` and the
  lookup box `rounded-lg`, the Question card and the chart card `rounded-xl`.
- `Tool` header `p-3` against content `p-4`: the content sits 4px right of the header icon.
- Two destructive buttons: the transaction delete dialog paints `bg-destructive text-white`
  over the primitive while every other confirm uses `variant="destructive"`.
- The transactions picker cell clips "Sparkasse Girok" without an ellipsis at both widths: the
  select trigger puts `line-clamp-1` on a nowrap span, which never ellipsizes.
- Hand-rolled pills where `Badge` exists: model chip, memories chip, Stopped chip, models card
  status, taxonomy subcategory pills, the scroll hint; a hand-rolled progress bar where
  `Progress` exists; a search box with an absolutely positioned icon where `InputGroup` exists.
- Three empty-state shapes: a centred dashed box on Imports, a horizontal strip on Memory and
  Feedback, bare text on Transactions.

**Pages**

- Two page-header patterns: Imports uses the compact bar (h-14, text-sm) like Transactions while
  Memory, Feedback and Settings use the document heading (text-2xl, subtitle, max-w-3xl); Imports
  is also the only max-w-4xl page. The chat header is h-11 next to a h-14 Transactions header.
- Settings cards are the only surfaces with a shadow.
- Sidebar icon column: New chat icon 16px at px-2.5, nav icons 14px at px-2, recent items pl-2.
- Transactions at 1024: the "Enriched title" header wraps to two lines; the filter bar wraps
  "Clear" onto its own row at 1440.
- Changeset tables show ISO dates (2025-12-07) where the app shows 07.12.2025.
- Empty-cell glyph: em dash in the changeset and transactions tables, en dash in query results.
- Question card row descriptions truncate prose ("This is what re-im...").
- Duplicated `Step` styles in the lookup step; a template-literal className in the feedback list;
  "line(s) skipped" on the preview step.

**Out of scope (behaviour), left for a ticket**

- Every turn with a tool call still renders a thinking panel before and after the step.
- A stray text part reading "thought" appeared between the applied Question card and the next.
- After Stop, the live transcript kept about one viewport of empty space below the last turn
  until a reload.
- The composer labels the hosted slots with the local model names.

### After, 2026-09-05

After screenshots: `/tmp/finquery-26/after/` (250 files, the same states, plus the memory step
opened and a markdown table answer). Contact sheets per route, before and after side by side in
light 1440 and dark 1024: `/tmp/finquery-26/sheets/<route>.png` for chat, transactions, imports,
memory, feedback, settings, sidebar and focus. Typecheck, lint and build clean, 157 tests green,
zero console messages across the whole session.
