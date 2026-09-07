# ADR 0006: The local provider is a custom Pydantic AI model over llama-cpp-python

Date: 2026-09-04
Amended: 2026-09-05 (ticket 23, the quality slot became Qwen3.5 9B; ticket 17, the sub-agent
output ceiling); 2026-09-06 (ticket 61, the shipped pair is Gemma 4 12B with E4B, and every
sub-agent role has a model setting)
Status: accepted

The file keeps its ticket-16 name so the links to it still work; the decision was never about
Gemma alone, and the pair it ships is a Gemma pair again since the 2026-09-06 amendment below.

## Context

The demo and the hand-in run on the machine, not on OpenRouter (ADR 0002). llama-cpp-python
has no Pydantic AI adapter, and neither model's chat format is one of the shapes it normalizes
for us: thinking, tool calls and the argument encoding all travel inside a single text stream
that only that model's own chat template understands, and the two models do not agree on any
of it. Two 4-bit models and their multimodal projectors also have to share one 24 GB Mac.

## Decision

- `finquery.local.model.LlamaCppModel` is a `pydantic_ai.models.Model`. `finquery.local` is the
  only package that imports `llama_cpp`; the API, the agent and the UI are unchanged.
- The prompt is built by the chat template inside the GGUF, reached through
  `llama_cpp.llama_chat_format.MTMDChatHandler` (`Gemma4ChatHandler` is an empty subclass of
  it, so one handler serves both models). Pydantic AI messages are rendered to the
  OpenAI-shaped dicts that template expects: instructions and system prompts fold into one
  leading system message, thinking travels as `reasoning` on assistant messages, tool calls as
  `tool_calls` with mapping arguments, tool results as `role: tool` messages. The one name
  that differs is the key past thinking travels under: `reasoning` for Gemma 4,
  `reasoning_content` for Qwen3.5.
- The handler is called directly rather than through `Llama.create_chat_completion`, which has
  no `**kwargs` and so cannot pass `enable_thinking` to the template. Thinking is therefore a
  template argument, not a request flag. Keeping the reasoning that led to a tool call and
  dropping the rest of the history's is `preserve_thinking` for Gemma 4 and nothing at all for
  Qwen3.5, whose template decides it by message index.
- A wire format is a module that turns the raw token stream into thinking parts, text parts and
  tool calls, holding back any delta that could still be the start of a marker. There is one
  per model, because Gemma 4 and Qwen3.5 agree on nothing about how a turn looks:
  `finquery.local.gemma` and `finquery.local.qwen`. `finquery.local.wire` is the shape they
  fill in, and `LlamaCppModel` picks one from the catalog entry, so the model is what decides,
  not the slot. Neither imports llama.cpp, so both are testable without a model.
- Schema-constrained output and free tool calling are never combined. A request with exactly one
  tool and no text output (the sub-agent shape) forces that tool, which makes llama.cpp build a
  GBNF grammar from its parameters, and turns thinking off because a grammar leaves no room for
  it. Every other request declares its tools with `tool_choice: auto`. `response_format` is
  never sent.
- A forced tool call is a grammar, and a grammar over a list has no end of its own: asked to
  read a statement page, the fast model repeated rows until the context was full (ticket 11,
  six minutes for three pages). Every sub-agent request therefore carries an output ceiling,
  `providers.SUBAGENT_MAX_TOKENS` (3072 tokens, above the largest honest answer of about 2500
  for a 30 booking page or a 25 merchant batch), on both providers. A call that hits it fails
  its validation and is retried once. The chat turn keeps the model's own default (4096).
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
with `n_gpu_layers=-1`, both models loaded in one process and each asked to read an image so
its projector is resident too:

| Config                     | Fast (E4B) | Quality        | Total   | Result            |
| -------------------------- | ---------- | -------------- | ------- | ----------------- |
| 32k, f16 KV, no flash attn | 7.9 GB     | 19.5 GB (12B)  | 27.4 GB | out of memory     |
| 32k, q8_0 KV, flash attn   | 5.5 GB     | 13.7 GB (12B)  | 19.2 GB | out of memory     |
| 16k, q8_0 KV, flash attn   | 5.8 GB     | 10.2 GB (12B)  | 16.0 GB | both resident, ok |
| 16k, q8_0 KV, flash attn   | 6.8 GB     | 6.1 GB (Qwen)  | 12.9 GB | both resident, ok |
| 32k, q8_0 KV, flash attn   | 7.1 GB     | 6.4 GB (Qwen)  | 13.5 GB | both resident, ok |

