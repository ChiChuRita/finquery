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
| `sql-benchmark.json` | 152 questions: German and English, kind and difficulty, an optional conversation prefix, the reference SQL and its rows |
| `chart-benchmark.json` | 73 chart requests: each with the shape it should get, the shapes that would do as well, the column roles, the reference SQL and its rows |

Half of each set was written by hand and half was drafted by a model and then judged one by one
(`source: "hand"` or `"generated"`, and the generated ones also carry a `generated` tag). Every
datapoint of both halves has been read against the data, question by question and figure by
figure. What that found is in `validation/`, below.

The questions are the ones a household really asks, and they are hard where the review of
2026-09-05 found the models weak: relative periods ("letztes Quartal", "seit Maerz"), two periods
compared, averages per week and per month, rankings with ties, merchants spelled the way people
type them (`Edeak`, `dm`, `Gesammtbetrag`, umlauts written both ways), categories against
subcategories (Groceries against Supermarket), Needs review as a bucket, refunds, income and
spending in one answer, follow-ups that only mean something after the turn before them,
Denglisch, and one name the data does not carry at all.

The database is the same every time: `fixtures/synthetic/sparkasse-2025.csv` imported through
the Sparkasse preset and categorized by the profile's rules and the merchant dictionary only,
with the model stage switched off. 433 bookings from 2025-01-01 to 2025-12-28, 384 categorized,
49 Needs review (the rent, the salary and the four friends paid through PayPal). No model runs
while it is built, which is why a gold row never moves.

`today` in each file is `2025-12-31`, and the runner builds the query prompt with it, so this
month is December 2025, last month is November, this quarter is the fourth and last quarter is
the third. Without that pin every relative period would ask about a year with no data in it.

### What is in them

The SQL set, by kind, with how many of each are hand-written, German, and held out of training:

| kind | n | hand | generated | German | heldout |
| --- | ---: | ---: | ---: | ---: | ---: |
| entity | 28 | 14 | 14 | 14 | 9 |
| total | 24 | 12 | 12 | 10 | 10 |
| breakdown | 18 | 9 | 9 | 9 | 7 |
| period | 18 | 9 | 9 | 9 | 6 |
| ranking | 18 | 9 | 9 | 8 | 5 |
| comparison | 16 | 8 | 8 | 7 | 5 |
| follow-up | 16 | 8 | 8 | 7 | 5 |
| trend | 14 | 7 | 7 | 6 | 3 |
| difficulty 1 | 23 | 13 | 10 | 9 | 6 |
| difficulty 2 | 76 | 36 | 40 | 33 | 24 |
| difficulty 3 | 53 | 27 | 26 | 28 | 20 |
| **all** | **152** | 76 | 76 | 70 | 50 |

The chart set, by shape:

| shape | n | hand | generated | German | heldout |
| --- | ---: | ---: | ---: | ---: | ---: |
| bar | 17 | 10 | 7 | 9 | 7 |
| line | 14 | 9 | 5 | 7 | 5 |
| doughnut | 8 | 4 | 4 | 5 | 2 |
| area | 8 | 5 | 3 | 5 | 2 |
| bar_horizontal | 6 | 3 | 3 | 2 | 2 |
| bar_grouped | 8 | 5 | 3 | 4 | 2 |
| bar_stacked | 6 | 3 | 3 | 2 | 1 |
| sankey | 6 | 3 | 3 | 3 | 3 |
| difficulty 1 | 4 | 4 | 0 | 2 | 1 |
| difficulty 2 | 39 | 18 | 21 | 21 | 13 |
| difficulty 3 | 30 | 20 | 10 | 14 | 10 |
| **all** | **73** | 42 | 31 | 37 | 24 |

Two of the newest are the line's own hard case, one per language (`33-grocery-lines-de` and
`34-grocery-lines-en`, ticket 50): five grocery shops over twelve months, which is five strokes
and a legend rather than one line or sixty bars. Their rows come long, one per month and shop,
and they are sparse, because no shop has a booking in every month.

