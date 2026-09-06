"""Turn the assembled samples of `training/data/assemble.py` into the rows `train.py` reads.

The assembly writes each sample as the two wire messages (system, user) plus the completion
as Gemma 4 writes a tool call on the wire. `train.py` renders a sample through the base model's
own chat template from `messages` with a `tool_calls` entry and the `tools` the local provider
declares, which is what the smoke run validated end to end. This script bridges the two: the
messages are taken as they are (the assembly uses the same system and user texts the local
provider sends), the tool call is parsed back into arguments, and the tool declarations are
captured once per tool from the real agents through `prompts._capture`.

    uv run --project training/cluster python training/cluster/convert_samples.py \
      training/data/out/samples/query-train.jsonl /tmp/query.jsonl
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prompts  # noqa: E402
from finquery.local import gemma  # noqa: E402
from finquery.query.check import CHECK_TOOL, check_agent  # noqa: E402

AGENTS = {
    prompts.QUERY_TOOL: prompts.query_agent,
    prompts.PLAN_TOOL: prompts.plan_agent,
    prompts.CODE_TOOL: prompts.code_agent,
    CHECK_TOOL: check_agent,
}
prompts.CANNED.setdefault(CHECK_TOOL, {"verdict": "ok", "reason": "", "intent": ""})


def tools_for(tool: str, cache: dict[str, list[dict]]) -> list[dict]:
    if tool not in cache:
        cache[tool] = prompts._capture(AGENTS[tool], tool, "x").tools
    return cache[tool]


def convert(source: Path, target: Path) -> None:
    cache: dict[str, list[dict]] = {}
    written = 0
    skipped = 0
    with target.open("w", encoding="utf-8") as out:
        for line in source.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            text = row["completion"][0]["content"]
            start = text.find(gemma.TOOL_CALL_OPEN)
            end = text.find(gemma.TOOL_CALL_CLOSE)
            if start < 0 or end < 0:
                skipped += 1
                continue
            try:
                call = gemma.parse_tool_call(text[start + len(gemma.TOOL_CALL_OPEN):end])
            except Exception:  # noqa: BLE001
                skipped += 1
                continue
            request = prompts.Request(tool=call.name, messages=row["prompt"], tools=tools_for(call.name, cache))
            out.write(
                json.dumps(
                    {
                        "id": row["id"],
                        "adapter": row["adapter"],
                        "task": row["task"],
                        "messages": request.with_answer(call.args),
                        "tools": request.tools,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            written += 1
    print(f"{target}: {written} rows written, {skipped} skipped (no parsable tool call)")


if __name__ == "__main__":
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
