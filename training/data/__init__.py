"""The training data harness: households, the execution gate, the render, the assembly.

Everything the writer and judge agents of ticket 64 call. They write questions, SQL, plans and
chart code; nothing here writes any of that, and nothing here calls a model. The two rules the
whole harness exists to keep are:

- a training sample is byte for byte the prompt the production sub-agent builds, so the modules
  under `finquery.query` and `finquery.chart` are imported and called rather than copied;
- a row is kept by execution, never by an opinion: the guard, the database, a second statement
  that computes the same figure differently, and for a chart the real self-check on the real
  rows plus a headless render.

`README.md` beside this file is what the fan-out agents read.
"""
