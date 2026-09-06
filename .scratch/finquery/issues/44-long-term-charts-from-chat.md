# 44: Long-term charts from chat, and a date range on the dashboard

**What to build:** Two kinds of chart, told apart and both made in chat. A one-time chart lives in its transcript. A long-term chart also lives on the dashboard, and the chat agent decides itself which kind it just drew. Long-term charts can be listed, shown, edited, renamed and removed from chat, edits and removals applying directly with Undo. The dashboard becomes an overview: its own "Add chart" line goes, and it gains a date range (from, to, presets) that narrows every stored statement and the tiles without a model call. Requested by the user on 2026-09-06, grilled, decisions below are settled.

**Blocked by:** 35, 36, 39, 42 (merged)

**Status:** done

Decisions, settled with the user:
- The agent decides. The `chart` tool gets a `keep: bool = False` argument the chat agent sets when the question reads like something to track: the user says keep, track, dashboard, each month, over time; or the question is a recurring overview (spending per month over a year, share by category, income against spending) rather than a one-off (one merchant, one comparison, one week). A kept chart is stored as a `dashboard_chart` row with `created_from = "chat"` right from the tool, only when the chart rendered. The chat card reads "On the dashboard" with a Remove action, so a wrong call is one click. The manual "Add to dashboard" stays for the charts the agent did not keep. The agent says in one line that the chart is on the dashboard; it never says so when `kept` in the payload is false.
- Chat manages long-term charts. New tools on the chat agent, all profile-scoped: `dashboard_charts()` lists id, title, shape, request and position (so "what is on my dashboard" and "the groceries one" resolve); `show_dashboard_chart(id)` re-runs the card and returns the chart payload so the chart card renders it in the answer; `edit_dashboard_chart(id, request)` re-runs the chart sub-agent (`run_chart`) with the stored title, plan and SQL handed over as the previous version plus the new request, stores the new title, shape, plan, sql, code, notes and language on the same row (same position), and returns the chart payload; `rename_dashboard_chart(id, title)` without a model call; `remove_dashboard_chart(id)`.
- Apply directly with Undo. Edit, rename and remove apply at once. The row keeps its previous version (`previous_json`: title, shape, language, plan, sql, code, notes) and removal is a `removed_at` timestamp the dashboard and the list tool hide; `POST /api/dashboard/charts/{id}/undo` restores the previous version or clears `removed_at`, once. The chat card for an edit shows the new chart with Undo; the card for a rename or a removal is a small line with Undo. Undo on a card whose change was already undone is disabled with "Undone".
- The dashboard is an overview. The "Add chart" line, the preview card, `POST /dashboard/charts/preview` and `POST /dashboard/charts` (Keep) are removed along with their frontend functions and tests, and the empty state and the page hint point to chat ("Ask for a chart in chat; charts worth keeping land here"). Rename inline, move left and right, refresh and remove stay on the cards.
- The date range narrows the view. `execute_read_only` takes optional `since` and `until` dates and writes them into the temp view's WHERE (`AND booked_on BETWEEN ...`, inlined like the profile id, ISO strings). `GET /api/dashboard` and the refresh endpoint take optional `from` and `to` query parameters (ISO dates, `from <= to`, 422 otherwise) and apply them to the tiles and to every card. The response carries the range that was applied and the profile's first and last booking day, so the page can bound its pickers and label "All". Nothing about the range is stored.
- The range control is two date fields and preset chips (This month, Last 3 months, This year, All; the three relative to the newest booking, like the tiles). The range lives in the dashboard route's search params (`validateSearch`), so reload, back and a shared link keep it, and the React Query key includes it. An empty search means All.
- One-time versus long-term is visible: the chart card in chat shows "On the dashboard" (kept by the agent or pinned by hand) or nothing; a dashboard card whose SQL came from chat keeps its `request` in Details as today.

