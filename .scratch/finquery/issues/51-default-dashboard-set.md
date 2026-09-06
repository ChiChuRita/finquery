# 51: The default dashboard: tiles with deltas and six cards

**What to build:** The dashboard's default set as decided from `docs/research/charts-and-dashboard-2026-09-06.md` (Proposal A, accepted by the user on 2026-09-06): four tiles that carry a comparison, and six default cards that answer a household's questions in order (trend, income against spending, where, what changed, what is fixed, who), with a seventh, month pacing, once ticket 50 is merged. Every figure still comes from one guarded statement per card; deltas, averages and folds are arithmetic on the returned rows, like `fold_rows`.

**Blocked by:** 44, 45 (merged); 50 for the pacing card only

**Status:** ready-for-agent

Decisions, settled:
- Tiles: Spent, Income, Net for the newest month of the range, each with "vs last month" and "vs 6-month average" as signed deltas (euro and percent, coloured by whether the direction is good: spending down is good, income up is good, net up is good), and Needs review as today. One statement returns the last seven months; the frontend takes the last row as the month, the one before as last month, the mean of the earlier rows as the average (fewer months means the average says over how many). No sparklines in this ticket.
- Cards, in this order, created from fixed SQL and code in `dashboard.py` like today, each passing the self-check in the tests: (1) Spending per month, 12 months, `bar` (replaces the line: months are discrete, bars rest on zero, and a one-month range still reads). (2) Income against spending per month, `bar_grouped`, unchanged. (3) Top categories for the range, eight plus Other, `bar_horizontal` (replaces the doughnut). (4) This month against last month, top six categories, `bar_grouped` with `period` as the series, long rows, the shared fold keeping the six largest categories per period. (5) Regular payments: merchants seen in at least three of the last four months with a steady amount (max within 15 percent of min), average monthly amount, `bar_horizontal`, ten rows; the card's details say it is a heuristic and how it is defined. (6) Top ten merchants for the range, `bar_horizontal`, scoped by the range instead of "this year". (7) After ticket 50 lands: month pacing, cumulative spending by day of month, this month against last month, two-series `line` over `day` with `SUM() OVER`.
- The SQL sketches in the research note are the starting point; "newest booking" stays `MAX(booked_on)` over the (range-narrowed) view so the presets from ticket 44 mean the same thing on every card.
- Existing profiles: `profile.dashboard_seeded` means the old four stay where they are. Add one action in the page's overflow menu, "Restore default cards", which adds any default card the profile is missing (matched by a stable `default_key` on the card, a new nullable column via `db.NEW_COLUMNS`) without touching user-made cards. The demo starts on a fresh profile anyway.
- The doughnut stays a chat shape. No change to `shapes.py` or the runtime.
- Both themes, 1024 and 1440; the card order above is the position order; the grid stays as it is.

- [ ] Tiles statement and the delta arithmetic in the frontend, with the direction colouring and the "over n months" note; empty profile still shows zeros
- [ ] Six default cards in `dashboard.py` with `default_key`, all passing the self-check in `tests/test_dashboard.py` against the shipped dataset, each drawing on the sample year; the regular-payments card's details name the heuristic
- [ ] "Restore default cards" in the page's overflow menu and its endpoint; adds only missing defaults; tests
- [ ] After merging main once ticket 50 is in: the pacing card as the seventh default, passing the self-check with two series and a legend
- [ ] `uv run pytest` green, `npm run build` clean, oxlint at baseline; headful browser verification (named session, own port above 8100, throwaway database with the sample year; the page needs no model call): the tiles with deltas, all cards drawn, the range presets changing every card, Restore default cards on a profile that had the old four, both themes; screenshots in `/tmp/finquery-51/`; Comments in the ticket 35 style
