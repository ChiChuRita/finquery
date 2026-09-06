# The split is frozen

Frozen on 2026-09-06, hash `7c036278dbd950cdc1ad17dfba140b569469b082b7d1f9bb2fa673610e381ca1`.

459 questions and 302 chart requests, 235 of them held out. This file is what
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
