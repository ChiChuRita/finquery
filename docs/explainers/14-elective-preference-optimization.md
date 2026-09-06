# 14: Preference optimisation, built and removed

**Not a claim.** Preference optimisation via human feedback was built (ticket 15, 2026-09-04),
used through several verification sessions, and removed from the product on 2026-09-06 (ticket
59). The elective it stood for is now multimodal ingestion (08). Nothing of it ships: no thumbs,
no Regenerate pair, no A/B, no Feedback page, no `preference_record` writes, no DPO scripts.

## What it was

Thumbs up and down on every answer and every chart card. Regenerate on a chart drew the same
request a second time and put the two side by side with a Pick. A thumbs down on an answer
offered a second answer at temperature 1.2 with only the read-only query tool, again with a
Pick. Every thumb and every pick became a preference record (prompt, chosen, rejected, kind,
rating), read server-side from the stored turn rather than sent by the browser. A Feedback page
listed the records and exported them as JSONL, and `training/preference/` turned the records
with both sides into DPO datasets and a TRL training script for the fast slot's adapters.

## What it measured, and why it went

| Figure | Value | Source |
| --- | --- | --- |
| Regenerate, local | 28 s for the second chart | ticket 17, `docs/demo-script.md` before 59 |
| Thumbs, Pick | instant, no model | ticket 15 |
| Pairs collected over the whole build | a handful, from verification sessions | ticket 15 |
| Export on a verification database | one query pair, zero chart pairs (the two definitions were identical) | ticket 15 |
| Training runs | none. No adapter file was ever produced from these pairs | ticket 15 |

The data was the reason. DPO mostly measures noise below about 32 pairs, and a personal-finance
app used by one person during a build does not produce them: a demo leaves two or three. The
training half was therefore a script that validated a dataset nobody had, and the product half
was two extra buttons under every answer and every chart. Ticket 43 (SFT samples written and
judged by a strong model) is the path that does not depend on user clicks, so the elective moved
to multimodal ingestion, which the app already does under real guards.

## Where to read the code

It is in the git history, not in the tree: `git show 88c1f07^:src/finquery/preferences.py`,
`git show 88c1f07^:src/finquery/api/preferences.py`,
`git show 88c1f07^:tests/test_preferences.py`,
`git show c988577^:frontend/src/components/feedback.tsx`, and
`git log --diff-filter=D --name-only -- training/preference` for the DPO export and the train
script. The three commits that took it out are the ticket 59 commits of 2026-09-06.

The `preference_record` table is left alone in any database that already has it: ticket 59
stopped creating and reading it rather than dropping rows a user might still want to export by
hand with `sqlite3`.