Four more are ticket 52's, the household questions the existing shapes were failing.
`35-this-month-versus-last-en` and `36-...-de` compare two periods by category, which is the
grouped bar with the period as the series and the category as the position, long rows again.
`37-change-per-month-en` and `38-...-de` ask how much more or less each month cost than the one
before it, which is the one figure in this year that really crosses zero: six months below the
baseline and five above it. `39-average-line-en` and `40-...-de` ask where the average lies,
which is the reference line: the statement returns the twelve months and nothing else, and the
chart computes the mean of the rows it was handed. `41-cumulative-halves-en` and `42-...-de` are
the pacing chart, a running total inside each period with the period as the series: two bands
lying over each other, the answer read off the gap. Two years would be the same picture with
the year as the series, and the shipped dataset holds one year, so its two halves are the
periods.

Adding those six re-cut two strata, so `20-daily-march-en` moved from the held-out third into
the training two thirds and both German twins of the new pairs went the other way. That is the
splitter doing its own job (`finquery_bench.splits`), and it is why the worked plans in the
chart prompt are drawn from whichever half of a pair landed in `train`.

No generated chart came out at difficulty 1: a request the drafter wrote always carried a period
and a grouping, and calling one of those easy would have been flattery.

### Train and heldout

Every datapoint carries `split`, `train` or `heldout`. A model fine-tuned on examples drawn from
the set it is then scored on is scored on its memory, so about a third of each set is kept out of
the examples: 50 of the 152 questions and 24 of the 73 charts. The rule is
`finquery_bench.splits`, run through `uv run python bench/split.py`, and it is written into the
files rather than drawn at run time, so a number from the held-out half means the same thing in
six months as it does today. It is stratified over kind (shape for charts), hand against
generated, language and difficulty, and inside a stratum the choice is a hash of the id, so
adding a datapoint somewhere else never moves it.

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
  "source": "hand",           // or "generated", drafted by a model and then judged
  "split": "train",           // or "heldout", about a third of each set
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
uv run finquery-bench --set e2e   --model local:qwen3.5-9b
uv run finquery-bench compare bench/results/A.json bench/results/B.json
uv run finquery-bench compare bench/results/{E4B,Qwen,Gemma12B}-sql.json
```

| Flag | Meaning |
| --- | --- |
| `--set` | `sql`, `chart`, `all`, or `e2e` (the end-to-end subset, below) |
| `--model` | a catalog key (`local:gemma-4-e4b`, `local:qwen3.5-9b`, `local:gemma-4-12b`), a role on the current provider (`fast`, `quality`), or any OpenRouter id |
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

`compare` with two runs prints them side by side and names the datapoints that changed hands.
With three or more it prints the table the candidates are chosen from, then each of them
against the first.

### The end-to-end subset

`--set e2e` is the same datapoints with a whole chat turn in front of the sub-agent: the chat
agent reads the question, decides which tool to call and writes the request the sub-agent gets,
and the tool result is held to the same figure match and shape match. The candidate answers both
roles, so the number is about one model.

Thirty cases, 15 questions and 15 chart requests, cut with a fixed seed from the **training**
half of each set and stratified over the kinds and the shapes. Fixed in code (`E2E_SEED`), not
on the command line: three models have to be compared on the same thirty, and so does the same
model after a fine-tune.

Two things read differently here:

- **figure match** is true when one of the turn's calls carried the gold figures. The chat agent
  is told to sharpen a request that came back answering less than the question asked, so a turn
  that got there on its second try got there.
- **first attempt** is the stricter number: the request it wrote first was already the right one.

A turn that never called the tool at all is a miss whose error says so, which is the routing
loss this subset exists to measure. The request the chat agent wrote is kept on every result.

The sub-agent sets stay the primary numbers: an adapter attaches to the sub-agent, and this
subset is 30 cases against their 225.

## The baseline

Both grown sets on OpenRouter on 2026-09-05, `--set all`, one datapoint after another, reasoning
off. The result files are in `results/`, one per model, and they hold every statement, every row
and every refusal.

| set | model | n | figure match | SQL valid | shape match | columns map | language | drawn | first attempt | median s | p90 s | run |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sql | google/gemini-3.8-flash | 152 | **93 %** | 98 % | - | - | - | - | 97 % | 1.9 | 3.5 | 7m 23s |
| sql | qwen/qwen3.5-9b | 152 | **57 %** | 92 % | - | - | - | - | 79 % | 1.7 | 4.7 | 6m 38s |
| chart | google/gemini-3.8-flash | 63 | **92 %** | 100 % | 98 % | 95 % | 100 % | 98 % | 97 % | 6.3 | 7.5 | 6m 53s |
| chart | qwen/qwen3.5-9b | 63 | **40 %** | 100 % | 94 % | 71 % | 89 % | 60 % | 38 % | 7.5 | 11.9 | 8m 51s |

Figure match per kind of question, and per difficulty:

| | n | gemini-3.8-flash | qwen3.5-9b |
| --- | ---: | ---: | ---: |
| entity | 28 | 96 % | 54 % |
| total | 24 | 96 % | 62 % |
| breakdown | 18 | 94 % | 67 % |
| period | 18 | 100 % | 83 % |
| ranking | 18 | 83 % | 67 % |
| comparison | 16 | 100 % | 56 % |
| follow-up | 16 | 81 % | 19 % |
| trend | 14 | 86 % | 43 % |
| difficulty 1 | 23 | 100 % | 78 % |
| difficulty 2 | 76 | 91 % | 57 % |
| difficulty 3 | 53 | 92 % | 49 % |

Figure match per shape:

| | n | gemini-3.8-flash | qwen3.5-9b |
| --- | ---: | ---: | ---: |
| line | 10 | 90 % | 80 % |
| area | 6 | 67 % | 0 % |
| bar | 15 | 87 % | 47 % |
| bar_horizontal | 6 | 100 % | 50 % |
| bar_grouped | 6 | 100 % | 33 % |
| bar_stacked | 6 | 100 % | 33 % |
| doughnut | 8 | 100 % | 12 % |
| sankey | 6 | 100 % | 33 % |

And by where a datapoint came from and which half it is in, which is the check that the grown
half is a real measurement and not filler:

| | n | gemini-3.8-flash | qwen3.5-9b |
| --- | ---: | ---: | ---: |
| hand-written | 108 | 92 % | 56 % |
| generated | 107 | 93 % | 49 % |
| train | 145 | 92 % | 57 % |
| heldout | 70 | 94 % | 43 % |

What the two runs say, beyond the headline:

- **The generated half is as hard as the hand-written half.** Gemini is within a point of itself
  on both (92 % against 93 %) and Qwen is seven points worse on the generated one, so growing the
  set did not water it down. The held-out third is not a soft third either: Qwen scores 43 % on
  it against 57 % on the training two thirds, which is the number to watch once an adapter has
  been trained on the training half.
- **Qwen3.5 9B still should not write the SQL**, and the bigger set is what makes that
  sentence worth anything. On the 76 questions of the old set it scored 45 %, then 58 %, then
  50 % on three runs of the same weights, so nothing under about ten points could be read there
  at all. 57 % of 152 is the same model with half the error bar. Its follow-ups are the collapse
  (19 % of 16): three words that inherit a period and a filter are the thing a 9B model cannot
  carry.
- **Half of Qwen's charts still never reach the screen** (60 % drawn, 38 % first attempt, 2.08
  model calls per chart against Gemini's 1.02), and the doughnut is now its worst shape (12 %),
  where the area chart is the one it cannot do at all.
- **Gemini's sixteen misses are one habit and a handful of slips.** Six of them answer a topic
  the household has a category for with a list of merchant names it wrote itself: `s06`, `s16`,
  `s32`, `s62`, `g002-follow-up` and `g007-follow-up` all match `%rewe%`, `%aldi%` or
  `%dm drogerie%` where `category = 'Groceries'` or the `Drugstore` subcategory was asked for,
  and each one silently loses the drugstore, the bakery or Rossmann. Two more filter on a
  category the data does not carry (`category = 'Income'`, `category = 'Transfers'`) and get no
  rows at all. Three ran out of output tokens before writing a statement. The last five are real
  slips: one statement with no sign filter, so the salary came back as the largest expense
  (`s46`), two cumulative charts drawn as plain monthly series (`04`, `g003-area`), one
  two-month comparison answered with a category breakdown (`18`), and one chart that folded its
  own tail into an `Other` row the prompt tells it never to ask for (`g007-bar`).
- Every one of those is a prompt fix rather than a weights problem, and the set now measures it
  on 215 datapoints instead of 108.

### What a full run costs

| | gemini-3.8-flash | qwen3.5-9b |
| --- | ---: | ---: |
| SQL set, 152 datapoints | 7m 23s, 2.9 s each | 6m 38s, 2.6 s each |
| chart set, 63 datapoints | 6m 53s, 6.6 s each | 8m 51s, 8.4 s each |
| both sets, wall clock | **14m 16s** | **15m 30s** |

A SQL datapoint is one model call (1.01 on average for Gemini, 1.21 for Qwen, which pays for its
refused statements), a chart is three to five (1.02 and 2.08 repair rounds on top). OpenRouter's
credit meter moved 1,27 USD over both runs together, and that figure also carries the forty or so
datapoints of two aborted starts, so a full run of both sets is around fifty to sixty cents per
model: cents, not euros. Running the two models as two processes at once takes about as long as
the slower one.

## The three local candidates on the cluster

2026-09-06, on the HPI cluster: Gemma 4 E4B, Qwen3.5 9B and Gemma 4 12B, the same Q4_K_M GGUFs
and wire formats the laptop runs, through llama-cpp with CUDA on one RTX PRO 6000 per job, 32k
context. `training/cluster/` holds the scripts and
`results/20260906-cluster-compare.md` the whole thing, per kind and per difficulty, with the
decision rule.

| model | sql | chart | chart drawn | e2e | median s (sql / chart / e2e) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemma 4 E4B | 66 % | 45 % | 90 % | 53 % | 8.2 / 34.9 / 34.3 |
| Qwen3.5 9B | 70 % | 42 % | 78 % | 73 % | 25.4 / 45.1 / 50.8 |
| **Gemma 4 12B** | **87 %** | **81 %** | **94 %** | **77 %** | 10.0 / 46.7 / 46.9 |

Figure match, 152 questions, 73 charts, 30 end-to-end cases. First attempt on the SQL set is
75 %, 30 % and 82 %: Qwen writes a statement that runs and is then sent back by the check pass,
which is also why its SQL run took 87 minutes against the 12B's 31. The seconds are the
cluster's GPU and say nothing about the laptop, where the pair costs 5.9 GB plus 7 GB and the
generation rates in `results/20260906-local-tokens-per-second.md`.

## Validated, then grown

A set nobody has read is not gold, it is a guess with a schema. On 2026-09-05 every datapoint of
both sets was read against the data, one at a time, by a judge who was told to be unforgiving:

1. read the question the way a user would (period, sign, category against subcategory, ties,
   singular against plural, the language it is in);
2. write down the figure that reading expects, and compute it in Python from the raw
   transactions, without running the reference statement;
3. only then run the reference statement through the guard and compare the rows and the figure;
4. record **correct**, **fixed** (with what was wrong) or **dropped** (with why it cannot be
   made unambiguous).

The verdicts are `validation/2026-09-05-opus.json`, in the shape the validation page exports
(`id`, `set`, `kind`, `question`, `verdict`, `note`), so a later review on the page can be read
beside them.

| | correct | fixed | dropped |
| --- | ---: | ---: | ---: |
| the 76 hand-written questions | 69 | 7 | 0 |
| the 32 hand-written charts | 31 | 1 | 0 |
| the 107 generated datapoints kept | 105 | 2 | 0 |
| the generated candidates refused | - | - | 40 |

All 108 hand-written figures reproduced from the raw transactions, to the cent. What was wrong
was never the arithmetic, it was the question: the eight fixes are in the notes, and they are
about a divisor a question never named (s06 divided by the 49 weeks that carry a grocery booking,
which made an honest division by 52 count as a miss), a word that names a subcategory over a
figure that sums the category (s16, s32 and chart 10), a column the question never asked for
(s20, s41), a count over the spending rows where the same words count every row elsewhere (s22),
and a "who got the most" answered with five names (s45).

Then the sets were grown. `bench/generate.py` drafted 190 candidates with
`google/gemini-3.8-flash`, in batches per kind and per shape; the guard and the database threw
out the ones whose statement did not run or returned nothing; the judge read every survivor the
same way and kept 107. Of the 83 it did not keep, 40 were wrong (the reasons are in the
validation file: an exclusion of a subcategory no booking carries, "letztes Quartal" read as
October, a top three of a category with one subcategory, a doughnut of one slice, a grouped bar
against a category with no bookings) and 43 were right but surplus, a figure the set already had
or one more of a kind that was full.

One refusal was worth a code change: a statement that filtered on a `Salary` subcategory nobody
carries returned a single NULL, which is a gold with no figure in it, so every answer would have
matched it. `run_reference` now refuses rows with no figure the same way it refuses no rows.

### Growing it further

```sh
uv run python bench/generate.py --set sql   --n 10 --kind entity   --dry-run
uv run python bench/generate.py --set chart --n 8  --shape doughnut
uv run python bench/build_gold.py
uv run python bench/split.py
```

A drafted datapoint is a question, its statement and, for a chart, the shape, the shapes that
would answer it as well and the column roles. Nothing it writes is trusted: every statement goes
through the guard and is executed, a chart's claimed roles are checked against the columns the
statement really returned, and only what survives is appended, tagged `generated`. `--dry-run`
prints what would be kept and writes nothing, which is how the drafts of a batch are read before
any of them enters a set. Then rebuild the gold rows and the split, and judge the new ones by
the four steps above before anybody quotes a number that rests on them.

### Opening the validation page

No build step and no server of ours:

```sh
cd bench/validate
uv run python -m http.server 8124      # any free port, not 8000, 5173, 8111, 8112 or 8123
open http://127.0.0.1:8124/
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
| `split.py` | marks every datapoint train or heldout; run it after adding datapoints |
| `generate.py` | drafts more datapoints with a hosted model, keeps only the ones that run |
| `finquery_bench/` | the runner: the database, the sets, the scoring, the splits, the tables, the CLI |
| `finquery_bench/e2e.py` | the end-to-end subset: one chat turn, and the scoring of what its tool gave it |
| `validate/` | the validation page and its sample |
| `validation/` | what a review of the whole set found, one file per review |
| `results/` | one JSON and one markdown table per run |
| `pyproject.toml` | makes this folder a small package so `uv run finquery-bench` finds it |

