"""The training data harness: the schema, the gate, the assembly, the judge pack, the audit.

No model runs here and no browser: the render is the one step that needs both a built bundle and
Chrome, and `training/data/smoke.sh` is where it is exercised. Everything else is code over the
cached household databases, which is what makes it worth a test at all.
"""

import json
from pathlib import Path

import pytest

from finquery.chart.subagent import CODE_INSTRUCTIONS, PLAN_INSTRUCTIONS, code_prompt, plan_prompt
from finquery.local.gemma import parse_tool_call
from finquery.query.check import CHECK_TOOL, check_prompt
from finquery.query.runner import figures as figure_lines
from finquery.query.subagent import INSTRUCTIONS as QUERY_INSTRUCTIONS
from finquery.query.subagent import query_prompt
from training.data import assemble, audit, gate, judge_pack, schema
from training.data.households import context_of

SAMPLES = Path(__file__).resolve().parents[1] / "training" / "data" / "samples"
QUERY_BATCH = SAMPLES / "query-smoke.jsonl"
QUERY_WRONG = SAMPLES / "query-wrong.jsonl"
CHART_BATCH = SAMPLES / "chart-smoke.jsonl"
CHART_WRONG = SAMPLES / "chart-wrong.jsonl"
VERDICTS = SAMPLES / "query-verdicts.jsonl"


@pytest.fixture(scope="module")
def query_gate(tmp_path_factory) -> Path:  # noqa: ANN001
    out = tmp_path_factory.mktemp("query")
    candidates = [*schema.read_batch(QUERY_BATCH, "query"), *schema.read_batch(QUERY_WRONG, "query")]
    gate.write_out(gate.run_gate(candidates), out)
    return out


@pytest.fixture(scope="module")
def chart_gate(tmp_path_factory) -> Path:  # noqa: ANN001
    out = tmp_path_factory.mktemp("chart")
    candidates = [*schema.read_batch(CHART_BATCH, "chart"), *schema.read_batch(CHART_WRONG, "chart")]
    gate.write_out(gate.run_gate(candidates), out)
    return out


# The schema


