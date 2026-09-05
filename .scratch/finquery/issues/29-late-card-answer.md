# 29: A Question card answered after a newer message does not resume

**What to build:** When the user types a new message before answering a pending Question card and then answers the card, the answer is stored on an older assistant message and useChat only auto-sends tool results for the newest assistant message, so the run never resumes and the card stays pending. Either the card is marked as expired once a newer turn exists (with a one-line note and a Continue button that re-asks through review_batch or review_duplicates), or answering an older card explicitly sends its results. Found by ticket 17 on the local provider.

**Blocked by:** 20 (merged)

**Status:** done

- [x] Decide and implement one behaviour: expire older pending cards with a Continue action, or send answers for an older card explicitly
- [x] HTTP-seam test for the chosen path; browser verification with a card, a new message, then the card

## Comments

Done 2026-09-05, inside ticket 32.

**The decision: send the answers explicitly and resume the turn the card belongs to.** Expiring
the card was the fallback, and it is not needed: resuming is sound as long as the prompt for
that one run ends where the card's turn ended, which is a two-line change and is what the
framework requires anyway.

Why resuming is the sound one:

- The user's decision is not stale. A category rule, a duplicate decision and an extraction
  review mean the same thing an hour later, and the appliers work against the data as it is when
  the answer arrives rather than against the data the card was built from. A card whose merchant
  was recategorized in between still applies, and the count it reports is what actually moved
  (test).
- Expiring it would throw away work the user already did, and the Continue button would have to
  re-ask the question through a tool that does not exist for two of the five card kinds
  (`mapping_confirmation` and `transaction_draft` have no re-ask; only `review_batch` and
  `review_duplicates` do). That is a worse product for a case that has a clean answer.
- The only soundness problem was real but narrow, and it is fixed rather than avoided. pydantic
  AI matches `deferred_tool_results` against the **last** `ModelResponse` of the history it is
  given (`_agent_graph.UserPromptNode._handle_deferred_tool_results`), so the later turns cannot
  be in that run's prompt: they stay in the transcript and in every later prompt, they are simply
  not part of the run being resumed. And the rolling summary can stand in for the very turn the
  card is on, which would leave the run nothing to resume from at all, so the marker is read one
  turn short of the card for that one run and nothing is compressed on it. Without that clamp
  the test resumes against the wrong response and answers 200 having applied nothing, which is
  worse than an error; the test fails without it.

What changed:

- `History` carries the turn ids and knows which turn each open call is on
  (`open_tool_calls` scans every turn now, `turn_of` names the one). `api/chat.chat` resumes
  that turn: `replaces` is its id, the prompt is `assemble(turns[: card_turn + 1], ...)`, and
  `turn_start` is where that turn starts.
- `persist_turn` keeps the replaced turn's position, so the rewritten turn stays where the user
  saw it instead of jumping to the bottom of the transcript.
- `chat-view.answerCard` is the browser half and is now the only path for every card, near or
  far. It puts the output on the message the card sits on and sends that one message
  (`prepareSendMessagesRequest` picks it out by the answered call id). `addToolOutput` and
  `sendAutomaticallyWhen` are both gone: the first writes to the newest assistant message
  whatever call id it is given, the second only ever looks at the newest message, which is the
  whole bug. Verified in the browser before the fix: clicking Send disabled the buttons, sent no
  request at all, and the rows were still Needs review afterwards.
- The output chunk of a card the browser answered from further up is left out of the resumed
  stream. The stream lands on the browser's newest message, that card is not on it, and the SDK
  answers "No tool invocation found for tool call ID ..." in the transcript. The browser already
  put the answers on the card before it sent them and reads the `applied` line back with the
  stored turn, which `onFinish` refetches for exactly that case.
- A second answer to a closed card is 409 with one sentence (`chat.ALREADY_ANSWERED`) rather
  than a replay of the appliers, which would insert a kept duplicate twice.

Tests: `test_categorization.test_a_card_answered_after_a_newer_message_still_resumes_its_own_turn`
(the answers apply, the prompt is the card's own turn and not the question asked in between, and
the transcript keeps its order), `..._twice_is_refused_rather_than_applied_again`,
`..._whose_merchant_moved_meanwhile_still_applies_and_counts_honestly` and
`test_context.test_a_card_the_summary_has_reached_is_still_answerable`.

Browser, port 8105, session `fq32`: a seeded review card, a groceries question in between, then
the card. The rules were stored ("Applied: Lea Hoffmann (via PayPal) -> Dining (5 bookings
recategorized).", `say` "1 merchant now has a rule."), the turn kept its place above the
question asked in between, and a reload shows the same transcript.
Screenshots `/tmp/finquery-32/before/05-late-card-answer.png` and
`/tmp/finquery-32/after/05-late-card-answer.png`.

ADR 0008 amended: the explicit answer, the in-place rewrite, and where a resumed run's prompt
ends.
