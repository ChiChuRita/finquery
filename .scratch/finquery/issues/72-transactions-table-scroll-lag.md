# 72: Transactions table lags when scrolling

**What to build:** The user feels a delay when scrolling the Transactions table (2026-09-07).
Measured on the sample year (433 rows, one page of 500, so no network in play) at 1440x900
with a scripted scroll of 120px per frame across the whole table: 50 ms per frame, worst 63,
33 rows mounted, 43 DOM nodes per row, 1,426 nodes in the table. Sixty frames a second needs
16 ms. TanStack Table and TanStack Virtual are headless and have no renderer to switch to; the
cost is in what each row mounts.

**Blocked by:** 70, 71 (done)

**Status:** done

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

- [x] Before and after with the same scripted scroll (script in Comments), same viewport, same
      data, both numbers in Comments
- [x] Picking a category on a Needs review row and on a categorized row still saves (ticket 71
      regression check), keyboard opening works, the subcategory picker still follows the category
- [x] `npm run build` clean, lint at or below 36 warnings

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

After (same script, same viewport and data, rebuilt bundle, two runs): rows 33, nodes 1,340,
nodesPerRow 41, msPerFrame 17 then 16, worstFrameMs 24 then 18. Sixty frames a second is 16.7 ms,
so the scripted scroll now runs at the display's ceiling; before it ran at about twenty frames a
second.

What changed:
- `transaction-cells.tsx`: `PickerCell` renders a plain `button` styled with the closed
  trigger's exact classes (copied from `ui/select.tsx`, `data-size="sm"`) and the same chevron.
  The Radix `Select` is mounted only after a click or keyboard activation, controlled `open`,
  and unmounted when it closes; focus is handed back to the button because Radix would return
  it to a trigger that no longer exists. The popper anchoring from ticket 71 stays.
- `transactions-table.tsx`: the subcategory choices are one `Map` built once per categories
  load instead of a `find` plus a fresh array per row render; `categories` left the columns'
  dependency list.

Regression checks in the browser after the change (port 8095, sessions `ticket72` and `vr5`):
a Needs review row (LEA HOFFMANN) took Dining with one PATCH and reads Dining from the API; a
categorized row (DOENER HAUS) took Shopping with one PATCH, its Subcategory reset to the dash and
its picker offers Shopping's four subcategories; focusing a category button and activating it
opens the list, Escape closes it and focus is back on the same button. Rendering at the top of
the table is unchanged (`/tmp/finquery-72/after/top-final.png` against
`/tmp/finquery-72/before/top.png`). Build clean, lint 36 warnings, `tsc -b` clean.

The implementation was started by a sub-agent that was cut off twice (a rate limit, then a
stall); its diff was complete and was verified and committed by the orchestrator.
