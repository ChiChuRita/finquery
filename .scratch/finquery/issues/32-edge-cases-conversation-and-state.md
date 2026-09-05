# 32: Edge cases, conversation and state

**What to build:** Hunt for edge cases in conversation flow, persistence and UI state, fix each at the root with a test, and polish what the user sees. Includes ticket 29 (a Question card answered after a newer message) and the two leftovers of ticket 30 (the import step's counted sentence repeated in prose; the resumed half of a card turn listing the merchants it just applied). Requested 2026-09-05.

**Blocked by:** 30 (merged)

**Status:** ready-for-agent

Cases to cover at least (add what you find):
- Cards: answering a card after a newer message (ticket 29), answering the same card twice, answering with free text only, skipping every row, a card whose merchant was recategorized meanwhile, a duplicate card after the import was deleted, a mapping card after the attachment was deleted
- Turns: Stop during thinking, during a tool call, during the follow-up step; server restart while a turn runs (the turn is marked interrupted on next load, the UI recovers without a stuck spinner); two tabs on the same conversation; reload during streaming; the model returning nothing; a tool raising; the follow-up and distillation steps failing (never visible to the user)
- Compression: cross the threshold twice; edit the summary to empty (422) and to 4000 characters; a conversation whose every turn is a card; compression on a conversation with attachments
- Memory: the same fact in two languages, a contradicting fact (the newer wins or both shown), 200 memories (selection cap and page performance), deleting a memory used in the open conversation
- Conversations and tabs: rename to empty or 500 characters, delete the open conversation, delete a conversation open in another tab, switch profile while streaming, 30 open tabs, a tab pointing at a deleted conversation on reload, browser back and forward through conversations
- Models: switch slot while streaming, the quality slot unavailable (503 shown as a sentence), onboarding default slot honoured on new conversations
- Keyboard: Enter sends and Shift Enter breaks a line; Escape cancels dialogs and inline edits; focus returns to the composer after a card answer
- Polish: the two ticket 30 leftovers; any text that still restates counts twice; any place where a pending state has no spinner or a finished state keeps one

- [ ] Each case tried through the real product and recorded in a table with outcome before and after
- [ ] Every defect fixed at the root with an HTTP-seam test; ticket 29 closed; suite green; typecheck and build clean; zero console errors during the browser runs
