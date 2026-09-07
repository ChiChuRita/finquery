# The adapters against their vanilla bases, 2026-09-07

Four QLoRA adapters (query and chart, on Gemma 4 E4B and on Gemma 4 12B), trained overnight on
the HPI cluster on 1,977 query and 1,791 chart samples over five synthetic households (tickets
62 to 65), converted to GGUF and attached through the product's adapter registry, scored with
the llama-cpp benchmark on the same GGUFs and wire formats as the laptop. The benchmark household
(the shipped year) was never in training; the split is frozen (`bench/SPLIT_FROZEN.md`).

Every row below is a full run of the set: 459 SQL questions or 302 chart requests. "Before" and
"after" ran on the same GPU type (RTX PRO 6000) within the same night. The epoch is the one the
official run picked, not the quick eval: on both bases the 30-case quick eval favoured epoch two
and the full run favoured epoch three, which is what a 30-case sample is worth.

## SQL set, figure match to the cent

| base | before | after (epoch 3) | after (epoch 2) | first attempt before | first attempt after | median s before | median s after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemma 4 E4B | 62 % | **78 %** | 76 % | 76 % | 91 % | 7.8 | 14.3 |
| Gemma 4 12B | 78 % | 82 % | 80 % | 86 % | 89 % | 10.6 | 15.2 |

Runs: `20260907T014357Z-local-gemma-4-e4b-sql` (before, a rerun that reproduced the first
pass to the point), `20260906T233117Z-local-gemma-4-e4b+query-sql` (epoch 3),
`20260907T004952Z-local-gemma-4-e4b+query-sql` (epoch 2), `20260907T004634Z-local-gemma-4-12b-sql`,
`20260907T051140Z-local-gemma-4-12b+query-sql` (12B, epoch 3) and `...+query-e2-sql` (12B, epoch 2;
both 12B runs started in the same second and the second overwrote the first's file on the cluster,
the epoch-two copy was recovered from git).

The 12B query adapter does not ship. Four points (78 to 82) on 459 cases is inside the set's
resolution, the first attempt gains three, and the adapter costs half again the time per question
(10.6 to 15.2 s median). Per case: 328 right in both, 51 wrong in both, 50 only with the adapter,
30 only without. A model that already answers 78 percent of a hard set has little left to learn
from 1,977 samples written for a 4B model's mistakes; the E4B is where the same data buys sixteen
points.

A finding on the way: the fine-tuned 12B writes its SQL over several lines, and llama.cpp passes
those raw line breaks into the JSON of the tool call, which strict JSON refuses. Before the fix
(`normalize_json_arguments` in `src/finquery/local/model.py`) two thirds of the 12B adapter's
answers failed validation for that reason alone. The vanilla model escapes its line breaks, so
only the adapters were hit; the E4B adapter never was.

What the E4B query adapter changes, from `finquery-bench compare` on the two runs: 261 questions
right in both, 75 wrong in both, 97 only right with the adapter, 26 only right without it. The
gains are where the training data was weighted: follow-ups ("Und im Dezember?", "Split that by
month.", "Und ohne die Miete?"), relative periods ("seit dem Sommer", "the last 90 days"),
entity questions with a count and an average, and rankings. The adapter is slower per question
(14.3 s against 7.8 s median): the LoRA is applied unmerged at inference, and the adapter run
shared its GPU with a second job for most of the night.

Note on the 12B baseline: 78 percent on the grown set against 87 percent on the original 152
questions (`20260906-cluster-compare.md`). The 307 questions added from the writers' shipped
household are harder on average (40 percent difficulty 3, a fifth follow-ups), which lowers
every model's number on this set; the before-and-after within a row is what the adapters are
judged on.

## Chart set, figure match and drawn

| base | figure before | figure after | shape before | shape after | drawn before | drawn after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemma 4 E4B | 38 % | 36 % (epoch 3) | 80 % | 81 % | 85 % | **72 %** |
| Gemma 4 12B | pending | pending | pending | pending | pending | pending |

Runs: `20260906T222238Z-local-gemma-4-e4b-chart` (before), `20260907T004634Z-local-gemma-4-e4b+chart-chart` (after, epoch 3).

The E4B chart adapter does not ship. Figure match is flat within noise (38 to 36 percent), the
shape is picked about as often (80 to 81), but the drawn rate falls from 85 to 72 percent and the
first attempt from 79 to 68: the adapter's code fails the self-check more often than the vanilla
model's, so more charts end in a repair round or not on screen. Per case: 78 right in both, 156
wrong in both, 32 only right with the adapter, 36 only right without. Two likely causes, both
about the data rather than the recipe: only 72 repair rows for 959 code rows (the research note
asked for 25 to 30 percent on the code side), and the chart training set is the one whose
samples were longest (p100 4,610 tokens), so the code completions carried the least attention
per token. A second data round with more repair rows is the fix to try before the hand-in.

## The decision rule for shipping

An adapter ships for a role when its after beats its before on figure match by more than the
set's resolution (about five points on 459 SQL cases, about six on 302 chart cases), with no
loss in validity or drawn rate. The E4B query adapter clears it. The rest of the table is filled
in as the runs land.

## Quick evals, for the record

Indicative only: 30 held-out cases each, HF weights through transformers, no grammar. The base
rows are not comparable (the vanilla model emits no tool call without a grammar).

| adapter | epoch 1 | epoch 2 | epoch 3 |
| --- | ---: | ---: | ---: |
| query, E4B (figure match) | 77 % | 87 % | 83 % |
| query, 12B (figure match) | 77 % | 87 % | 83 % |
| chart, E4B (shape, drawn) | 93 / 97 % | 93 / 100 % | 97 / 100 % |
| chart, 12B (shape, drawn) | 83 / 97 % | 97 / 100 % | 90 / 100 % |

Training: three epochs each, loss 1.40 to 0.08 (query, E4B), 0.69 to 0.09 (chart, E4B), 1.35
to 0.27 after one epoch (query, 12B); about 1 h 30 per E4B run and 2 h 50 per 12B run on one
H100. Conversions: 516 tensors, one global alpha, 70 MB per E4B adapter, 262 MB per 12B adapter.
