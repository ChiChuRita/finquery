# 34: AI Elements adoptions from the audit

**What to build:** The AI Elements audit of 2026-09-05 (../ai-elements-audit-2026-09-05.md) checked all 48 components against the app. Adopt the three that add value before Monday, and record the deliberate rejections so nobody re-litigates them.

**Blocked by:** 33 (touches the transcript renderer)

**Status:** done

- [x] `attachments`: the composer's attachment chips and the stored attachment chip on the user message use the AI Elements attachments component (image thumbnails for photos, file chips for CSV and PDF, remove action in the composer); `npx ai-elements@latest add attachments`; zero new dependencies
- [x] `chain-of-thought` inside the chart card's details only: the sub-agent's plan and repair rounds render as steps with complete, active and pending status on the icon rail while the chart is being made, and stay as a completed chain afterwards; the query, chart, changeset and question cards themselves stay as they are (they are the audit trail and must not collapse behind one toggle); `npx ai-elements@latest add chain-of-thought`
- [x] `ConversationDownload` (already vendored, unused): a download action in the conversation header with a formatMessage that writes tool steps, cards and figures as readable markdown, not only text parts
- [x] Never re-run `add` for an already vendored component: context, tool, message, model-selector, reasoning and sources carry local edits; add a one-line note to README's AI Elements paragraph
- [x] Recorded as rejected with the reason in the audit: agent (no status or controls), MessageBranch (one branch at a time, our pairs are side by side), task (no status icons in source), checkpoint, confirmation, code-block, plan, artifact, sandbox, web-preview, open-in-chat (against local-first), jsx-preview (breaks the sandbox), speech-input (posts audio off the machine), the xyflow family
- [x] Typecheck and build clean, suite green, browser verification in both themes of an image and a CSV attachment in the composer and on the message, and a chart's plan as a chain of thought while it runs

## What was built

The rejected list, with a reason per component, is the "Rejected, and why" table in
`../ai-elements-audit-2026-09-05.md`, next to the full 48-row table it is drawn from.

**`attachments`.** `composer.tsx`'s `AttachedFiles` renders the inline variant: a photo by a
thumbnail with a hover card holding the picture at readable size, a CSV or a PDF by its icon,
each with the name and a remove button that stays visible (the library hides it until hover,
which a touch screen never reaches). Every rule about what the box takes and every refusal
sentence stays in `prompt-input`. `chat-view.tsx`'s `MessageAttachments` draws the stored files
of a message as one row rather than one chip per part: photos as 96 px thumbnails in the grid
variant, documents as chips, each a link to the copy the server stored.

**`chain-of-thought`.** `chart-tool.tsx`'s Footer replaces the plan paragraph and the "Repairs"
list with `chartSteps`: planned, queried, wrote, one step per repair round, checked. The words
are the ones the sub-agent narrates (`chart/runner.py`). A chart still being made now has the
same details, open by itself, with the first step active and the rest pending; the card above it
is unchanged.

**`ConversationDownload`.** In the chat header next to the context badge, with
`lib/transcript-markdown.ts` as its `formatMessage`: query steps with their SQL and row counts,
chart titles with the plan and the SQL, changeset previews with their status and rows, question
cards with the answers given, import summaries, attachments as links, and the answers.

**Two things found on the way.**
`npx tsc --noEmit` in `frontend/` checks nothing: `tsconfig.json` is a solution file with
`"files": []`, so the only real typecheck is `npm run build` (`tsc -b`). The README said the
former; it now says the latter, and two type errors it had been hiding are fixed.
"Load the sample year" stored its CSV chip as `/api/attachments/None`: `attachments.store`
returned a record that had not been flushed, so it had no id yet. Fixed in `store` rather than
in the caller, and `tests/test_onboarding.py` now fetches the chip's URL.
