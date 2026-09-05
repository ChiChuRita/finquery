# 41: Validate every benchmark datapoint and grow the sets

**What to build:** Judge every gold datapoint of the SQL and chart benchmarks (question against reference SQL against expected rows, with the data and the taxonomy in hand), fix or drop the wrong ones, record the verdicts in the same JSON shape the validation page exports, then grow both sets with the generator once the hand-written ones are clean. The user delegated the judging on 2026-09-05.

**Blocked by:** 38 (merged)

**Status:** done

- [x] Every one of the 76 SQL and 32 chart datapoints judged with a verdict (correct, fixed, dropped) and a one-line reason where it is not simply correct; the check is against the actual data (run the SQL, inspect the rows, recompute the figure independently in Python from the raw transactions) and against the question's natural reading (period, sign, category versus subcategory, ties, language)
- [x] Wrong reference SQL fixed and gold rebuilt; ambiguous questions rewritten so one reading is right; datapoints that cannot be made unambiguous dropped; the verdicts stored at bench/validation/2026-09-05-opus.json in the page's export shape and summarized in bench/README.md
- [x] The sets grown with bench/generate.py: SQL to at least 150 datapoints and charts to at least 60, stratified by kind, difficulty and language like the hand-written ones, each generated datapoint's SQL executed and its rows stored only after it runs and returns rows, tagged generated, and each judged the same way (a generated datapoint is only kept when the judge agrees the SQL answers the question)
- [x] A held-out split marked in the files (a `split` field: train or heldout, about 30 percent held out, stratified), so later fine-tuning can use the train half for examples and the held-out half for the score
- [x] Baseline re-run on the grown sets for google/gemini-3.8-flash and qwen/qwen3.5-9b, results committed, README table updated
- [x] Tests still green (gold reproducible, sample stable)

## Comments

**2026-09-05, the judging.** Every one of the 108 hand-written datapoints was read against the
data: the question as a user reads it, the figure recomputed in Python from the raw
transactions, then the reference statement through the guard. All 108 figures reproduced to the
cent, so nothing was wrong with the arithmetic. Eight questions were wrong about what they were
asking, and are fixed: s06 (a per-week average divided by the 49 weeks that carry a grocery
booking, which made an honest division by 52 a miss), s16 and s32 and chart 10 (a word that
names a subcategory over a figure that sums the category), s20 and s41 (a column the question
never asked for, so a right answer failed the figure match), s22 (a booking count over the
spending rows where the same German words count every row in s36), s45 (a singular "who got the
most" answered with five names). Nothing was dropped. Verdicts:
`bench/validation/2026-09-05-opus.json`.

**2026-09-05, the growth.** 190 candidates drafted with google/gemini-3.8-flash, per kind and
per shape; 107 kept after the same judging (105 correct, 2 with a surplus column removed), 40
refused as wrong, 43 right but surplus. The sets are 152 questions and 63 charts, stratified
like the hand-written halves. One refusal earned a code change: a statement filtering on a
subcategory nobody carries returned a single NULL, a gold with no figure in it that every answer
would have matched, so `run_reference` now refuses rows with no figure the way it refuses no
rows.