The cluster runs are `training/cluster/`: the three candidates on all three sets on one A100
per job, with its own README.

The tests are `tests/test_bench.py` and `tests/test_bench_e2e.py` in the main suite: gold that rebuilds identically, a
reference that answers nothing and one whose rows carry no figure both failing the build, a
runner scoring a scripted right and a scripted wrong statement, the compare diff, a review sample
that is stable for its seed, and a split that is about a third of each set and does not move when
a datapoint is added elsewhere. The end-to-end tests cover the subset (thirty training cases,
stable, spread over the kinds) and the scoring (the first call right, a sharpened second call,
a turn that called nothing, a chart of the wrong shape), plus one scripted turn through the real
chat agent. No test calls a model.

## Check and retry

Ticket 40 put two judgements between a statement and its answer, and ticket 42's prompt work
went into the same sub-agent: nine worked examples drawn from this set's train split, a required
`reasoning` field the model fills before its SQL, and a retry that shows it its own reading
instead of asking for a fresh start. `--no-check` turns ticket 40 off (the degenerate rewrite and
the check pass both), so a run measures the check against the prompt it runs with.

```sh
uv run finquery-bench --set sql   --model qwen/qwen3.5-9b --no-check   # the prompt alone
uv run finquery-bench --set sql   --model qwen/qwen3.5-9b              # and with the check
```

