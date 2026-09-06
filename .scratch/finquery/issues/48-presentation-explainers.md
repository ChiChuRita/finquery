# 48: Explainers for the presentation, one per mandatory and elective task

**What to build:** A set of short documents the presenter can read the evening before and explain from: how each mandatory feature and each claimed elective works in this codebase, with a diagram, the exact files and functions, the request flow, what is deterministic and what the model does, the guards, the measurements we have, and the two or three sentences to say out loud. Requested by the user on 2026-09-06: "I have to do the presentation and I should be able to explain everything."

**Blocked by:** none (documents only; describe main as it is, note where a ticket is still running)

**Status:** done

Decisions:
- One file per topic under `docs/explainers/`, plus `docs/explainers/README.md` as the index with the one-paragraph elevator pitch and the map of topic to files. Each file: the claim in one line; how it works (a Mermaid sequence or flow diagram, rendered the same way `docs/overview.html` renders its Mermaid, and the same diagram as text so it reads in a terminal too); the code path as a numbered list of `file:function` steps; where the model is in the loop and where it is not; failure handling and guards; what we measured (from the ticket files under `.scratch/finquery/issues/` and `bench/results/`), with the numbers; what to say in the talk (three sentences); likely questions from the graders with answers; what is not finished, honestly.
- Topics. Mandatory: local-first chat assistant on two resident models with a model switch (providers, local runtime, wire formats, the fast and quality slots); the numbers invariant and the SQL guard with the query sub-agent and check-and-retry; charts as checked code in a sandboxed frame; ingestion (CSV mapping, text-layer PDF, vision for scans and receipts, verbatim and reconciliation guards, duplicates); categorization with rules, Question cards and the taxonomy; transactions page and edits through changesets; the dashboard; the training and benchmark loop (benchmarks, validation page, adapters, what the two fine-tuned models are for and the current state of ticket 43 and the adapter training). Electives: intelligent context management (profiles as isolation, per-turn context assembly and selection, rolling summary compression at 60 percent, memory distillation); sub-agent deployment (query, chart, categorizer, extraction, memory, web lookup, all on the fast slot, how they are dispatched as tools and narrate their steps); preference optimization from human feedback (thumbs, Regenerate pairs, A/B, Feedback page, DPO export and training scripts); self-directed web search (the loop, the merchant token scrubber, the outbound journal, the cache).
- Read first: `CLAUDE.md`, `CONTEXT.md`, every ADR in `docs/adr/`, `docs/overview.html`, `docs/demo-script.md`, `.scratch/finquery/spec.md`, the ticket files (their Comments sections hold the measurements and the as-built notes), `bench/README.md` and `bench/results/`. The old repo's `DECISIONS.md` on branch `archive/old-main` (`git show archive/old-main:DECISIONS.md`) has the electives list as the course framed it; the user-provided-tools and secure-code-execution electives were dropped and must not be claimed.
- Honest by construction: every number quoted has a source (a ticket comment, a results file) named next to it; every "works" is something a test or a verification session showed; anything still running (tickets 44 to 47 at the time of writing, ticket 43 not started, adapter training not started) is written as such.
- English, plain, no em dashes anywhere. Readable in a terminal and on GitHub. No code changes outside `docs/explainers/` except one link from `README.md` and one from `docs/overview.html` to the index.

- [x] `docs/explainers/README.md` index with pitch, topic map and the order to read in
- [x] One explainer per topic listed above, each with all the sections in the decision
- [x] Every figure sourced; every unfinished part marked; a final pass that checks each `file:function` reference exists on main
- [x] Links from `README.md` and `docs/overview.html`

## Comments

Done 2026-09-06 on the worktree branch, documents only, no code changed.

- `docs/explainers/`: `README.md` (pitch, topic map, reading order), `checklist.md` (every
  bullet of the course sheet with status, code and evidence), fifteen explainers, and
  `check_refs.py`. The structure follows the course sheet, which landed on main as
  `docs/course/task-description.md` mid-ticket and is copied into this branch: files 01 to 05
  are one home per required bullet (run and UI and chat and conversations; the model switch;
  memory across the profile's chats; the two fine-tuned models with the benchmark loop behind
  them; the video demo), 06 to 11 are the technical chapters (numbers invariant and SQL guard,
  charts, ingestion, categorization, transactions and changesets, dashboard), 12 to 15 the four
  electives.
- Every `path:symbol` reference was checked by `uv run python docs/explainers/check_refs.py`:
  395 references, 0 failures. The script also refuses an em dash or an en dash in the files.
  About 25.000 words in total.
- Honest state written into the files: no adapter is trained and no sub-agent sets
  `finquery_adapter` yet (only the bench runner's `--adapter` does); the video is not made;
  ticket 43 has not started; tickets 44 to 47 run in parallel and their code is not on main;
  the four benchmark runs with the check on and Qwen's chart re-run (26 of 63) are missing
  because the OpenRouter key hit its limit; the sub-agent extra credit (a controlling LLM that
  continues without waiting) is not claimed, and the checklist says which electives are not
  claimed at all.
- One number the README and `docs/overview.html` still show as "not run" or "pending" has a
  result file: Gemma 4 E4B on the chart set, 48 % figure match, 73 % drawn, median 36 s
  (`bench/results/20260905T183745Z-local-fast-chart.md`, commit fce271a). The explainers quote
  the file; updating the two overview tables was outside this ticket's link-only allowance.
- Links added: one line in `README.md`, one line in `docs/overview.html`.
