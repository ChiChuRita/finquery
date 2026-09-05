# 29: A Question card answered after a newer message does not resume

**What to build:** When the user types a new message before answering a pending Question card and then answers the card, the answer is stored on an older assistant message and useChat only auto-sends tool results for the newest assistant message, so the run never resumes and the card stays pending. Either the card is marked as expired once a newer turn exists (with a one-line note and a Continue button that re-asks through review_batch or review_duplicates), or answering an older card explicitly sends its results. Found by ticket 17 on the local provider.

**Blocked by:** 20 (merged)

**Status:** ready-for-agent

- [ ] Decide and implement one behaviour: expire older pending cards with a Continue action, or send answers for an older card explicitly
- [ ] HTTP-seam test for the chosen path; browser verification with a card, a new message, then the card
