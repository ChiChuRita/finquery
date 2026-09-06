"""One QLoRA adapter, driven by one YAML file under `configs/`.

    uv run python train.py configs/query-e4b.yaml
    uv run python train.py configs/query-e4b.yaml --max-steps 20 --samples smoke.jsonl

A 4-bit NF4 base with bf16 compute, LoRA on the attention and MLP projections only, completion
only loss on the chat-format samples, and one checkpoint per epoch. `quick_eval.py` scores each
of those checkpoints and only the best one is converted to GGUF, which is the rule the README
spells out.

Everything that decides a number is in the YAML, so a run is reproducible from the file beside
its output. Nothing here reaches the network beyond the Hugging Face cache on scratch, and the
first thing it does is refuse to run if an OpenRouter key is in the environment.
"""

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prompts  # noqa: E402


def refuse_openrouter_key() -> None:
    """The one thing no job under training/cluster/ may see. Asserted in every entry point."""
    if os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit(
            "OPENROUTER_API_KEY is set. Nothing under training/cluster/ may use it: the cluster "
            "runs on local weights and the key belongs to the dev server on the laptop."
        )


@dataclass(frozen=True)
class Config:
    """One adapter's whole recipe."""

    name: str
    adapter: str
    base: str
    samples: Path
    output: Path
    lora: dict[str, Any]
    train: dict[str, Any]

    @staticmethod
    def read(path: Path, root: Path) -> "Config":
        # Imported here, not at the top: `check_lora` and the rest of this module are read by
        # check_adapter.py and by the tests, neither of which has the training environment.
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Config(
            name=payload["name"],
            adapter=payload["adapter"],
            base=payload["base"],
            samples=root / payload["samples"] if not payload["samples"].startswith("/") else Path(payload["samples"]),
            output=Path(payload["output"]),
            lora=payload["lora"],
            train=payload["train"],
        )


# The three keys the GGUF converter ignores in silence, so a run that sets one produces an
# adapter with the wrong effective scale and no error anywhere (research note, section 9,
# pitfall 4). They are refused here rather than discovered after a night of training.
FORBIDDEN_LORA = ("use_rslora", "use_dora", "rank_pattern", "alpha_pattern", "modules_to_save")

# The converter hard-rejects an adapter that carries embeddings, and on a tied-embedding model
# it can skip the tensor and convert "successfully" into something that never applies
# (pitfall 3). So these never go in `target_modules`, whatever a guide says.
FORBIDDEN_MODULES = ("embed_tokens", "lm_head", "embed_tokens_per_layer")


AUTO_MODULES = "auto"
"""`target_modules: auto` in a config: let PEFT pick, and check what it picked afterwards.

Gemma 4 needs this. Its projections are wrapped in `Gemma4ClippableLinear` outside the language
model, and PEFT refuses one of those with "Target module Gemma4ClippableLinear is not
supported", so an explicit `q_proj, k_proj, ...` list fails before the first step. PEFT's own
defaults for this architecture are scoped to the language model's layers, which is what the
research note says and what the run of 2026-09-06 confirmed. `check_adapted` then reads the
wrapped model and refuses anything that is an embedding or the head, so the guarantee the
explicit list was there for is kept, from the model rather than from the YAML.
"""


def check_lora(lora: dict[str, Any]) -> None:
    for key in FORBIDDEN_LORA:
        if lora.get(key):
            raise SystemExit(
                f"{key} is set in the LoRA config. convert_lora_to_gguf.py writes one global "
                "alpha and ignores the rest, so the adapter would have the wrong scale in "
                "llama.cpp with nothing to warn you. See docs/research/finetuning-data-2026-09-06.md."
            )
    targets = lora.get("target_modules") or []
    if targets == AUTO_MODULES:
        return
    # A string is a regular expression, which is what the Gemma 4 configs use; a list is names.
    for module in [targets] if isinstance(targets, str) else targets:
        if any(bad in module for bad in FORBIDDEN_MODULES):
            raise SystemExit(f"{module} is an embedding or the head, which the GGUF converter rejects.")