def test_a_malformed_batch_is_reported_line_by_line(tmp_path: Path):
    good = QUERY_BATCH.read_text(encoding="utf-8").splitlines()[0]
    broken = json.loads(good)
    broken["difficulty"] = 7
    same_id = json.loads(good)
    path = tmp_path / "batch.jsonl"
    path.write_text(
        "\n".join([good, "{not json", json.dumps(broken), json.dumps(same_id), '{"id": "x"}']) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(schema.BatchInvalid) as raised:
        schema.read_batch(path, "query")
    problems = "\n".join(raised.value.problems)
    assert "line 2: not JSON" in problems
    assert "line 3: difficulty" in problems
    assert "line 4" in problems and "already on line 1" in problems
    assert "line 5: household" in problems


def test_a_shape_no_chart_has_is_refused(tmp_path: Path):
    payload = json.loads(CHART_BATCH.read_text(encoding="utf-8").splitlines()[0])
    payload["shape"] = "pie"
    path = tmp_path / "chart.jsonl"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    with pytest.raises(schema.BatchInvalid) as raised:
        schema.read_batch(path, "chart")
    assert "shape" in "\n".join(raised.value.problems)


# The gate


def test_the_hand_written_batch_survives_the_gate(query_gate: Path, chart_gate: Path):
    kept = schema.read_jsonl(query_gate / "kept.jsonl")
    assert len(kept) == 10
    assert {row["candidate"]["household"] for row in kept} == {
        "shipped",
        "student",
        "family",
        "freelancer",
        "pensioner",
        "couple",
    }
    assert len(schema.read_jsonl(chart_gate / "kept.jsonl")) == 10


def test_every_wrong_attempt_is_dropped_with_its_own_reason(query_gate: Path, chart_gate: Path):
    reasons = {row["candidate"]["id"]: row["reason"] for row in schema.read_jsonl(query_gate / "dropped.jsonl")}
    assert reasons["smoke-w01-student-subcategory-as-category-de"] == gate.GUARD_REFUSED
    assert reasons["smoke-w02-pensioner-misspelled-like-de"] == gate.DEGENERATE
    assert reasons["smoke-w03-family-wrong-month-de"] == gate.DISAGREE
    charts = {row["candidate"]["id"]: row for row in schema.read_jsonl(chart_gate / "dropped.jsonl")}
    assert charts["smoke-w04-student-line-no-grid-en"]["reason"] == gate.SELFCHECK_FAILED
    assert charts["smoke-w04-student-line-no-grid-en"]["findings"]


def test_a_figure_the_rows_do_not_carry_is_dropped():
    candidate = schema.read_batch(QUERY_BATCH, "query")[0].model_copy(deep=True)
    candidate.expected.figure = 12345.67
    dropped = gate.run_gate([candidate]).dropped
    assert [item.code for item in dropped] == [gate.FIGURE_MISSING]


def test_the_check_statement_may_not_be_the_statement_again():
    candidate = schema.read_batch(QUERY_BATCH, "query")[0].model_copy(deep=True)
    candidate.expected.check_sql = candidate.sql.replace("\n", " ").upper()
    dropped = gate.run_gate([candidate]).dropped
    assert [item.code for item in dropped] == [gate.SAME_STATEMENT]


def test_a_reasoning_line_that_says_nothing_is_dropped():
    candidate = schema.read_batch(QUERY_BATCH, "query")[0].model_copy(deep=True)
    candidate.reasoning = "spending"
    assert gate.run_gate([candidate]).dropped[0].code == gate.THIN_REASONING


def test_a_report_counts_by_household_kind_language_and_reason(query_gate: Path):
    report = (query_gate / "report.md").read_text(encoding="utf-8")
    assert "10 of 13 candidates kept" in report
    assert "| household | rows | share |" in report
    assert gate.WHY[gate.DEGENERATE] in report


# The assembly: the one invariant of the whole effort


def test_a_query_sample_is_the_production_prompt_byte_for_byte(query_gate: Path):
    samples = assemble.query_samples(assemble.read_batch(query_gate))
    written = [sample for sample in samples if sample.task == assemble.WRITE_SQL]
    assert len(written) == 10
    for sample in written:
        candidate = next(
            item for item in schema.read_batch(QUERY_BATCH, "query") if item.id == sample.id
        )
        session_factory, _profile_id, context, _entry = context_of(candidate.household)
        session_factory.kw["bind"].dispose()
        expected = query_prompt(candidate.question, context, hints=assemble.hints_of(candidate.prefix))
        assert sample.user == expected
        assert sample.system == QUERY_INSTRUCTIONS


def test_a_check_sample_is_the_judge_prompt_byte_for_byte(query_gate: Path):
    samples = assemble.query_samples(assemble.read_batch(query_gate))
    sample = next(item for item in samples if item.task == assemble.CHECK_PASS)
    row = next(
        item
        for item in schema.read_jsonl(query_gate / "kept.jsonl")
        if item["candidate"]["id"] == sample.id.removesuffix("--check")
    )
    candidate = schema.QueryCandidate.model_validate(row["candidate"])
    session_factory, _profile_id, context, _entry = context_of(candidate.household)
    session_factory.kw["bind"].dispose()
    assert sample.user == check_prompt(
        candidate.question,
        context,
        row["validated_sql"],
        figure_lines(row["columns"], row["rows"]),
        hints=assemble.hints_of(candidate.prefix),
        reasoning=candidate.reasoning,
    )


def test_a_chart_sample_is_the_plan_and_code_prompts_byte_for_byte(chart_gate: Path):
    samples = assemble.chart_samples(assemble.read_batch(chart_gate))
    rows = {row["candidate"]["id"]: row for row in schema.read_jsonl(chart_gate / "kept.jsonl")}
    plans = [sample for sample in samples if sample.task == assemble.PLAN]
    codes = [sample for sample in samples if sample.task == assemble.CODE]
    assert len(plans) == len(codes) == 10
    for sample in [*plans, *codes]:
        ident = sample.id.rsplit("--", 1)[0]
        row = rows[ident]
        candidate = schema.ChartCandidate.model_validate(row["candidate"])
        session_factory, _profile_id, context, _entry = context_of(candidate.household)
        session_factory.kw["bind"].dispose()
        if sample.task == assemble.PLAN:
            assert sample.system == PLAN_INSTRUCTIONS
            assert sample.user == plan_prompt(candidate.request, context)
        else:
            assert sample.system == CODE_INSTRUCTIONS
            assert sample.user == code_prompt(gate.plan_of(candidate), row["columns"], row["rows"])


def test_a_repair_sample_carries_the_refusal_and_the_corrected_answer(query_gate: Path, chart_gate: Path):
    query = [item for item in assemble.query_samples(assemble.read_batch(query_gate)) if item.task == assemble.REPAIR]
    assert query, "the wrong attempts should have produced a repair sample"
    assert "Your previous statement did not run." in query[0].user
    assert query[0].source == "smoke-w01-student-subcategory-as-category-de"
    chart = [item for item in assemble.chart_samples(assemble.read_batch(chart_gate)) if item.task == assemble.REPAIR]
    assert chart, "a failed self-check should have produced a repair sample"
    assert "The check found:" in chart[0].user


def test_repairs_stay_at_the_rate_the_runtime_fires_them(query_gate: Path, chart_gate: Path):
    query = assemble.query_samples(assemble.read_batch(query_gate))
    written = sum(1 for item in query if item.task == assemble.WRITE_SQL)
    repairs = sum(1 for item in query if item.task == assemble.REPAIR)
    assert repairs <= round(written * assemble.REPAIR_SHARE)
    chart = assemble.chart_samples(assemble.read_batch(chart_gate))
    codes = sum(1 for item in chart if item.task == assemble.CODE)
    assert sum(1 for item in chart if item.task == assemble.REPAIR) <= round(codes * assemble.CHART_REPAIR_SHARE)


def test_the_target_is_a_tool_call_the_production_parser_reads_back(query_gate: Path):
    for sample in assemble.query_samples(assemble.read_batch(query_gate)):
        body = sample.target.removeprefix("<|tool_call>").removesuffix("<tool_call|>")
        call = parse_tool_call(body)
        assert call.name in ("run_sql", CHECK_TOOL)
        if call.name == "run_sql":
            assert call.args["sql"].strip().lower().startswith(("select", "with"))
            assert call.args["reasoning"]


def test_a_value_carrying_the_quote_marker_is_refused():
    with pytest.raises(ValueError, match="quote marker"):
        assemble.tool_call("run_sql", {"sql": 'SELECT <|"|> FROM transaction_view'})


# The judge pack


def test_a_verdict_file_moves_rows_and_re_gates_a_fix(query_gate: Path, tmp_path: Path):
    batch = tmp_path / "batch"
    batch.mkdir()
    for name in ("kept.jsonl", "dropped.jsonl"):
        (batch / name).write_text((query_gate / name).read_text(encoding="utf-8"), encoding="utf-8")
    verdicts = judge_pack.read_verdicts(VERDICTS)
    result = judge_pack.apply(batch, "query", verdicts)
    kept = {item.candidate.id: item for item in result.kept}
    assert len(kept) == 10, "a fix that survives the gate is kept"
    assert "simply have no row" in kept["smoke-q03-freelancer-income-per-month-de"].candidate.reasoning
    revised = next(item for item in result.dropped if item.candidate.id == "smoke-w03-family-wrong-month-de")
    assert revised.verdict is not None and revised.verdict["verdict"] == "revise"


def test_a_fix_that_does_not_run_is_dropped_rather_than_believed(query_gate: Path, tmp_path: Path):
    batch = tmp_path / "batch"
    batch.mkdir()
    for name in ("kept.jsonl", "dropped.jsonl"):
        (batch / name).write_text((query_gate / name).read_text(encoding="utf-8"), encoding="utf-8")
    verdict = judge_pack.Verdict(
        id="smoke-q01-student-groceries-de",
        verdict="fix",
        fix=judge_pack.Fix(sql="SELECT total FROM other_table"),
    )
    result = judge_pack.apply(batch, "query", [verdict])
    dropped = {item.candidate.id: item.code for item in result.dropped}
    assert dropped["smoke-q01-student-groceries-de"] == judge_pack.FIX_FAILED


def test_a_judge_drop_leaves_the_kept_file_without_it(query_gate: Path, tmp_path: Path):
    batch = tmp_path / "batch"
    batch.mkdir()
    for name in ("kept.jsonl", "dropped.jsonl"):
        (batch / name).write_text((query_gate / name).read_text(encoding="utf-8"), encoding="utf-8")
    verdict = judge_pack.Verdict(id="smoke-q02-family-july-breakdown-en", verdict="drop", note="the period is wrong")
    result = judge_pack.apply(batch, "query", [verdict])
    assert "smoke-q02-family-july-breakdown-en" not in {item.candidate.id for item in result.kept}


def test_the_review_file_carries_what_a_judge_needs_and_no_more(query_gate: Path):
    rows = judge_pack.review_rows(query_gate, "query")
    assert {row["state"] for row in rows} == {"kept", "dropped"}
    row = rows[0]
    assert set(row) >= {"id", "question", "sql", "rows", "figure", "reasoning", "check_sql"}
    assert "expected" not in row


# The audit


def test_a_paraphrase_of_a_benchmark_question_is_caught():
    matches = audit.nearest(
        [
            ("paraphrase", "Wie viel habe ich 2025 fuer Fitness First bezahlt?"),
            ("swapped-name", "Wie viel habe ich 2025 fuer Netflix ausgegeben?"),
            ("its own question", "Welcher Wochentag ist der teuerste, und um wie viel?"),
        ]
    )
    caught = {match.id: match for match in matches}
    assert caught["paraphrase"].too_close
    assert caught["swapped-name"].too_close
    assert caught["swapped-name"].same_normal_form
    assert not caught["its own question"].too_close


def test_the_hand_written_batches_are_not_benchmark_questions(query_gate: Path, chart_gate: Path):
    for folder in (query_gate, chart_gate):
        matches = audit.nearest(audit.questions_of([folder / "kept.jsonl"]))
        assert [match.id for match in matches if match.too_close] == []


def test_the_split_is_frozen_and_still_hashes_to_the_frozen_file():
    ok, message = audit.freeze(check=True)
    assert ok, message


def test_the_held_out_report_names_every_held_out_case():
    report = audit.heldout_report()
    held = [case for case in audit.cases() if case.split == "heldout"]
    assert f"{len(held)} held-out datapoints" in report
    for case in held[:5]:
        assert f"`{case.id}`" in report