Constraints: numbers still come only from executed SQL through the guard (no change to the guard's rules, only to the temp view's WHERE); the chart runtime contract and `docs/chart-runtime.md` do not move; the sub-agent prompt gains the previous-version hint for edits only; no new dependency; the chat agent's instructions for `keep` are few lines with two examples (one kept, one not), written in the style of ticket 42; do not restyle anything (ticket 45 runs a UI pass in parallel and owns radii, borders and spacing), keep your frontend changes to behaviour and copy.

- [x] `chart(request, hints, keep)` stores a kept, rendered chart as a dashboard card from the tool; payload carries `kept` and `dashboard_chart_id`; the pins endpoint reports it so the chat card reads "On the dashboard" after a reload; a kept chart is never stored twice for one call
- [x] Tools `dashboard_charts`, `show_dashboard_chart`, `edit_dashboard_chart`, `rename_dashboard_chart`, `remove_dashboard_chart` with docstrings in the ticket 42 style; the chat agent's instructions say when to keep and how to talk about it
- [x] `previous_json`, `removed_at` via `db.NEW_COLUMNS`; `POST /api/dashboard/charts/{id}/undo`; the edit card, rename line and removal line in chat with Undo and the Undone state; Remove on the chat chart card
- [x] Dashboard page: Add line, preview card, preview and keep endpoints removed; range bar with two date fields and the four presets; search params validated; tiles and cards re-query on change; empty state and hint point to chat
- [x] `execute_read_only(since, until)`; `GET /api/dashboard?from&to` and refresh with the range; the response's applied range and data bounds; 422 for a reversed range
- [x] HTTP-seam tests with the scripted FunctionModel: kept chart stored once and reported by pins; not kept means not stored; not rendered means not stored; list, show, edit (previous version kept, position kept), rename, remove, undo each once, second undo 409; dashboard with a range returns fewer rows and the tiles for the range's last month; defaults' "newest booking" follows the range's end; reversed range 422; preview and keep routes gone (404)
- [x] `uv run pytest` green, `npm run build` clean, oxlint at baseline; headful browser verification (named session, own port, throwaway database, sample year loaded): a tracking question kept by the agent and shown on the dashboard after reload, a one-off not kept, "show me the groceries chart" rendering it in chat, an edit with Undo and the dashboard reflecting both, a removal with Undo, the range bar with each preset and a custom range, both themes; screenshots in `/tmp/finquery-44/`; a note under Comments with what was built and what was seen

## Comments

Done 2026-09-06. `uv run pytest` is 334 passed, 4 skipped (326 before; the four skips are the
usual environmental ones: the two private Trade Republic fixtures, the private statement PDF and
the opt-in local smoke suite). Nine tests are new and one was replaced. `npm run build` is clean
and `oxlint` is 41 warnings, which is the count on `main`: this ticket adds none.

### As built

**The agent decides, inside the tool.** `chart(request, hints, keep)` stores a kept, rendered
chart as a dashboard card before it returns, and the payload carries `kept` and
`dashboard_chart_id`. A chart nobody could see is never kept, because a card of a drawing that
failed is worse than no card. The prompt says when to pass `keep` in eight lines with two worked
examples, one kept and one not, and it says to read `kept` before writing a word about the
dashboard.

**The tool call id is the identity of a kept card.** The turn row does not exist yet while the
tool runs, so `source_turn_id` stays null there and `source_call_id` is the whole key:
`dashboard.keep_chat_chart` looks a card up by `(profile_id, source_call_id)`, which is what
makes a kept chart stored once, Add to dashboard on the same chart find the card the agent
already made, and the pins endpoint report it after a reload. The table's own
`UniqueConstraint(source_turn_id, source_call_id)` cannot do that job, because SQLite counts two
NULL turn ids as different rows; the uniqueness is therefore in that one function, and the
constraint is left as the second lock it always was. `POST /charts/from-turn` fills the turn id
in when it is the one that stores the card.

