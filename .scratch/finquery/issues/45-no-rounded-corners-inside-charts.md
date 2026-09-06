# 45: Square inside charts, and an audit of rounded borders across the UI

**What to build:** Nothing inside a chart is rounded: doughnut slices, bars, legend swatches. Rounding stays where the rest of the UI uses it (cards, buttons, inputs, popovers, the tooltip). Then a pass over every page and component for corners and borders that look odd: radii on elements flush with an edge, nested containers with mismatched radii, doubled borders (a bordered element inside a bordered element with no gap), pill shapes where a rectangle is meant, radii on table cells and inline editors, iframes or images rounded differently from their card, and anything similar. Requested by the user on 2026-09-06: "sometimes rounded borders make no sense, for example in the pie chart they look odd".

**Blocked by:** 36 (merged)

**Status:** done

Decisions, settled with the user:
- Square everywhere inside charts, one rule. The frame enforces it: the runtime's `barY`, `barX` and `radialArc` globals ignore `radius` and `cornerRadius` from generated code (a stored card takes the new look on reload without regeneration, the same reason ticket 36 kept the look in the frame), the legend swatches are square, and the two examples in the sub-agent's code prompt and the four defaults in `dashboard.py` drop those options so the model stops writing them. The self-check does not need a new rule if the frame ignores the options; add one only if the option is otherwise a repair loop.
- The chart runtime contract otherwise stays (`docs/chart-runtime.md`; note the rule there in one line). No new dependency. Dark and light parity.
- The audit covers Chat (transcript, composer, cards: chart, query result, question, changeset, web lookup, models, taxonomy, memory divider), Dashboard, Transactions (table, filters, inline edit, splits, bulk bar), Import, Memory, Feedback, Settings, Onboarding, the sidebar and tabs, dialogs, dropdowns and toasts. Both themes, 1024 and 1440.
- Fixes go to the component or theme token, not to call sites, when a pattern repeats. The radius scale stays the app's existing one (Tailwind `rounded-*` as configured); the fix for an odd corner is usually the right token, `rounded-none` on an edge-flush element, or removing a nested border, not a new value.

Constraints: ticket 44 runs in parallel and owns the dashboard's Add line (it removes it), the chat chart card's actions and the range bar; do not restructure those, style only what exists; do not touch `src/finquery/chart/selfcheck.py` rules beyond what the decision above needs; the suite and the frontend build stay green; headful browser session with a name, own port, throwaway database, never port 8000 or 5173.

- [x] Before screenshots: every chart shape in chat and on the dashboard (doughnut first), and every page listed, both themes, 1024 and 1440
- [x] Frame: `radius` and `cornerRadius` ignored by the bar and arc globals, square legend swatches, tooltip unchanged; prompt examples and the four defaults without those options; `docs/chart-runtime.md` says the rule; self-check and defaults tests still pass
- [x] Audit list written first (element, page, what is odd, root cause, fix), then fixed by token or component
- [x] After screenshots of the same inventory, contact sheets before and after per page, a note under Comments with the audit list and what changed; `uv run pytest` green, `npm run build` clean, oxlint at baseline, zero console errors

## Comments

Done 2026-09-06. `uv run pytest` is 326 passed, 4 skipped (the self-check and defaults tests
run the four defaults through the check; nothing in `selfcheck.py` moved). `npm run build` is
clean, `oxlint` is at its baseline (41 warnings on main, 41 here). Zero browser console messages
and zero page errors on the dashboard and the chat; no 4xx or 5xx in the server log over the whole
session apart from one 404 for the pre-rebuild `main-*.js` hash that the browser's cached
`index.html` asked for once (OpenRouter, Gemini 3.8 Flash on both slots, port 8145, throwaway
database under `/tmp/finquery-45/data`, headed session `ticket45`). Screenshots:
`/tmp/finquery-45/before/` (150 files) and `/tmp/finquery-45/after/` (133 files), both themes,
1440x900 and 1024x768; contact sheets per page and state in `/tmp/finquery-45/sheets/` (37
sheets, before left, after right, the four variants as rows; popups, the inline editor and the
tooltip as one row per theme). Inventory: onboarding (four steps), chat (import step, Question
card, doughnut, line, stacked and grouped charts, chart details, query rows, memory step open and
closed, changeset proposed and applied, thinking panel, Regenerate pair and picked state, empty
chat, model picker), sidebar (conversation menu, profile menu, rename), dashboard (four defaults,
tooltip), transactions (table, inline edit, split editor, bulk bar, filters, add dialog, category
menu), imports (list, delete dialog), memory, feedback, settings (setup, categories, models, web
lookup).

The four stored defaults in that database were created by the server before `dashboard.py`
changed, so their code still carries `cornerRadius: 3` and `radius: 2` and `4`: they took the
square look on reload without being regenerated, which is what enforcing the rule in the frame
is for.

### The audit list

Element, page, what is odd, root cause, fix.

