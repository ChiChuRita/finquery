# 62: Training data harness: households, execution gate, render, judge inputs, benchmark audit tools

**What to build:** Everything the writer and judge agents of ticket 64 call, so that they only write questions and answers and never invent a pipeline. Settled with the user on 2026-09-06 (see `.scratch/finquery/training-plan.md`).

**Blocked by:** 43 (design), 56 (cluster bench), 57 (research), 61 (in flight; not needed for this ticket)

**Status:** done

Decisions:
- Households: `scripts/generate_synthetic.py` gains five profiles with fixed seeds (student, family with children, freelancer with irregular income, pensioner, couple with two accounts), each a full year with its own merchant set, categories, amounts, recurring payments and a few edge cases, written to `fixtures/synthetic/households/<name>-2025.csv` plus a `households.json` with the truth the generator knows (merchants and their categories, monthly totals). Deterministic, committed, each under 100 KB. The shipped year stays as it is.
- Databases: `training/data/households.py` builds one SQLite database per household with the production import path (the same code `bench/finquery_bench/dataset.py:fresh_database` uses) and caches them under `training/data/.db/` (gitignored).
- Candidate format: a writer produces JSONL rows `{"id", "household", "language", "kind", "difficulty", "question", "prefix": [previous turns or []], "sql", "reasoning", "expected": {"figure": number or null, "check_sql": an independent statement computing the same figure differently}}` for query; for chart `{"id", "household", "language", "request", "shape", "plan", "sql", "code", "reasoning_plan", "reasoning_code"}`. The exact schema lives in `training/data/schema.py` with Pydantic models and a `validate_batch` command that rejects a malformed file with line numbers.
- Execution gate `training/data/gate.py`: for a query row, the SQL through `validate_sql` and `execute_read_only` on the household database, `check_sql` likewise, the two figures compared with the benchmark's `figure_match` tolerance, the row kept only on agreement and on a non-degenerate result (the same degenerate rules `query/check.py` uses); for a chart row, the SQL executed, `fold_rows`, then `selfcheck` on the real rows, kept only when the check passes on the first attempt; every drop carries a reason. Output: kept JSONL plus a `report.md` with counts by household, kind, language, difficulty and drop reason.
- Render `training/data/render.py`: every kept chart row rendered headless through the real chart runtime (reuse `bench/validate`'s static page or the frame's built bundle; drive it with `agent-browser` in headless mode or Playwright if it is already installed, no new dependency otherwise) to `training/data/renders/<id>.png` at 640 by 280, both themes optional, light by default; a manifest with the file names. This is what the vision judges look at.
- Sample assembly `training/data/assemble.py`: a kept row becomes training samples exactly as the sub-agents send them: the query prompt built by `query/subagent.py`'s builder with the household's profile facts and the target tool call with `reasoning` and `sql`; the chart plan prompt and its target, the chart code prompt with the rows brief and its target; plus repair rows (a wrong first attempt and the check's finding, then the corrected target) and check-pass rows (the judge prompt and its verdict) at the rates the research note names, produced from real drops of the gate where possible. Output JSONL in the chat-messages format TRL's `SFTTrainer` accepts with completion-only loss, one file per adapter, and a `stats.md`.
- Judge inputs: `training/data/judge_pack.py` writes, for a batch, a compact review file (question, SQL, rows, figure, reasoning) for the second Opus pass, and reads its verdict file back (`keep`, `drop`, `fix` with a corrected field), applying it. The judge agents never touch the kept files directly.
- Benchmark audit tools `training/data/audit.py`: near-duplicate detection between candidate questions and every benchmark case (character n-gram Jaccard above a threshold, and a normalized-form equality after lowercasing, number and merchant masking), a report of held-out cases with their kind, difficulty, language and the models' pass or fail from the cluster results (so the fairness review knows what to look at), and a `freeze` command that writes `bench/SPLIT_FROZEN.md` with the split hash and refuses further `split.py` re-cuts unless a flag is passed.
- Smoke: `training/data/smoke.sh` runs a ten-row hand-written batch of each kind end to end (validate, gate, render, assemble, audit) in under two minutes with no model, and is the acceptance test the fan-out agents run first.
- Tests for the schema, the gate (a wrong figure is dropped, a degenerate result is dropped, a passing chart is kept), the assembly (prompt equals the sub-agent's builder output byte for byte), the audit (a paraphrase is caught), and the households (deterministic, counts). No em dashes anywhere.

- [x] Five households generated and committed with their truth file; databases build and cache
- [x] Schema and `validate_batch`; gate with reasons and report; tests
- [x] Headless render of kept charts to PNG with a manifest; verified on ten charts
- [x] Assembly to TRL chat format for both adapters with repair and check rows; byte-equality test against the production prompt builders
- [x] Judge pack and verdict apply; audit tools and the freeze command; tests
- [x] `training/data/README.md` for the writer and judge agents: the exact commands, the candidate schema, the quotas per agent (household, language, kind, difficulty), and what a good candidate looks like with three examples per task; `smoke.sh` green in under two minutes

## Comments

2026-09-06, done on branch `worktree-agent-abeb6d2b1e907da49`. The whole harness is
`training/data/`, and `training/data/README.md` is what the twenty agents of ticket 64 read.

- **Households.** `scripts/generate_synthetic.py` gained five: `student` (300 bookings),
  `family` (486), `freelancer` (381), `pensioner` (349) and `couple` (565 over two accounts),
  each a deterministic year in the Sparkasse layout under
  `fixtures/synthetic/households/`, each CSV under 100 KB, the shipped year untouched.
  `households.json` carries what the generator knows: every merchant with its category, the
  totals per category and the totals per month per category. `tests/test_training_households.py`
  holds that file to the database the production import path builds out of the same CSV,
  merchant by merchant and month by month, which is what makes it truth a judge can recompute
  from rather than a claim.
- **The gate is the whole design.** A query row is kept only when a second statement, written
  differently on purpose, agrees on every figure to the cent (the benchmark's own
  `figure_match`) and the result is not one of the shapes `query/check.py` would send back. A
  chart row is kept only when the statement returns exactly the planned columns, the fold and
  `data_findings` pass, production would not downgrade the shape, and the real self-check passes
  first time. Every drop carries its reason, and half of them are worth as much as a keep: a
  refusal becomes a repair sample, a degenerate result becomes a rewrite sample, and a statement
  that ran and answered a different question becomes a `revise` verdict for the check pass once
  a judge has written the sentence.
- **Renders.** `render.py` serves the built runtime and one job file per chart from a short-lived
  HTTP server in the process and drives headless Chrome through `agent-browser` on the session
  `ticket62`. Ten charts, all eight shapes, render in under two seconds at 640 by 280; the dark
  theme is one flag. The chart runtime has to be built once (`npm --prefix frontend run build`),
  which the README says twice.
- **Two things worth knowing for ticket 64.** The near-duplicate threshold was set by measuring
  the benchmark against itself, 25,200 pairs, and it caught two of my own hand-written smoke
  questions immediately, so expect it to catch real ones. And the split is now frozen:
  `bench/SPLIT_FROZEN.md` holds the hash, `bench/split.py` refuses to re-cut without `--force`,
  and `audit freeze --check` is in `smoke.sh` so a run notices before it writes a row.
- **Not done here, on purpose.** No `revise` verdict can be written by code, because it is a
  sentence about what a statement answered instead. `assemble.py` says so in `stats.md` when a
  set has none, and the README tells the judges it is the only way those samples exist.

`smoke.sh` runs validate, gate, render, judge pack, judge apply, assemble and audit over the
committed batches in seven seconds with no model. `uv run pytest`: 442 passed, 4 skipped,
against 405 before.
