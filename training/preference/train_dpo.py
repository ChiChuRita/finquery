"""DPO on Gemma 4 E4B with QLoRA, one adapter per sub-agent (query, chart).

The fast slot is the only slot a sub-agent runs on, so it is the only slot an adapter is trained
for. One run produces one adapter for one sub-agent from that sub-agent's pairs:

    uv run python training/preference/train_dpo.py --adapter chart --dry-run   # validate only
    python training/preference/train_dpo.py --adapter chart                    # needs a GPU

The dry run is the part that belongs in this repository: it reads the dataset, checks it has the
three columns DPOTrainer wants and reports what training would see, and it imports neither torch
nor trl, so it runs on the laptop. Training itself is the phase after this spec (`--dry-run` off
needs a CUDA machine, `pip install trl peft bitsandbytes transformers datasets`), and the
resulting adapter has to be converted to GGUF before llama.cpp can attach it. See the README
next to this file.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

BASE_MODEL = "google/gemma-4-E4B-it"
"""The fast slot's model. The local provider runs its Q4_K_M GGUF; training reads the same
weights from Hugging Face, so the adapter fits what serves it (see finquery.local.catalog)."""

ADAPTERS = ("query", "chart")

COLUMNS = ("prompt", "chosen", "rejected")

# QLoRA: 4-bit base, LoRA on the attention and MLP projections. Small rank, because the
# datasets here are hundreds of pairs, not thousands.
LORA_RANK = 16
LORA_ALPHA = 32
LORA_TARGETS = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")
BETA = 0.1
LEARNING_RATE = 5e-6
EPOCHS = 1
MAX_PROMPT_TOKENS = 3072
MAX_TOKENS = 4096

MIN_PAIRS = 32
"""Below this a DPO run mostly measures noise. It is a warning, not a refusal."""


@dataclass(frozen=True)
class Dataset:
    """The pairs for one adapter, as they came out of `export_pairs.py`."""

    adapter: str
    path: Path
    rows: list[dict[str, Any]]

    def report(self) -> str:
        lengths = sorted(len(row["prompt"]) + max(len(row["chosen"]), len(row["rejected"])) for row in self.rows)
        longest = lengths[-1] if lengths else 0
        return (
            f"{self.adapter}: {len(self.rows)} pairs from {self.path}, "
            f"longest example {longest} characters (~{longest // 4} tokens)"
        )


def load(adapter: str, path: Path) -> Dataset:
    """Read the JSONL and refuse anything DPOTrainer would refuse later, but with a sentence."""
    if not path.is_file():
        raise SystemExit(f"No dataset at {path}. Run export_pairs.py first.")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number} is not JSON: {exc}") from exc
        for column in COLUMNS:
            value = row.get(column)
            if not isinstance(value, str) or not value.strip():
                # The Feedback page exports the raw table (objects, not strings), which is not
                # what a DPO run reads.
                raise SystemExit(
                    f"{path}:{number} has no usable {column}. A dataset here has three string "
                    "columns; run export_pairs.py on the database to produce one."
                )
        if row["chosen"].strip() == row["rejected"].strip():
            raise SystemExit(f"{path}:{number} prefers an output over itself")
        rows.append(row)
    if not rows:
        raise SystemExit(f"{path} holds no pairs yet.")
    return Dataset(adapter=adapter, path=path, rows=rows)


def train(dataset: Dataset, output: Path) -> None:
    """One DPO run on the base weights with a QLoRA adapter. Needs a GPU."""
    import torch  # noqa: PLC0415 - a dry run must not need it
    from datasets import Dataset as HFDataset  # noqa: PLC0415
    from peft import LoraConfig  # noqa: PLC0415
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig  # noqa: PLC0415
    from trl import DPOConfig, DPOTrainer  # noqa: PLC0415

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        dtype=torch.bfloat16,
        device_map="auto",
        quantization_config=BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        ),
    )
    trainer = DPOTrainer(
        model=model,
        # No reference model: with a LoRA adapter, the base weights are the reference.
        ref_model=None,
        args=DPOConfig(
            output_dir=str(output),
            beta=BETA,
            learning_rate=LEARNING_RATE,
            num_train_epochs=EPOCHS,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=8,
            gradient_checkpointing=True,
            max_prompt_length=MAX_PROMPT_TOKENS,
            max_length=MAX_TOKENS,
            bf16=True,
            logging_steps=5,
            report_to=[],
        ),
        train_dataset=HFDataset.from_list(dataset.rows),
        processing_class=tokenizer,
        peft_config=LoraConfig(
            r=LORA_RANK,
            lora_alpha=LORA_ALPHA,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=list(LORA_TARGETS),
        ),
    )
    trainer.train()
    trainer.save_model(str(output))
    print(f"adapter written to {output}")
    print("Convert it for llama.cpp before the app can attach it (see README.md).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", choices=ADAPTERS, required=True, help="which sub-agent to train")
    parser.add_argument("--data", type=Path, default=None, help="the JSONL, default data/<adapter>.jsonl")
    parser.add_argument("--out", type=Path, default=None, help="output folder, default runs/<adapter>")
    parser.add_argument("--dry-run", action="store_true", help="validate the dataset and stop")
    arguments = parser.parse_args()

    path = arguments.data or DATA / f"{arguments.adapter}.jsonl"
    dataset = load(arguments.adapter, path)
    print(dataset.report())
    if len(dataset.rows) < MIN_PAIRS:
        print(f"Warning: fewer than {MIN_PAIRS} pairs. Collect more feedback before trusting the result.")
    if arguments.dry_run:
        print(f"Dry run: the dataset is usable. Training would start from {BASE_MODEL} with QLoRA r={LORA_RANK}.")
        return
    train(dataset, arguments.out or HERE / "runs" / arguments.adapter)


if __name__ == "__main__":
    main()
