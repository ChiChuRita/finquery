"""Score one checkpoint on a fixed set of held-out cases, with the HF weights.

    uv run python quick_eval.py --base <hf base> --label base-e4b
    uv run python quick_eval.py --base <hf base> --checkpoint <run>/checkpoint-120 --label query-e4b-e2

This is the number the checkpoint curve is read from, and it decides which epoch gets converted
to GGUF. It is indicative and it is not the reported number: the reported number is the
llama-cpp benchmark of the converted adapter against the vanilla base, because that is what the
product runs.

It is indicative in one direction only, which is the safe one. The prompts are the product's,
built by `query_prompt`, `plan_prompt` and `code_prompt` through `prompts.py`; the scoring is
the benchmark's, `figure_match` and `shape_match` over the guard and `execute_read_only`, and
the chart code goes through the product's own self-check. What is missing is llama.cpp's GBNF
grammar, which in the app forces a well-formed tool call: here a malformed answer is simply a
miss. So a checkpoint scores at most as well here as it will in the app, never better.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prompts  # noqa: E402
from train import refuse_openrouter_key  # noqa: E402

from finquery.chart.fold import fold_rows  # noqa: E402
from finquery.chart.selfcheck import check_chart_code  # noqa: E402
from finquery.query.guard import SqlFailed, SqlRejected, execute_read_only, validate_sql  # noqa: E402
from finquery.query.subagent import load_query_context, subcategory_parents  # noqa: E402
from finquery_bench.datapoints import SQL_SET, ChartPoint, SqlPoint, load_charts, load_sql, pick, read  # noqa: E402
from finquery_bench.dataset import fresh_database  # noqa: E402
from finquery_bench.run import _hints as prefix_hints  # noqa: E402 - the benchmark's own builder
from finquery_bench.score import figure_match, shape_match  # noqa: E402
from finquery_bench.splits import HELD  # noqa: E402

QUICK_SEED = 63
"""The seed the quick set is cut with. Fixed forever: a curve whose validation set moves between
epochs measures the set and not the checkpoint. Ticket 63."""

MAX_NEW_TOKENS = 768
"""Enough for a statement or a chart definition and its reasoning, and not enough to let a model
that has started repeating itself cost ten minutes."""


def quick_set(sql_n: int, chart_n: int) -> tuple[list[SqlPoint], list[ChartPoint]]:
    """The fixed cases: held-out only, cut by `QUICK_SEED`, never touched by training."""
    sql = [point for point in load_sql() if point.split == HELD]
    charts = [point for point in load_charts() if point.split == HELD]
    return pick(sql, n=sql_n, seed=QUICK_SEED), pick(charts, n=chart_n, seed=QUICK_SEED)  # type: ignore[return-value]


class Generator:
    """The base weights with a checkpoint's adapter on top, generating greedily."""

    def __init__(self, base: str, checkpoint: Path | None, *, four_bit: bool = True) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self.tokenizer = AutoTokenizer.from_pretrained(base)
        quantization = None
        if four_bit:
            quantization = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
        started = time.monotonic()
        self.model = AutoModelForCausalLM.from_pretrained(
            base,
            quantization_config=quantization,
            dtype=torch.bfloat16,
            device_map={"": 0},
            attn_implementation="eager",
        )
        if checkpoint is not None:
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(self.model, str(checkpoint))
        self.model.eval()
        self.load_seconds = round(time.monotonic() - started, 1)
        self.torch = torch

    def answer(self, request: prompts.Request) -> str:
        """The assistant turn this request produces, markers and all."""
        from finquery.local import gemma

        text = prompts.render(self.tokenizer, request)
        encoded = self.tokenizer(text, return_tensors="pt", add_special_tokens=False).to(self.model.device)
        with self.torch.no_grad():
            out = self.model.generate(
                **encoded,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False,
                stop_strings=gemma.STOP,
                tokenizer=self.tokenizer,
                pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            )
        # Never `skip_special_tokens`: the tool-call markers the product parses are special
        # tokens, and stripping them would leave nothing for the splitter to find.
        return self.tokenizer.decode(out[0][encoded.input_ids.shape[1] :], skip_special_tokens=False)


