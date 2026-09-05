# The benchmarks

Two sets of hand-written datapoints and a runner that scores any model on them: the fast local
model, the hosted ones, and later the fine-tuned adapters. The SQL set measures the query
sub-agent, the chart set measures the whole chart path. Ticket 38.

**Gold is code, not a model.** Every datapoint carries a reference statement we wrote against
`transaction_view`, and `bench/build_gold.py` runs it through the real guard against a fresh
database holding the shipped synthetic year. What that statement returns is the expected answer,
so a figure in this folder is exact, reproducible and auditable, exactly like a figure in the
app (ADR 0004).

## The two sets

| File | What is in it |
| --- | --- |
| `sql-benchmark.json` | 76 questions: German and English, kind and difficulty, an optional conversation prefix, the reference SQL and its rows |
| `chart-benchmark.json` | 32 chart requests: the 24 of `fixtures/chart-benchmark.json` that ticket 25 measured, plus eight more, each with the shape it should get, the shapes that would do as well, the column roles, the reference SQL and its rows |

The questions are the ones a household really asks, and they are hard where the review of
2026-09-05 found the models weak: relative periods ("letztes Quartal", "seit Maerz"), two periods
compared, averages per week and per month, rankings with ties, merchants spelled the way people
type them (`Edeak`, `dm`), categories against subcategories (Groceries against Supermarket),
Needs review as a bucket, refunds, income and spending in one answer, follow-ups that only mean
something after the turn before them, Denglisch, and one name the data does not carry at all.

The database is the same every time: `fixtures/synthetic/sparkasse-2025.csv` imported through
the Sparkasse preset and categorized by the profile's rules and the merchant dictionary only,
with the model stage switched off. 433 bookings from 2025-01-01 to 2025-12-28, 384 categorized,
49 Needs review (the rent, the salary and the four friends paid through PayPal). No model runs
while it is built, which is why a gold row never moves.

`today` in each file is `2025-12-31`, and the runner builds the query prompt with it, so this
month is December 2025, last month is November, this quarter is the fourth and last quarter is
the third. Without that pin every relative period would ask about a year with no data in it.

### What a datapoint holds

```json
{
  "id": "s70-last-quarter-de",
  "kind": "period",           // total, breakdown, comparison, trend, ranking, entity, follow-up, period
  "difficulty": 3,            // 1 one filter, 2 two things at once, 3 what the small models get wrong
  "language": "de",
  "question": "Wie viel habe ich letztes Quartal ausgegeben?",
  "prefix": [],               // earlier questions of the conversation, for a follow-up
  "tags": ["relative period", "quarter", "German"],
  "why": "Letztes Quartal is the quarter before the one today falls in, so July to September.",
  "source": "hand",           // or "generated"
  "sql": "SELECT ...",        // the reference statement
  "gold": { "columns": [...], "rows": [...] }   // written by build_gold.py, never by hand
}
```

A chart datapoint carries `shape`, `also` (shapes that answer the request as directly),
`roles` (what the columns have to be, in order: a position or a label, an optional series, the
euro figure last) and `covers` instead of `tags`.

## Running it

```sh
uv run finquery-bench --set sql   --model google/gemini-3.8-flash
uv run finquery-bench --set chart --model qwen/qwen3.5-9b
uv run finquery-bench --set all   --model fast --n 20 --seed 7
uv run finquery-bench compare bench/results/A.json bench/results/B.json
```

| Flag | Meaning |
| --- | --- |
| `--set` | `sql`, `chart` or `all` |
| `--model` | a slot on the current provider (`fast`, `quality`), any OpenRouter id, or `local:<slot>` |
| `--adapter` | `query` or `chart`, a LoRA adapter attached for the whole run (local only) |
| `--n` | run a sample of this many datapoints instead of all of them |
| `--seed` | which sample `--n` takes; the same seed is the same datapoints |
| `--out` | where the result files go, `bench/results` by default |

Every slot the path asks for resolves to the model under test, so a run never quietly answers
half its datapoints on something else. Sub-agent settings are the app's own
(`providers.subagent_settings`): reasoning off, 3072 output tokens.

A run writes two files, `results/<timestamp>-<model>-<set>.json` (every statement, every row,
every refusal and the per-datapoint seconds) and `.md` (the table below).

