# Training samples

Every prompt below is the production builder's own output, and every target is the forced tool call written the way Gemma 4 writes one on the wire.

TRL reads `prompt` and `completion` and masks the loss to the completion by itself. The other columns are for the report and the split; drop them before training.

## query

13 samples.

| task | rows | share |
| --- | ---: | ---: |
| write_sql | 10 | 77 % |
| check_pass | 2 | 15 % |
| repair | 1 | 8 % |

| household | rows | share |
| --- | ---: | ---: |
| student | 4 | 31 % |
| family | 3 | 23 % |
| couple | 2 | 15 % |
| pensioner | 2 | 15 % |
| freelancer | 1 | 8 % |
| shipped | 1 | 8 % |

| kind | rows | share |
| --- | ---: | ---: |
| total | 4 | 31 % |
| breakdown | 2 | 15 % |
| entity | 2 | 15 % |
| comparison | 1 | 8 % |
| follow-up | 1 | 8 % |
| period | 1 | 8 % |
| ranking | 1 | 8 % |
| trend | 1 | 8 % |

| language | rows | share |
| --- | ---: | ---: |
| de | 8 | 62 % |
| en | 5 | 38 % |

| difficulty | rows | share |
| --- | ---: | ---: |
| 2 | 9 | 69 % |
| 3 | 3 | 23 % |
| 1 | 1 | 8 % |

> No `revise` verdict is in this set. Every check-pass sample says `ok`, and a check pass that has only ever seen `ok` stops sending anything back. The judges of ticket 64 write a `revise` verdict onto the drops that ran and answered a different question (`judge_pack.py`), and this is assembled again.

## chart

22 samples.

| task | rows | share |
| --- | ---: | ---: |
| code | 10 | 45 % |
| plan | 10 | 45 % |
| repair | 2 | 9 % |

| household | rows | share |
| --- | ---: | ---: |
| couple | 6 | 27 % |
| student | 6 | 27 % |
| family | 4 | 18 % |
| pensioner | 4 | 18 % |
| freelancer | 2 | 9 % |

| kind | rows | share |
| --- | ---: | ---: |
| line | 5 | 23 % |
| area | 4 | 18 % |
| doughnut | 3 | 14 % |
| bar | 2 | 9 % |
| bar_grouped | 2 | 9 % |
| bar_horizontal | 2 | 9 % |
| bar_stacked | 2 | 9 % |
| sankey | 2 | 9 % |

| language | rows | share |
| --- | ---: | ---: |
| en | 13 | 59 % |
| de | 9 | 41 % |

| difficulty | rows | share |
| --- | ---: | ---: |
| 2 | 12 | 55 % |
| 3 | 10 | 45 % |
