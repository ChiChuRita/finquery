# 55: Codebase cleanup: redundant code, smells, unnecessary files

**What to build:** A review of the whole repository for dead and duplicated code, smells, and files nobody needs, followed by the removals and small refactors that make the codebase smaller without changing behaviour. Requested by the user on 2026-09-06.

**Blocked by:** none; tickets 53 (weblookup, categorize, extract/bill, the lookup card) and 54 (providers, settings, local/, api/models, api/chat, db model columns, slots.ts, model selector, onboarding default model) run in parallel and own those files: leave them alone and list what you would have done there under Comments

**Status:** done

Rules:
- Behaviour does not change. Every step is verified by `uv run pytest`, `npm run build` and `oxlint`; a removal that a test relied on means the test was the only caller, so remove both only when the test tested the removed thing itself.
- What counts: unused functions, classes, exports, imports, CSS rules and components; duplicated helpers (two formatters, two date parsers, two "quote for SQL"); dead branches and flags; stale scripts under `scripts/` and `/tmp`-style leftovers committed by mistake; docs that describe code that no longer exists (check every `path:function` reference the same way `docs/explainers/check_refs.py` does); fixtures nobody reads; dependencies in `pyproject.toml` and `frontend/package.json` that nothing imports; lint warnings that are real (the oxlint baseline of 41 should go down, not up); repeated code across the API routers that a shared helper already covers; comments that narrate the obvious or contradict the code; `TODO`s whose ceiling was passed.
- What does not count: the vendored AI Elements files with local edits, shadcn `ui/` components, the chart runtime contract, the SQL guard, the prompt examples, `fixtures/private/` (gitignored), `models/`, the ticket and review files under `.scratch/`, the benchmark data, the prototypes under `.scratch/finquery/prototypes/`.
- YAGNI applies to the cleanup itself: no new abstractions, no renames for taste, no reformatting sweeps. A refactor is only made when it deletes code.
- Write the audit first (file, what, why, action) under Comments, then act in small commits grouped by area, each green.

- [x] Audit list written (Python, frontend, docs, scripts, fixtures, dependencies)
- [x] Removals and merges done, each commit green (pytest, build, oxlint), oxlint count at or below 41
- [x] Docs references verified; stale docs fixed or removed
- [x] A short Comments note: lines removed, files removed, dependencies removed, what was left for tickets 53 and 54, anything found that needs a decision

## Comments

### Audit, 2026-09-06

How the list was found, not guessed: `uvx vulture src tests --min-confidence 80`, an AST scan of
every top-level function, class and CONSTANT in `src/finquery/` and `bench/finquery_bench/`
counted against the whole repository as one string (`/tmp/unused2.py`), `uvx ruff check` with
`F,B,SIM,RET,PIE,C4`, `npx knip` in `frontend/`, `npx oxlint`, `uv run python
docs/explainers/check_refs.py`, and a copy of that checker widened to `docs/adr`,
`docs/research`, `docs/course`, `bench/README.md`, `README.md` and `CONTEXT.md`
(`/tmp/check_refs_all.py`).

| File | What | Why | Action |
| --- | --- | --- | --- |
| `src/finquery/__init__.py` | `hello()` | The `uv init` sample function. No caller anywhere, docs included. | Removed, file left empty as the package marker |
| `src/finquery/changesets.py` | `_taxonomy_label` | One definition, no call site. | Removed |
| `src/finquery/prose.py` | `_SCRIPTS` | A constant `_is_foreign` never reads; it tests `name.startswith("LATIN")` itself. | Removed |
| `src/finquery/api/dashboard.py` | `import json` | Unused import (ruff F401). | Removed |
| `bench/finquery_bench/cli.py` | `COMMANDS` | Never read; argparse names the subcommands. | Removed |
| `bench/finquery_bench/datapoints.py` | `DIFFICULTIES` | Never read; the field is typed `int`. | Removed |
| `tests/test_background_turns.py` | `default_profile_id` import | Unused import (ruff F401). | Removed |
| `tests/test_chart.py` | second `check_chart_code` import | Imported twice from the same module (ruff F811). | Removed |
| `frontend/package.json` | `date-fns` | Not imported by anything under `frontend/src` (knip). `react-day-picker` carries its own date maths. | Removed |
| `frontend/src/components/empty-state.tsx` | `export` on `STARTER_SUGGESTIONS` | Used only in its own file; the export is what makes oxlint refuse the file for fast refresh. | `export` dropped, one oxlint warning fewer |
| `frontend/src/components/chart-tool.tsx` | `export` on `SHAPE_LABELS` | Same. | `export` dropped, one oxlint warning fewer |
| `frontend/src/lib/workspace.tsx` | `export` on `rememberActiveTab` | Same. | `export` dropped, one oxlint warning fewer |

Checked and deliberately left alone:

