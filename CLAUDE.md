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

Hosted development runs on OpenRouter with `qwen/qwen3.5-9b` on both slots (set in `.env`),
because Qwen3.5 9B is the model class the local provider ships. Do not switch a verification
run to a stronger hosted model: what works on Gemini and fails on Qwen is a bug we want to see.
The Monday demo runs on `FINQUERY_PROVIDER=local`.