def score_sql(
    point: SqlPoint, generator: Generator, session_factory: Any, profile_id: str, context: Any
) -> dict[str, Any]:
    """One question: the prompt the app builds, the guard the app runs, the benchmark's scorer."""
    started = time.perf_counter()
    request = prompts.query_request(point.question, context, hints=prefix_hints(point))
    answered = prompts.parse_sql(generator.answer(request))
    record: dict[str, Any] = {
        "id": point.id,
        "set": "sql",
        "kind": point.kind,
        "language": point.language,
        "difficulty": point.difficulty,
        "called": answered is not None,
        "sql_valid": False,
        "figure_match": False,
        "error": None,
    }
    if answered is None:
        record["error"] = "no run_sql call in the answer"
    else:
        record["sql"] = answered.sql
        try:
            statement = validate_sql(answered.sql, taxonomy=subcategory_parents(context))
            with session_factory() as session:
                rows = execute_read_only(session, statement, profile_id)
            record["sql_valid"] = True
            gold = point.gold.rows if point.gold else []
            record["figure_match"] = figure_match(gold, rows.rows, answer=point.answer)
        except (SqlRejected, SqlFailed) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 - one case that throws is one miss
            record["error"] = f"{type(exc).__name__}: {exc}"
    record["seconds"] = round(time.perf_counter() - started, 2)
    return record


def score_chart(point: ChartPoint, generator: Generator, context: Any) -> dict[str, Any]:
    """One chart request through both prompts the chart adapter is attached over.

    The plan pass is scored with the benchmark's `shape_match`. The code pass then runs against
    the datapoint's own gold rows, folded exactly as `run_chart` folds them, and is scored by
    the product's self-check: a definition the check would refuse is a chart that is not drawn.
    The query in between is skipped on purpose, because the gold rows are what the SQL set
    already measures and re-measuring it here would make one number out of two.
    """
    started = time.perf_counter()
    record: dict[str, Any] = {
        "id": point.id,
        "set": "chart",
        "kind": point.shape,
        "language": point.language,
        "difficulty": point.difficulty,
        "called": False,
        "shape_match": False,
        "drawn": False,
        "error": None,
    }
    plan = prompts.parse_plan(generator.answer(prompts.plan_request(point.prompt, context)))
    if plan is None:
        record["error"] = "no chart_plan call in the answer"
        record["seconds"] = round(time.perf_counter() - started, 2)
        return record
    record["called"] = True
    record["shape"] = plan.shape
    record["shape_match"] = shape_match(point.shape, point.also, plan.shape)

    columns = list(point.gold.columns) if point.gold else []
    rows = list(point.gold.rows) if point.gold else []
    if not rows:
        record["error"] = "the datapoint has no gold rows, so the code pass cannot be scored"
        record["seconds"] = round(time.perf_counter() - started, 2)
        return record
    folded = fold_rows(plan.shape, columns, rows, language=plan.language).rows
    code = prompts.parse_code(generator.answer(prompts.code_request(plan, columns, folded)))
    if code is None:
        record["error"] = "no chart_code call in the answer"
    else:
        result = asyncio.run(check_chart_code(code.code, folded, plan.shape))
        record["drawn"] = not result.fatal
        record["findings"] = list(result.findings)
    record["seconds"] = round(time.perf_counter() - started, 2)
    return record


def share(records: list[dict[str, Any]], key: str) -> float | None:
    values = [bool(record[key]) for record in records if key in record]
    return round(sum(values) / len(values), 3) if values else None


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    sql = [record for record in records if record["set"] == "sql"]
    charts = [record for record in records if record["set"] == "chart"]
    return {
        "n": len(records),
        "sql": {
            "n": len(sql),
            "called": share(sql, "called"),
            "sql_valid": share(sql, "sql_valid"),
            "figure_match": share(sql, "figure_match"),
        },
        "chart": {
            "n": len(charts),
            "called": share(charts, "called"),
            "shape_match": share(charts, "shape_match"),
            "drawn": share(charts, "drawn"),
        },
    }


