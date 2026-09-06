# 64: The training data fan-out: writers, judges, the benchmark audit, the freeze

**What to build:** The data itself, produced by many Opus agents in parallel through the harness of ticket 62, then judged, audited and frozen. A Workflow run by the coordinator, not a hand-run agent. Settled with the user on 2026-09-06 (see `.scratch/finquery/training-plan.md`).

**Blocked by:** 62 (the harness), 61 (not needed)

**Status:** blocked

Plan:
- Writers: ten query writers and ten chart writers, each with a quota sheet: two households, one language emphasis, a spread of kinds and difficulties (40 percent at difficulty 3), follow-ups with a prefix for a fifth of the query rows, every shape for charts. Each writes about 300 query or 150 chart candidates in the schema, runs `validate_batch` and the gate on its own batch, reads the drop reasons, fixes or replaces the dropped rows once, and hands over the kept file with its report. Writers never look at the benchmark files, so they cannot copy them.
- Judges: six query judges and four chart judges over the kept rows in disjoint slices, through the judge pack: verdicts keep, drop or fix, the reasoning line held to the same standard as the SQL; chart judges additionally receive the renders of a stratified fifth per shape and score the picture (readable labels, right shape, legend present when there is more than one series, nothing clipped); any failure pattern becomes a rule applied to the whole set.
- Audit: two agents over the benchmark: near-duplicates between candidates and every benchmark case removed from the training side, ambiguous gold flagged and fixed or dropped, the fairness review of every held-out case a base model failed on the cluster (is the gold right, is the question answerable from the data, is the difficulty label right), balance per kind, difficulty and language; the held-out set grown to about 400 per set from the judged surplus, then the freeze command.
- Assembly: the kept and judged rows through `assemble.py` into the four training files (query and chart, shared across bases) with repair and check rows; 400 held out per adapter; `stats.md`.
- Outputs committed: `training/data/candidates/` (raw, gitignored if large), `training/data/kept/`, the judged verdicts, `training/data/sets/` (the TRL files, committed if under a few MB each, otherwise stored on the cluster and referenced), `bench/` growth with `SPLIT_FROZEN.md`.

- [ ] Writer quotas written and the twenty writers run; gate reports collected (candidates, kept, drop reasons per agent)
- [ ] Judges run; verdicts applied; picture scores and any derived rules recorded
- [ ] Benchmark audited, grown and frozen; audit report committed
- [ ] Training sets assembled with stats; smoke check that every sample's prompt equals the production builder's output
