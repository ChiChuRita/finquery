# The split is frozen

Frozen on 2026-09-06, hash `8b753985233b48e6d3be1b8c4a5c99666b6e1fd17c24c2918a501204a708f929`.

152 questions and 73 chart requests, 74 of them held out. This file is what
`bench/split.py` refuses to run against: the split is a hash of the id inside a stratum, so
adding a datapoint re-cuts that stratum and can move an existing one from `train` to `heldout`
(ticket 57, section 8). A datapoint that moves after it has seeded a training sample or a worked
example makes the held-out number meaningless.

So, in this order and not another:

1. append every judged surplus datapoint to the sets;
2. `uv run python bench/build_gold.py`;
3. `uv run python bench/split.py --force`;
4. `uv run python -m training.data.audit freeze`;
5. only then generate training data.

`uv run python -m training.data.audit freeze --check` says whether the split still hashes to the
line above. It is what a training run should assert before it writes a single row.