1. **Doughnut slices**, chat and dashboard. Every slice had rounded ends, so a ring built from
   six flat arcs read as six soft pills. The prompt's two doughnut examples and the dashboard's
   category default wrote `cornerRadius: 3`, and the frame passed it through. Fixed in the frame:
   `radialArc` drops `cornerRadius` whatever the code wrote; the examples and the default no
   longer write it.
2. **Bars**, every bar shape (bar, horizontal, grouped, stacked), chat and dashboard. Each rect
   had four rounded corners, so a stacked segment was a rounded tile sitting on another and a
   short horizontal bar was a pill. The examples and two defaults wrote `radius: 2` or `4`.
   Fixed in the frame: `barY` and `barX` drop `radius`; the examples and the defaults no longer
   write it.
3. **Legend swatches**, every chart with a series. Round dots beside square marks. TanStack's
   categorical `colorLegend` draws a `dot` node of radius 4 and has no option for anything else.
   Fixed in the frame: `colorLegend` is wrapped and each `legend-dot:*` node becomes a rect of
   the same size on its way to the renderer.
4. **Dashboard chart cards beside the tiles**, dashboard. The cards were `rounded-lg`, the tiles
   `rounded-xl`: two radii for the same kind of container on one page. `ChartCard` carried the
   transcript's radius and could not take another. Fixed in the component: `ChartCard` takes a
   `className`, and `DashboardCard` passes `rounded-xl`, the radius every other card on a page
   has (the tiles, the imports list, the settings sections, the empty states).
5. **Question card rows**, chat. `rounded-lg border` rows inside a `rounded-lg border` card, the
   same radius nested, while every other container nested in a transcript block steps one down
   (the changeset's table, the query rows, the chart's code block are `rounded-md`). Fixed:
   `rounded-md`.
6. **Regenerate pair sides**, chat chart card. The two `rounded-lg border` frames sat inside the
   `rounded-lg` card. Fixed: `rounded-md`. The picked side keeps its `border-primary` and soft
   ring: a highlight, not a second edge.

### What changed

**Frame** (`frontend/src/chart-runtime/globals.ts`). `withDefaults` for `barY` and `barX` now
strips `radius` before adding the surface gap, `radialArc` strips `cornerRadius`; a `without`
helper does both. `squareLegend` wraps `colorLegend` and rewrites the rendered scene: every
`dot` keyed `legend-dot:` becomes a `rect` at the same centre and size, groups are walked, the
gradient and stepped legends already draw rects and pass through. The tooltip's swatch, surface,
radius and shadow are as ticket 36 left them. The contract did not move: same twenty-four
globals, same shapes, same house rules.

**Prompt and defaults** (`src/finquery/chart/subagent.py`, `src/finquery/dashboard.py`). The
six `radius: N` and three `cornerRadius: 3` occurrences are gone from the code examples and the
four defaults, so the model stops writing them; the frame ignores them anyway, which is why no
self-check rule was added.

**Components** (`chart-tool.tsx`, `dashboard-card.tsx`, `question-card.tsx`, `feedback.tsx`).
`ChartCard` merges a `className`; the dashboard card passes `rounded-xl`; the Question card's
rows and `PairSide` step down to `rounded-md`.

**Docs.** `docs/chart-runtime.md`, "What the frame's theme sets": a "Corners" line with the rule.

### Checked, and left as they are

- Pills by intent: every `Badge` (shape badge, status chips, subcategory pills, model and memory
  chips, the summary divider's dashed pill, the scroll hint), the suggestion chips under an
  answer and on the empty chat, the composer's round submit, the scroll-to-bottom button, the
  onboarding progress segments, `Switch` and `Progress`.
- Controls keep their own radius inside any container: `Button`, `Input`, `Select` and the
  Needs review chip at `rounded-lg`, small sizes at `min(var(--radius-md), 10px or 12px)`, the
  checkbox at 4 px.
- Nested containers already one step down: settings sections xl over lists lg, `Tool` lg over
  content md, changeset lg over its table md, chart card lg over code block and rows md,
  onboarding section xl over its list lg, models card xl over model rows lg.
- Edge-flush elements carry no radius: page headers, the tab bar, the sidebar, the sticky table
  header, the bulk bar, the error banner, the split editor.
- Table cells and inline editors: the read cell is the ghost button's `rounded-md` hover, the
  write cell a `rounded-md` input, the select trigger `rounded-md` with a transparent border, all
  inside borderless rows, so nothing doubles.
- The iframe is `border-0`, painted in the card's own surface and clipped by the card's
  `overflow-hidden`, so it has no corner of its own; on the dashboard it is now clipped at xl.
- The active conversation tab is a bordered `rounded-md` chip on the flush bar; the onboarding
  `Card` (ring) and the pages' `border bg-card` boxes are both xl with an equal hairline.
- `MessageBranchSelector` in the vendored `message.tsx` carries an inverted
  `rounded-l-md`/`rounded-r-md` rule from the registry but is rendered nowhere in the app.
- Ticket 44's parts (the dashboard's Add line, the chat card's actions, the range bar) were
  screenshotted but not touched.
- Gemini 3.8 Flash wrote the identical definition again for the doughnut and the line, so the
  pair state was captured on the stacked bars before and on grouped bars after.
