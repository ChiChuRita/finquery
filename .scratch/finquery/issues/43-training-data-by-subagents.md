# 43: Training data for the two adapters, generated and validated by Opus sub-agents

**What to build:** The training sets for the query adapter and the chart adapter, written and judged by Opus sub-agents (Claude, not OpenRouter models), against the shipped synthetic year and the production prompts exactly as the sub-agents send them. Decided by the user on 2026-09-05: data generation and validation use sub-agents and Opus, not OpenRouter.

**Blocked by:** 40, 41, 42 (merged)

**Status:** ready-for-agent

Decisions, settled earlier and still standing:
- Training equals production: every sample is the exact prompt the sub-agent builds (query_prompt with the reasoning field; the chart plan and code prompts) and the exact forced-tool output it should return. A change to the prompt invalidates the set, so the generator calls the same prompt builders.
- Gold by execution: a query sample is kept only when its SQL runs through the guard and its rows reproduce a figure the judge recomputed independently; a chart sample only when its code passes the self-check on the real rows.
- The benchmark's held-out third is never used for training; the train split may seed patterns but samples are new questions.
- Sizes: about 600 query samples (German and English, all kinds and difficulties, follow-ups with prefix) and about 300 chart samples (request, plan, SQL, code, over the eight shapes), each judged by a second Opus pass with a different seed of questions than the writer saw.
- The chart labeling page from the original design stays available for spot checks: the same static page pattern as bench/validate, showing request, plan, SQL, rows and the rendered chart through the runtime, with Correct, Wrong, Unsure and export.

- [ ] training/data/generate_query.py orchestrated by a sub-agent: writes candidate questions and reference SQL in batches, runs each through the guard and the database, recomputes the figure independently, keeps only agreements; output JSONL with prompt messages and target tool call as the sub-agent would produce them
- [ ] training/data/generate_chart.py the same for charts: plan, SQL via run_query, code through the self-check on the real rows, kept only when it passes first attempt; output JSONL for the plan pass and the code pass
- [ ] A second judging pass by a different sub-agent over every kept sample, verdicts stored, disagreements dropped
- [ ] training/labeling/ static page for the chart samples (rendered chart, plan, SQL, rows) with labels in localStorage and export
- [ ] Split into train and validation stratified by kind, difficulty and language; README in training/ with counts and the loop
- [ ] Tests: the generators are reproducible for a seed, every kept sample passes the guard or the self-check when replayed

## Comments

2026-09-06, ticket 57 (`docs/research/finetuning-data-2026-09-06.md`): the sizes are revised up. 600 query and 300 chart become **900 query rows plus 150 repair and 150 check-pass rows, and 500 chart requests** (500 plan + 500 code + 150 repair), because the published structured-output learning curve elbows at roughly 300 samples per task and the query adapter has eight kinds over two languages, not one task; hold out 400 of each for validation. Three additions to the spec, none of which change what this ticket builds: the adapter is attached for a whole run (`bench/finquery_bench/models.py`), so the query set needs check-pass rows and the chart set needs repair rows or those prompts regress; the second judging pass must validate the `reasoning` line as strictly as execution validates the SQL, since a rationale field at partial coverage measurably loses to no rationale at all; and benchmark growth has to happen first, because `splits.py` re-cuts a stratum when items are added and can move a datapoint into `heldout` after it seeded a training sample. Ticket 43 stays not started.
