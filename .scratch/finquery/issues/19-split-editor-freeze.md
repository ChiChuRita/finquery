# 19: Transactions page freezes when adding a split leg after an inline edit

**What to build:** On the Transactions page, editing a cell inline and then expanding that row and clicking Add a leg pegs a core and freezes the page with no console error. Reproduced on the ticket 04 commit itself. The likely cause is the virtualizer re-measuring the expanded row while its height changes and oscillating against the offsets it feeds back. The page must stay responsive through inline edits, expansion and leg editing in any order.

**Blocked by:** 04 Transactions page (merged)

**Status:** done

- [x] Root cause found: it is not in FinQuery. No render loop exists; the freeze belongs to the
      browser automation harness, and no app code needed changing
- [x] Browser verification: inline edit, expand, add and remove legs, save, reset, remove the
      split, collapse, repeated in both orders on several rows, with CPU staying idle
- [x] Existing transactions tests still pass; there is nothing to regression-test at the HTTP
      seam and nothing to regression-test in the browser either, since the app never looped

## Comments

Investigated 2026-09-04. The premise is wrong: the virtualizer never loops, and no line of
FinQuery is at fault.

- The freeze reproduces: 130 to 150 percent across the browser and renderer processes, matching
  the reported 145 percent, and the page stops answering.
- It is not a render loop. `agent-browser react renders` captured zero renders while the core
  was pegged, so React was not re-rendering at all and `measureElement` was not firing.
- A Chrome trace named it. In three seconds the renderer took 26431 `InputLatency::RawKeyDown`
  events, all trusted, `key: "Unidentified"`, `repeat: false`, targeted at `BODY`, about 5000 a
  second. `jsEventListeners` climbed past 33000 on a page of 3260 nodes, because Radix's `Menu`
  registers one document keydown listener per instance and each of those adds two `once` pointer
  listeners per keydown. That listener pile is what turns a single keydown into 43 ms of work and
  the storm into a freeze, but it is a consequence, not the cause.
- The cause is the key event source. `agent-browser press Enter` (0.27.0, Chrome for Testing 152)
  never stops dispatching when the focused input calls `blur()` inside its own keydown handler,
  which is what `transaction-cells.tsx` does for Enter. A twenty-line static HTML page with one
  input, no React, no virtualizer and no FinQuery code reproduces the same 110 to 138 percent
  storm (`/tmp/finquery-19/repro.html` and `blur-only.html`, served on 8092). Removing the DOM
  node is not needed; the `blur()` alone is enough. `agent-browser keyboard type` with a newline
  storms the same way, so it is the harness's key delivery, not one command. The agent-browser
  daemon sits at 0.0 percent CPU throughout while the browser process burns 87, so the loop lives
  below the client.
- Ticket 04's own verification hit this and read the symptom as a virtualizer measure loop. It
  never was one. Anyone verifying an inline cell in the browser should save by clicking away
  rather than by sending Enter, or they will freeze the harness and blame the page.
- One measurement trap worth naming: several chrome-for-testing instances run on this machine at
  once, one per agent session. A `top` on the wrong renderer reads another agent's work. Read
  `~/.agent-browser/<session>.pid`, take the browser process whose parent is that daemon, and sum
  that tree.
- What was verified, with CPU idle (under 1 percent) after every single action: inline edit saved
  by blur and saved through the app's Enter path, expand, add a leg, add a second leg, edit leg
  amounts, the empty-description refusal shown in place, save the split and the badge appearing,
  remove a leg, reset, remove the split, collapse, and scrolling the virtualizer with a row
  expanded. Both orders (edit then expand, expand then edit) on rows 0, 3 and 4 of the 433 row
  synthetic Sparkasse import. The Enter path was driven by a synthetic `keydown` from temporary
  instrumentation, since the harness cannot deliver a real one to this page.
- No source file changed. `npx tsc --noEmit` and `npm run build` are clean and `uv run pytest` is
  55 passed, 2 skipped. Screenshots: /tmp/finquery-19/.
- Not done, deliberately: `transaction-cells.tsx` could commit on Enter directly instead of
  calling `event.currentTarget.blur()` and letting the blur handler infer the intent. That would
  read slightly better and would sidestep the harness bug, but the current code is correct and
  the bug is not ours, so it is a line here rather than a diff.
