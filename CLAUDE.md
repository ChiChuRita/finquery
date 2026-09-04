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
