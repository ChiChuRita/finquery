# 16: Local provider

**What to build:** With the provider set to local, the same app runs on Gemma 4 E4B (fast) and 12B (quality) in-process through llama-cpp-python. First run downloads the GGUF files and their multimodal projectors with progress shown in the UI, reusing a parked copy if its hash matches. Both models stay resident with a context cap that fits 24 GB. Thinking is enabled through the chat template and split into reasoning parts; tool calls are parsed from the Gemma 4 syntax; images work through the vision path; schema-constrained calls use a forced single tool and are never combined with free tool calling. An adapter registry attaches a LoRA adapter to the fast slot per sub-agent with a lock, falling back to base weights with an audit note when the file is missing. A sanity check command proves both models answer, think and call a tool.

**Blocked by:** 01 Walking skeleton

**Status:** done

- [x] Custom Pydantic AI model over llama-cpp-python with streaming, thinking split, tool-call parsing, usage reporting, cancellation
- [x] Gemma 4 multimodal chat handler wrapped so thinking is on; images passed as content parts
- [x] Download manager with progress endpoint and UI; hash reuse of parked files
- [x] Both models resident, Metal on macOS, 16k context each (32k does not fit 24 GB, see the comment)
- [x] Adapter registry (query, chart) with attach and detach through the low-level API and a lock; missing adapter falls back loudly
- [x] Sanity check command and Settings button covering answer, thinking, tool call, vision, for both slots
- [x] HTTP-seam tests that do not load real models: provider resolution, adapter fallback note, download progress endpoint with a stubbed downloader
- [x] Opt-in smoke test on real local models; browser verification of a chat turn on local

## Comments

Done 2026-09-04. `FINQUERY_PROVIDER=local` and nothing else moves: the API, the chat agent and
the UI are unchanged. `docs/adr/0005-local-gemma-4-through-llama-cpp.md` records the design and
the memory measurements.

What ticket 05, 06 and 07 need from this:

- A sub-agent gets a schema by having exactly one tool and no text output. The model then forces
  that tool, which makes llama.cpp build a GBNF grammar from its parameters, and turns thinking
  off for that request. `response_format` is never sent, so a schema and free tool calling are
  never in the same request. Just use `Agent(model, output_type=YourModel)`; nothing local-specific.
- A sub-agent asks for its LoRA adapter with `model_settings={"finquery_adapter": "query"}`
  (or `"chart"`). With no adapter file the run continues on the base weights and the audit note
  lands on the response metadata, which the chat endpoint lifts into the turn metadata as
  `audit_notes`.
- Sub-agents share the fast slot with the chat agent, serialized per slot. Do not hold a slot
  across an `await` that waits on the user.

Deviation from the acceptance list: the context cap is 16384, not 32768. Both models at 32k need
19.2 GB of Metal working set even with flash attention and a q8_0 KV cache, and this 24 GB Mac
allows 18.2 GB. `FINQUERY_LOCAL_N_CTX` raises it on a bigger machine. Table in the ADR.

Layout: `src/finquery/local/` (`catalog.py` files and hashes, `downloads.py` progress and parked
reuse, `runtime.py` resident slots plus per-slot thread and lock, `adapters.py` LoRA registry,
`model.py` the Pydantic AI model, `gemma.py` the wire format, `check.py` the sanity check),
`src/finquery/api/models.py` (`GET /api/models` is the progress endpoint, plus download and
check), `frontend/src/components/models-card.tsx` on `/settings`.

Tests: 11 new at the HTTP seam plus one opt-in smoke suite. `uv run pytest` is 18 passed,
1 skipped. Screenshots of the verification: /tmp/finquery-16/.
