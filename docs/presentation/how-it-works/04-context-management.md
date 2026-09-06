# Elective: intelligent context management

**Claim.** We implement the three things the sheet names: isolation, selection and compression,
plus a memory the user can see and edit.

## Isolation

A profile is a workspace. It owns transactions, accounts, categories and rules, conversations,
the distilled memory, the web lookup cache and journal, the dashboard cards. Every SQL query
runs through a temporary view created for that request with the profile id inlined, so a
statement cannot reach another profile even if it tried. Switching profiles switches all of it.

## Selection

Each turn assembles exactly what it needs, in this order and within one token budget:

1. the memory block: durable facts the profile has learned, selected for this turn;
2. the rolling summary of older turns, if one exists;
3. the recent turns since the summary, with their tool results;
4. the tools that apply: web lookup is not even declared to the model when the profile has it
   off, so the model cannot call what the user did not allow.

The header badge shows the tokens used against the 32k budget.

## Compression

When a turn would cross 60 percent of the budget, the older turns are folded into a summary by
the fast model before the answer runs, so the turn that crosses the threshold already runs
small. The divider in the transcript marks where the summary starts; the user can edit it, so
what was kept is under their control, and the pending Question card is never summarized away
(the run could not resume from it).

## Memory

After every turn a memory sub-agent distills at most two durable facts ("my flatmate is Max
Schulz"), never figures or dates unless the user states a rule. The Memory page lists and
edits them. A new chat in the same profile recalls them, which is the sheet's "project folder"
memory across a group of chats.

## Decisions

- Summary at 60 percent, not at the limit: the model that summarizes needs room too.
- Facts, not transcripts, in memory: a small model poisons itself with figures it half
  remembers (ticket 37 measured it), so figures are forbidden.
- Editable divider: compression is visible and reversible; the user owns the context.

## Numbers

Context budget 32k on both local models; the compression threshold and the memory limits are
in `src/finquery/context.py` and `memory.py`; tests in `tests/test_context.py` re-measure the
budget (5,700 tokens of fixed prompt).

## Say

"Isolation is the profile, selection is the per-turn assembly, compression is a rolling summary
at 60 percent with a divider you can edit. Memory is two facts per turn, never a number."
