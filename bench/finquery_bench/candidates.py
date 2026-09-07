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

Gemma 4 12B is here because it was the shipped chat model until ticket 75, when the 26B A4B took
the seat on the same accuracy and much more speed. It keeps its catalog key, `local:gemma-4-12b`,
so `finquery-bench --model local:gemma-4-12b`, the cluster scripts and every recorded run under
that name still resolve: its runs are the baseline the newer numbers are read against.
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

LOCAL_GEMMA_12B = ModelSpec(
    key="local:gemma-4-12b",
    seat="chat",
    name="gemma-4-12b-it",
    label="Gemma 4 12B (local)",
    wire="gemma",
    weights=FileSpec(
        kind="weights",
        repo_id="unsloth/gemma-4-12b-it-GGUF",
        filename="gemma-4-12b-it-Q4_K_M.gguf",
        size=7121861440,
        sha256="0a270ec9fe6b34f4a0d33992b6135117b484ebc4766ab76b51d4ae8c457e4c42",
    ),
    projector=FileSpec(
        kind="projector",
        repo_id="unsloth/gemma-4-12b-it-GGUF",
        filename="mmproj-F16.gguf",
        size=175115840,
        sha256="91f086971e56d7a7d8d39e271873fccdb49541bd259d6e02c401a4f1cb7a219e",
    ),
)

CANDIDATES: dict[str, ModelSpec] = {spec.key: spec for spec in (QWEN38_27B, LOCAL_GEMMA_12B)}
