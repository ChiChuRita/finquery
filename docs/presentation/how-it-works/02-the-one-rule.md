# The one rule: numbers come from executed queries, never from the model

**Claim.** Every figure in an answer is the result of a SQL statement the assistant really ran
against the user's own transactions. The model writes the question and the words; the database
writes the numbers. The same rule covers charts.

## How a question becomes a number

1. The chat agent (Gemma 4 12B) reads the user's message and decides it needs data. It calls
   the `query` tool with a request written in plain words, for example "total spending on
   groceries in May 2025".
2. Code builds the query sub-agent's prompt: the schema of one view (`transaction_view`, euro
   amounts, no cents), the household's facts (newest booking, categories, accounts), the rules,
   and nine worked examples. The sub-agent must answer through a forced tool call with two
   fields: `reasoning` (period, filters, sign, grouping, one short line each) and `sql`.
3. The SQL guard checks the statement before anything runs: parsed with sqlglot, exactly one
   SELECT, only the profile-scoped view, read-only (`PRAGMA query_only`), a LIMIT, no invented
   categories inside a CASE, no cents in the projection, no subcategory used as a category, at
   most eight LIKE terms. A refusal is a sentence the sub-agent gets back once.
4. SQLite runs it against a temporary view that only holds this profile's rows. Rows come back.
5. The check pass looks at the rows: empty, all NULL, a single zero on something the household
   has, or a shape that does not answer the question. One `revise` with the finding, then the
   sub-agent rewrites once. That pass alone lifted figure match from 69 to 79 percent on the
   same model (Qwen3.5 9B, `bench/results/20260905T182106Z-*-nocheck-sql.md` against
   `20260906T115540Z-*-sql.md`).
6. The answer shows the SQL and the rows in a card next to the words. A figure typed into the
   prose that no query produced is flagged by a prose verifier.

## Where the model is, and is not

The model is in steps 1, 2 and the rewrite of step 5. It is never in steps 3, 4 or 6: it does
not touch the database, does not compute, and cannot put a number on the screen that a query
did not return.

## Charts follow the same path

The chart sub-agent plans (shape, columns, title), gets its rows through the same query path,
writes JavaScript for TanStack Charts against an allowlist of globals, and a self-check runs
that code on the real rows before a sandboxed iframe draws it. Failures become repair rounds
the user can see. The house rules (palette, axes, corners, legend) live in the frame, so a
stored dashboard card takes a new look without being regenerated.

## Decisions

- SQL over a view rather than tool functions per question: one guard covers every question.
- Cents hidden from the model: a small model turned cents into euros once; now it cannot.
- Check pass as a second model call rather than more rules: rules cannot read intent.

## Say

"The model writes the question, the database writes the numbers. Every number you see has its
SQL next to it. The check pass alone was worth ten points on the same model."