Three runs per model, then, and the first is the baseline above:

| | the prompt | the check |
| --- | --- | --- |
| **baseline** | before ticket 40 | off |
| **no check** | after | off |
| **check** | after | on |

### What the prompt is worth

One complete run, `qwen/qwen3.5-9b` on the SQL set, `--no-check`, against the same 152
datapoints as the baseline
(`results/20260905T182106Z-qwen-qwen3.5-9b-nocheck-sql.json`, written at commit `687f3f5`, so
with the examples and the reasoning field but before the field was made required):

| | n | figure match | heldout | SQL valid | first attempt | median s | p90 s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline | 152 | 57 % | 48 % | 92 % | 79 % | 1.7 | 4.8 |
| the new prompt, no check | 152 | **69 %** | **64 %** | 99 % | 85 % | 2.8 | 7.3 |

Twelve points, and sixteen on the held-out third, which is the half the examples were not drawn
from. Per kind, the two rows above:

| kind | baseline | new prompt |
| --- | ---: | ---: |
| total | 62 % | 88 % |
| entity | 54 % | 75 % |
| follow-up | 19 % | 44 % |
| trend | 43 % | 57 % |
| breakdown | 67 % | 72 % |
| comparison | 56 % | 62 % |
| period | 83 % | 89 % |
| ranking | 67 % | **50 %** |

