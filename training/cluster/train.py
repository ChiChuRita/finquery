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
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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


def check_lora(lora: dict[str, Any]) -> None:
    for key in FORBIDDEN_LORA:
        if lora.get(key):
            raise SystemExit(
                f"{key} is set in the LoRA config. convert_lora_to_gguf.py writes one global "
                "alpha and ignores the rest, so the adapter would have the wrong scale in "
                "llama.cpp with nothing to warn you. See docs/research/finetuning-data-2026-09-06.md."
            )
    for module in lora.get("target_modules", []):
        if any(bad in module for bad in FORBIDDEN_MODULES):
            raise SystemExit(f"{module} is an embedding or the head, which the GGUF converter rejects.")


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
    peft_config = LoraConfig(
        r=config.lora["r"],
        lora_alpha=config.lora["alpha"],
        lora_dropout=config.lora["dropout"],
        target_modules=list(config.lora["target_modules"]),
        bias="none",
        task_type="CAUSAL_LM",
    )
    train = config.train
    sft = SFTConfig(
        output_dir=str(output),
        max_length=train["seq_len"],
        num_train_epochs=train["epochs"],
        per_device_train_batch_size=train["per_device_batch"],
        gradient_accumulation_steps=train["grad_accum"],
        learning_rate=float(train["lr"]),
        lr_scheduler_type=train["scheduler"],
        warmup_ratio=train["warmup_ratio"],
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
    trainer = SFTTrainer(model=config.base, args=sft, train_dataset=dataset, peft_config=peft_config)
    trainer.model.print_trainable_parameters()

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
        "train": train,
    }
    (output / "train-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"checkpoints in {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
