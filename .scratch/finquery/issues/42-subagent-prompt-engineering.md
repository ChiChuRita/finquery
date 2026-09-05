# 42: Prompt engineering for the sub-agents and the chat agent

**What to build:** Give every model-facing prompt three things a small model needs: few-shot examples drawn from validated data, a short reasoning step before the answer, and a retry framing that shows the mistake and asks for a correction instead of a fresh start. Measured before and after on the benchmarks and the existing measurement scripts. Requested by the user on 2026-09-05. The query sub-agent's prompt is done inside ticket 40 (same file); this ticket covers the rest.

**Blocked by:** 37 (merged); coordinate with 40 (query prompt) and 41 (benchmark files)

**Status:** ready-for-agent

Prompts in scope: chart sub-agent (plan and code passes, chart/subagent.py), categorizer (categorize/subagent.py), extraction (statement pages and receipts, extract/subagent.py), memory distillation (memory.py), the follow-up step (followups.py), the web lookup decision loop (weblookup/loop.py), and the chat agent's system prompt (agent.py) for how it uses tool results and hands mistakes back.

- [ ] Few-shot: every prompt carries one worked example per hard pattern it is known to get wrong, taken from validated sources (the chart benchmark's train split once ticket 41 lands, else the hand-written ones judged correct; the twenty public receipts and the real Edeka receipt for extraction, described without personal data; the categorization measure script's misses; the review reports), never a heldout benchmark item
- [ ] Reasoning before the answer: each forced tool gets a short `reasoning` field filled first (three to five one-line steps specific to that job: for charts the shape choice and the columns, for the categorizer the merchant reading and the category versus subcategory choice, for extraction the layout and where the date and total sit, for memory whether the fact is durable), so the model commits to an interpretation before producing the structured answer; the reasoning is kept in the narration or the tool result where a step already renders it, never in prose
- [ ] Retry framing everywhere a retry exists (chart self-check repairs, categorizer confidence resubmits, extraction guard rejections, memory dedup refusals, tool validation errors): the message shows the previous reasoning and answer, the exact finding, and asks for the corrected reasoning and answer with a diff of what changed
- [ ] Chat agent prompt: how to read a tool result (figures, rendered flag, applied lines), when to call a tool again with a sharper request, and how to say what could not be done; kept within a few hundred tokens of growth with the context BUDGET re-measured
- [ ] Measured: chart benchmark on qwen/qwen3.5-9b and google/gemini-3.8-flash before and after (figure match, first attempt, drawn); categorization on the shipped year with scripts/measure_categorization.py before and after (share categorized, spot check of twenty); extraction on the twenty public receipts and the synthetic PDF before and after (items add up, dates read); tables in the ticket and the bench README's own section
- [ ] Prompt example tests still cover every worked example; suite green; build clean
