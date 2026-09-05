# 37: Robustness against a small model

**What to build:** The Qwen3.5 9B capability review (../qwen-capability-2026-09-05.md, 30 exact of 46) found failure patterns that are not Qwen's alone: they are places where a small model can do damage or state a wrong figure and the code lets it. Close each at the code level with a test, so E4B and Qwen both become safe, then re-measure.

**Blocked by:** 30, 32 (merged)

**Status:** done

- [x] Cents never reach prose as euros: the query guard refuses a statement whose selected expression aggregates amount_cents without dividing by 100.0 (or the view exposes only euro amounts to the sub-agent and amount_cents is removed from the prompt schema); integer division is impossible (100 becomes 100.0 in the prompt examples and a guard rewrites `/ 100` to `/ 100.0`); a test per rule
- [x] Figures the prose states must come from a query: the answer text is checked against the figures of the turn's tool results (every EUR amount in the prose must appear in a tool result, tolerance one cent), and a mismatch is rewritten server-side into a sentence that quotes the tool figures, with a log line; the chat prompt says the model never adds, subtracts or nets numbers itself and asks the query tool for totals
- [x] `propose_changeset` accepts what a small model sends: nested optional fields may be null or missing (legs: null, where: null), and the tool schema is flattened where nesting is not needed; a scripted test with the exact failing arguments from the review passes
- [x] `apply_simple_edit` never changes a field the user did not name: unset fields are unset, `amount_cents: 0` or an empty description is refused with a sentence unless the user's message named the amount (the tool gets the user's request text or the model must pass `fields_changed` explicitly), and the answer sentence names every field that changed
- [x] Memory distillation refuses one-off figures and dates (a fact containing an amount or a date is not durable unless kind is rule), refuses facts about entities the turn proved absent, and caps distilled facts per turn at two; the review's 27 memories in one afternoon become a handful
- [x] The taxonomy line in the sub-agent prompt cannot be read as categories: subcategories are listed under their category with a clear marker, the guard refuses a `category IN (...)` or `category =` whose literal is a subcategory name (it knows the taxonomy) and answers with the parent, with a test
- [x] The query sub-agent never narrows the period silently and reads "last quarter" and "last month" relative to the latest booking month with a rule in the prompt; a query call budget of five per turn stops runaway loops, and a statement longer than 1500 characters or with a CROSS JOIN is refused
- [x] Text degradation: template and foreign-script token leaks in a German or English answer are stripped by the existing filter where they are single stray tokens; the chart repair narration never reaches prose (it is reasoning)
- [x] Re-measure: rerun the review's 46 questions against the scripted-slot tests where possible and, in the browser on OpenRouter with qwen/qwen3.5-9b on both slots, the ten that failed on SQL; report before and after
- [x] Suite green, build clean

## Comments

Done 2026-09-05. `uv run pytest` is 305 passed, 4 skipped (the four are environmental: the two
private Trade Republic fixtures, the private statement PDF and the opt-in local smoke suite).
`npx tsc --noEmit` and `npm run build` are clean, `oxlint` is the pre-existing 40 warnings with
nothing in a touched file (no frontend file is touched). Screenshots: `/tmp/finquery-37/`.

### What changed, per failure pattern

**1 and 2, cents printed as euros and integer division** (`query/guard.py`). A selected
expression that returns `amount_cents` bare, sums it or divides it is refused with the euro
column named. A comparison is untouched, so the sign test and a `CASE WHEN amount_cents <
-20000` still run, which is what ticket 22's shape examples use. The sub-agent's schema no
longer has a cents column at all: `amount` is described as the only money column, and the rules
and the six worked examples filter `amount < 0`. `/ 100` is rewritten to `/ 100.0`, that one
divisor only, because a quarter is `(month - 1) / 3 + 1` and wants its integer division.

**4, subcategory names used as category values.** `profile_facts` renders one line per category
with the word subcategories in front of the names, instead of `Groceries (Supermarket, Bakery,
Drugstore)` on one line, which a 9B model reads as alternative category values. The guard knows
the taxonomy (`subcategory_parents`, passed by the runner) and refuses a `category =` or
`category IN (...)` whose literal is a subcategory, naming the category it belongs to. Refused
rather than rewritten: `category = 'Bakery'` mapped silently to Groceries would answer a
question about bakeries with the whole grocery total.