**Five tools manage the cards from a chat**, all profile-scoped, all with docstrings in the
ticket 42 style: `dashboard_charts` (the list, with the id each chart is named by),
`show_dashboard_chart`, `edit_dashboard_chart`, `rename_dashboard_chart` and
`remove_dashboard_chart`. An id the model invented comes back as a `ModelRetry` naming the ids
that do exist, so the next call is right rather than the user reading an error. The two tools
that answer with a chart answer with `dashboard.card_chart`, which is the card's statement run
through the guard just now, in the shape the `chart` tool returns, so the card in the transcript
is the same component and the figures are today's.

**An edit is a change to a chart, not a new chart.** `run_chart(previous=...)` hands the planning
pass the version on the dashboard (title, plan, statement) through
`chart.subagent.previous_hint`, and the pass is told to change what the request names and keep
the rest. That is the only prompt this ticket grew, and only an edit carries it.

**Apply at once, one Undo deep.** `previous_json` holds the version a change replaced plus the id
of the tool call that made the change, and `removed_at` is the removal; both are new columns
through `db.NEW_COLUMNS`. `POST /api/dashboard/charts/{id}/undo` restores that version and clears
`removed_at`, which is one operation for an edit, a rename and a removal, and a second Undo is a
409 the card reads as "Undone". The call id is what the endpoint is told to undo, so a card whose
chart changed again is refused rather than rolling the newer change back. Removal on the page is
the same soft removal without a stash: that button asks for a confirmation first, and a previous
version left behind would let an older card in some transcript restore the wrong thing.

**The range narrows the view, not the statements.** `execute_read_only(since, until)` writes the
two days into the temp view's WHERE next to the profile id, inlined as ISO days from `date`
objects the API parsed first (`from` and `to`, 422 when they read backwards or are not days).
Every card and both tile statements go through it unchanged, and because `LATEST_DAY` reads
`MAX(booked_on)` of that same narrowed view, "this month" and "the last twelve months" follow the
range's end: a range ending in June makes the tiles say June 2025 and the doughnut the three
months before it. The response carries the range that was applied and the profile's first and
last booking day, which is what bounds the presets and what "All · 01.01.2025 to 28.12.2025"
says. Nothing about it is stored: it lives in the route's search params (`validateSearch` keeps
only ISO days) and in the React Query key.

**The dashboard is an overview.** The Add line, the preview card, `POST /charts/preview` and
`POST /charts` are gone with their frontend functions and their test; `run_chart` is called from
the chat and nowhere else now. What is left on a card is rename, move, refresh and remove. The
page hint and the empty state both point at chat, and the empty state has a button that opens
one.

**The chat chart card tells the two kinds apart.** It reads "On the dashboard" with a Remove next
to it, from the tool's own `kept` while the turn is live and from the pins endpoint after a
reload. The pins now carry the card id next to the call id, because such a card can also take the
chart off again, and after a reload the call id is all it knows about itself.

### Tests

Nine new at the HTTP seam in `tests/test_dashboard.py`, all with the scripted FunctionModel: a
kept chart stored once, reported by the pins and found again by Add to dashboard; a chart the
agent did not keep and a chart that was never drawn, neither stored; the list and the show tools;
an edit that keeps its position and its previous version, whose planning prompt is asserted to
carry the version it changed, undone once and refused with 409 the second time; a rename and a
removal from a chat, each undone, with the positions renumbered and restored; a range that
narrows the tiles to its own last month and every card to its days, including a refresh; and a
reversed range and a word instead of a day, both 422.
`test_a_chart_asked_for_on_the_dashboard_is_previewed_before_it_is_kept` became
`test_the_page_no_longer_draws_a_chart_of_its_own`, which holds the two removed routes to being
gone. The two tests that stored a card through `POST /dashboard/charts` now call
`dashboard.keep_chat_chart` directly, which is also where the guard refusal is asserted now.

