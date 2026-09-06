# Writing and judging the adapter training data

You are one of twenty agents (ticket 64). Ten write query candidates, ten write chart
candidates, and a second pass judges every one of them. **You write questions, statements, plans
and chart code. You never write a pipeline**: everything else in this folder already exists and
is tested.

Two rules decide whether your work counts:

1. **A sample is the prompt production builds.** The assembly calls the real
   `query_prompt`, `check_prompt`, `plan_prompt` and `code_prompt` with the household's own
   facts. You never write a prompt, so you never have to match one.
2. **A row is kept by execution.** Your statement runs through the real guard against the real
   household database, a second statement you wrote differently has to agree with it to the
   cent, and your chart code has to pass the real self-check on the real rows. Nothing you say
   about a candidate matters; only what it does.

## Before anything else

```sh
training/data/smoke.sh
```

Green in under ten seconds, with no model. If it is green, the harness is not what is wrong with
your batch. It needs the chart runtime built once, which is a build artifact and not committed:

```sh
npm --prefix frontend install && npm --prefix frontend run build
```

## The six households

```sh
uv run python -m training.data.households list
uv run python -m training.data.households build      # about a second each, then cached
```

| slug | what it is | watch out for |
| --- | --- | --- |
| `shipped` | the Berlin household the app ships with, 433 bookings | the benchmark is written against it, so a question about it has to be a new question |
| `student` | Leipzig, BAfoeG and a university job, 300 bookings | small amounts, discounters, a semester fee twice a year, one big purchase in October |
| `family` | Dortmund, two salaries, Kindergeld, two children, 486 bookings | months are not equal: a holiday in July, Christmas in December, school supplies in August |
| `freelancer` | Hamburg, fifteen invoices over the year, 381 bookings | August and September carry no client payment at all, and the VAT is quarterly |
| `pensioner` | Muenster, a pension and a company pension, 349 bookings | the pharmacy every other week, the most cash of the six, a heating settlement in February |
| `couple` | Stuttgart, a joint account and a personal one, 565 bookings | two accounts in one profile: say which one you mean, or mean both |

The household CSVs are Latin-1 like a real Sparkasse export, so read them with that encoding.
`fixtures/synthetic/households/households.json` is the truth: every merchant with the category
the import path gives it, the totals per category, and the totals per month per category. Read a
figure there before you claim it. Every household ends on 2025-12-28 and every question is asked
on 2025-12-31, so "this month" is December 2025 and "last month" is November 2025.

## What one candidate looks like

### A query candidate

```json
{"id": "w03-student-de-014", "household": "student", "language": "de", "kind": "total",
 "difficulty": 2, "question": "...", "prefix": [], "sql": "SELECT ...",
 "reasoning": "period: ...; filters: ...; sign: ...; grouping: ...",
 "expected": {"figure": 149.9, "check_sql": "SELECT ..."}}
```

| field | what it has to be |
| --- | --- |
| `id` | `<your agent number>-<household>-<language>-<counter>`, unique across all twenty agents |
| `kind` | one of total, breakdown, comparison, trend, ranking, entity, follow-up, period |
| `difficulty` | 1 one filter, 2 two things at once, 3 what a 9B model gets wrong |
| `question` | what a household really types, in the language named. Misspellings and Denglisch welcome |
| `prefix` | the earlier questions, for a follow-up. Empty otherwise |
| `sql` | one SELECT over `transaction_view`, written the way the prompt's rules ask for it |
| `reasoning` | one short line each for the period, the filters, the sign and the grouping. Judged as strictly as the SQL |
| `expected.figure` | the figure you expect, when the answer is one figure. `null` otherwise |
| `expected.check_sql` | **a different statement computing the same figure**, from the other end of the question |

The check statement is the whole gate. A statement agreeing with itself is not evidence, so
write the check from the other side: `BETWEEN` against `>= ... <`, `category = 'Groceries'`
against the subcategory names, a `LIMIT 3` against a `HAVING` over the third largest, a
`strftime('%Y-%m', ...)` against a `substr(booked_on, 1, 7)`. If both statements are yours in
the same handwriting, the row proves nothing.