**5 and 6, runaway statements.** A join with no condition (an explicit CROSS JOIN or a comma
join) is refused, and so is a statement over 1500 characters. `query` is capped at five calls
per turn (`agent.QUERY_BUDGET`): the sixth is answered by a sentence rather than a model, which
is what A5's fifteen statements and 256 seconds needed.

**7, arithmetic in prose** (`src/finquery/prose.py`, new). Every euro amount in the answer is
compared against the figures this conversation's tools returned and the amounts the user wrote,
one cent of tolerance, and a figure that is in neither has its sentence replaced by one the
server writes quoting what the query did return. It runs on the stream, so the wrong figure is
never on screen, and again on the text that is stored, so a reload does not bring it back; the
count is `figures_rewritten` on the turn metadata. Two deliberate limits: the set of allowed
figures is permissive (every number a tool result carries, and the whole conversation's, because
a follow-up quotes the turn before it), and nothing is judged until a query has produced a
figure, since a number with no query behind it may as easily be the user's own or a date.

**8, `propose_changeset` cannot be called.** The schema the model sees was already flat (pydantic
AI flattens a single model argument), so the defect was nullability: `legs: null` on a
recategorize failed validation, burned all three retries and ended the turn with no answer, no
card and nothing to act on. `nullish.empty_list_before` reads a null in a list field as the
absence it looks like. `where: {}` is the other half of the same hazard, since an empty filter
selects every booking in the profile: it is refused with the sentence that says to name the rows.

**9, `apply_simple_edit` destroyed data.** The amount now has to be in the user's own words, or
equal to what the row already holds (a model copies the row it just read into the call to look
complete, and refusing that only spends the retries). `ChatDeps.user_message` carries the turn's
message, which the endpoint already had. The result carries a `say` line counted in code, and
the preview names the fields that really moved rather than the fields the payload writes.

**10, memory distillation.** At most two facts per turn, a fact carrying an amount or a date is
refused unless its kind is `rule`, and a fact naming something this turn's query proved absent
is refused (`memory.worth_keeping`, fed by the requests whose result held no rows or nothing but
NULLs). The distillation prompt says the same in words.

**11, silent period narrowing.** The household paragraph spells out this month, last month, this
quarter and last quarter as dates counted from the newest booking, and the rules say to use them
as they stand and to cover the whole range when the question names no period. The chat prompt
says the same and asks the answer to name the period it used.

**12, text degradation.** A word carrying letters of another script is dropped where it is a
stray token (`prose.strip_foreign_tokens`), unless the text is mostly written that way. The two
blank lines every answer of the review opened with are gone, live and stored. The chart's repair
rounds stay in the thinking panel: they are already narrated there, and one prompt line says the
plan, the notes and a second attempt are never something to write about.

### The re-measure

OpenRouter, both slots `qwen/qwen3.5-9b`, port 8112, throwaway database, session `fq37`, the
same private Trade Republic export the review used (1517 rows, 1179 categorized, 338 Needs
review). Before is the review's own table.

