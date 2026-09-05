"""The benchmarks: two hand-written sets, a runner that scores a model on them, a validation page.

The sets live beside this package as JSON (`bench/sql-benchmark.json`, `bench/chart-benchmark.json`).
Gold is code, not a model: every datapoint carries reference SQL we wrote, and `bench/build_gold.py`
runs it through the real guard against a fresh database holding the shipped synthetic year, so the
expected rows in the file are exact and reproducible.

`cli.main` is `uv run finquery-bench`.
"""
