# 16: Local provider

**What to build:** With the provider set to local, the same app runs on Gemma 4 E4B (fast) and 12B (quality) in-process through llama-cpp-python. First run downloads the GGUF files and their multimodal projectors with progress shown in the UI, reusing a parked copy if its hash matches. Both models stay resident with a context cap that fits 24 GB. Thinking is enabled through the chat template and split into reasoning parts; tool calls are parsed from the Gemma 4 syntax; images work through the vision path; schema-constrained calls use a forced single tool and are never combined with free tool calling. An adapter registry attaches a LoRA adapter to the fast slot per sub-agent with a lock, falling back to base weights with an audit note when the file is missing. A sanity check command proves both models answer, think and call a tool.

**Blocked by:** 01 Walking skeleton

**Status:** ready-for-agent

- [ ] Custom Pydantic AI model over llama-cpp-python with streaming, thinking split, tool-call parsing, usage reporting, cancellation
- [ ] Gemma 4 multimodal chat handler wrapped so thinking is on; images passed as content parts
- [ ] Download manager with progress endpoint and UI; hash reuse of parked files
- [ ] Both models resident, 32k context each, Metal on macOS
- [ ] Adapter registry (query, chart) with attach and detach through the low-level API and a lock; missing adapter falls back loudly
- [ ] Sanity check command and Settings button covering answer, thinking, tool call, vision, for both slots
- [ ] HTTP-seam tests that do not load real models: provider resolution, adapter fallback note, download progress endpoint with a stubbed downloader
- [ ] Opt-in smoke test on real local models; browser verification of a chat turn on local
