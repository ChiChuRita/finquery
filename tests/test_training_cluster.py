"""The parts of the cluster training loop that can be checked without a GPU.

No weights, no Slurm, no network: what is checked here is the seam between the product and the
training scripts, which is where a silent mistake would cost a whole training round. The rest
of the loop is proven by `training/cluster/smoke_train.sh` on the cluster.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

CLUSTER = Path(__file__).resolve().parents[1] / "training" / "cluster"
sys.path.insert(0, str(CLUSTER))

import prompts  # noqa: E402
import train  # noqa: E402
from finquery.query.subagent import load_query_context, query_prompt  # noqa: E402
from finquery_bench.datapoints import SQL_SET, load_sql, read  # noqa: E402
from finquery_bench.dataset import fresh_database  # noqa: E402
from finquery_bench.splits import HELD  # noqa: E402


@pytest.fixture(scope="module")
def context():
    with fresh_database() as (session_factory, profile_id):
        with session_factory() as session:
            yield load_query_context(session, profile_id, today=date.fromisoformat(read(SQL_SET)["today"]))


def test_the_training_prompt_is_the_products_prompt(context) -> None:
    """The user turn of a sample is `query_prompt`'s output, character for character.

    This is the whole reason `prompts.py` goes through the sub-agents rather than rebuilding
    their text: a training row that differs from the production prompt by one line trains the
    adapter for a prompt it will never be attached over.
    """
    request = prompts.query_request("Wie viel habe ich im Mai 2025 ausgegeben?", context)
    assert [message["role"] for message in request.messages] == ["system", "user"]
    assert request.messages[1]["content"] == query_prompt("Wie viel habe ich im Mai 2025 ausgegeben?", context)
    assert request.tool == "run_sql"
    assert [tool["function"]["name"] for tool in request.tools] == ["run_sql"]
    assert set(request.tools[0]["function"]["parameters"]["required"]) == {"reasoning", "sql"}


def test_a_repair_prompt_carries_the_finding(context) -> None:
    """The repair round the runtime really fires is a prompt shape the adapter is trained on."""
    rejected = prompts.Rejection(sql="SELECT 1", error="no such column: cents", reasoning="one figure")
    request = prompts.query_request("How much did I spend?", context, rejected=rejected)
    assert "no such column: cents" in request.messages[1]["content"]


class StubTokenizer:
    """A chat template that behaves the way a real one does: the generation prompt is a prefix."""

    def apply_chat_template(self, messages, tools=None, add_generation_prompt=False, tokenize=False, **kwargs):
        text = "".join(f"<{message['role']}>{message.get('content') or ''}" for message in messages if message["role"] != "assistant")
        text += f"[tools:{len(tools or [])}]"
        if add_generation_prompt:
            return text + "<assistant>"
        answers = [message for message in messages if message["role"] == "assistant"]
        for message in answers:
            call = message["tool_calls"][0]["function"]
            text += "<assistant>" + json.dumps(call["arguments"], sort_keys=True)
        return text


def test_render_pair_splits_where_generation_begins(context) -> None:
    request = prompts.query_request("How much did I spend?", context)
    prompt, completion = prompts.render_pair(StubTokenizer(), request, {"reasoning": "r", "sql": "SELECT 1"})
    assert prompt.endswith("<assistant>")
    assert completion == json.dumps({"reasoning": "r", "sql": "SELECT 1"}, sort_keys=True)


def test_render_pair_refuses_a_template_that_does_not_prefix(context) -> None:
    """A template whose two renderings disagree would put the loss in the wrong place."""

    class Wrong(StubTokenizer):
        def apply_chat_template(self, messages, **kwargs):
            return "different" if kwargs.get("add_generation_prompt") else "text"

    request = prompts.query_request("How much did I spend?", context)
    with pytest.raises(RuntimeError, match="cannot be split off"):
        prompts.render_pair(Wrong(), request, {"reasoning": "r", "sql": "SELECT 1"})


def test_a_generated_tool_call_is_parsed_by_the_products_own_splitter() -> None:
    text = '<|tool_call>call:run_sql{reasoning:<|"|>one figure<|"|>,sql:<|"|>SELECT 1<|"|>}<tool_call|><turn|>'
    answered = prompts.parse_sql(text)
    assert answered is not None
    assert answered.sql == "SELECT 1"
    assert prompts.parse_sql("I cannot answer that.") is None


def test_the_conversion_pitfalls_are_refused_before_a_step_runs() -> None:
    """The three settings the GGUF converter ignores in silence, and the head."""
    for bad in ({"use_rslora": True}, {"use_dora": True}, {"rank_pattern": {"q_proj": 8}}):
        with pytest.raises(SystemExit):
            train.check_lora({"target_modules": ["q_proj"], **bad})
    with pytest.raises(SystemExit, match="embedding or the head"):
        train.check_lora({"target_modules": ["q_proj", "lm_head"]})
    train.check_lora({"target_modules": ["q_proj", "gate_proj"], "use_rslora": False, "rank_pattern": {}})
    # `auto` leaves the choice of modules to PEFT, which is the only thing that works on
    # Gemma 4. It does not excuse anything else: rslora is still refused.
    train.check_lora({"target_modules": train.AUTO_MODULES})
    with pytest.raises(SystemExit):
        train.check_lora({"target_modules": train.AUTO_MODULES, "use_rslora": True})


class StubModel:
    """Just enough of a wrapped model for `check_adapted` to read the LoRA layers off it."""

    def __init__(self, names: list[str]) -> None:
        self._names = names

    def named_modules(self):
        return [(name, object()) for name in self._names]


def test_what_peft_really_adapted_is_read_off_the_model() -> None:
    """`target_modules: auto` gives up naming the modules, so they are checked afterwards."""
    good = [
        "model.language_model.layers.0.self_attn.q_proj",
        "model.language_model.layers.0.self_attn.q_proj.lora_A",
        "model.language_model.layers.0.mlp.down_proj.lora_A",
    ]
    assert train.check_adapted(StubModel(good)) == ["down_proj", "q_proj"]
    with pytest.raises(SystemExit, match="PEFT adapted"):
        train.check_adapted(StubModel(["model.embed_tokens.lora_A"]))
    with pytest.raises(SystemExit, match="adapter would be empty"):
        train.check_adapted(StubModel(["model.language_model.layers.0.self_attn.q_proj"]))


def test_every_config_passes_its_own_check() -> None:
    import yaml

    configs = sorted((CLUSTER / "configs").glob("*.yaml"))
    assert [path.stem for path in configs] == ["chart-12b", "chart-e4b", "query-12b", "query-e4b"]
    for path in configs:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        train.check_lora(payload["lora"])
        # alpha is 2r, which is what keeps the effective scale right after conversion.
        assert payload["lora"]["alpha"] == 2 * payload["lora"]["r"]
        assert payload["train"]["per_device_batch"] * payload["train"]["grad_accum"] == 16


def test_the_warmup_is_three_percent_of_the_steps_trl_will_run() -> None:
    settings = {"per_device_batch": 1, "grad_accum": 16, "epochs": 3, "warmup_ratio": 0.03}
    assert train.warmup_steps(2000, settings, None) == (375, 11)
    # A smoke run names its own step count, and warmup is never zero.
    assert train.warmup_steps(40, settings, 20) == (20, 1)


def test_the_smoke_fixture_names_real_train_split_datapoints() -> None:
    """A datapoint that moved into the held-out half would contaminate the quick evaluation."""
    seed = json.loads((CLUSTER / "samples" / "smoke-query.json").read_text(encoding="utf-8"))
    points = {point.id: point for point in load_sql()}
    assert len(seed["samples"]) == 40
    for sample in seed["samples"]:
        point = points.get(sample["id"])
        assert point is not None, f"{sample['id']} is not in the SQL benchmark"
        assert point.split != HELD, f"{sample['id']} is held out"
        assert sample["reasoning"].strip()
        # The prompt says there is no cents column, so a target may not name one.
        assert "amount_cents" not in point.sql


def test_the_quick_set_is_held_out_and_does_not_move() -> None:
    import quick_eval

    sql, charts = quick_eval.quick_set(50, 50)
    assert all(point.split == HELD for point in [*sql, *charts])
    again, _ = quick_eval.quick_set(50, 50)
    assert [point.id for point in sql] == [point.id for point in again]
