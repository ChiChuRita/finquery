# 23: The quality slot becomes Qwen3.5 9B

**What to build:** The two chat-selectable models become Gemma 4 E4B (fast slot, unchanged, also the sub-agent slot where the adapters attach) and Qwen3.5 9B (quality slot, replacing Gemma 4 12B). The user decided this on 2026-09-04. On OpenRouter the quality slot maps to `qwen/qwen3.5-9b` (the exact same model, 262k context, tools, reasoning, image input). Locally it runs from a Q4_K_M GGUF (unsloth/Qwen3.5-9B-GGUF or bartowski/Qwen_Qwen3.5-9B-GGUF, whichever ships a Q4_K_M plus a vision projector) through llama-cpp-python, with Qwen's own wire format: `<think>` reasoning blocks and Hermes-style `<tool_call>{json}</tool_call>` tool calls, parsed into Pydantic AI thinking, text and tool-call parts the same way local/gemma.py does for Gemma.

**Blocked by:** 16 Local provider (merged)

**Status:** done

- [x] OpenRouter mapping: quality slot is qwen/qwen3.5-9b with reasoning enabled; fast stays google/gemma-4-26b-a4b-it; the model selector shows "Gemma 4 E4B" and "Qwen3.5 9B" as labels with a one-line description each
- [x] Local catalog: the quality entry downloads the Qwen3.5 9B Q4_K_M GGUF and its mmproj (verify the vendored llama.cpp b10454 supports the architecture and its vision projector; if vision is unsupported locally, say so in Settings and route images to the fast slot); the parked Gemma 12B file is no longer referenced
- [x] A Qwen wire-format module next to local/gemma.py: chat template rendering through the GGUF's embedded template with thinking enabled, stream splitting on the think tags, tool-call parsing from the tool_call JSON blocks, tool results rendered back through the template, template tokens stripped; forced single tool works through the grammar path; both providers keep the "never combine schema and free tool calling" rule
- [x] Memory budget re-measured with both models resident (E4B plus Qwen 9B, q8 KV, flash attention) and the context cap set accordingly in the ADR table; the sanity check command passes all four checks (answer, thinking, tool call, vision or a documented skip) on both slots
- [x] ADR 0006 amended (models per slot, why Qwen replaces 12B, wire format differences); CONTEXT.md and README updated; DECISIONS about "no Qwen" from the old repo do not exist here, but the new ADR states the tool-calling parse is ours
- [x] HTTP-seam tests: provider resolution for both providers, Qwen think-tag split across delta boundaries, Qwen tool-call parse to a tool part and the result rendered back, a fake llama object drives both; opt-in local smoke test runs the sanity check on both slots
- [x] Browser verification on OpenRouter: a turn on each model with thinking visible and the label per turn; then on the local provider (the only agent allowed to load models; load once): a turn on each slot, a query tool call on Qwen, stop mid-generation, measured tokens per second per model reported

## Comments

Done 2026-09-05. `FINQUERY_PROVIDER` still decides everything; the slot ids are unchanged and
only the labels moved.

**The tool-call format is not the one this ticket assumed.** Qwen3.5 does not write Hermes
JSON. Its embedded chat template instructs the model to write one tag per parameter, which is
what vLLM calls the `qwen3_coder` parser:

```
<tool_call>
<function=query>
<parameter=question>
total spending in May 2025
</parameter>
</function>
</tool_call>
```

So `finquery.local.qwen` parses that, not JSON. A parameter body arrives as text and stays
text unless it opens a JSON object or array: Pydantic reads "20" as 20 for an int field, while
an int handed to a string field is a validation error, so guessing types would cost more than
it buys. Everything else the ticket asked for held: thinking is `<think>`/`</think>`, tool
results go back as `role: tool` messages the template renders as `<tool_response>`, and past
thinking travels as `reasoning_content` rather than Gemma's `reasoning`.

**Layout.** `finquery.local.wire` is the shape a wire format has (splitter, stop strings,
sampling, the reasoning key, whether the prompt opens the thought channel, extra template
arguments) plus the marker-splitting helper. `finquery.local.gemma` was left untouched, as
asked, and keeps its own copy of that helper. `finquery.local.qwen` is the new one.
`LlamaCppModel` picks between them through `WIRE_FORMATS`, keyed by the new `wire` field on
the catalog entry, so it is the model that decides and not the slot. One handler serves both:
`Gemma4ChatHandler` turned out to be an empty subclass of `MTMDChatHandler`.

**Context cap is now 32768**, the number the spec originally asked for and ticket 16 could not
afford. Both models resident with a projector each, q8_0 KV, flash attention: E4B 7.1 GB plus
Qwen 6.4 GB is 13.5 GB of a Mac that allows 18.2 GB. Doubling Qwen's context costs 0.27 GB
because only every fourth layer is full attention. Table in ADR 0006.

**A bug this ticket found and fixed.** The forced-tool path (every sub-agent: query, chart,
categorizer, mapping, extraction, memory) was broken on the local provider and had never been
exercised against a real model. llama-cpp-python repeats the whole tool name on every stream
chunk, Pydantic AI treats a name as a delta and concatenates it, so `run_sql` arrived as
`run_sqlrun_sqlrun_sql...` and every sub-agent call failed with "exceeded max retries". The
name now goes with the first chunk of a call only. The fake slot in
`test_a_schema_constrained_request_forces_a_single_tool` now streams the way llama.cpp really
does, and that test fails without the fix.

**Measured on this 24 GB M4 Pro**, from `uv run finquery-check`:

| Slot                     | load  | answer          | tool call       | vision          |
| ------------------------ | ----- | --------------- | --------------- | --------------- |
| fast, Gemma 4 E4B        | 0.7s  | 4.7s, 32 tok/s  | 2.3s, 37 tok/s  | 2.9s, 43 tok/s  |
| quality, Qwen3.5 9B      | 2.2s  | 97s, 29 tok/s   | 6.0s, 18 tok/s  | 4.0s, 28 tok/s  |

All eight checks pass. Qwen's 97 seconds is not slowness, it is 8426 characters of thinking
for a three-number sum: it generates at the same rate as E4B and simply thinks much longer.

What ticket 17 (demo on the local provider) should know:

- Budget for thinking. A Qwen turn is 30 to 120 seconds even when the answer is one line.
  Choosing the fast slot for the live demo and the quality slot for one prepared question is
  the safer shape.
- llama-cpp-python's multimodal handler clears the KV cache and re-evaluates the whole prompt
  on every request, so there is no prefix caching: turn latency grows with the conversation,
  and the first token of a late turn can be 20 seconds behind the submit. Stop pressed in that
  window keeps the turn and marks it interrupted, but there is nothing to show in it.
- Both models stay resident after first use: 13.5 GB. Do not run anything else heavy.
- The models live in `models/` (12.6 GB) and are linked from
  `/Users/chichurita/Dev/finquery-old-models` when `FINQUERY_PARKED_MODELS_DIR` points there.

Tests: 132 passed, 3 skipped, plus the opt-in smoke suite (`FINQUERY_PROVIDER=local
FINQUERY_SMOKE=1 uv run pytest tests/test_local_smoke.py -s`). Screenshots of the verification:
/tmp/finquery-23/.
