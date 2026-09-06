# How FinQuery works, one note per slide

These are the presenter's notes on the system itself, written so that either of us can explain
every part without the code open. One file per slide of the deck built in Claude Design from `../BRIEF.md`. Each file has the
same shape: the claim in one line, how it works as a numbered flow, where the model is and is
not in the loop, the decisions we made and why, the numbers with their source, and the three
sentences to say. The long versions with file and function references are `docs/explainers/`.

| slide | note | deeper chapter |
| --- | --- | --- |
| 2 | [02-the-one-rule.md](02-the-one-rule.md) | explainers 06, 07 |
| 3 | [03-architecture.md](03-architecture.md) | explainers 01, 02, 13 |
| 4 | [04-context-management.md](04-context-management.md) | explainer 12 |
| 5 | [05-sub-agents.md](05-sub-agents.md) | explainer 13 |
| 6 | [06-multimodal-ingestion.md](06-multimodal-ingestion.md) | explainers 08, 16 |
| 7 | [07-web-search.md](07-web-search.md) | explainer 15 |
| 8 | [08-models-and-training.md](08-models-and-training.md) | explainer 04, bench/results, training/ |
| 9 | [09-ownership.md](09-ownership.md) | docs/adr, the spec amendments |

Rule for all of them: a number without a source file next to it does not go on a slide.
