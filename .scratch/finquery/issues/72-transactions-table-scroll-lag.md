# 72: Transactions table lags when scrolling

**What to build:** The user feels a delay when scrolling the Transactions table (2026-09-07).
Measured on the sample year (433 rows, one page of 500, so no network in play) at 1440x900
with a scripted scroll of 120px per frame across the whole table: 50 ms per frame, worst 63,
33 rows mounted, 43 DOM nodes per row, 1,426 nodes in the table. Sixty frames a second needs
16 ms. TanStack Table and TanStack Virtual are headless and have no renderer to switch to; the
cost is in what each row mounts.

**Blocked by:** 70, 71 (done)

**Status:** open

Decisions:
- Each row mounts three Radix `Select` roots (Category, Subcategory, Account) though at most
  one is open at a time. `PickerCell` (`frontend/src/components/transaction-cells.tsx`) is to
  render a plain `button` that looks exactly like the closed trigger (same classes, the name or
  placeholder, the chevron) and to mount the `Select` only after a click or keyboard activation,
  opened at once (`open` controlled, `onOpenChange` unmounting it again when it closes without a
  choice). A picked value saves as today. Focus returns to the button after closing.
- Keep the virtualizer's `measureElement`: an expanded split and a cell error line change a
  row's height. Keep `overscan: 10` unless the after-measurement says otherwise.
- No new dependency, no restructuring of the table, no change to the row grid from tickets 70
  and 71.
- Anything else found to be heavy (a hook per cell, `useMemo` churn on the columns) is fair
  game if it is a few lines; report it, do not redesign.

- [ ] Before and after with the same scripted scroll (script in Comments), same viewport, same
      data, both numbers in Comments
- [ ] Picking a category on a Needs review row and on a categorized row still saves (ticket 71
      regression check), keyboard opening works, the subcategory picker still follows the category
- [ ] `npm run build` clean, lint at or below 36 warnings

## Comments

Measurement script (run in the page with the table scrolled to the top; the scroller is the
parent of `[role=table]`):

```js
(async()=>{const s=document.querySelector('[role=table]').parentElement;
const rows=document.querySelectorAll('[role=row]').length;
const nodes=document.querySelector('[role=table]').querySelectorAll('*').length;
let frames=0,worst=0,last=performance.now();const t0=performance.now();let y=0;
await new Promise(res=>{const step=()=>{const now=performance.now();worst=Math.max(worst,now-last);last=now;frames++;y+=120;s.scrollTop=y;if(y<36*433-800)requestAnimationFrame(step);else res()};requestAnimationFrame(step)});
const total=performance.now()-t0;
return JSON.stringify({rows,nodes,nodesPerRow:Math.round(nodes/rows),frames,msPerFrame:Math.round(total/frames),worstFrameMs:Math.round(worst)})})()
```

Before (2026-09-07, headless Chromium via agent-browser, 1440x900): rows 33, nodes 1,426,
nodesPerRow 43, msPerFrame 50, worstFrameMs 63.