The three 12B rows are ticket 16's measurement, which counted the model, KV and compute
buffers; the two Qwen rows also have each projector resident, which is most of the extra
gigabyte on the fast slot.

The last row is the one in force: the cap is 32768 (`FINQUERY_LOCAL_N_CTX`), the number the
spec asked for, with flash attention and a q8_0 KV cache. Qwen3.5 9B is what makes it fit.
Doubling its context costs 0.27 GB, against 3.5 GB for the 12B, because only every fourth
layer is full attention (`qwen35.full_attention_interval = 4`, 8 of 32 layers, 4 KV heads of
256) and the other twenty-four hold a fixed-size recurrent state instead: 544 MiB of KV plus
50 MiB of recurrent state at 32k. Flash attention and the q8_0 KV cache still earn their keep
on the fast slot, whose sliding-window and full-attention caches are 952 MiB at 32k.

Ticket 12 compresses at 60 percent of the slot's context (`FINQUERY_CONTEXT_BUDGET` caps that
further), so a conversation now runs to roughly 20k tokens before it needs to.

## The models per slot

*Superseded in part by the 2026-09-06 amendment at the end of this file: the chat seat ships
Gemma 4 12B, and Qwen3.5 9B is one of the two local entries a user can pick.*

Fast is `gemma-4-E4B-it` (Q4_K_M plus its F16 projector, 6.0 GB) and quality is `Qwen3.5-9B`
(Q4_K_M plus its F16 projector, 6.6 GB), both from `unsloth` on Hugging Face. On OpenRouter the
same two are `google/gemma-4-26b-a4b-it` and `qwen/qwen3.5-9b`, so a turn does not change
character with the provider.

Quality was Gemma 4 12B until ticket 23. Qwen3.5 9B replaces it because it is better at the
work this app asks of the quality slot (tool calling and multi-step reasoning over numbers),
it is smaller, and its hybrid attention is what buys the 32k the spec asked for. Vision comes
along: its projector is a `qwen3vl_merger`, which the vendored llama.cpp (b10454 in
llama-cpp-python 0.3.35) supports through libmtmd, and the sanity check reads a red square on
both slots.

The two wire formats differ in every detail:

|                            | Gemma 4 (fast) | Qwen3.5 (quality) |
| -------------------------- | -------------- | ----------------- |
| Thinking | `<\|channel>thought ... <channel\|>`, opened by the model | `<think> ... </think>`, opened by the prompt |
| Thought open at generation | only after a tool response | on every turn with thinking on |
| Tool call | `<\|tool_call>call:name{key:<\|"\|>value<\|"\|>}<tool_call\|>` | `<tool_call><function=name><parameter=key>value</parameter></function></tool_call>` |
| Argument types | its own DSL, typed | text per parameter, JSON only for objects and arrays |
| Past thinking | `reasoning`, gated by `preserve_thinking` | `reasoning_content`, gated by message index |
| End of turn | `<turn\|>` | `<\|im_end\|>` |
| Sampling | 1.0 / 0.95 / top_k 64 | 1.0 / 0.95 / top_k 20, min_p 0, presence 1.5 |

Parsing either is ours to maintain. llama.cpp knows both formats in its own server (Qwen's is
what vLLM calls `qwen3_coder`), but none of that is reachable from llama-cpp-python's chat
handler, which hands back the raw stream. A Qwen `<parameter>` body arrives as text and stays
text unless it starts a JSON object or array: Pydantic reads "20" as 20 for an int field,
while an int handed to a string field is a validation error, so guessing would cost more than
it buys.

## Consequences

- Switching provider stays a config change. `FINQUERY_PROVIDER=local` and nothing else moves.
- Tickets 05 and 06 get their schema-constrained calls by handing a sub-agent a single output
  tool, and their adapters by setting `finquery_adapter`. Neither needs to know about llama.cpp.
- The wire format is ours to maintain: a future llama-cpp-python that exposed llama.cpp's own
  tool-call parsers would let both modules shrink, but until then the splitter for the slot in
  question is the piece to check first when a local answer looks wrong.