### A chart candidate

```json
{"id": "c05-family-de-021", "household": "family", "language": "de", "request": "...",
 "shape": "bar_grouped", "difficulty": 3,
 "plan": {"title": "...", "question": "...", "columns": ["topic", "period", "total_eur"]},
 "sql": "SELECT ...", "code": "return defineChart({ ... });",
 "reasoning_plan": "...", "reasoning_code": "..."}
```

`plan.columns` must be exactly what the statement returns, in order, with the euro column last.
`code` is the body of a function of `data`, over the allowlisted globals only
(`docs/chart-runtime.md`). Both reasoning fields are three to five very short lines, one per
line, the way the production fields ask for them.

## The commands, in order

```sh
# 1. Is the file even readable? Line numbers come back, nothing else happens.
uv run python -m training.data.schema validate --task query training/data/batches/w03.jsonl
uv run python -m training.data.schema example  --task chart          # a template to copy

# 2. Run it. kept.jsonl, dropped.jsonl and report.md land in the output folder.
uv run python -m training.data.gate --task query --out training/data/out/w03 \
  training/data/batches/w03.jsonl training/data/batches/w03-wrong.jsonl

# 3. Charts only: draw every kept row through the real runtime.
uv run python -m training.data.render --kept training/data/out/c05/kept.jsonl \
  --out training/data/renders --session ticket62

# 4. Is any question a benchmark question with the name swapped? It scores the question text
#    alone, so a three-word follow-up ("Und im November?") collides with benchmark follow-ups
#    easily: rephrase it or make the follow-up carry one more word of its own.
uv run python -m training.data.audit duplicates --task query training/data/out/w03/kept.jsonl

# 5. Hand the batch to the judges, and apply what they answer.
uv run python -m training.data.judge_pack pack  --task query --batch training/data/out/w03
# charts: hand the renders over, or every review row says render: null
uv run python -m training.data.judge_pack pack  --task chart --batch training/data/out/c05 \
  --renders training/data/renders
uv run python -m training.data.judge_pack apply --task query --batch training/data/out/w03 \
  --verdicts training/data/out/w03/verdicts.jsonl

# 6. Assemble the samples. Only the coordinator runs this, over every batch at once.
uv run python -m training.data.assemble --query training/data/out/query \
  --chart training/data/out/chart --out training/data/out/samples
```

Never `agent-browser close --all`: other agents are holding sessions. Use
`--session ticket62`, which is the default.

## Your quota

Ten query writers, ninety candidates each; ten chart writers, fifty each. Inside your own
batch, hit these:

| query writer, 90 rows | count |
| --- | ---: |
| household `shipped` / `student` / `family` / `freelancer` / `pensioner` / `couple` | 15 each |
| German / English | 45 / 45 |
| difficulty 1 / 2 / 3 | 14 / 40 / 36 |
| kind: follow-up | 17 |
| kind: entity | 13 |
| kind: total | 12 |
| kind: trend | 11 |
| kind: breakdown / period | 10 each |
| kind: ranking | 9 |
| kind: comparison | 8 |
| plus wrong attempts, see below | 12 |

| chart writer, 50 requests | count |
| --- | ---: |
| households | 8 each, 10 on one of your choice |
| German / English | 25 / 25 |
| difficulty 1 / 2 / 3 | 8 / 22 / 20 |
| shape: line / bar | 8 each |
| shape: area / doughnut | 7 each |
| shape: bar_grouped / bar_stacked / bar_horizontal / sankey | 5 each |
| plus wrong attempts, see below | 14 |

Follow-ups are over-weighted because they are the worst kind in the benchmark (19 % for
Qwen3.5 9B against 57 % overall), trend and entity because they are the next two, and area and
doughnut because they are the two shapes the small models cannot draw at all. Difficulty 3 is
40 % on purpose: that is where the adapter has to earn its place.

## Wrong attempts, which are half the value

An adapter is attached for a whole run, so it also serves the retry, the rewrite and the check
pass. Those prompts only exist if you hand in the wrong answer as well as the right one.