| Thing | Why it stays |
| --- | --- |
| Every route handler vulture called unused | All eighteen are reached over HTTP by `frontend/src/lib/api.ts` or by a test; a decorated handler simply has no Python caller. Each one was grepped by its path. |
| `_stripped_and_not_empty` in `api/profiles.py`, `api/memories.py`, `api/conversations.py` | Same name, three different rules (a 120-character cap, `clean_text`, a title cut to `TITLE_LENGTH`) and three different messages. Merging them would add an abstraction, not delete code. |
| `strip_markers` in `local/qwen.py` and `local/gemma.py` | Different bodies over different `TEMPLATE_MARKERS`; Gemma's also drops channel lines. |
| `to_cents` in `prose.py` and `ingest/typed.py` | Different signatures and different inputs (a written phrase, an amount plus a direction). |
| `NONE = '__none__'` in `split-editor.tsx`, `transaction-dialogs.tsx`, `transaction-cells.tsx` | One line each. Sharing it would mean importing a component module for a sentinel. |
| Numbers formatted in `query-result.tsx` rather than `lib/format.ts` | A raw SQL cell is a plain number, not a euro figure; `formatEur` would be wrong there. |
| `fixtures/chart-benchmark.json` beside `bench/chart-benchmark.json` | The smaller one is still what `tests/test_chart.py` reads. |
| `fixtures/edge/`, `scripts/*.py`, `training/preference/` | All read: `tests/test_edge_cases.py`, the measurement and generation runs the docs cite, the DPO export. |
| Every `TODO` in `src/` | Each names a live ceiling with an upgrade path; none has been passed. |
| `python-multipart` | Not imported by name; FastAPI needs it for `UploadFile`. |
| `@tanstack/charts` (knip calls it unused) | knip cannot load `vite.config.ts` here, so it misses the chart-runtime entry, which is the only importer. |
| The other 38 oxlint warnings | 30 are `only-export-components` on files that genuinely export a hook or a context next to a component (`workspace.tsx`, `routes.tsx`, `theme.tsx`, the vendored AI Elements, shadcn `ui/`). Silencing them means new files, which the ticket rules out. The rest are `set-state-in-effect`, `static-components` and `incompatible-library`: real, but each is a behaviour change to fix. |
| Unreachable `yield` after `return`/`raise` in `tests/test_chat.py` and `tests/test_edge_cases.py` | That is what makes those functions generators. Both already say so in a `pragma` comment. |

Nothing was touched under `src/finquery/weblookup/`, `categorize/`, `extract/bill.py`,
`providers.py`, `settings.py`, `local/`, `api/models.py`, `api/chat.py`, `db.py`,
`frontend/src/lib/slots.ts`, the model selector or the onboarding model step (tickets 53 and 54).

### Result

Three commits after the audit, each green on `uv run pytest`, `npm run build` and `npx oxlint`.

- **20 lines deleted, 3 changed, no file removed.** The three changed lines are the dropped
  `export` keywords.
- **Dependencies:** one, `date-fns`, gone from `frontend/package.json`. It stays in the lock as
  `react-day-picker`'s own dependency, which is where the calendar was getting it from anyway.
  Nothing was removed from `pyproject.toml`: every dependency there is imported, and
  `python-multipart` is what FastAPI needs for `UploadFile` even though no file names it.
- **oxlint:** 41 before, 38 after.
- **pytest:** 348 passed, 4 skipped before and after. No test was removed.
- **Docs:** `docs/explainers/check_refs.py` passes at 395 references, and the same check widened
  to `docs/adr`, `docs/research`, `docs/course`, `bench/README.md`, `README.md` and `CONTEXT.md`
  reports 47 references with no failure. The one hit it raises, `docs/guides/choosing-a-chart.md`
  in `docs/research/charts-and-dashboard-2026-09-06.md`, is a path inside the TanStack package,
  not ours. No stale doc was found, so none was fixed or removed.
- **Left for tickets 53 and 54:** nothing. Nothing dead was found in `weblookup/`, `categorize/`,
  `extract/bill.py`, `providers.py`, `settings.py`, `local/`, `api/models.py`, `api/chat.py`,
  `db.py`, `slots.ts` or the model selector, so there is no list to hand over. The five methods
  the scan flagged there (`_TextExtractor.handle_*` in `weblookup/client.py`,
  `LlamaCppStreamedResponse._get_event_iterator` in `local/model.py`) are framework overrides,
  called by `HTMLParser` and by Pydantic AI.

Nothing needs a decision. The honest finding is that the repository was already tight: no dead
endpoint (all eighteen the scan flagged are reached by `lib/api.ts` or a test), no unused
fixture, no stale script, no commented-out code, no `console.log`, no passed-ceiling `TODO`.
What was left is the 38 oxlint warnings, and the reason they stay is in the audit table above:
30 want a file split, which the ticket's own YAGNI rule forbids, and the other 8 are behaviour
changes, not cleanup. If they are wanted, they are a ticket of their own.
