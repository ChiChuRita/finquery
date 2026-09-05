# 37: Robustness against a small model

**What to build:** The Qwen3.5 9B capability review (../qwen-capability-2026-09-05.md, 30 exact of 46) found failure patterns that are not Qwen's alone: they are places where a small model can do damage or state a wrong figure and the code lets it. Close each at the code level with a test, so E4B and Qwen both become safe, then re-measure.

**Blocked by:** 30, 32 (merged)

**Status:** ready-for-agent

- [ ] Cents never reach prose as euros: the query guard refuses a statement whose selected expression aggregates amount_cents without dividing by 100.0 (or the view exposes only euro amounts to the sub-agent and amount_cents is removed from the prompt schema); integer division is impossible (100 becomes 100.0 in the prompt examples and a guard rewrites `/ 100` to `/ 100.0`); a test per rule
- [ ] Figures the prose states must come from a query: the answer text is checked against the figures of the turn's tool results (every EUR amount in the prose must appear in a tool result, tolerance one cent), and a mismatch is rewritten server-side into a sentence that quotes the tool figures, with a log line; the chat prompt says the model never adds, subtracts or nets numbers itself and asks the query tool for totals
- [ ] `propose_changeset` accepts what a small model sends: nested optional fields may be null or missing (legs: null, where: null), and the tool schema is flattened where nesting is not needed; a scripted test with the exact failing arguments from the review passes
- [ ] `apply_simple_edit` never changes a field the user did not name: unset fields are unset, `amount_cents: 0` or an empty description is refused with a sentence unless the user's message named the amount (the tool gets the user's request text or the model must pass `fields_changed` explicitly), and the answer sentence names every field that changed
- [ ] Memory distillation refuses one-off figures and dates (a fact containing an amount or a date is not durable unless kind is rule), refuses facts about entities the turn proved absent, and caps distilled facts per turn at two; the review's 27 memories in one afternoon become a handful
- [ ] The taxonomy line in the sub-agent prompt cannot be read as categories: subcategories are listed under their category with a clear marker, the guard refuses a `category IN (...)` or `category =` whose literal is a subcategory name (it knows the taxonomy) and answers with the parent, with a test
- [ ] The query sub-agent never narrows the period silently and reads "last quarter" and "last month" relative to the latest booking month with a rule in the prompt; a query call budget of five per turn stops runaway loops, and a statement longer than 1500 characters or with a CROSS JOIN is refused
- [ ] Text degradation: template and foreign-script token leaks in a German or English answer are stripped by the existing filter where they are single stray tokens; the chart repair narration never reaches prose (it is reasoning)
- [ ] Re-measure: rerun the review's 46 questions against the scripted-slot tests where possible and, in the browser on OpenRouter with qwen/qwen3.5-9b on both slots, the ten that failed on SQL; report before and after
- [ ] Suite green, build clean
