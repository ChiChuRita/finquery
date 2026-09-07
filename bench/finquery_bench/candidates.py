"""Models the benchmark can score that the app does not offer.

A candidate is a `ModelSpec` like the catalog's, so the runner loads it through the same
`LocalStack`, the same wire formats and the same sub-agent paths; the difference is that it is
never in `finquery.local.catalog.LOCAL_MODELS`, so the app never lists it, never downloads it and
never lets a conversation start on it. Promotion to the catalog is a move of the spec, nothing
else. `finquery-bench --model local:<name>` finds both maps (`finquery_bench.models`).

Qwen3.8 27B is here because the user wants to see how the state of the art of this size class
does on the finance sets (2026-09-07), after Qwen3.5 9B lost to Gemma 4 12B on every column.
It is a dense 27B: on the 24 GB laptop it would not fit beside a resident E4B, which is one more
reason it is a candidate and not an entry.
"""

from finquery.local.catalog import FileSpec, ModelSpec

QWEN38_27B = ModelSpec(
    key="local:qwen3.8-27b",
    seat="chat",
    name="Qwen3.8-27B",
    label="Qwen3.8 27B (benchmark)",
    # Qwen3.8's `model_type` is qwen3_5 and its chat template carries the same markers as
    # Qwen3.5's (`<think>`, `<tool_call>`, `<function=`, `<parameter=`, `reasoning_content`).
    wire="qwen",
    weights=FileSpec(
        kind="weights",
        repo_id="unsloth/Qwen3.8-27B-GGUF",
        filename="Qwen3.8-27B-UD-Q4_K_M.gguf",
        size=16464440224,
        sha256="322e194ff79741c7baa497c240f677f54b201b0efab44ca8e50f122b39123482",
    ),
    projector=FileSpec(
        kind="projector",
        repo_id="unsloth/Qwen3.8-27B-GGUF",
        filename="mmproj-F16.gguf",
        size=927607488,
        sha256="cbb841a9ee0636b2ec172f5bb8df2ea8dfeb01e90fe7c6126581d662a0b4e43e",
    ),
)

CANDIDATES: dict[str, ModelSpec] = {spec.key: spec for spec in (QWEN38_27B,)}