def check_adapted(model: Any) -> list[str]:
    """The modules that really got a LoRA, read off the wrapped model. Returns their suffixes."""
    found: set[str] = set()
    for name, _ in model.named_modules():
        parts = name.split(".")
        # `...self_attn.q_proj.lora_A` and `...self_attn.q_proj.lora_A.default` both name the
        # module that was adapted one segment in front of `lora_A`.
        if "lora_A" in parts and parts.index("lora_A") > 0:
            found.add(parts[parts.index("lora_A") - 1])
    adapted = sorted(found)
    if not adapted:
        raise SystemExit("no module got a LoRA: the adapter would be empty.")
    carried = [name for name in adapted if any(bad in name for bad in FORBIDDEN_MODULES)]
    if carried:
        raise SystemExit(
            f"PEFT adapted {carried}, which the GGUF converter rejects and can silently skip on "
            "a tied-embedding model. Name the projections in the config's target_modules."
        )
    return adapted


def load_samples(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"{path} has no samples")
    return rows


def to_pairs(tokenizer: Any, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Every sample as a prompt and the completion the loss is taken on."""
    pairs = []
    for row in rows:
        request = prompts.Request(
            tool=row["messages"][-1]["tool_calls"][0]["function"]["name"],
            messages=row["messages"][:-1],
            tools=row["tools"],
        )
        arguments = row["messages"][-1]["tool_calls"][0]["function"]["arguments"]
        prompt, completion = prompts.render_pair(tokenizer, request, arguments)
        pairs.append({"prompt": prompt, "completion": completion})
    return pairs


def report_lengths(tokenizer: Any, pairs: list[dict[str, str]], seq_len: int) -> None:
    """What the samples really cost in tokens, against the sequence length that was chosen.

    The research note asks for the true p100 before the first run: a repair prompt is the long
    one, and a sample that is truncated is a sample whose answer is cut off mid-statement.
    """
    lengths = sorted(len(tokenizer(pair["prompt"] + pair["completion"]).input_ids) for pair in pairs)
    p = lambda q: lengths[min(len(lengths) - 1, int(q * (len(lengths) - 1)))]  # noqa: E731
    print(f"tokens per sample: p50 {p(0.5)}, p95 {p(0.95)}, p100 {lengths[-1]}, sequence length {seq_len}")
    over = sum(1 for length in lengths if length > seq_len)
    if over:
        print(
            f"WARNING: {over} of {len(lengths)} samples are longer than the sequence length and "
            "will be truncated. Raise `seq_len` in the config.",
            flush=True,
        )


def warmup_steps(samples: int, train: dict[str, Any], max_steps: int | None) -> tuple[int, int]:
    """The total number of optimizer steps and the warmup that is three percent of it.

    TRL 1.12 takes `warmup_steps` and no longer takes a ratio, so the ratio the config names is
    turned into steps here rather than being silently dropped. At least one step: a cosine
    schedule that starts at the full learning rate on a small set is what a diverging first
    epoch looks like.
    """
    per_epoch = max(1, math.ceil(samples / (train["per_device_batch"] * train["grad_accum"])))
    total = max_steps or per_epoch * train["epochs"]
    return total, max(1, round(total * train["warmup_ratio"]))


def main(argv: list[str] | None = None) -> int:
    refuse_openrouter_key()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--samples", type=Path, default=None, help="override the config's sample file")
    parser.add_argument("--output", type=Path, default=None, help="override the config's output directory")
    parser.add_argument("--max-steps", type=int, default=None, help="stop after this many steps (the smoke run)")
    parser.add_argument("--dry-run", action="store_true", help="build the dataset and report, load no weights")
    args = parser.parse_args(argv)

    root = args.config.resolve().parent.parent
    config = Config.read(args.config, root)
    check_lora(config.lora)
    samples = args.samples or config.samples
    output = args.output or config.output
    print(f"{config.name}: {config.base} on {samples}", flush=True)

    import torch
    from peft import LoraConfig
    from transformers import AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    tokenizer = AutoTokenizer.from_pretrained(config.base)
    pairs = to_pairs(tokenizer, load_samples(samples))
    report_lengths(tokenizer, pairs, config.train["seq_len"])
    print(f"{len(pairs)} samples", flush=True)
    if args.dry_run:
        print(pairs[0]["completion"])
        return 0

    from datasets import Dataset

    dataset = Dataset.from_list(pairs)

    # 4-bit NF4 with double quantization, bf16 compute. Never fp16 on Gemma 4: the audio path's
    # mask value of -1e9 overflows fp16's range (research note, section 5).
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    targets = config.lora["target_modules"]
    peft_config = LoraConfig(
        r=config.lora["r"],
        lora_alpha=config.lora["alpha"],
        lora_dropout=config.lora["dropout"],
        bias="none",
        task_type="CAUSAL_LM",
        # A string reaches PEFT as a regular expression it full-matches every module name
        # against; a list reaches it as names. `auto` passes nothing and lets PEFT choose.
        **({} if targets == AUTO_MODULES else {"target_modules": targets if isinstance(targets, str) else list(targets)}),
    )
    train = config.train
    total_steps, warmup = warmup_steps(len(pairs), train, args.max_steps)
    print(f"{total_steps} steps, {warmup} of them warmup", flush=True)
    sft = SFTConfig(
        output_dir=str(output),
        max_length=train["seq_len"],
        num_train_epochs=train["epochs"],
        per_device_train_batch_size=train["per_device_batch"],
        gradient_accumulation_steps=train["grad_accum"],
        learning_rate=float(train["lr"]),
        lr_scheduler_type=train["scheduler"],
        warmup_steps=warmup,
        weight_decay=train["weight_decay"],
        seed=train["seed"],
        bf16=True,
        fp16=False,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        logging_steps=1,
        # One checkpoint per epoch is the unit quick_eval.py scores and the curve is read from.
        save_strategy="epoch",
        save_total_limit=None,
        report_to=[],
        # A prompt-completion dataset, so the loss is on the completion. Spelled out rather than
        # left to the default: putting the loss on the prompt trains the model on its own rules.
        completion_only_loss=True,
        model_init_kwargs={
            "quantization_config": quantization,
            "dtype": torch.bfloat16,
            "device_map": {"": 0},
            "attn_implementation": "eager",
        },
        **({"max_steps": args.max_steps} if args.max_steps else {}),
    )
    # The tokenizer and not an `AutoProcessor`: Gemma 4 is multimodal, so TRL would otherwise
    # load `Gemma4Processor` and pull in the whole image pipeline for a dataset that is two
    # strings per row. There is no image in any training sample and there never will be: the
    # sub-agents this trains are text in, tool call out.
    trainer = SFTTrainer(
        model=config.base,
        args=sft,
        train_dataset=dataset,
        peft_config=peft_config,
        processing_class=tokenizer,
    )
    trainer.model.print_trainable_parameters()
    adapted = check_adapted(trainer.model)
    print(f"adapted modules: {', '.join(adapted)}", flush=True)

    started = time.monotonic()
    result = trainer.train()
    seconds = time.monotonic() - started
    trainer.save_model(str(output / "final"))

    steps = max(1, int(result.global_step))
    summary = {
        "name": config.name,
        "adapter": config.adapter,
        "base": config.base,
        "samples": str(samples),
        "n": len(pairs),
        "steps": result.global_step,
        "epochs": train["epochs"] if not args.max_steps else None,
        "train_loss": round(float(result.training_loss), 4),
        "seconds": round(seconds, 1),
        "seconds_per_step": round(seconds / steps, 2),
        "lora": config.lora,
        "adapted_modules": adapted,
        "train": train,
    }
    (output / "train-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"checkpoints in {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