| # | Question | Before | After |
| --- | --- | --- | --- |
| A5 | groceries per week (en) | 256 s, 15 statements, invented merchants, a 9294-char parse error, the division done in prose | 5 queries, the sixth refused by the budget, the invented weekly figure replaced by the queried ones, ~40 s (`a5.png`) |
| B1 | letztes Quartal (de) | Leisure **90.762,00 EUR** (cents aliased euros), wrong quarter | Leisure **941,94 EUR**, euros throughout; still the current quarter, but the answer names it, and one invented figure was replaced (`b1.png`) |
| B4 | Abos im Jahr (de) | 208.9 s of estimates, "ca. 1.056 EUR/Jahr", text degraded | 5 queries, then the provider refused the sixth request (110 rows in one result) and the turn is kept as interrupted with its question. No estimate reached the user (`b4.png`) |
| B5 | groesste einzelne Ausgabe (de) | **10.560,00 EUR**, 82 cents lost to integer division | **10.560,82 EUR**, exact (`b5.png`) |
| B6 | kleinste wiederkehrende Zahlung (de) | "APPLE.COM/BILL ca. 22-23 EUR", sorted the wrong way and truncated | **1,55 EUR**, the true smallest subscription payment (`b6.png`) |
| C4 | highest grocery month (en) | **Feb 2026**, silently 2026 only | **May 2025**, one statement over the whole range (`c4.png`) |
| C5 | is dining going up (en) | 2026 only, the 2025 rise never appears | the whole range 2024-06 to 2026-09 queried; one estimated figure replaced. Answered in German for an English question, which is Qwen drifting, not the period (`c5.png`) |
| F2 | doughnut by category (en) | chart failed, six categories presented as the whole picture | chart still fails the self-check (the known doughnut weakness, ticket 25/36); the six figures are quoted from the rows and nothing is invented (`f2.png`) |
| F3 | income vs spending, grouped bars (en) | chart failed, a category breakdown with no income | the chart drew; it is still a category breakdown rather than income against spending (`f3.png`) |
| I3 | transport 2025 and biggest subscription (en) | transport right, biggest subscription **wrong** (a made-up `LIKE` keyword list) | both figures queried, the second from `category = 'Subscriptions'` (`i3.png`) |
| G1 | recategorize all Netflix (en) | **two empty turns**, `legs: null`, no card | a card with 18 rows on the **first** call, arguments `legs: null, where: null, taxonomy: null` (`g1.png`, `g1-card.png`) |
| G2 | set one booking to Dining (en) | `amount_cents: 0` **zeroed a real booking**, the sentence hid it | the booking is intact at -7,90 EUR and now Dining > Restaurant; the sentence names the fields that changed. Two earlier phrasings ended in "I could not find that booking" instead of any damage (`g2.png`, `g2b.png`, `g2c.png`, `g2d.png`) |
| E1 | memory (en) | an invented memory about a person the same turn proved absent, 27 memories in an afternoon | 3 memories after 13 turns, none with a figure or a date, none about Max Schulz (`e1.png`, `memory.png`) |

The SQL benchmark of ticket 38, same 76 datapoints, same model, same seed:

| | figure match | SQL valid | first attempt | median s |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.5 9B before | 45 % | 91 % | 75 % | 2.2 |
| Qwen3.5 9B after | **58 %** | 92 % | 80 % | 1.9 |

Sixteen datapoints turn from wrong to right and six the other way. Among the gains are the three
relative-period questions ("last month", "letztes Quartal", "diesen Monat"), which is the
household paragraph spelling those dates out. `bench/results/20260905T161746Z-qwen-qwen3.5-9b-sql.md`.

### What merging ticket 38 needed

Two places where the benchmark and the new rules disagreed, both of them the benchmark's
assumptions: the smallest-recurring reference compared `MIN(amount_cents)` with
`MAX(amount_cents)` in its projection (the same test in euros returns the same row), and the
runner test's deliberately wrong statement was the review's 100x failure, which the guard now
refuses outright rather than running with wrong figures. `validate_sql` also catches
`sqlglot.errors.TokenError` now, which is what an unterminated string literal raises and what
took a turn down during the benchmark baseline.

### Numbers and requests

- Requests per turn are unchanged. The query budget can only lower them.
- **The test context budget went from 4800 to 5300.** Re-measured rather than assumed: the
  system prompt is 3765 tokens (ticket 32 measured 3166) and the floor a compressed prompt
  cannot go below is 4500 (was 4110), so 5300 leaves about 18 percent of headroom. Both numbers
  are in the comment in `tests/test_context.py`. Ninth ticket to move it.
- `tests/test_small_model.py` is new: 22 tests, each one a failure of the review scripted with
  its own SQL, its own tool arguments or its own prose. Three existing tests changed shape (the
  taxonomy line in two prompt assertions, a profile-scope statement that summed cents) and two
  memory tests now seed the profile through `add_memory` rather than through twenty turns of
  distillation, because a turn leaves at most two facts behind now.

### What is still open

- The doughnut and the grouped bars are still the chart sub-agent's weak spots (F2, F3). Charts
  are tickets 25 and 36; nothing here touched them.
- Qwen still picks the current quarter for "letztes Quartal" often enough to matter, even with
  the dates in front of it, and still answers an English question in German now and then.
- A turn that spends its five queries and then meets a provider error (B4) ends without an
  answer. The question is kept with its interrupted marker, which is ticket 32's behaviour.
