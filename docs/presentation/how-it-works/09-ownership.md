# What we own: decisions, reversals, and what we chose not to claim

The graders judge thinking and ownership. This is the list, each with the evidence that forced it.

## Kept from day one

- Numbers only from executed SQL. The invariant is the first line of `CLAUDE.md` and the reason
  the guard, the check pass, the prose verifier and the chart self-check exist.
- Sub-agents as forced tool calls with a reasoning field first (ticket 42's prompt work).
- Every import and every decision happens in the chat; the Import page and the Dashboard are
  overviews (spec amendments of 2026-09-05 and 2026-09-06).
- Training equals production: a sample is the exact prompt the sub-agent sends.

## Reversed on evidence

- **Qwen3.5 9B as quality slot** (ticket 23, chosen because it fit next to E4B) became **Gemma 4
  12B** after the cluster benchmark: 87 against 70 on SQL, 81 against 42 on charts
  (`bench/results/20260906-cluster-compare.md`, ticket 61).
- **Preference optimisation** was built (thumbs, Regenerate pair, A/B, Feedback page, DPO
  scripts), measured, and **removed** for multimodal ingestion, which was already built,
  guarded and demonstrable (tickets 58 and 59). The hard part of the preference elective is
  training on choice data, which we never had enough of.
- **"No dashboard"** in the spec became a dashboard of guarded queries with a date range
  (tickets 35, 44, 51) after the research note on what finance apps show by default
  (`docs/research/charts-and-dashboard-2026-09-06.md`).
- **Gemini for verification** was refused: what works on a strong hosted model and fails on
  Gemma is a bug we want to see (`CLAUDE.md`, models section).

## Not claimed, on purpose

- The sub-agent extra credit (a controller that continues without waiting).
- Python code execution: our sandbox runs JavaScript charts, and we say so.
- Audio ingestion.
- Adaptive RAG, user-provided tools, multi-user, prompt caching, Tree-of-Thought: not built.

## How it was built

Forty-plus tickets from an empty repo in a week, each implemented by an agent in its own
worktree and verified in a headful browser before merging; reviews and end-to-end tests by
browser agents; benchmarks on the cluster; research notes with sources before each big
decision. `docs/adr` holds thirteen decisions, `.scratch/finquery/issues` every ticket with its
measurements.

## Next

Adapter numbers against vanilla, the video, a second data round if the learning curve says so.

## Say

"Three reversals, each forced by a measurement we made ourselves. And three things we could have
claimed and did not."
