# 34: AI Elements adoptions from the audit

**What to build:** The AI Elements audit of 2026-09-05 (../ai-elements-audit-2026-09-05.md) checked all 48 components against the app. Adopt the three that add value before Monday, and record the deliberate rejections so nobody re-litigates them.

**Blocked by:** 33 (touches the transcript renderer)

**Status:** ready-for-agent

- [ ] `attachments`: the composer's attachment chips and the stored attachment chip on the user message use the AI Elements attachments component (image thumbnails for photos, file chips for CSV and PDF, remove action in the composer); `npx ai-elements@latest add attachments`; zero new dependencies
- [ ] `chain-of-thought` inside the chart card's details only: the sub-agent's plan and repair rounds render as steps with complete, active and pending status on the icon rail while the chart is being made, and stay as a completed chain afterwards; the query, chart, changeset and question cards themselves stay as they are (they are the audit trail and must not collapse behind one toggle); `npx ai-elements@latest add chain-of-thought`
- [ ] `ConversationDownload` (already vendored, unused): a download action in the conversation header with a formatMessage that writes tool steps, cards and figures as readable markdown, not only text parts
- [ ] Never re-run `add` for an already vendored component: context, tool, message, model-selector, reasoning and sources carry local edits; add a one-line note to README's AI Elements paragraph
- [ ] Recorded as rejected with the reason in the audit: agent (no status or controls), MessageBranch (one branch at a time, our pairs are side by side), task (no status icons in source), checkpoint, confirmation, code-block, plan, artifact, sandbox, web-preview, open-in-chat (against local-first), jsx-preview (breaks the sandbox), speech-input (posts audio off the machine), the xyflow family
- [ ] Typecheck and build clean, suite green, browser verification in both themes of an image and a CSV attachment in the composer and on the message, and a chart's plan as a chain of thought while it runs