### What is scored

- **figure match**: every number in the gold rows comes back in the model's rows, to the cent.
  Column names, their order and an extra column are not judged, because two statements that
  answer the same question rarely look alike. What is judged is that the result is not a dump:
  more than three times the reference's rows has handed over the table instead of answering.
  A datapoint whose honest answer is "the data holds none of that" (`"answer": "none"`) matches
  when the statement returns no rows or only zeroes.
- **SQL valid**: the guard admitted the statement and SQLite ran it.
- **first attempt**: it did so without a repair round. `run_query` retries once with the
  refusal in the prompt, and so does the runner, so this is the number that separates a model
  that writes the statement from one that eventually finds it.
- **shape match** (charts): the plan chose `shape` or one of `also`.
- **columns map** (charts): the rows carry one column per role, names first and the euro figure
  last.
- **language** (charts): the caption is in the language of the request.
- **drawn** (charts): a chart is on screen, which is `rendered` in the tool result.
- **median and p90 seconds**, per datapoint, measured one after the other so the numbers are
  what a user would wait.

Everything is reported overall, per kind (per shape for charts) and per difficulty.

## The baseline

Both sets on OpenRouter on 2026-09-05, one datapoint after another, reasoning off. The result
files are in `results/`.

| set | model | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | p90 s | run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sql | google/gemini-3.8-flash | 76 | **92 %** | 99 % | - | - | - | - | 97 % | 2.3 | 13.0 | 5m 20s |
| sql | qwen/qwen3.5-9b | 76 | **45 %** | 91 % | - | - | - | - | 75 % | 2.2 | 7.0 | 4m 48s |
| chart | google/gemini-3.8-flash | 32 | **94 %** | 100 % | 97 % | 94 % | 100 % | 97 % | 97 % | 6.3 | 7.9 | 3m 26s |
| chart | qwen/qwen3.5-9b | 32 | **41 %** | 100 % | 94 % | 69 % | 97 % | 53 % | 34 % | 9.6 | 33.2 | 7m 55s |

Figure match per kind of question, and per difficulty:

| | n | gemini-3.8-flash | qwen3.5-9b |
| --- | ---: | ---: | ---: |
| breakdown | 9 | 89 % | 11 % |
| comparison | 8 | 100 % | 50 % |
| entity | 14 | 93 % | 57 % |
| follow-up | 8 | 88 % | 38 % |
| period | 9 | 100 % | 44 % |
| ranking | 9 | 100 % | 44 % |
| total | 12 | 92 % | 50 % |
| trend | 7 | 71 % | 57 % |
| difficulty 1 | 13 | 100 % | 77 % |
| difficulty 2 | 36 | 89 % | 31 % |
| difficulty 3 | 27 | 93 % | 48 % |

Figure match per shape:

| | n | gemini-3.8-flash | qwen3.5-9b |
| --- | ---: | ---: | ---: |
| line | 5 | 100 % | 80 % |
| area | 3 | 100 % | 0 % |
| bar | 8 | 88 % | 50 % |
| bar_horizontal | 3 | 100 % | 33 % |
| bar_grouped | 3 | 100 % | 0 % |
| bar_stacked | 3 | 100 % | 67 % |
| doughnut | 4 | 75 % | 50 % |
| sankey | 3 | 100 % | 0 % |

What the two runs say, beyond the headline:

- **Qwen3.5 9B should not write the SQL.** 45 of 100 figures right, and difficulty 2 (a period
  and a category at once) is worse than difficulty 3 for it, which is what a model that guesses
  the shape of an answer looks like. The capability read of 2026-09-05 said the same after 46
  questions through the UI; this set says it in five minutes.
- Half of Qwen's charts never reach the screen (53 % drawn, 34 % first attempt), and the two it
  cannot do at all are the ones that need a second dimension: every grouped bar and every
  sankey failed. Its queries are valid SQL (100 %) and answer the wrong question.
- Gemini's six SQL misses are worth reading, because none of them is sloppiness: it answers
  "groceries" with a list of supermarket names instead of the profile's own `Groceries`
  category four times (`s16`, `s32`, `s33`, `s62`), it divides a weekly average by 52 rather
  than by the weeks the data covers (`s06`), and it once narrowed a PayPal question with a
  category filter that matches nothing (`s58`). Every one of those is a prompt fix, not a
  weights problem.
