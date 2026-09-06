# Architecture: one chat agent, six sub-agents as tools, a guard, a sandbox

**Claim.** One local process serves a React app, runs two Gemma 4 models through llama.cpp,
and keeps everything in one SQLite file. The model never touches the database or the screen
directly.

## The pieces

- **Chat agent.** Pydantic AI agent on the conversation's catalog entry (default Gemma 4 12B),
  thinking on and shown in a Reasoning panel. Its context is assembled per turn: the profile's
  memory block, the rolling summary, the recent turns, and only the tools that apply.
- **Tools.** `query`, `chart`, `review_batch`, `review_duplicates`, `lookup_merchant`,
  `extract_transaction`, the dashboard tools, `remember`. Most call a sub-agent; the rest are
  plain code.
- **Sub-agents.** Query, chart, categorizer, extraction, memory, web lookup. Each gets one
  prompt built by code, answers through a forced tool schema with a reasoning field first, gets
  one retry with the finding, and streams its steps into the transcript as a chain of thought.
- **Question cards.** `ask_user` is a deferred tool: the run ends with the call open, the card
  renders, and the answer resumes the same turn. Since ticket 60 the user can type the answer
  into the composer; the model maps it to the rows.
- **Guards.** The SQL guard is the only door to the data. The chart self-check is the only door
  to the screen. Extraction has two guards of its own (verbatim, reconciliation).
- **Storage.** SQLite through SQLAlchemy 2, additive migrations, one file per install.
  Profiles isolate everything.
- **Runtime.** llama-cpp-python in process, two seats: the chat seat (Gemma 4 12B, or Qwen3.5 9B
  if picked, swapped on demand) and the fast seat (Gemma 4 E4B, always resident, where adapters
  attach). 32k context each, 12.9 GB for the pair.
- **Background turns.** A turn is a server-owned task with a replay buffer; closing the tab does
  not stop it, and progress is persisted at every tool boundary.

## The model catalog

Four entries: Gemma 4 12B (local), Gemma 4 26B (cloud), Qwen3.5 9B (local), Qwen3.5 9B
(cloud). The chat runs on the conversation's entry; every sub-agent role has its own setting:
`chat` (the same entry, the default), `fast` (the provider's fast seat), or a pinned entry. The
cloud entries exist for development; the demo runs local.

## Decisions

- Everything happens in the chat, including imports and their decisions; the Import page and
  the Dashboard are overviews.
- Two resident models rather than one: sub-agents on a small fast model were the original
  design; the benchmark moved them to the 12B for the demo, and the setting keeps both options.
- Pydantic AI supplies the model abstraction and the stream; the sub-agents, the guards, the
  compression, the memory and the web loop are our code, as the course rule requires.

## Say

"Three columns: what the user touches, what the models do, what the machine guarantees. The
model is never on the right."
