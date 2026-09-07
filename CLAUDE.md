# FinQuery

Local-first conversational personal-finance analyst. Import bank statements,
ask questions in natural language, get deterministic, auditable answers.

**The invariant: numbers always come from executed queries, never from the model.**

Domain vocabulary lives in `CONTEXT.md`, architecture decisions in `docs/adr/`.
Read both before any architecture-adjacent work.

## Agent skills

### Issue tracker

Local markdown: specs and tickets live under `.scratch/<feature-slug>/`, one file
per ticket in `issues/`. There is no git remote and no external tracker.
See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name.
See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root.
See `docs/agents/domain.md`.

## Models for development and verification

The catalog has two local entries: Gemma 4 E4B, the fast slot a sub-agent role set to `fast`
runs on and the base the LoRA adapters attach to, and Gemma 4 26B A4B, the local default a new
conversation starts on (chat and, for the demo, every sub-agent). The 26B replaced Gemma 4 12B
on 2026-09-07 (ticket 75): the same accuracy on the SQL set, 79 against 78 percent of 459
questions, and much more speed on the laptop, 38.1 tok/s generation against 22.3. Hosted
development runs on OpenRouter with `google/gemma-4-26b-a4b-it` on both slots (set in `.env`),
which is the same model as the local default. Do not switch a verification run to a stronger
hosted model: what works on Gemini and fails on Gemma is a bug we want to see. The Monday demo
runs on `FINQUERY_PROVIDER=local`.

## Benchmarks and fine-tuning

Benchmarks and fine-tuning run on the HPI scientific computing cluster (reached through the
user's Tunnelblick VPN), never on the laptop and never against the OpenRouter key. The key is
for the dev server and short browser verifications only. Gemini and other stronger hosted
models are not benchmarked: the candidates are the local models the product can ship.
