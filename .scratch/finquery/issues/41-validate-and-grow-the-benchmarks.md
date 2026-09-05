# 41: Validate every benchmark datapoint and grow the sets

**What to build:** Judge every gold datapoint of the SQL and chart benchmarks (question against reference SQL against expected rows, with the data and the taxonomy in hand), fix or drop the wrong ones, record the verdicts in the same JSON shape the validation page exports, then grow both sets with the generator once the hand-written ones are clean. The user delegated the judging on 2026-09-05.

**Blocked by:** 38 (merged)

**Status:** ready-for-agent

- [ ] Every one of the 76 SQL and 32 chart datapoints judged with a verdict (correct, fixed, dropped) and a one-line reason where it is not simply correct; the check is against the actual data (run the SQL, inspect the rows, recompute the figure independently in Python from the raw transactions) and against the question's natural reading (period, sign, category versus subcategory, ties, language)
- [ ] Wrong reference SQL fixed and gold rebuilt; ambiguous questions rewritten so one reading is right; datapoints that cannot be made unambiguous dropped; the verdicts stored at bench/validation/2026-09-05-opus.json in the page's export shape and summarized in bench/README.md
- [ ] The sets grown with bench/generate.py: SQL to at least 150 datapoints and charts to at least 60, stratified by kind, difficulty and language like the hand-written ones, each generated datapoint's SQL executed and its rows stored only after it runs and returns rows, tagged generated, and each judged the same way (a generated datapoint is only kept when the judge agrees the SQL answers the question)
- [ ] A held-out split marked in the files (a `split` field: train or heldout, about 30 percent held out, stratified), so later fine-tuning can use the train half for examples and the held-out half for the score
- [ ] Baseline re-run on the grown sets for google/gemini-3.8-flash and qwen/qwen3.5-9b, results committed, README table updated
- [ ] Tests still green (gold reproducible, sample stable)