def percent(value: float | None) -> str:
    return "-" if value is None else f"{round(value * 100)} %"


def write_curve(directory: Path) -> Path:
    """Every quick evaluation in this directory as one table, newest run of each label kept.

    Rebuilt from the JSON rather than appended to, so a rerun of one epoch corrects its row
    instead of adding a second one.
    """
    runs: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("quick-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        runs[payload["label"]] = payload
    lines = [
        "# The checkpoint curve",
        "",
        "Every quick evaluation in this directory, on the fixed held-out set cut with seed "
        f"{QUICK_SEED}. Indicative: the reported number is the llama-cpp benchmark of the "
        "converted adapter (`bench/results/<date>-adapters-compare.md`). The epoch that is "
        "converted is the one with the highest figure match for a query adapter, and the "
        "highest shape match then drawn for a chart adapter.",
        "",
        "| label | checkpoint | sql n | called | SQL valid | figure match | chart n | called | shape match | drawn | minutes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label in sorted(runs):
        payload = runs[label]
        sql, chart = payload["summary"]["sql"], payload["summary"]["chart"]
        lines.append(
            f"| {label} | {payload['checkpoint'] or 'base weights'} | {sql['n']} | "
            f"{percent(sql['called'])} | {percent(sql['sql_valid'])} | {percent(sql['figure_match'])} | "
            f"{chart['n']} | {percent(chart['called'])} | {percent(chart['shape_match'])} | "
            f"{percent(chart['drawn'])} | {round(payload['seconds'] / 60, 1)} |"
        )
    path = directory / "curve.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    refuse_openrouter_key()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="the Hugging Face base directory on scratch")
    parser.add_argument("--checkpoint", type=Path, default=None, help="a checkpoint to attach; none is the base")
    parser.add_argument("--label", required=True, help="how this run is named in the curve")
    parser.add_argument("--sql", type=int, default=50)
    parser.add_argument("--chart", type=int, default=50)
    parser.add_argument("--out", type=Path, required=True, help="where the JSON and curve.md go")
    parser.add_argument("--no-4bit", dest="four_bit", action="store_false", help="load the base in bf16")
    args = parser.parse_args(argv)

    sql_points, chart_points = quick_set(args.sql, args.chart)
    print(f"{len(sql_points)} questions and {len(chart_points)} chart requests, held out, seed {QUICK_SEED}")
    generator = Generator(args.base, args.checkpoint, four_bit=args.four_bit)
    print(f"loaded in {generator.load_seconds} s: {args.base} + {args.checkpoint or 'nothing'}", flush=True)

    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    with fresh_database() as (session_factory, profile_id):
        with session_factory() as session:
            context = load_query_context(
                session, profile_id, today=date.fromisoformat(read(SQL_SET)["today"])
            )
        for point in sql_points:
            record = score_sql(point, generator, session_factory, profile_id, context)
            records.append(record)
            print(f"  {'ok  ' if record['figure_match'] else 'MISS'} {record['id']:28s} {record['seconds']:6.1f}s", flush=True)
        for chart_point in chart_points:
            record = score_chart(chart_point, generator, context)
            records.append(record)
            mark = "ok  " if record["shape_match"] and record["drawn"] else "MISS"
            print(f"  {mark} {record['id']:28s} {record['seconds']:6.1f}s", flush=True)

    payload = {
        "label": args.label,
        "base": args.base,
        "checkpoint": str(args.checkpoint) if args.checkpoint else None,
        "seed": QUICK_SEED,
        "seconds": round(time.perf_counter() - started, 1),
        "load_seconds": generator.load_seconds,
        "summary": summarize(records),
        "results": records,
    }
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"quick-{args.label}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"written: {path}\n         {write_curve(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
