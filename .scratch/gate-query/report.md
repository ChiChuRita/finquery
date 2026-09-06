# Gate report

10 of 13 candidates kept (77 %), 3 dropped.

| household | rows | share |
| --- | ---: | ---: |
| couple | 2 | 20 % |
| family | 2 | 20 % |
| freelancer | 2 | 20 % |
| student | 2 | 20 % |
| pensioner | 1 | 10 % |
| shipped | 1 | 10 % |

| kind | rows | share |
| --- | ---: | ---: |
| entity | 2 | 20 % |
| total | 2 | 20 % |
| breakdown | 1 | 10 % |
| comparison | 1 | 10 % |
| follow-up | 1 | 10 % |
| period | 1 | 10 % |
| ranking | 1 | 10 % |
| trend | 1 | 10 % |

| language | rows | share |
| --- | ---: | ---: |
| de | 6 | 60 % |
| en | 4 | 40 % |

| difficulty | rows | share |
| --- | ---: | ---: |
| 2 | 6 | 60 % |
| 3 | 3 | 30 % |
| 1 | 1 | 10 % |

## Why the rest was dropped

| reason | rows | share |
| --- | ---: | ---: |
| degenerate-result | 1 | 33 % |
| guard-refused | 1 | 33 % |
| statements-disagree | 1 | 33 % |

One line per drop:

- `smoke-w01-student-subcategory-as-category-de` the guard refused the statement: Supermarket is a subcategory of Groceries, not a category, so `category = 'Supermarket'` matches nothing. Filter the parent with `category = 'Groceries'`, or the subcategory column with `subcategory = 'Supermarket'`.
- `smoke-w02-pensioner-misspelled-like-de` the result is one production would send back for a rewrite: every figure it returned is empty, so nothing in the data matched it
- `smoke-w03-family-wrong-month-de` the two statements do not agree on the figures: the statement returns ['4416.75'] and the check statement ['3598.45']
