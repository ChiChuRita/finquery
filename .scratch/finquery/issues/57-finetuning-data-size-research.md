# 57: Research: how much data the two adapters need

**What to build:** A research note with sources that answers: how many training samples, of what mix, QLoRA adapters for the query task (natural language to guarded SQL with a reasoning field) and the chart task (plan, then checked JavaScript) need on 4B to 12B instruction models (Gemma 4 E4B, Qwen3.5 9B, Gemma 4 12B), what quality of gold matters more than quantity, how to split train and validation, which hyperparameters the literature and practitioners use for this size, and how the generated data can also grow the benchmark's validation set under the split rule. Decided with the user on 2026-09-06 to run now, in parallel with ticket 56.

**Blocked by:** none (reading only)

**Status:** ready-for-agent

Scope:
- Primary sources first: the LoRA and QLoRA papers, LIMA and "less is more" style results, text-to-SQL fine-tuning reports on small models (Spider, BIRD, and small-model SQL fine-tunes), structured or tool-call fine-tuning reports (function calling on 4B to 9B models), Unsloth and Hugging Face PEFT documentation on data sizes and hyperparameters, Gemma 4 and Qwen3.5 fine-tuning guides. Cite URLs.
- Ground it in this repo: read `.scratch/finquery/issues/43-training-data-by-subagents.md` (600 query and 300 chart samples were the working sizes), `bench/README.md`, `src/finquery/query/subagent.py` and `src/finquery/chart/subagent.py` (what a sample looks like: the exact prompt and the forced tool call with reasoning), `training/preference/` (the DPO scripts, which set the training stack), and the tokens-per-second note.
- Answer with numbers: a recommended size per adapter with a range, the mix (languages, kinds, difficulties, follow-ups, repairs after a failed check), how much of it should be "hard" cases, the validation size that makes a two-point difference detectable, the epochs, rank, alpha, learning rate and sequence length to start from, the expected training time on one A100 or H100, and what to measure to know whether more data would help (a learning curve on subsets).
- Write `docs/research/finetuning-data-2026-09-06.md`, under 2,000 words plus tables, plain English, no em dashes, every number with its source, and a one-paragraph recommendation the user can act on.

- [ ] Research note written with sources and the recommendation
- [ ] Ticket 43's sizes confirmed or revised in a line under its Comments (a note only; 43 stays not started until the user says so)
