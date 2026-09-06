# 59: Remove the preference feature

**What to build:** The preference optimisation feature leaves the product: thumbs on answers, the Regenerate pair with Pick, A/B, the Feedback page, the preference API, the `preference_record` table and its `model_key`, the DPO export and training scripts under `training/preference/`, and their tests. Decided by the user on 2026-09-06: multimodal ingestion is claimed instead, and the product should be as simple as possible for the grade.

**Blocked by:** 15, 34, 54 (merged)

**Status:** ready-for-agent

Decisions, settled:
- Remove, do not hide. Every caller is grepped: `api/preferences.py`, the `RERUN_TOOLS` machinery in `preferences.py`, the pair view and Pick in the chat, the thumbs in the message actions, the Feedback route and sidebar entry, `feedback.tsx`, `lib/api.ts` functions and types, the `preference_record` model and its `NEW_COLUMNS` entries (leave the table in existing databases alone; only stop creating and reading it, and drop the model class), `training/preference/` entirely, tests for all of it.
- Regenerate as a plain action (one new answer replacing the last, no pair, no pick) stays only if it exists independently of the pair machinery today; if it is part of the pair code, it goes too and the ticket says so.
- Docs: ADR for the preference feature gets a "Superseded 2026-09-06: removed, elective replaced by multimodal ingestion" line at the top; `docs/explainers/14-elective-preference-optimization.md` is replaced by a short note that the feature was built, measured and removed and why, with the pointer to the git history; the README index, the checklist row (built, removed, not claimed), CONTEXT.md terms, the demo script step and `docs/overview.html` follow. The spec's preference section gets an amendment pointer.
- The catalog and the chat message actions must keep working: run the whole suite and the build after each removal step; oxlint at or below 38.

- [ ] Backend removal (API, module, model class, columns from `NEW_COLUMNS` creation, tests); suite green
- [ ] Frontend removal (pair view, Pick, thumbs, Feedback page and route, sidebar entry, api.ts); build clean, oxlint at or below 38
- [ ] `training/preference/` removed; pyproject extras or dependencies only it used removed
- [ ] Docs: ADR superseded line, explainer 14 replaced, README index, checklist row, CONTEXT.md, demo script, overview; Comments with the line counts removed
- [ ] Headful browser check (named session, own port above 8100, throwaway database, no model call needed beyond one turn on Qwen cloud): chat message actions intact, no Feedback in the sidebar, History and the models card fine, both themes; screenshots in `/tmp/finquery-59/`
