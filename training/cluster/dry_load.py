"""Attach a converted adapter to its base and generate once, in the product's own environment.

    FINQUERY_MODELS_DIR=... uv run python training/cluster/dry_load.py --adapter query

The fifth pitfall of the research note is a crash during warmup on a quantized base with an
adapter attached, reported once and closed as stale. It costs half a minute to find out here
rather than eight hours into a benchmark, so every conversion ends with this.

It goes through `LlamaSlot` and `AdapterRegistry`, which is the path the app takes, so a load
that works here is a load that works in the app. This runs in the repository's own environment,
not the training one: it is the only step of the conversion that needs llama-cpp-python.
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from finquery.local.adapters import AdapterRegistry  # noqa: E402
from finquery.local.catalog import LOCAL_MODELS, adapter_path  # noqa: E402
from finquery.local.runtime import LlamaSlot  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    if os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit("OPENROUTER_API_KEY is set. Nothing under training/cluster/ may use it.")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", required=True, choices=("query", "chart"))
    parser.add_argument("--model", default="local:fast", help="the catalog key of the base to attach to")
    parser.add_argument("--models-dir", type=Path, default=Path(os.environ.get("FINQUERY_MODELS_DIR", "models")))
    parser.add_argument("--n-ctx", type=int, default=4096)
    args = parser.parse_args(argv)

    spec = LOCAL_MODELS[args.model]
    path = adapter_path(args.models_dir, args.adapter)
    if not path.is_file():
        raise SystemExit(f"there is no adapter at {path}")

    started = time.monotonic()
    slot = LlamaSlot(
        spec,
        spec.path(args.models_dir, spec.weights),
        spec.path(args.models_dir, spec.projector),
        args.n_ctx,
    )
    print(f"loaded {spec.name} in {round(time.monotonic() - started, 1)} s", flush=True)

    registry = AdapterRegistry(args.models_dir)
    started = time.monotonic()
    with registry.attached_to(args.adapter, slot) as note:  # type: ignore[arg-type]
        if note is not None:
            raise SystemExit(f"the adapter did not attach: {note.text}")
        print(f"attached {path.name} in {round(time.monotonic() - started, 2)} s", flush=True)
        # One generation with the adapter in place: this is the warmup that pitfall 5 crashes in.
        chunks = slot.stream(
            messages=[{"role": "user", "content": "Say ok."}],
            max_tokens=16,
            temperature=0.0,
            enable_thinking=False,
        )
        text = "".join(chunk["choices"][0].get("delta", {}).get("content") or "" for chunk in chunks)
        print(f"generated with the adapter attached: {text.strip()[:60]!r}")
    print("detached cleanly")
    slot.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
