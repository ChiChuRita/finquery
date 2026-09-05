# 33: Turns run in the background and survive a closed chat

**What to build:** A turn (and so an import) keeps running when the user switches conversation, closes the tab or reloads, and the user can come back and watch it. Today the run is tied to the HTTP stream: dropping the connection four seconds into a turn left nothing behind, not even the user's message (measured 2026-09-05 on the OpenRouter build). For a two-minute CSV import or a twenty-minute PDF that is a real loss.

**Blocked by:** 32 (conversation and state edge cases, touches the same file)

**Status:** ready-for-agent

- [ ] The user's message and a pending assistant turn are persisted before the model is called, so a dropped connection never loses the question
- [ ] The run is a server-side task detached from the response: the HTTP stream is one subscriber; a disconnect unsubscribes and never cancels; Stop is the only cancel
- [ ] Progress and parts are persisted as they arrive (at least at every tool boundary and every few seconds of text), so a reload mid-turn shows the turn so far with a running marker
- [ ] Reattach: useChat's resume (GET .../stream) replays what was missed and continues live; the composer stays disabled for that conversation while it runs
- [ ] A running indicator on the conversation's tab and its sidebar row (a small spinner or dot) wherever the user is; the Imports overview shows a running import too
- [ ] Server restart marks running turns interrupted (ticket 32's recovery) and the indicator clears
- [ ] HTTP-seam tests: message persisted before the model answers; a dropped stream leaves the turn to finish and the full result is in the conversation afterwards; reattach replays; Stop cancels; browser verification: start a sample-year import, switch conversation, come back, see progress and the cards; reload mid-turn; close the tab entirely and reopen
