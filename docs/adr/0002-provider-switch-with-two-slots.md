# ADR 0002: Provider switch with two logical model slots

Date: 2026-09-04
Status: accepted

## Context

Development runs on OpenRouter so the laptop stays usable. The demo and the hand-in run local
Gemma 4 models through llama-cpp-python. The rest of the app must not care which one is active,
and two fine-tuned adapters will later slot into the same base weights.

## Decision

- Two logical slots, `fast` and `quality` (`finquery.providers.ModelSlot`). Conversations store
  a slot, never a model name. Sub-agents are pinned to `fast`.
- One environment variable, `FINQUERY_PROVIDER` (`openrouter` or `local`), resolved in one module
  (`finquery.providers.build_resolver`) into a callable `slot -> pydantic_ai Model`. Nothing else
  imports provider SDKs.
- OpenRouter maps fast to `google/gemma-4-26b-a4b-it` and quality to `google/gemma-4-31b-it` with
  reasoning enabled through `OpenRouterModelSettings(openrouter_reasoning={"enabled": True})`.
  The key comes from `OPENROUTER_API_KEY` in the gitignored `.env`.
- `local` is a stub until ticket 16: the app starts, and a chat attempt fails with a 503 naming
  the ticket. Resolution never touches the network, so startup is safe with either value.
- The app factory accepts a `resolve_model` override. Tests pass scripted `FunctionModel`s for
  both slots (see ADR 0003).

## Consequences

- Switching provider is a config change, not a code change.
- Ticket 16 implements a `Model` subclass and a resolver branch; the API and UI stay untouched.
