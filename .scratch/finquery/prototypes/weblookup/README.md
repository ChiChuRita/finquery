# Web lookup prototypes (2026-09-06)

Throwaway scripts behind `.scratch/finquery/reviews/weblookup-2026-09-06.md`. They reuse
`finquery.weblookup` unchanged and add only instruments. Not part of the app, not tested.

Run from the repo root with a `.env` that has `OPENROUTER_API_KEY`:

    uv run python .scratch/finquery/prototypes/weblookup/run_lookups.py          # step 1, the loop as it is
    uv run python .scratch/finquery/prototypes/weblookup/resolve_receipts.py     # step 3b, receipt headers
    uv run python .scratch/finquery/prototypes/weblookup/measure_categorizer.py  # step 3a, with and without

- `common.py`: the hosted fast model (Gemini 3.8 Flash) behind a token meter, an in-memory
  journal, a recording web client.
- `web_knowledge.py`: the `WebKnowledge` helper (batch, dedupe, cache, pause) and
  `widened_scrub`, a legal-form aware person rule.
- `merchants.py`: the merchant sets and their hand-assigned truth.
- `results/`: the tables (`*.md`), the full logs (`*.json`, every request that left) and the
  shared cache (`cache.json`). Delete `cache.json` to re-run the lookups for real.

Only merchant tokens leave the machine: the synthetic year and public brand names, never an
amount, a date, an IBAN or a person.