- A third model means a third wire module and one more entry in `WIRE_FORMATS`, not a change
  to `LlamaCppModel`.

## Amendment, 2026-09-06 (ticket 61): the shipped pair, and a model per sub-agent role

The quality slot part of the 2026-09-05 amendment is superseded. Qwen3.5 9B stays a catalog
entry; it is no longer what the app ships on.

### What the benchmark said

Three candidates, Q4_K_M through llama-cpp with CUDA on one RTX PRO 6000 of the HPI cluster,
32k context, the same wire formats and the same sub-agent paths the laptop runs
(`bench/results/20260906-cluster-compare.md`, ticket 56):

| model | SQL figure match | SQL first attempt | chart figure match | chart shape match | end to end |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gemma 4 E4B | 66 % | 75 % | 45 % | 85 % | 53 % |
| Qwen3.5 9B | 70 % | 30 % | 42 % | 89 % | 73 % |
| Gemma 4 12B | **87 %** | **82 %** | **81 %** | **96 %** | **77 %** |

152 SQL datapoints, 73 chart, 30 end to end. On the SQL set the 12B is right on 35 that E4B
misses and wrong on 4 that E4B gets; against Qwen3.5 9B the gap is the same size and in the
same direction. The decision rule was accuracy first, speed as a tie-breaker within about five
points, and the pair has to fit in memory: nothing was within five points of the 12B, so speed
never decided anything.

### The decision

- **The pair is Gemma 4 12B and Gemma 4 E4B.** `local:gemma-4-12b` is the entry a new
  conversation starts on when `FINQUERY_PROVIDER=local`, and E4B keeps the fast seat: resident,
  the adapter target, and what a role set to `fast` runs on. The pair is about 12.9 GB at 32k
  against Qwen's 13.5 GB, so it costs no memory to switch to it
  (`bench/results/20260906-local-tokens-per-second.md`). It costs speed: 22.4 tok/s generation
  and 205 tok/s prompt processing against 29.5 and 329 for the Qwen pair, which the demo script
  budgets for.
- **Which model a sub-agent runs on is a setting per role**, `FINQUERY_SUBAGENT_MODEL_<ROLE>`
  over the seven roles of `finquery.providers.SUBAGENT_ROLES` (query, chart, categorizer,
  extraction, memory, summary, weblookup). Each takes `chat` (the conversation's own entry),
  `fast` (the fast slot of that entry's provider) or a catalog key. The default is `chat`,
  which is what the numbers above buy: the sub-agent path is where the benchmark scores, so the
  demo runs it on the 12B. `fast` is what every role meant before, and a role that is switched
  back to it costs nothing but its own quality.
- **Adapters still attach only on the fast seat.** A LoRA trained on E4B's base weights is not
  a LoRA for a 12B. A role on `fast` with an adapter registered gets it; a role on `chat` asks
  and does not get it, and the run carries an audit note saying so.
- **Sub-agent settings do not depend on the provider any more.** Reasoning is off and
  `SUBAGENT_MAX_TOKENS` is 3072 for a sub-agent call whatever model answers it: a bigger model
  is not a reason for a sub-agent to think or to write more.
- **Hosted development is Gemma 4 26B A4B on both slots.** OpenRouter serves no Gemma 4 12B, so
  the 26B A4B is the nearest thing in the family and in the tool-call wire format. The two
  hosted chat entries are constants of the catalog rather than settings, so pointing the fast
  slot at one of them does not take the other out of the picker.

### Memory, and what gives way if it does not fit

*Superseded by the ticket 68 amendment of ADR 0013: one local model is resident at a time, so
nothing here has to fit beside anything else and `finquery-check` no longer measures a pair.*

The 32k cap of the table above was measured with Qwen in the chat seat. The three 12B rows in
that table are ticket 16's, from before the seat existed, and they had E4B and the 12B loaded
by one process at 32k without flash attention or a q8_0 KV cache. The pair figures are why the
seats existed; the 26B A4B of ticket 67 is what ended them, because 12.9 GB of weights could
not decode beside a resident E4B on this machine
(`bench/results/20260907-local-tokens-per-second.md`).

`FINQUERY_LOCAL_N_CTX` is still the one context cap, and every catalog model fits on its own at
32k. Lowering it makes compression start sooner (ADR 0007).
