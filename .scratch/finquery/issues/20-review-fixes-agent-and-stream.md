# 20: Review fixes, agent and stream side

**What to build:** The headful review of 2026-09-04 (see ../review-2026-09-04.md) found leaks between model and screen that would show on stage. This ticket fixes the agent, prompt and stream side; ticket 21 takes the frontend side.

**Blocked by:** 06, 07, 09 (all merged)

**Status:** ready-for-agent

- [ ] Question card answers are applied deterministically in code: when the answered `ask_user` output arrives, the server turns each answer into a category rule and recategorizes that merchant before the model is asked to continue, and the model only summarizes and asks the next card. The fast model must never be asked to sequence N `set_rule` calls itself (it looped for 145 seconds and created nothing)
- [ ] The Gemma end-of-turn marker `<turn|>` (and any other chat-template token) never reaches answer text on either provider: stripped in the stream path in one place, with a test
- [ ] The answer language follows the latest user message, not the conversation so far, and money in prose uses German formatting (comma decimals, dot thousands, EUR after the number); one prompt paragraph, verified on a German then English then German exchange
- [ ] "Recategorize all X rows" and any other bulk change goes through `propose_changeset` with a preview card; `set_rule` is reserved for teaching statements ("PayPal to Anna is always Dining") and Question card answers. Prompt wording plus a guard: `set_rule` refuses when the user's request was a bulk edit phrase is not feasible, so the prompt has to carry it and a test asserts the tool choice on a scripted turn
- [ ] Every assistant fragment carries `model_slot` in metadata so a model switch never relabels an earlier turn; the context badge never shows NaN (older conversations without a data-context part show a dash)
- [ ] The "cannot answer" reply gives one sentence of why and an alternative, and still gets follow-ups
- [ ] Every tool gets a visible step: `remember`, `set_rule`, `review_batch`, `propose_changeset`, `apply_simple_edit` render as collapsible steps like `query`
- [ ] Thinking duration persisted per turn matches the live value after reload
- [ ] HTTP-seam tests for each item; full suite green; browser verification of the Question card flow end to end on the real fast model
