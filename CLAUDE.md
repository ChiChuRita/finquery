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

The shipped local pair is Gemma 4 12B (chat and, for the demo, every sub-agent) with Gemma 4 E4B
resident as the fast slot and the adapter target, decided on the cluster benchmark of 2026-09-06.
Hosted development runs on OpenRouter with `google/gemma-4-26b-a4b-it` on both slots (set in
`.env`): OpenRouter has no Gemma 4 12B, and the 26B shares the family and the tool-call wire
format. Do not switch a verification run to a stronger hosted model: what works on Gemini and
fails on Gemma is a bug we want to see. The Monday demo runs on `FINQUERY_PROVIDER=local`.

## Benchmarks and fine-tuning

Benchmarks and fine-tuning run on the HPI scientific computing cluster (reached through the
user's Tunnelblick VPN), never on the laptop and never against the OpenRouter key. The key is
for the dev server and short browser verifications only. Gemini and other stronger hosted
models are not benchmarked: the candidates are the local models the product can ship.