Every kind gains except ranking, which loses seventeen points: the one worked example of a
ranking is a top five with a `LIMIT 5`, and a model that copies it puts a limit on rankings that
did not ask for one. That example is the first thing to change when this is picked up again.

`google/gemini-3.8-flash` on the same run went from 93 % to **95 %** figure match (100 % on the
held-out third, 100 % SQL valid, 99 % first attempt, median 2.1 s). Its result file is not in
`results/`: it was deleted before the key ran out, see below.

### What the check is worth: not measured

The OpenRouter key hit its total limit part-way through the runs
(`403 Key limit exceeded (total limit)`), so the four runs that would have measured the check on
the final code all failed at the first request and were thrown away. What is missing is the
`check` row of the table above for both models and both sets, and with it the median latency the
check costs. Everything needed to produce it is in place; with a key that has credit it is four
commands and about half an hour:

```sh
uv run finquery-bench --set sql   --model qwen/qwen3.5-9b
uv run finquery-bench --set chart --model qwen/qwen3.5-9b
uv run finquery-bench --set sql   --model google/gemini-3.8-flash
uv run finquery-bench --set chart --model google/gemini-3.8-flash
```

Two things are worth knowing before reading those numbers, both seen in the browser on Qwen:

- **The check pays for a second model call on every query it judges**, and the runner records
  what it did: every result carries the narration lines, so `Checking the result` and
  `Rewriting: ...` in a result's `notes` count the pass and the rewrites it asked for.