The chat prompt grew 408 tokens (3919 to 4327 in the app's own estimator). The floor a compressed
prompt cannot go below, measured the way `tests/test_context.py` describes, is 5235 of the
`BUDGET = 5700` that test runs at, so the headroom is down from 18 to 8 percent. The next prompt
growth has to move that number.

### Verified on OpenRouter (gemini-3.8-flash on both slots), port 8163, throwaway database, session `ticket44`

A fresh profile through onboarding with "Load the sample year" (433 rows, 25 needing review),
then, in both themes at 1440:

- The dashboard with its range bar, the four defaults and the tiles (`01`), and the range: "Last
  3 months" (`02`, four months on the line, the merchants of those months, 8 needing review),
  "This month" (`03`, one row on the line, the doughnut's total equal to the Spent tile to the
  cent, 3 needing review) and a custom 01.03. to 30.06. (`04`, tiles on June 2025, Shopping in
  the doughnut where Cash and Health were). The URL carries the range each time.
- "I want to track my spending on groceries per month over 2025." The agent kept it: the card
  reads "On the dashboard" with Remove, and the answer's second line says so (`05`).
- "Show me a chart of what I spent per day at Edeka in March 2025." Not kept: "Add to dashboard",
  and the answer says nothing about the dashboard (`06`).
- A full reload: the kept card still reads "On the dashboard", the one-off still "Add to
  dashboard" (`07`), which is the pins path with a null turn id.
- "What is on my dashboard? Show me the groceries one." The five titles listed, and the card
  drawn in the answer with "On the dashboard" under it (`08`, `09`).
- "Make the groceries chart on my dashboard a bar chart." The card comes back as bars with
  "Changed on the dashboard" and Undo (`10`), and the dashboard's fifth card is bars in the same
  place (`11`). Undo: the card reads "Undone" (`12`) and the dashboard is a line again (`13`).
- "Take the groceries chart off my dashboard." A line with an Undo (`14`), the card gone from the
  page, then Undo, after which the line reads "Undone", the older edit card reads "Undone" too,
  and the card is back at position 4 as the line the edit had been undone to (`15`).
- Remove and then Add to dashboard on the chat card itself: off the page, then back at position 4
  as the same row rather than a second one (`19`).
- Both themes (`16`, `17`) and a second, empty profile's dashboard: tiles at zero, no cards, and
  "This dashboard is empty. Ask for a chart in a chat; the ones worth keeping land here." with a
  button into a chat (`18`).

Zero browser console messages and zero page errors, and 562 requests in the server log with no
4xx and no 5xx. Screenshots: `/tmp/finquery-44/`.

### Two bugs found in that session and fixed

- **A dashboard tool card kept the running card's open details.** Both branches of
  `DashboardChartToolStep` put a `Footer` at the same position in the tree, so React kept its
  state and the drawn card inherited the "open" the running card sets on itself. The two are
  keyed now. The chat's own chart card never had this, because its two branches are different
  components.
- **A second change to one chart read the first card's cached answer.** Both cards asked
  `dashboard-chart` under the same key, and the edit card's Undo had written its own result
  there, so the removal line said "Undone" while its Undo still applied (a reload showed it
  correctly). The query is keyed by the change it is about now, and an Undo invalidates every
  card of that chart rather than writing to one.

### Left, seen in passing

- The two native date fields could not be driven by the automation harness: synthetic key events
  do not reach `<input type="date">` and this session had no `eval`. What was verified is the
  path the fields write (the search params, from the presets and from a hand-built URL) and the
  fields rendering the applied range; one `fill` that emptied the from field did reach React and
  the page re-queried with an open start, which is the field-to-URL direction. Ticket 46 replaces
  the pair with the shared picker anyway, and the component here already has that name, that file
  and that prop shape (`{ from, to, onChange }` over ISO days, empty for an open end).
- `dashboard_charts` renders no card in the transcript on purpose: the answer names the charts,
  and a list card would be a second copy of it. If a later ticket wants one, it is a component,
  not a wire change.
- One stray navigation into the review conversation happened during the session (a tab that was
  on the dashboard was on `/c/...` a moment later). Nothing in the log or the console goes with
  it and it did not recur; most likely a mis-click of the Needs review tile's link by the
  automation.
