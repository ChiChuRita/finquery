# Presentation notes, 2026-09-07 (8 minutes talk, 2 minutes questions)

The deck is built in Claude Design from `BRIEF.md` (one section per slide, with the diagrams
described). These notes are the timing and the sentences to say; `how-it-works/` explains each
part.

## Timing

| slide | minute | what to say in one line |
| --- | --- | --- |
| 1 Title | 0:00 | What FinQuery is, who did what. |
| 2 The one rule | 0:30 | Numbers come from executed SQL, never from the model; the guard, the check pass, charts as checked code. |
| 3 Architecture | 1:45 | Left to right: what the user touches, what the model does, what the machine guarantees. |
| 4 Context management | 2:45 | Isolation is the profile, selection is per-turn assembly, compression is the rolling summary at 60 percent with an editable divider. |
| 5 Sub-agents | 3:45 | Six sub-agents as forced tool calls with reasoning first; check-and-retry; one model setting per role. Say the extra credit is not claimed. |
| 6 Multimodal | 4:45 | A vision model that is never trusted with a number it cannot point at in the source. |
| 7 Web search | 5:45 | It finds a page, reads it and quotes it; only a scrubbed token leaves; the log proves it. |
| 8 Models and training | 6:45 | The benchmark table, the decision rule, the adapter loop as it stands on Monday morning. |
| 9 Ownership | 7:40 | Three reversals with the evidence that forced them. Stop. |

## The line to update on Monday morning (slide 8)

Replace the training status with what is true at that hour. Candidates:

- "Four adapters trained overnight; the official before-and-after runs are finishing; first
  numbers: ..." (fill in from `bench/results/<date>-adapters-compare.md`).
- "Training data is done (N query and M chart samples, judged); the four trainings are running
  on the cluster; numbers by the hand-in."

Never state an adapter number that is not in `bench/results/`.

## Numbers you may be asked for, with their source

| number | value | source |
| --- | --- | --- |
| SQL benchmark, three local models | E4B 66, Qwen 70, Gemma 12B 87 percent figure match | `bench/results/20260906-cluster-compare.md` |
| Chart benchmark | E4B 45, Qwen 42, Gemma 12B 81 percent | same |
| End-to-end subset (30 cases through the chat agent) | 53, 73, 77 percent | same |
| Check pass effect | 69 to 79 percent on Qwen3.5 9B cloud | `bench/results/20260905T182106Z-*-nocheck-sql.md`, `20260906T115540Z-*-sql.md` |
| Tokens per second on the laptop | E4B 47, Qwen 30, Gemma 12B 22 generation | `bench/results/20260906-local-tokens-per-second.md` |
| Receipts | 19 of 19 totals right | `.scratch/finquery/reviews/receipts-web-2026-09-05.md` |
| Web lookup reruns | lookups without a search 9 to 0, pages read 0 to 12 | ticket 53 Comments |
| Test suite | 460 passed on main, 2026-09-06 evening | `uv run pytest` |
| Memory of the pair | E4B plus Gemma 4 12B about 12.9 GB | `bench/results/20260906-cluster-compare.md` |

## Likely questions

- Why not let the model compute? Because a wrong number in finance is worse than no number; the
  guard and the check pass make the number auditable, and the transcript shows the SQL.
- Why Gemma 4 12B and not Qwen? Benchmark on the cluster with the product's own runtime, 87
  against 70 on SQL and 81 against 42 on charts; Qwen was chosen on memory in week one.
- What do the fine-tuned models do? Query adapter: natural language to guarded SQL with a
  reasoning line. Chart adapter: plan plus checked chart code. Trained on E4B and on the 12B,
  scored on a frozen held-out set from a household never seen in training.
- Where does data leave the machine? Only with web lookup on, only a scrubbed merchant token,
  journaled before sending. Nothing else, ever. The dev server used OpenRouter; the demo does not.
- What about the sub-agent extra credit? Not claimed. The turn survives a closed tab, the chat
  agent still waits for its tool.
- Why JavaScript charts and not Python? The chart runs in the browser sandbox where a picture is
  needed; Python execution would have needed a second sandbox and was dropped on 2026-09-01.

Everything else: `docs/explainers/README.md` and one chapter per topic.