- **A 9B model judging a 9B model asks for rewrites it should not.** It read "letztes Quartal"
  from today rather than from the newest booking until the check prompt was told where those
  dates are written, and it still invents reasons ("the raw sum is divided by 2"). A rewrite
  whose result is degenerate while the one it replaced was not is thrown away in code, which is
  the floor under that; the benchmark is what says whether the rest of it nets positive.

## Ticket 42: the sub-agent prompts, chart set before and after

The prompts of the chart sub-agent grew a `reasoning` field on both passes, two more worked
examples and a repair round framed as a correction (ticket 42). Before is the baseline above,
the `--set all` run of 2026-09-05; after is `--set chart` on the same 63 datapoints, same day,
same provider.

| google/gemini-3.8-flash | n | figure match | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| before | 63 | 92 % | 98 % | 95 % | 100 % | 98 % | 97 % | 6.3 |
| **after** | 63 | **97 %** | 98 % | 97 % | 100 % | 98 % | 97 % | 7.2 |

Figure match per shape, same two runs:

| | n | before | after |
| --- | ---: | ---: | ---: |
| line | 10 | 90 % | 100 % |
| area | 6 | 67 % | 100 % |
| bar | 15 | 87 % | 93 % |
| bar_horizontal | 6 | 100 % | 100 % |
| bar_grouped | 6 | 100 % | 100 % |
| bar_stacked | 6 | 100 % | 100 % |
| doughnut | 8 | 100 % | 88 % |
| sankey | 6 | 100 % | 100 % |

