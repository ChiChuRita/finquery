# Elective: sub-agent deployment

**Claim.** A sub-agent fulfils one LLM-defined task as a tool call: the chat agent calls a tool,
the tool runs a second model with its own prompt and schema, and the result comes back as
data. Six of them ship.

## The loop, the same for all six

1. The chat agent decides a tool is needed and writes the request in words.
2. Code builds the sub-agent's prompt: rules, worked examples in the ticket 42 style (reasoning
   before the answer), the household's facts. The chat agent never writes this prompt.
3. The sub-agent answers through a forced tool schema. The first field is always `reasoning`,
   so the model commits to its plan before the answer.
4. A check that is not a model: the guard and execution for SQL, the self-check on real rows for
   charts, the two extraction guards, the no-figures rule for memory, the floors and the verbatim
   quote for web lookup. A finding goes back once with the exact sentence.
5. The result returns as structured data. Every step streams into the transcript.

## The six

| sub-agent | one task | its check |
| --- | --- | --- |
| query | natural language to one guarded SELECT with a reasoning line | guard, execution, check pass with one revise |
| chart | plan (shape, columns, title), then chart code over the allowlisted globals | self-check on the real rows, repair rounds, the frame |
| categorizer | a batch of unknown bookings to categories with confidence | threshold 0.75, Question cards for the rest, answers become rules |
| extraction | one page (text or image) to bookings | verbatim guard, reconciliation, review card |
| memory | the finished turn to at most two facts | no figures, no dates unless a rule |
| web lookup | a scrubbed token to search, fetch or finish decisions | one-search floor, own-site fetch, verbatim quote, confidence cap |

## Which model runs them

One setting per role. Default `chat`: the conversation's own entry, Gemma 4 12B in the demo.
`fast`: the provider's fast seat, Gemma 4 E4B, where the adapters attach. A pinned entry is the
third option. Sub-agents always run with reasoning off and a 3,072 token ceiling, whatever the
model.

## What we do not claim

The extra credit for a controlling LLM that continues without waiting. Our turn is a
server-owned task that survives a closed tab, but the chat agent waits for its tool result.
Saying this before being asked is part of the ownership story.

## Numbers

Cluster benchmark of the sub-agent paths (`bench/results/20260906-cluster-compare.md`): Gemma 4
12B 87 percent SQL, 81 percent charts; E4B 66 and 45; Qwen3.5 9B 70 and 42. The check pass
alone: 69 to 79 percent on Qwen (the two SQL result files of 2026-09-05 and 2026-09-06).

## Say

"Six sub-agents, one loop: a forced schema with reasoning first, a check that is code, one retry
with the finding. The check pass was worth ten points without training anything."
