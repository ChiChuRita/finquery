# 45: Square inside charts, and an audit of rounded borders across the UI

**What to build:** Nothing inside a chart is rounded: doughnut slices, bars, legend swatches. Rounding stays where the rest of the UI uses it (cards, buttons, inputs, popovers, the tooltip). Then a pass over every page and component for corners and borders that look odd: radii on elements flush with an edge, nested containers with mismatched radii, doubled borders (a bordered element inside a bordered element with no gap), pill shapes where a rectangle is meant, radii on table cells and inline editors, iframes or images rounded differently from their card, and anything similar. Requested by the user on 2026-09-06: "sometimes rounded borders make no sense, for example in the pie chart they look odd".

**Blocked by:** 36 (merged)

**Status:** ready-for-agent

Decisions, settled with the user:
- Square everywhere inside charts, one rule. The frame enforces it: the runtime's `barY`, `barX` and `radialArc` globals ignore `radius` and `cornerRadius` from generated code (a stored card takes the new look on reload without regeneration, the same reason ticket 36 kept the look in the frame), the legend swatches are square, and the two examples in the sub-agent's code prompt and the four defaults in `dashboard.py` drop those options so the model stops writing them. The self-check does not need a new rule if the frame ignores the options; add one only if the option is otherwise a repair loop.
- The chart runtime contract otherwise stays (`docs/chart-runtime.md`; note the rule there in one line). No new dependency. Dark and light parity.
- The audit covers Chat (transcript, composer, cards: chart, query result, question, changeset, web lookup, models, taxonomy, memory divider), Dashboard, Transactions (table, filters, inline edit, splits, bulk bar), Import, Memory, Feedback, Settings, Onboarding, the sidebar and tabs, dialogs, dropdowns and toasts. Both themes, 1024 and 1440.
- Fixes go to the component or theme token, not to call sites, when a pattern repeats. The radius scale stays the app's existing one (Tailwind `rounded-*` as configured); the fix for an odd corner is usually the right token, `rounded-none` on an edge-flush element, or removing a nested border, not a new value.

Constraints: ticket 44 runs in parallel and owns the dashboard's Add line (it removes it), the chat chart card's actions and the range bar; do not restructure those, style only what exists; do not touch `src/finquery/chart/selfcheck.py` rules beyond what the decision above needs; the suite and the frontend build stay green; headful browser session with a name, own port, throwaway database, never port 8000 or 5173.

- [ ] Before screenshots: every chart shape in chat and on the dashboard (doughnut first), and every page listed, both themes, 1024 and 1440
- [ ] Frame: `radius` and `cornerRadius` ignored by the bar and arc globals, square legend swatches, tooltip unchanged; prompt examples and the four defaults without those options; `docs/chart-runtime.md` says the rule; self-check and defaults tests still pass
- [ ] Audit list written first (element, page, what is odd, root cause, fix), then fixed by token or component
- [ ] After screenshots of the same inventory, contact sheets before and after per page, a note under Comments with the audit list and what changed; `uv run pytest` green, `npm run build` clean, oxlint at baseline, zero console errors