- The doughnut is the only shape Gemini drops (75 %), which is the same weakness ticket 25
  measured.

### What a full run costs

| | gemini-3.8-flash | qwen3.5-9b |
| --- | ---: | ---: |
| SQL set, 76 datapoints | 5m 20s, 4.2 s each | 4m 48s, 3.8 s each |
| chart set, 32 datapoints | 3m 26s, 6.4 s each | 7m 55s, 14.8 s each |
| both sets | **8m 46s** | **12m 43s** |

A SQL datapoint is one model call (1.01 on average for Gemini, 1.24 for Qwen, which pays for
its refused statements), a chart is three to five. The query prompt is about 9.000 characters, so the SQL set is roughly 190k input tokens
and the chart set two to three times that: a full run on a hosted flash model is cents, not
euros. The runner does not meter tokens, so that is arithmetic over the prompts and not a bill.
Running the four combinations above as four processes at once takes about as long as the
slowest one.

## Validate, then grow

A set nobody has read is not gold, it is a guess with a schema. The loop is:

1. **Cut a sample**: `uv run finquery-bench sample --seed 7` writes
   `bench/validate/sample.json`, a stratified 30: 20 SQL datapoints spread over the eight kinds
   and 10 charts spread over the shapes.
2. **Read them by hand** on the validation page (below). Each one shows the question, its tags,
   what makes it hard, the reference SQL and the expected rows as a table, and for a chart its
   shape and column roles. Mark **Correct**, **Wrong** or **Unsure** and leave a note.
   Labels live in the browser's localStorage under a key that carries the seed, and **Export
   JSON** writes them out.
3. **Fix what the review found** in the JSON, then `uv run python bench/build_gold.py` to
   recompute the rows. The build fails loudly on a statement the guard refuses, one SQLite
   cannot run and one that answers nothing, with the datapoint's id.
4. **Grow the set** only then: `uv run python bench/generate.py --n 10 --kind entity` drafts
   more datapoints with a hosted model (`google/gemini-3.8-flash` by default) against the same
   view schema and household facts the query sub-agent gets. Nothing it writes is trusted: each
   candidate statement goes through the guard and is executed, and only one that runs and
   returns rows is appended, tagged `generated` with the rows it returned as its gold. Use
   `--dry-run` to look first.
5. **Read the generated ones too**, with a fresh sample, before anybody quotes a number that
   rests on them.

### Opening the validation page

No build step and no server of ours:

```sh
cd bench/validate
uv run python -m http.server 8123      # any free port, not 8000, 5173, 8111 or 8112
open http://127.0.0.1:8123/
```

`1`, `2`, `3` label the datapoint, the arrow keys move, the numbered squares jump. The summary
line at the top counts what is reviewed and what is left.

## Later: the local slots and the adapters

Nothing has to change here when the models move in process. The runner resolves
`local:fast` through the same `finquery.providers` the app uses, and `--adapter query` attaches
the LoRA adapter for the whole run through the `finquery_adapter` model setting, so a
before-and-after measures weights and nothing else:

```sh
FINQUERY_PROVIDER=local uv run finquery-bench --set sql --model local:fast
FINQUERY_PROVIDER=local uv run finquery-bench --set sql --model local:fast --adapter query
uv run finquery-bench compare bench/results/<base>.json bench/results/<adapter>.json
```

Expect the local numbers to be slower by an order of magnitude, and run the sets with `--n` on
a laptop that is also serving a demo.

## The files

| File | What it is |
| --- | --- |
| `sql-benchmark.json`, `chart-benchmark.json` | the sets, gold included |
| `build_gold.py` | recomputes every gold row through the guard; run it after any edit |
| `generate.py` | drafts more datapoints with a hosted model, keeps only the ones that run |
| `finquery_bench/` | the runner: the database, the sets, the scoring, the tables, the CLI |
| `validate/` | the validation page and its sample |
| `results/` | one JSON and one markdown table per run |
| `pyproject.toml` | makes this folder a small package so `uv run finquery-bench` finds it |

The tests are `tests/test_bench.py` in the main suite: gold that rebuilds identically, a runner
scoring a scripted right and a scripted wrong statement, the compare diff, and a review sample
that is stable for its seed. No test calls a model.
