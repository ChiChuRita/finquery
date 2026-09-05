# 40: A query checks itself and retries

**What to build:** A valid statement that answers the wrong question is the failure the guard cannot see: the benchmark shows small models writing valid SQL 93 to 97 percent of the time and the right figure only about half the time. After every query the result is checked against the question and, when it does not answer it, rewritten once. Empty and degenerate results trigger a retry with a hint. Both steps narrate into the thinking panel like the chart repairs. Measured on the benchmark before and after.

**Blocked by:** 37, 38 (merged)

**Status:** ready-for-agent

Decisions, settled:
- Degenerate result retry, in code: zero rows, all-NULL figures, or a single figure of exactly 0 on a question that names a merchant or category trigger one rewrite with a hint naming the likely cause (spelling and LIKE, the data's date range, category versus subcategory, sign). At most one such retry.
- Check pass, on the fast slot, one forced single tool: given the question (with the conversation prefix when it is a follow-up), the taxonomy digest, the data range, the statement and up to ten result rows, it returns ok, or revise with a one-sentence reason and the corrected intent (not SQL). A revise triggers one rewrite by the query sub-agent with that reason attached. At most one revise per query call, so a query costs at most three model calls.
- The check is skipped when the statement came from a retry already or when the chat agent passed an explicit hint that pins the interpretation, to keep cost bounded; the runner exposes a flag to disable the check so the benchmark can measure with and without.
- Narration: "Checking the result", "Rewriting: <reason>" lines through the existing narrate seam.

- [ ] Degenerate result detection and the hinted retry, with tests for each trigger and for the single-retry ceiling
- [ ] The check pass with its forced tool, the revise path, the skip rules, the cost ceiling, and the narration, with tests (a scripted check that says revise makes the sub-agent run again with the reason; ok leaves the result alone; the ceiling holds)
- [ ] The benchmark runner gets --no-check; both SQL and chart sets run on qwen/qwen3.5-9b and google/gemini-3.8-flash with and without the check, results committed, a before and after table in bench/README.md with the median latency cost
- [ ] Browser verification on OpenRouter with Qwen on both slots: the review's failing questions (wrong period, wrong sign, subcategory as category) show the check catching and rewriting in the thinking panel; both themes
- [ ] Suite green, build clean; tests/test_context.py BUDGET re-measured if the prompt grew