Four datapoints turn from wrong to right and one the other way. The area chart is the whole
story: `04-cumulative-area-de` and `g003-area` were drawn as plain monthly series before, which
is what the second area example (a `quarter` column, a name axis, no `monthShort`) teaches; the
one loss, `28-friends-doughnut-de`, is a query that came back with no rows at all.
`results/20260905T183545Z-google-gemini-3.8-flash-chart.{json,md}`.

**The qwen run is incomplete and its table is not the after number.** The OpenRouter key hit its
total limit 26 datapoints in, and the remaining 37 are 403s in
`results/20260905T183542Z-qwen-qwen3.5-9b-chart.json`. On the 26 that ran, all of them
hand-written, against the same 26 of the baseline:

| qwen/qwen3.5-9b, 26 of 63 | figure match | columns map | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: |
| before | 46 % | 73 % | 73 % | 38 % | 7.9 |
| after | 50 % | 85 % | 69 % | 46 % | 12.8 |

Twenty-six datapoints on a model this noisy is worth about as much as the paragraph above says
it is: the README's own reading is that nothing under ten points can be read on Qwen even at 76
datapoints. What it is not is a regression signal, and the columns-map move is the one the two
new examples were written for. Run `--set chart --model qwen/qwen3.5-9b` again when the key has
credit and replace this table.


## Ticket 50: the line datapoints, before and after the multi-series line

The line and the area may now carry a series, so the twelve line datapoints were re-run on
their own. The CLI takes `--n` and a seed rather than a list of ids, so the run filtered
`load("chart")` to `shape == "line"` and called `run_points` exactly as `command_run` does;
everything else is the same database, the same target and the same scoring. Before is the
ticket 42 run of the ten line datapoints that existed then
(`results/20260905T183545Z-google-gemini-3.8-flash-chart.json`), after is
`results/20260906T101920Z-google-gemini-3.8-flash-lines-chart.json`.

| google/gemini-3.8-flash, line only | n | figure match | shape match | columns map | language | drawn | first attempt | median s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| before (ticket 42) | 10 | 100 % | 100 % | 100 % | 100 % | 100 % | 90 % | 6.5 |
| after | 12 | 92 % | 100 % | 92 % | 100 % | 92 % | 83 % | 7.6 |

**The two new datapoints both pass on the first attempt**, figure, shape, columns and language:
`33-grocery-lines-de` in 8.7 s and `34-grocery-lines-en` in 8.2 s. Five shops, five strokes, a
legend, and no repair round, which is the whole point of the ticket.

The one miss is `g001-line` ("Show my monthly income across 2025 as a line chart"), and it is
not a chart failure: the statement came back with no rows, the query pass rewrote it once and
still got none, 20.1 s for the round trip. It passed on the ticket 42 run of the same prompt on
the same model, so it is the query sub-agent's own variance on an income filter, which is the
habit the baseline section already names as Gemini's. Nine of the ten old datapoints and both
of the new ones drew and matched, which is what this table says about the line.
