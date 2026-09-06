# 55: Codebase cleanup: redundant code, smells, unnecessary files

**What to build:** A review of the whole repository for dead and duplicated code, smells, and files nobody needs, followed by the removals and small refactors that make the codebase smaller without changing behaviour. Requested by the user on 2026-09-06.

**Blocked by:** none; tickets 53 (weblookup, categorize, extract/bill, the lookup card) and 54 (providers, settings, local/, api/models, api/chat, db model columns, slots.ts, model selector, onboarding default model) run in parallel and own those files: leave them alone and list what you would have done there under Comments

**Status:** ready-for-agent

Rules:
- Behaviour does not change. Every step is verified by `uv run pytest`, `npm run build` and `oxlint`; a removal that a test relied on means the test was the only caller, so remove both only when the test tested the removed thing itself.
- What counts: unused functions, classes, exports, imports, CSS rules and components; duplicated helpers (two formatters, two date parsers, two "quote for SQL"); dead branches and flags; stale scripts under `scripts/` and `/tmp`-style leftovers committed by mistake; docs that describe code that no longer exists (check every `path:function` reference the same way `docs/explainers/check_refs.py` does); fixtures nobody reads; dependencies in `pyproject.toml` and `frontend/package.json` that nothing imports; lint warnings that are real (the oxlint baseline of 41 should go down, not up); repeated code across the API routers that a shared helper already covers; comments that narrate the obvious or contradict the code; `TODO`s whose ceiling was passed.
- What does not count: the vendored AI Elements files with local edits, shadcn `ui/` components, the chart runtime contract, the SQL guard, the prompt examples, `fixtures/private/` (gitignored), `models/`, the ticket and review files under `.scratch/`, the benchmark data, the prototypes under `.scratch/finquery/prototypes/`.
- YAGNI applies to the cleanup itself: no new abstractions, no renames for taste, no reformatting sweeps. A refactor is only made when it deletes code.
- Write the audit first (file, what, why, action) under Comments, then act in small commits grouped by area, each green.

- [ ] Audit list written (Python, frontend, docs, scripts, fixtures, dependencies)
- [ ] Removals and merges done, each commit green (pytest, build, oxlint), oxlint count at or below 41
- [ ] Docs references verified; stale docs fixed or removed
- [ ] A short Comments note: lines removed, files removed, dependencies removed, what was left for tickets 53 and 54, anything found that needs a decision
