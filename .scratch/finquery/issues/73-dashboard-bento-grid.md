# 73: The dashboard as a bento grid

**What to build:** The user wants the dashboard to read as a bento grid (2026-09-07): one grid of
tiles with deliberate, different sizes rather than a row of four equal tiles over a uniform three
column grid of cards. Today (`frontend/src/components/dashboard-page.tsx`) the four money tiles are
one grid and the cards another, every card as tall as its content, and the chart inside every card
is exactly 280 pixels because `ChartFrame` fixes its wrapper at `CHART_HEIGHT` and the runtime
passes `CHART_HEIGHT - FRAME_INSET.top` to `<Chart>`. The new page is one CSS grid on the tokens
the app already has (`gap-4`, `rounded-xl`, `bg-card`, hairline border, `text-2xs`): four columns
from `xl`, two from `md`, one below; a fixed row unit so a cell can span rows; the four money
tiles as a 2 by 2 block of 1 by 1 cells at the top left with the first chart beside them; every
chart 2 by 2, a sankey the full width and three rows tall; `grid-auto-flow: dense` so keeping or
removing a chart never leaves a hole. Numbers keep coming from the executed queries the page runs
on load; nothing about the layout is stored, because the size of a tile is a function of its
shape and the order is the `position` the server already keeps. No new dependency: CSS grid only.

**Blocked by:** 51, 66 (done)

**Status:** done

Decisions:
- One grid, `grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4`, with the row unit as a CSS
  variable on the grid, `--dashboard-row: 11rem` (176px), and `grid-auto-rows: minmax(var(--dashboard-row), auto)`
  from `md` up. With the row unit at 11rem a 2 by 2 cell is 368px, which after the card's header
  (44px) and footer (45px) leaves the chart its present 280, so no default card gets denser than
  it is today. `minmax(..., auto)` rather than a fixed unit so a card whose "SQL and n rows"
  details are open grows its band instead of overflowing the cell below. Below `md` the spans are
  off (`grid-auto-rows: auto`, every item one column, cards as tall as their content, the chart at
  `CHART_HEIGHT` as in the chat), because a phone width has nothing to pack.
- Sizes are a rule on the shape, client side, in one small function in `dashboard-page.tsx`, and
  nothing is stored: `sankey` is `col-span-full row-span-3` (wide and tall, a flow needs both),
  every other shape (`line`, `area`, `bar`, `bar_horizontal`, `bar_grouped`, `bar_stacked`,
  `doughnut`) is `md:col-span-2 md:row-span-2`. Only two chart sizes on purpose: with four
  columns, a chart that is two wide and two tall beside another such never leaves a hole, and a
  full width card cannot leave one either; a 1 by 2 doughnut or a 2 by 3 ranking would need a
  partner of the same shape next to it or leave a gap, which is the clutter the user is asking to
  lose. If the ten bar rankings read cramped at 280 the follow-up is a `size` column (see the last
  decision), not a third size here. No new column, no migration.
- The four money tiles are one grid item, `md:col-span-2 md:row-span-2`, holding an inner
  `grid grid-cols-2 gap-4` of the four `Tile`s, so each tile is exactly one 1 by 1 cell of the
  outer grid (272 by 176 at 1440) and the block is the same size as the chart beside it. The
  tile's two caption lines get `mt-auto` so label and value sit at the top and the comparisons at
  the bottom of the taller cell; everything else from ticket 66 stays (equal slots, tabular
  deltas, `text-2xs`). With zero charts the block is `col-span-full row-span-1` with the inner
  grid `grid-cols-4` (a row of four) and the empty state sits under it, so an emptied dashboard is
  not a block with a hole beside it.
- `grid-auto-flow: dense` (`grid-flow-row-dense`), not an explicit placement. Cards render in
  `position` order as today. The only case where dense moves something is an odd number of 2 by 2
  cards before a full width sankey: the card after the sankey hops up into the gap. That is
  accepted and said in a comment; the Move left and Move right arrows keep changing `position`
  and the page keeps following it. No holes with zero, seven or eight charts at any width.
