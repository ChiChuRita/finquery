# 27: UI and UX refinement pass across every page and component

**What to build:** Walk every page and every flow as a first-time user in a real browser and refine the experience: discoverability, affordances, flow friction, copy clarity, empty, loading and error states, keyboard use, confirmation and undo patterns, what the user sees while waiting, and how each tool step, card and page explains itself. Ticket 26 owns spacing and visual consistency and ticket 25 owns chart internals; this ticket owns how things work and read. Requested by the user on 2026-09-05.

**Blocked by:** 24 (merged)

**Status:** ready-for-agent

- [ ] A written walkthrough as a first-time user of the full demo path (new profile, drop a CSV in chat, answer Question cards, ask questions, chart, changeset, split from a bill photo, memory in a second conversation, model switch, stop, compression, thumbs and Regenerate, web lookup, Imports overview, Transactions, Memory, Feedback, Settings) with a friction list: every moment of confusion, dead end, missing affordance, unclear copy, or wait without feedback
- [ ] Fixes for the friction list at the source: flow changes (what happens next after an import, after a card, after Apply), affordances (what is clickable, what is pending, what is done), copy (titles, notes, empty states, buttons, tooltips, error messages in plain language, real plurals, one date and money format), loading and streaming feedback (what the user sees during a two-minute PDF extraction or a long Qwen turn), keyboard (Enter to send, Escape to cancel, focus management in dialogs and cards), confirmations only where they earn their place, undo where it is cheap
- [ ] Every tool step and card explains itself in one line to someone who did not read the spec (query, chart, changeset, question, import, lookup, memory, set_rule, review_batch, duplicates, extraction review)
- [ ] Empty states on every page say what to do next and offer the action; error states say what went wrong and what to try
- [ ] Before and after screenshots of each fixed moment in both themes; behaviour changes covered by HTTP-seam tests where the server changed; typecheck, build and suite green; zero console messages
