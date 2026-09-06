# 65: Train the four adapters, follow the curve, convert the best, compare against vanilla

**What to build:** The real training runs on the cluster and the numbers. Settled with the user on 2026-09-06 (see `.scratch/finquery/training-plan.md`).

**Blocked by:** 63 (the loop), 64 (the data)

**Status:** blocked

Plan:
- Four jobs in parallel (query and chart on E4B and on the 12B), one GPU each, the configs from ticket 63, three epochs with a checkpoint each; quick eval after every epoch on the fixed 100-case set; the curve read by the coordinator: rising means finish, flat from epoch one means stop and grow the data (a second writer round on the weakest kinds).
- The best checkpoint per adapter converted to GGUF, dry-run loaded, smoke-tested on five cases, then the official llama-cpp runs: base and base plus adapter, both tasks, both bases, plus the end-to-end subset with the adapter on the sub-agent role; `bench/results/<date>-adapters-compare.md` with the before and after and the decision rule.
- The report to the user: the table, the curves, what the adapters fix and what they still miss (the per-case lists from `compare`), the shipped configuration recommendation (which roles on E4B plus adapter, which on the 12B), and the second data round plan if needed.

- [ ] Four trainings submitted with smoke-verified configs; curves recorded
- [ ] Best checkpoints converted, loaded, smoke-tested; adapters copied to `models/adapters/` on the laptop and registered
- [ ] Official runs finished; comparison table committed; report written under Comments and to the user