**Write the wrong attempt with the same `question` (or `request`) as the right one**, in a
second file. The gate drops one and keeps the other, and the assembly pairs them by that
question. Four kinds are worth writing, all of them in `samples/query-wrong.jsonl` and
`samples/chart-wrong.jsonl`:

- a statement the guard refuses (`category IN ('Supermarket', 'Bakery')`, nine LIKE terms, a
  `CASE` over the booking text that invents a category);
- a statement that runs and answers nothing (a misspelled merchant, a period outside the data);
- a statement that runs and answers a different question (the wrong month, the wrong sign);
- chart code the self-check refuses (no grid on the euro axis, no tooltip, a legend on one
  series, a domain that does not hold zero).

The assembly caps them at the rate the runtime really fires them, 14 % of the query rows and
28 % of the chart code rows, so a handful more than the quota is fine and a hundred is waste.

## Three good query candidates

All ten of `samples/query-smoke.jsonl` are worked examples. These three say why.

**A category, not a list of shops** (`smoke-q01`, student, de, total, 2)

```
question   Wie viel habe ich im Oktober 2025 fuer Lebensmittel ausgegeben?
sql        SELECT ROUND(-SUM(amount), 2) AS total_eur FROM transaction_view
           WHERE amount < 0 AND category = 'Groceries'
             AND booked_on BETWEEN '2025-10-01' AND '2025-10-31'
check_sql  ... WHERE category = 'Groceries' AND amount < 0
             AND strftime('%Y-%m', booked_on) = '2025-10'
reasoning  period: October 2025, the month the question names; filters: the category Groceries,
           which is the whole topic and never a list of shops; sign: spending, so amount < 0 and
           the figure is reported positive; grouping: none, one figure.
```

Good because the topic is the household's own category rather than three merchant names, the
period is written both ways across the two statements, and the reasoning names all four things
without a word of prose.

**A follow-up that inherits everything but the month** (`smoke-q06`, student, en, follow-up, 2)

```
prefix     ["How much did I spend on groceries in October 2025?"]
question   And in November?
reasoning  period: November 2025, the month the follow-up names, in the year the question before
           it was about; filters: the category Groceries, inherited from that question; ...
```

Good because the question is three words that mean nothing on their own, which is exactly the
kind the models collapse on, and the reasoning says what it inherited and from where.

**A relative period, counted from the data** (`smoke-q09`, family, de, period, 3)

```
question   Wie viel haben wir letzten Monat ausgegeben?
reasoning  period: last month is the month before the newest booking, which the household
           paragraph spells out as 2025-11-01 to 2025-11-30, never the month before today; ...
```

Good because "letzten Monat" is the trap: the prompt hands the model the dates, and the
reasoning has to show it read them there rather than computing them from today.

## Three good chart candidates

**A trend** (`smoke-c01`, student, en, line, 2): two columns, `month` and `total_eur`, twelve
rows, and code that names its euro domain over the amounts because a line brings no baseline of
its own. The simplest shape done exactly right is worth as much as a hard one.

**A series** (`smoke-c02`, family, de, line, 3): `month, merchant, total_eur`, three shops over
twelve months, the euro column last, `z` and `color` on the merchant and a legend under the
plot. This is the shape a small model draws as sixty bars.

**Two periods crossed with the categories** (`smoke-c06`, family, de, bar_grouped, 3): columns
`topic, period, total_eur`, the categories on the axis and the two months in the colour. The
euro column is last, both periods come back for every category, and the code tilts the tick
labels rather than letting long category names overlap.

## What the gate drops, and what to do about it

`report.md` counts every drop by reason. The ones you will meet:

| reason | what it means |
| --- | --- |
| `guard-refused` | the guard said no. The message is the fix; it is also a good wrong attempt |
| `statements-disagree` | your two statements do not agree. One of them is wrong, and often the question is ambiguous, which is worse |
| `degenerate-result` | no rows, all NULL, or a single zero on something the household really has |
| `expected-figure-missing` | the figure you wrote in `expected.figure` is not in the rows |
| `check-is-the-same-statement` | write the check differently |
| `reasoning-too-thin` | fewer than thirty characters of reasoning is not a reasoning line |
| `columns-not-as-planned` | the chart statement returned other columns than the plan named |
| `rows-cannot-carry-the-shape` | two rows for the same pair, a circular flow, a negative in a sankey |
| `shape-would-be-downgraded` | production would draw bars here, so the sample would be a lie |
| `self-check-failed` | the findings are in the file, and they are the repair instructions |

A drop is not a failure of yours unless you leave it there. Fix it, or keep it deliberately as a
wrong attempt.

## If you are a judge

You read `review.jsonl`, never `kept.jsonl`. One row per candidate: the question, the statement
that ran, the rows it returned, the figure, the reasoning, and for a chart the plan, the code and
the file name of its render under `training/data/renders/`.

For every row, in this order:

1. read the question the way a user would (period, sign, category against subcategory, ties,
   singular against plural, the language it is in);
2. work the figure out yourself, from `households.json` or from the CSV, without reading the
   statement;
3. only then read the statement and the rows;
4. **judge the reasoning as strictly as the SQL**. For a query row the contract is the period,
   the filters, the sign and the grouping the statement really implements. For a chart row the
   plan reasoning's contract is the language, the comparison, the shape, the columns and the
   period (there is no sign line), and the code reasoning names the marks, the scales, the
   legend and the tooltip the code really draws; a plan that promises a colour or a bucket the
   code never draws is a `fix`. A right statement with a hand-wavy
   reasoning is a `fix` or a `drop`, never a `keep`. A rationale field at partial coverage
   measurably loses to no rationale at all (ticket 57, section 3);
5. for a chart, open the render and ask whether it answers the request as a picture.

Then write one line per candidate into a verdict file:

```json
{"id": "w03-student-de-014", "verdict": "keep"}
{"id": "w03-student-de-015", "verdict": "drop", "note": "letztes Quartal is July to September"}
{"id": "w03-student-de-016", "verdict": "fix", "note": "the reasoning never named the sign",
 "fix": {"reasoning": "period: ...; filters: ...; sign: ...; grouping: ..."}}
{"id": "w03-student-de-017", "verdict": "revise",
 "reason": "it totals the year, not November", "intent": "the spending of November 2025 only"}
```

`fix` may correct `question`, `reasoning`, `sql`, `check_sql`, `request`, `title`, `code`,
`reasoning_plan` and `reasoning_code`, and the row is run through the gate again before it is
believed. `revise` is only for a **dropped** row that ran and answered a different question: it
is the verdict production's own check pass should have given, and it is the only way the
check-pass samples get a `revise` in them at all. Without those, the adapter learns to answer
`ok` to everything and the check pass stops working.

Disagreements are dropped, not argued: putting back a sample that failed a checker measurably
hurts, and hurts the smaller model more.

## Before a single training row is generated

The benchmark split has to be frozen first, because adding datapoints re-cuts a stratum and can
move an existing one into the held-out third after it has already seeded a training sample:

```sh
uv run python -m training.data.audit freeze --check
```

If that fails, stop and tell the coordinator. `bench/SPLIT_FROZEN.md` says what to do.

## The files

| file | what it is |
| --- | --- |
| `households.py` | the six households and their cached databases |
| `schema.py` | the two candidate shapes and `validate` |
| `gate.py` | the execution gate: what is kept, what is dropped and why |
| `render.py`, `render.html` | the headless render of a kept chart through the real runtime |
| `judge_pack.py` | the review file for the judges, and their verdicts applied |
| `assemble.py` | kept rows into TRL samples, in the production prompts |
| `audit.py` | near-duplicates, the held-out report, the split freeze |
| `smoke.sh` | all of it, on the sample batches, in seconds |
| `samples/` | ten hand-written candidates of each kind, the wrong attempts, and a verdict file |
| `batches/` | the writers' candidate files, committed with the run so the data has a provenance |
| `out/`, `renders/`, `.db/` | everything the harness builds. Not committed |