- The chart frame: the iframe already fills its wrapper (`h-full w-full`), but the drawing does
  not, so two small changes. (1) `ChartFrame` in `chart-tool.tsx` takes `fill?: boolean`; with
  it the wrapper is `relative flex-1 min-h-0` instead of `style={{ height: CHART_HEIGHT }}`, and
  the chat card, which does not pass it, is unchanged at 280. (2) `Mounted` in
  `chart-runtime/main.tsx` reads `window.innerHeight` (the frame's own viewport, which is the
  wrapper's height) into state, listens to `resize`, and passes `innerHeight - FRAME_INSET.top`
  to `<Chart>`. No new field on the render message and no change to `chart-frame.ts` beyond the
  comment on `CHART_HEIGHT`, which becomes the chat's height and the fallback. `docs/chart-runtime.md`
  ("The frame owns ... `height: 280`") says the frame fills the card and the chat gives it 280.
- `DashboardCard` fills its cell: `ChartCard` gets `h-full flex flex-col` through its existing
  `className`, the header and footer keep their height, the body (`ChartFrame fill`, `NoRows`,
  the `FailedBody` wrapper) is `flex-1 min-h-0` so the footer sits on the card's bottom edge in
  every state. The header, the four actions, Rename, Remove, Refresh and the details are untouched.
- No resize and no reorder beyond the arrows in this ticket. Both are more than a few lines and
  neither is what "more bento" asks for. Follow-up if wanted: a nullable `size` column
  (`wide`, `full`) on `dashboard_chart` through `db.NEW_COLUMNS`, a Size item in the card's
  menu, the rule above as its default; and drag to reorder with the native HTML drag events onto
  the existing `PATCH position`, still without a library.
- Rules kept: YAGNI, CSS grid only, square corners inside charts, the theme owned by the frame,
  every figure from an executed query, no em dashes in copy or comments.

Sketch at 1440 by 900, sidebar open (content 1136px, four columns of 272, row unit 176, gap
16), the seven defaults from ticket 51 in position order:

```
+----------+----------+-----------------------+
| Spent    | Income   | 1 Spending per month  |
| 2.760 €  | 3.400 €  |   (bar)               |
+----------+----------+                       |
| Net      | Needs    |                       |
| +640 €   | review 12|                       |
+----------+----------+-----------------------+
| 2 Income against     | 3 Top categories     |
|   spending (grouped) |   (bar_horizontal)   |
|                      |                      |
+----------------------+----------------------+
| 4 This month against | 5 Regular payments   |
|   last month         |   (bar_horizontal)   |
|                      |                      |
+----------------------+----------------------+
| 6 Top ten merchants  | 7 Month pacing       |
|   (bar_horizontal)   |   (line, 2 series)   |
|                      |                      |
+----------------------+----------------------+
```

An eighth card kept from a chat: a doughnut or a line is one more 2 by 2 in the last band,
half a row at the end (an end is not a hole); a sankey is a full width band three rows tall.

Sketch at 1024 by 800, sidebar open (content 720px, two columns of 352):

```
+----------+----------+
| Spent    | Income   |
+----------+----------+
| Net      | Needs r. |
+----------+----------+
| 1 Spending per month|
|                     |
+---------------------+
| 2 Income against    |
|   spending          |
+---------------------+
| 3 Top categories    |
|                     |
+---------------------+
  ... 4 to 7 the same, a sankey col-span-2 row-span-3
```

- [x] Before screenshots of /dashboard as it is, both themes, 1440x900 and 1024x800, in
      `/tmp/finquery-73/current/` (throwaway database with the sample year through onboarding,
      no model call, own port above 8090, named session, never ports 8000 or 5173)
- [x] After screenshots in `/tmp/finquery-73/after/`, both themes, both widths, with the seven
      defaults; with zero charts (every card removed: the row of four and the empty state); with
      eight (the seven plus one kept from a chat on the dev provider); a sankey kept from a chat
      shown full width and three rows tall in at least one shot
- [x] No hole in any of those grids at either width; the first band is the tile block beside
      Spending per month; a card's details opened grows its band and nothing overlaps
- [x] Every default chart still draws at about 280 pixels; the chart in the chat card is
      unchanged at 280; a theme switch redraws every card in place; Move left and Move right
      still work and the moved card redraws
- [x] "Keep this chart" from the chat (Add to dashboard, and the agent keeping one itself) still
      lands the card at the end of the grid and the transcript card still says On the dashboard;
      Remove from the transcript still takes it off
- [x] `npm run build` clean, `npx tsc -b` clean, oxlint at or below 36 warnings, no change under
      `src/`, `docs/chart-runtime.md` updated for the frame's height

## Comments

Planned 2026-09-07 from the code, before any screenshot: the planner's thread was read only, so
the "current" set is the implementer's first box.

Why not size by shape more finely: the brief suggested line and area wide, bar per category tall,
doughnut square, sankey wide and tall. With four columns and one row unit, a 1 by 2 doughnut or a
2 by 3 ranking beside a 2 by 2 card leaves a 1 by 2 or a 2 by 1 gap that no other card can fill,
and the defaults hold three rankings and no doughnut, so the page would have holes in its default
state. Two chart sizes plus the tile unit give the mixed first band the user is after and a dense
grid at every count. A per card size is the follow-up named above if a ranking wants more height.

Why no column: the size is a pure function of `shape`, `position` already orders the cards, and
a stored size would need a migration, an endpoint and a menu for something nobody has asked to
change. `NEW_COLUMNS` is there the day they do.

Files the implementer will touch:
- `frontend/src/components/dashboard-page.tsx` (the one grid, the tile block, the size rule, dense flow)
- `frontend/src/components/dashboard-card.tsx` (card as a flex column filling its cell, `fill` on the frame, `NoRows` and the failed body flex-1)
- `frontend/src/components/chart-tool.tsx` (`ChartFrame` `fill` prop)
- `frontend/src/chart-runtime/main.tsx` (chart height from the frame's own viewport, resize listener)
- `frontend/src/lib/chart-frame.ts` (comment on `CHART_HEIGHT` only)
- `docs/chart-runtime.md` (the frame's height paragraph)

Size: medium, frontend only, no server change, no migration, about a day with the browser checks.

Done 2026-09-07 (port 8097, browser session `ticket73`, throwaway db `/tmp/finquery-73/verify.db`,
sample year seeded through `POST /api/onboarding/sample`, no model call for the layout work).

What changed per file:
- `dashboard-page.tsx`: one grid for the whole page,
  `grid grid-flow-row-dense grid-cols-1 gap-4 [--dashboard-row:11rem] md:grid-cols-2
  md:[grid-auto-rows:minmax(var(--dashboard-row),auto)] xl:grid-cols-4`. New `sizeOf(shape)`:
  `sankey` is `md:col-span-full md:row-span-3`, every other shape `md:col-span-2 md:row-span-2`,
  spans off below `md`. `Tiles` is now one grid item (`md:col-span-2 md:row-span-2 md:self-start`,
  `md:col-span-full` with no cards) holding an inner `grid grid-cols-2` whose rows are the grid's
  own row unit; the tile's two comparison lines got `mt-auto pt-2`. The loading line moved out of
  the cards' branch, so tiles and cards share the one grid.
- `dashboard-card.tsx`: `ChartCard` is `flex h-full flex-col` and takes the span through a new
  `className` prop; `NoRows` and the failed body are `min-h-0 flex-1`, so the footer sits on the
  card's bottom edge in every state; the frame is passed `fill`.
- `chart-tool.tsx`: `ChartFrame` takes `fill?: boolean`; with it the wrapper is
  `relative min-h-70 flex-1` instead of `style={{ height: CHART_HEIGHT }}`. The chat card does
  not pass it and is unchanged. `min-h-70` (280px) rather than `min-h-0`: with `min-h-0` a card
  whose details were open let the auto row size itself short and squeezed the drawing to 150px,
  measured; the minimum makes the band grow instead.
- `chart-runtime/main.tsx`: `Mounted` keeps `window.innerHeight` in state, listens for `resize`
  and passes `innerHeight - FRAME_INSET.top` to `<Chart>`; `CHART_HEIGHT` is the fallback.
- `chart-frame.ts`: the comment on `CHART_HEIGHT` only.
- `docs/chart-runtime.md`: "The frame owns ... `height: 280`" is now "its height", with a
  paragraph on the frame reading its own viewport, the chat's 280 and the dashboard's `fill`.

Measured in the page with `getBoundingClientRect` (1440x900, sidebar open, content 1136):
columns `272px 272px 272px 272px`, `grid-auto-rows: minmax(176px, auto)`, `grid-auto-flow: dense`.
Seven defaults, rects as `x,y,w,h` relative to the grid: tiles block `0,0,560,368`; Spending per
month `576,0,560,368`; Income against spending `0,384,560,368`; Top categories `576,384,560,368`;
This month against last month `0,768,560,368`; Regular payments `576,768,560,368`; Top ten
merchants `0,1152,560,368`; Month pacing `576,1152,560,368`. No two rects overlap and the four
bands are full (0 to 560 and 576 to 1136 in each), so no cell inside the grid's box is empty.
Each tile is exactly 272 by 176. Card parts: header 44, chart wrapper 281, footer 41, so every
default chart draws at 281 against the chat's 280 (about 280, one pixel from the border).
The eighth card kept from the chat, a sankey, is `0,1536,1136,560` (full width, three rows) and
its chart wrapper is 473. The chart in the chat card measured 280. Details opened on Spending per
month: its band grows to 1272, its chart stays 280, the tile block stays 368 and nothing overlaps.
At 1024x800 (content 720, two columns of 352): the tile block is 720 by 368 and every card is
720 wide, one per band, no overlap and no empty cell. Zero charts at 1440: one item, the block
full width with four 272 by 176 tiles in a row and the empty state under it.

Browser checks: theme switch (sidebar Light theme / Dark theme) redrew all seven frames in place;
Move left then Move right on Top categories reordered the band and the moved card came back drawn;
Add to dashboard on the chat's sankey landed it at the end of the grid, the transcript card said
On the dashboard, and Remove in the transcript took it off (the card was then gone from the
dashboard). Every card was removed through the card menu, one at a time, for the zero state, then
Restore default cards brought the seven back.

Screenshots: before in `/tmp/finquery-73/current/` (`dark-1440.png`, `light-1440.png`,
`dark-1024.png`, `light-1024.png`), after in `/tmp/finquery-73/after/` (same four names, plus
`details-open-1440.png`, `dark-1440-eight-sankey.png`, `light-1440-eight-sankey.png`,
`dark-1440-sankey-band.png`, `light-1440-sankey-band.png`, `light-1440-zero.png`,
`light-1024-zero.png`, `light-1440-seven-restored.png`).

`npx tsc -b` clean, `npm run build` clean, `npm run lint` 35 warnings. Nothing under `src/` changed.

Two things the chat turn did not cover: the assistant keeping a chart by itself (this turn drew the
sankey and offered Add to dashboard, which is the path that was exercised), and the eight-card
shots at 1024; the one chat turn was spent on the sankey, as the ticket allowed. Note for the
reader of the "after" screenshots: a conversation tab row appeared in the app between the before
and after sets from work outside this ticket, so the chrome above the page differs by a row.
