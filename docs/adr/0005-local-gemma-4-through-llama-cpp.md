# ADR 0005: The local provider is a custom Pydantic AI model over llama-cpp-python

Date: 2026-09-04
Status: accepted

## Context

The demo and the hand-in run on the machine, not on OpenRouter (ADR 0002). Gemma 4 through
llama-cpp-python has no Pydantic AI adapter, and its chat format is not one of the shapes
llama.cpp normalizes for us: thinking, tool calls and the argument encoding all travel inside a
single text stream that only the Gemma 4 chat template understands. Two 4-bit models and their
multimodal projectors also have to share one 24 GB Mac.

## Decision

- `finquery.local.model.LlamaCppModel` is a `pydantic_ai.models.Model`. `finquery.local` is the
  only package that imports `llama_cpp`; the API, the agent and the UI are unchanged.
- The prompt is built by the chat template inside the GGUF, reached through
  `llama_cpp.llama_chat_format.Gemma4ChatHandler`. Pydantic AI messages are rendered to the
  OpenAI-shaped dicts that template expects: instructions and system prompts fold into one
  leading system message, thinking travels as `reasoning` on assistant messages, tool calls as
  `tool_calls` with mapping arguments, tool results as `role: tool` messages.
- The handler is called directly rather than through `Llama.create_chat_completion`, which has
  no `**kwargs` and so cannot pass `enable_thinking` to the template. Thinking is therefore a
  template argument, not a request flag. `preserve_thinking` keeps the reasoning that led to a
  tool call and drops the rest of the history's.
- `finquery.local.gemma` is the wire format: a splitter that turns the raw token stream into
  thinking parts, text parts and tool calls, holding back any delta that could still be the
  start of a marker, and a parser for the Gemma argument DSL (`<|"|>`-quoted strings, bare
  keys). It imports nothing, so it is testable without a model.
- Schema-constrained output and free tool calling are never combined. A request with exactly one
  tool and no text output (the sub-agent shape) forces that tool, which makes llama.cpp build a
  GBNF grammar from its parameters, and turns thinking off because a grammar leaves no room for
  it. Every other request declares its tools with `tool_choice: auto`. `response_format` is
  never sent.
- Cancellation is checked between tokens. Generation runs one token at a time in a worker
  thread, so the Stop endpoint's `CancellationToken` and the `StreamedResponse.close_stream`
  path both end the loop within one token.
- LoRA adapters attach through the low-level API (`llama_adapter_lora_init`,
  `llama_set_adapters_lora`, `llama_adapter_lora_free`; there is no remove call, so detaching
  means setting an empty adapter list). A `threading.Lock` makes attach, run and detach one
  unit. A sub-agent asks for its adapter by setting `finquery_adapter` in its model settings.
- A missing adapter file is a supported state: the run continues on the base weights and an
  audit note rides the response metadata into the turn metadata, so the client sees it live and
  a reload still shows it.
- Both slots load on first use and stay resident. Files are downloaded on startup with
  per-file progress on `GET /api/models`, and a parked copy whose sha256 matches the Hugging
  Face metadata is linked in instead of downloaded again.

## The context cap

The spec asked for 32k per model. Measured on this 24 GB M4 Pro (Metal working set 18.2 GB),
with `n_gpu_layers=-1`:

| Config                        | Fast (E4B) | Quality (12B) | Total     | Result             |
| ----------------------------- | ---------- | ------------- | --------- | ------------------ |
| 32k, f16 KV, no flash attn    | 7.9 GB     | 19.5 GB       | 27.4 GB   | out of memory      |
| 32k, q8_0 KV, flash attn      | 5.5 GB     | 13.7 GB       | 19.2 GB   | out of memory      |
| 16k, q8_0 KV, flash attn      | 5.8 GB     | 10.2 GB       | 16.0 GB   | both resident, ok  |

So the cap is 16384 (`FINQUERY_LOCAL_N_CTX`), with flash attention and a q8_0 KV cache. Flash
attention is what makes it comfortable: it takes the 12B's compute buffer from 1216 MiB to
527 MiB, and the q8_0 KV cache halves 5.4 GB of KV down to 2.7 GB. Ticket 12 compresses at 60
percent of the slot's context, so a conversation still runs long before it needs to.

## Consequences

- Switching provider stays a config change. `FINQUERY_PROVIDER=local` and nothing else moves.
- Tickets 05 and 06 get their schema-constrained calls by handing a sub-agent a single output
  tool, and their adapters by setting `finquery_adapter`. Neither needs to know about llama.cpp.
- The wire format is ours to maintain: a future llama.cpp that parses Gemma tool calls itself
  would let `finquery.local.gemma` shrink, but until then the splitter is the piece to check
  first when a local answer looks wrong.
