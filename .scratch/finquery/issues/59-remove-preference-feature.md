# 59: Remove the preference feature

**What to build:** The preference optimisation feature leaves the product: thumbs on answers, the Regenerate pair with Pick, A/B, the Feedback page, the preference API, the `preference_record` table and its `model_key`, the DPO export and training scripts under `training/preference/`, and their tests. Decided by the user on 2026-09-06: multimodal ingestion is claimed instead, and the product should be as simple as possible for the grade.

**Blocked by:** 15, 34, 54 (merged)

**Status:** done

Decisions, settled:
- Remove, do not hide. Every caller is grepped: `api/preferences.py`, the `RERUN_TOOLS` machinery in `preferences.py`, the pair view and Pick in the chat, the thumbs in the message actions, the Feedback route and sidebar entry, `feedback.tsx`, `lib/api.ts` functions and types, the `preference_record` model and its `NEW_COLUMNS` entries (leave the table in existing databases alone; only stop creating and reading it, and drop the model class), `training/preference/` entirely, tests for all of it.
- Regenerate as a plain action (one new answer replacing the last, no pair, no pick) stays only if it exists independently of the pair machinery today; if it is part of the pair code, it goes too and the ticket says so.
- Docs: ADR for the preference feature gets a "Superseded 2026-09-06: removed, elective replaced by multimodal ingestion" line at the top; `docs/explainers/14-elective-preference-optimization.md` is replaced by a short note that the feature was built, measured and removed and why, with the pointer to the git history; the README index, the checklist row (built, removed, not claimed), CONTEXT.md terms, the demo script step and `docs/overview.html` follow. The spec's preference section gets an amendment pointer.
- The catalog and the chat message actions must keep working: run the whole suite and the build after each removal step; oxlint at or below 38.

- [x] Backend removal (API, module, model class, columns from `NEW_COLUMNS` creation, tests); suite green
- [x] Frontend removal (pair view, Pick, thumbs, Feedback page and route, sidebar entry, api.ts); build clean, oxlint at or below 38
- [x] `training/preference/` removed; pyproject extras or dependencies only it used removed
- [x] Docs: ADR superseded line, explainer 14 replaced, README index, checklist row, CONTEXT.md, demo script, overview; Comments with the line counts removed
- [x] Headful browser check (named session, own port above 8100, throwaway database, no model call needed beyond one turn on Qwen cloud): chat message actions intact, no Feedback in the sidebar, History and the models card fine, both themes; screenshots in `/tmp/finquery-59/`

## Comments

Done 2026-09-06. 2433 lines removed against 192 added, in four commits.

- **Backend (1121 removed, 63 added).** `src/finquery/preferences.py` (225),
  `src/finquery/api/preferences.py` (381) and `tests/test_preferences.py` (421) are gone, with
  the `PreferenceRecord` class and its docstring in `db.py` (48), its `NEW_COLUMNS` entry, the
  router line in `app.py` and the `ratings` list on `GET /api/conversations/{id}` (30). The
  table is untouched in any database that has it: nothing creates it, nothing reads it.
- **Three helpers were never about preferences and moved rather than died.** `turn_or_404`,
  `chart_or_404` and the chart half of `read_turn` (now `turn_charts`, `TurnCharts`) live in
  `src/finquery/api/charts.py`, next to the code that writes a chart onto a turn; the
  render-failure retry and Add to dashboard are their two callers. The answer half of
  `TurnContent` (text, tools, `beyond_rerun`) had no caller left and went with the rest.
- **Frontend (706 removed, 12 added).** `feedback.tsx` (263) and `feedback-page.tsx` (151), the
  `/feedback` route and its sidebar row, the thumbs, the A/B and `RERUNNABLE_PARTS` in
  `chat-view.tsx` (77), the pair view and Regenerate in `chart-tool.tsx` (132), and the
  preference types and calls in `lib/api.ts` (89).
- **No plain Regenerate survived, because there was none.** The button called
  `POST /api/preferences/chart-alternative` and existed only to draw the second half of a pair,
  so it went with the pair. The card keeps its frame, its details, Add to dashboard and the
  server-side retry a failed render already triggers by itself.
- **`training/preference/` (363) removed whole.** No dependency came out with it: `trl`, `peft`
  and `bitsandbytes` were always a `pip install` line in that folder's README, never in
  `pyproject.toml`.
- **Docs (232 removed, 116 added).** Explainer 14 is now a short "built, measured, removed"
  note with the reason (the pairs never came: a handful over the whole build, and DPO below
  about 32 pairs measures noise) and `git show` pointers into the history. The checklist rows
  say built, removed, not claimed; the multimodal row is ticket 58's. README index, root
  README, CONTEXT.md (the Preference record term and the Profile line), the demo script (steps
  24 and 25 out, section 11 renamed, the rest renumbered, the timings table), `overview.html`,
  and the spec's two preference sections with an amendment pointer. There is no ADR of its own
  for the feature: the two ADRs that named it (0001's "our code" list, 0013's `model_key`
  columns) now say it was removed on 2026-09-06 and point at explainer 14. Explainers 01, 02,
  04, 05, 07, 10, 12, 13, 15, `chart-runtime.md` and the ticket 57 research note lost their
  dangling references. `uv run python docs/explainers/check_refs.py`: 369 references, 0
  failures.
- Suite 399 passed, 4 skipped before; 389 passed, 4 skipped after (`test_preferences.py` was
  ten). `npm run build` clean, `oxlint` 38 before and 36 after (the two were `feedback.tsx`).
- Browser: headful session `ticket59` on port 8137 with a throwaway database and Qwen on both
  cloud slots. One turn ("What can you help me with?") answered on `openrouter:qwen/qwen3.5-9b`.
  The message toolbar under the answer is the model chip and nothing else, no thumbs and no
  "Compare a second answer"; the sidebar is Dashboard, Transactions, Imports, Memory, Settings,
  with no Feedback; a reload rebuilt the transcript and the conversation row (the detail no
  longer carries `ratings`); Settings shows the four catalog entries, the two fast slots and
  the adapter lines. Both themes, no console errors, no error in the server log. A bookmarked
  `/feedback` is the router's plain "Not Found", the same as any unknown path. Screenshots:
  `/tmp/finquery-59/`.
