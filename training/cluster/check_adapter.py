"""The pitfall checks around the GGUF conversion, before and after.

    uv run python check_adapter.py config <checkpoint dir>
    uv run python check_adapter.py gguf <adapter.gguf>

Section 9 of `docs/research/finetuning-data-2026-09-06.md` lists five ways a LoRA adapter goes
wrong on the way into llama.cpp. Three of them are silent: a per-module rank or `use_rslora`
gives a wrong effective scale with no error, an adapter carrying `embed_tokens` on a
tied-embedding model can be skipped and still convert "successfully", and a converted adapter
that never applies looks exactly like one that works, because `AdapterRegistry` treats a
missing or inert adapter as a supported state and only leaves an audit note.

So the checks are here, they run on every conversion, and they are failures and not warnings.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from train import FORBIDDEN_MODULES, check_lora  # noqa: E402


def check_config(directory: Path) -> int:
    """The PEFT config of a checkpoint, before it is handed to the converter."""
    path = directory / "adapter_config.json"
    if not path.is_file():
        raise SystemExit(f"{path} does not exist, so this is not a PEFT checkpoint")
    config = json.loads(path.read_text(encoding="utf-8"))
    check_lora(
        {
            "use_rslora": config.get("use_rslora"),
            "use_dora": config.get("use_dora"),
            "rank_pattern": config.get("rank_pattern"),
            "alpha_pattern": config.get("alpha_pattern"),
            "modules_to_save": config.get("modules_to_save"),
            "target_modules": list(config.get("target_modules") or []),
        }
    )
    print(
        f"config ok: r {config['r']}, alpha {config['lora_alpha']}, "
        f"{len(config.get('target_modules') or [])} target modules, "
        f"effective scale {config['lora_alpha'] / config['r']}"
    )
    return 0


GGUF_EMBEDDINGS = ("token_embd.weight", "per_layer_token_embd.weight", "output.weight")
"""The tensors llama.cpp names the embeddings and the head, exactly.

Matched whole and not as substrings: `attn_output.weight` ends in `output.weight` and is the
attention output projection, which is one of the seven this adapter is meant to carry. Checking
for the substring failed the first converted adapter of 2026-09-06 on all 42 of them.
"""


def _is_embedding(tensor: str) -> bool:
    base = tensor.removesuffix(".lora_a").removesuffix(".lora_b")
    return base in GGUF_EMBEDDINGS or any(bad in base for bad in FORBIDDEN_MODULES)


def check_gguf(path: Path) -> int:
    """The converted file: no embeddings among the tensors, one global alpha in the metadata."""
    from gguf import GGUFReader

    reader = GGUFReader(str(path))
    names = [tensor.name for tensor in reader.tensors]
    carried = [name for name in names if _is_embedding(name)]
    if carried:
        raise SystemExit(
            f"{path} carries {carried}. llama.cpp rejects an adapter with embeddings, and on a "
            "tied-embedding model it can skip the tensor and apply nothing at all."
        )
    if not names:
        raise SystemExit(f"{path} has no tensors: the conversion produced an adapter that does nothing.")
    alphas = [field for key, field in reader.fields.items() if key.endswith("lora.alpha")]
    if len(alphas) != 1:
        raise SystemExit(
            f"{path} has {len(alphas)} alpha values. The converter writes one global float32 "
            "alpha and ignores anything per module, so a wrong count means a wrong scale."
        )
    alpha = float(alphas[0].parts[alphas[0].data[0]][0])
    print(f"gguf ok: {len(names)} tensors, one global alpha of {alpha}, {path.stat().st_size / 1e6:.1f} MB")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser("config", help="the PEFT checkpoint, before conversion")
    config.add_argument("directory", type=Path)
    gguf = commands.add_parser("gguf", help="the converted adapter, after conversion")
    gguf.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.command == "config":
        return check_config(args.directory)
    return check_gguf(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
