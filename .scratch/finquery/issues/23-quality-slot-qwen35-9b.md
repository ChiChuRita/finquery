# 23: The quality slot becomes Qwen3.5 9B

**What to build:** The two chat-selectable models become Gemma 4 E4B (fast slot, unchanged, also the sub-agent slot where the adapters attach) and Qwen3.5 9B (quality slot, replacing Gemma 4 12B). The user decided this on 2026-09-04. On OpenRouter the quality slot maps to `qwen/qwen3.5-9b` (the exact same model, 262k context, tools, reasoning, image input). Locally it runs from a Q4_K_M GGUF (unsloth/Qwen3.5-9B-GGUF or bartowski/Qwen_Qwen3.5-9B-GGUF, whichever ships a Q4_K_M plus a vision projector) through llama-cpp-python, with Qwen's own wire format: `<think>` reasoning blocks and Hermes-style `<tool_call>{json}</tool_call>` tool calls, parsed into Pydantic AI thinking, text and tool-call parts the same way local/gemma.py does for Gemma.

**Blocked by:** 16 Local provider (merged)

**Status:** ready-for-agent

- [ ] OpenRouter mapping: quality slot is qwen/qwen3.5-9b with reasoning enabled; fast stays google/gemma-4-26b-a4b-it; the model selector shows "Gemma 4 E4B" and "Qwen3.5 9B" as labels with a one-line description each
- [ ] Local catalog: the quality entry downloads the Qwen3.5 9B Q4_K_M GGUF and its mmproj (verify the vendored llama.cpp b10454 supports the architecture and its vision projector; if vision is unsupported locally, say so in Settings and route images to the fast slot); the parked Gemma 12B file is no longer referenced
- [ ] A Qwen wire-format module next to local/gemma.py: chat template rendering through the GGUF's embedded template with thinking enabled, stream splitting on the think tags, tool-call parsing from the tool_call JSON blocks, tool results rendered back through the template, template tokens stripped; forced single tool works through the grammar path; both providers keep the "never combine schema and free tool calling" rule
- [ ] Memory budget re-measured with both models resident (E4B plus Qwen 9B, q8 KV, flash attention) and the context cap set accordingly in the ADR table; the sanity check command passes all four checks (answer, thinking, tool call, vision or a documented skip) on both slots
- [ ] ADR 0006 amended (models per slot, why Qwen replaces 12B, wire format differences); CONTEXT.md and README updated; DECISIONS about "no Qwen" from the old repo do not exist here, but the new ADR states the tool-calling parse is ours
- [ ] HTTP-seam tests: provider resolution for both providers, Qwen think-tag split across delta boundaries, Qwen tool-call parse to a tool part and the result rendered back, a fake llama object drives both; opt-in local smoke test runs the sanity check on both slots
- [ ] Browser verification on OpenRouter: a turn on each model with thinking visible and the label per turn; then on the local provider (the only agent allowed to load models; load once): a turn on each slot, a query tool call on Qwen, stop mid-generation, measured tokens per second per model reported
