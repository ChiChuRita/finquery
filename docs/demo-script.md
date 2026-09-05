# Demo script

The live demo of Monday 2026-09-07, on the local provider, from a clean database. Every step
below was run on 2026-09-05 on the 24 GB M4 Pro with `FINQUERY_PROVIDER=local`, and the time
next to it is what that step took there, measured on the chat request itself (from Send to the
last byte of the stream, so it includes the follow-up suggestions and the memory distillation
that close every turn). Budget about 35 minutes of talking for the whole script, of which
roughly 20 are the models working.

Two slots, two speeds. **Fast** is Gemma 4 E4B, which also runs every sub-agent (SQL, chart,
categorizer, extraction, memory). **Quality** is Qwen3.5 9B, which thinks for a long time
before it answers. The script stays on the fast slot and switches to Qwen for exactly one
prepared question, because a Qwen turn is two to three minutes. A fast turn with one query is
about a minute, most of it prompt evaluation: llama.cpp's multimodal handler re-reads the whole
prompt on every request and a turn is three to five requests (the chat model, the sub-agent,
the chat model again, then follow-ups and distillation).

Both models resident take 13.5 GB. Close everything else heavy before you start.

## Before you start

```sh
cd finquery
cp .env.example .env                      # FINQUERY_PROVIDER=local, no key needed
# optional: FINQUERY_PARKED_MODELS_DIR=/path/to/already-downloaded/ggufs
cd frontend && npm install && npm run build && cd ..
mv data/finquery.db data/finquery.before-demo.db 2>/dev/null   # a clean database
uv run finquery-check                     # both slots answer, think, call a tool, see
uv run finquery                           # http://127.0.0.1:8000
```

`finquery-check` loads both models once (about 3 seconds each) and takes two to three minutes,
nearly all of it Qwen thinking about a three-number sum. Green means the demo can start. Open
Settings once before the audience arrives: the Models card shows both files ready, where each
came from (a parked copy or Hugging Face), and the sanity check button.

Have the browser at 1440 wide, the theme you prefer (both are fine), and these two files in a
Finder window: `fixtures/synthetic/bill-edeka-2025-03-14.png` and
`fixtures/synthetic/sparkasse-2025.csv`.

## The script

Times are for the fast slot unless the step says Qwen. "Instant" means no model runs.

### 1. Onboarding (no model, about 2 minutes of talking)

A fresh database opens `/onboarding`.

1. **Step 1, categories.** Fifteen default categories, all on. Turn one off (Education),
   rename a subcategory inline, add one ("Pets"). Every toggle is a real taxonomy change; say
   that the Settings page uses the same code. Continue.
2. **Step 2, how I should answer.** Pick **English** (or **Deutsch** for a German audience).
   Do not leave "Follow my message": the small local model drifts into German on German data,
   and a fixed language is the honest demo. Leave the model on Gemma 4 E4B, leave web lookup
   off (it comes later, with its log). Continue.
3. **Step 3, your first data.** Press **Load the sample year**. 32 s. It imports 433
   bookings of a synthetic German household through the same function the composer's
   `import_file` tool uses, categorizes them (384 by the merchant dictionary, 24 by the
   categorizer sub-agent, 25 left for you) and lands in a chat with the import step and the
   first Question card. Point at the counted summary: 433 read, 433 imported, 408 categorized.

### 2. Question cards (fast, two turns)

4. **Answer three rows** of the card (Jonas Keller: Dining, Max Schulz: Transfers, Anna Weber:
   Dining), leave Lea Hoffmann open, press **Send 3 answers**. The `Applied:` line appears on
   the card within a second: the rules were written by the server before the model spoke. The
   model then summarizes and asks the next card by itself. 67 s.
5. **Answer the last row** (Lea Hoffmann: Dining), **Send 1 answer**. "Nothing left to
   review." 54 s. Open Transactions in a new tab if you like: 0 rows Needs review.

### 3. Three questions with the query step (fast)

Press **New chat** first: a fresh conversation keeps the prompt short and every turn faster.

6. **"How much did I spend on groceries in May 2025?"** 63 s. Open the Query step: the
   request the model wrote, the SQL a sub-agent produced, the guard's `LIMIT 200`, the one row.
   The figure in the sentence is the figure in the row (440,72 EUR).
7. **"Und im Vergleich zum April?"** 72 s. A German follow-up in the same chat; the model
   rewrites it into a standalone request ("April 2025 compared with May 2025") because the SQL
   sub-agent sees no history. Two rows, two figures (252,70 EUR and 440,72 EUR).
8. **"Which merchants took the most money in 2025? Show me the top five."** 73 s. A five row
   table; the landlord first (13.800,00 EUR). Every number is one of the five rows.

### 4. Two chart shapes (fast)

9. **"Show me my monthly spending in 2025 as a chart."** 96 s. Open the thinking panel while
   it runs: the plan ("area, titled ..."), the data line, "Self-check passed". The card carries
   the shape badge, the SQL and its 12 rows, Regenerate and thumbs. Hover a month.
10. **"Show my five biggest merchants of 2025 as horizontal bars."** 86 s. A ranking with
    long labels reads as horizontal bars; five bars, the landlord longest. Toggle the theme
    once here: the chart repaints in the other palette. (Not the doughnut, see below.)

### 5. A bulk changeset (fast)

11. **"Recategorize all Amazon Prime bookings as Shopping."** 66 s. A changeset card with the
    12 affected rows, old category struck through, "A preview. Nothing is written until you
    press Apply." Press **Apply**: instant, the card turns to Applied with an Undo.

### 6. A bill photo becomes a split (fast, vision)

12. Drop `bill-edeka-2025-03-14.png` on the composer and send **"Here is the receipt for this
    payment."** 100 s. The fast slot reads the photo: seven line items that add up to the
    printed total of 20,73 EUR, matched against the EDEKA booking of 14.03.2025. A split
    proposal appears inside the import step: two legs, Groceries 11,75 EUR and Shopping
    8,98 EUR. Press **Apply**. Say the rule: queries count the legs, never the parent.

### 7. Memory across two conversations (fast, two turns)

13. Still in this chat: **"Remember: my flatmate is Max Schulz."** 49 s to 84 s. A `remember`
    step and a one-line confirmation. Keep the sentence this short: the fast model stores a
    short fact nearly word for word, and it is the word "flatmate" in the stored fact that the
    next step needs. A longer sentence came back stored without that word, and the next
    question then missed.
14. **New chat.** **"How much did I send my flatmate in 2025?"** 59 s. "The total amount sent
    to your flatmate, Max Schulz, was 137,50 EUR", with "5 memories used" under it: the model
    wrote "Max Schulz" into its request, and the SQL matched the PayPal description. Open
    `/memory` in a tab: the fact, "you asked for it", edit and delete.

### 8. A model switch to Qwen for one prepared question (quality)

15. In the composer, pick **Qwen3.5 9B** and ask **"What was my largest single expense in
    2025, and what was it for?"** 138 s, of which the first is the model loading and about 12
    are visible thinking. The answer names the rent (1.150,00 EUR, 01.01.2025). The turn chip
    reads "Qwen3.5 9B model" while every earlier turn keeps "Gemma 4 E4B model".

### 9. Stop mid-generation (quality)

16. Ask Qwen something long: **"Explain in detail how my spending developed over 2025, month
    by month, and what might explain each change."** Let it think and write for 20 seconds,
    press **Stop**. The partial thinking, tool steps and text stay, chipped "Stopped". Switch
    the composer back to **Gemma 4 E4B**.

### 10. The context badge, thumbs, a Regenerate pair (fast)

17. Click the percentage in the conversation header: used tokens over the 32k budget, the
    model, memories in the prompt, and the note that past 60 percent the older turns are
    summarized.
18. **Thumbs up** the Qwen answer: instant, "This response was useful" stays pressed.
19. Back in the charts conversation (its tab), press **Regenerate** on the area chart. 28 s.
    Two charts side by side, "Both charts drew the rows of the same query. Pick the better
    one." Press **Pick** under one: "Stored as a preference pair". Open `/feedback`: the
    records, and Export JSONL.

### 11. Web lookup with the outbound log (fast)

20. Settings, **Web lookup** on. The card says "Off" turned to "On" and the outbound log is
    still empty: "nothing has ever left this machine for this profile".
21. New chat: **"What is dean&david on my statement?"** 53 s. The lookup step shows the
    merchant token that left, the searches, the category it suggests and the sources under the
    answer.
22. Back to Settings: the outbound log lists the request, its target and the token, and
    nothing else. Switch web lookup off again.

### 12. The Imports overview with Continue in chat and Delete (fast)

23. Drop `sparkasse-2025.csv` on the composer a second time and send it. 58 s. Every one
    of its 433 bookings is already there, so the import writes nothing and asks about the
    duplicates on a card. Leave the card unanswered.
24. Open `/import`. Two imports: the first with 433 imported, the second with "433 undecided"
    in amber and a **Continue in chat** link. Click it: the conversation with the open card.
    Back on `/import`, **Delete** the second import: the confirmation names what goes with
    it, and the list is back to one.

### 13. The Transactions page with the split (no model)

25. Open `/transactions`. 433 rows. Type "edeka" into the search, set From 01.03.2025 to
    31.03.2025: the EDEKA row of 14.03.2025 has a chevron. Expand it: the two legs from step
    12, summing to the parent. Edit one category inline (click the cell, pick, click away: it
    saves). Clear the filters.

## What runs where, and how long

| Step | Slot | Measured |
| --- | --- | --- |
| Load the sample year (import, categorizer) | fast | 32 s |
| Answer a Question card (3 rows, next card drawn) | fast | 67 s |
| Answer the last card row | fast | 54 s |
| Query question, import conversation | fast | 63 s |
| German follow-up, same conversation | fast | 72 s |
| Query question, fresh conversation | fast | 73 s |
| Area chart | fast | 96 s |
| Horizontal bars, five merchants | fast | 86 s |
| Doughnut per category (folded to six slices, then failed its check, not in the live script) | fast | 118 s |
| Bulk changeset proposal | fast | 66 s |
| Bill photo, split proposal (vision) | fast | 100 s |
| `remember` | fast | 49 s to 84 s |
| Question answered from memory, fresh conversation | fast | 59 s |
| Prepared question | Qwen | 138 s |
| Stop | either | under a second after the click |
| Regenerate a chart | fast | 28 s |
| Thumbs, Pick, Apply, Undo | none | instant |
| Web lookup (one search, one page read) | fast | 53 s |
| Second import of the same CSV (433 duplicate candidates) | fast | 58 s |
| Statement PDF, 15 pages, 433 bookings, reconciled (not in the live script) | fast | 1458 s |

## What is not in the live script

- **The PDF statement.** It works locally: `sparkasse-kontoauszug-2025.pdf` extracted all 433
  bookings with 0 flagged rows and reconciled to the printed closing balance, in 24 minutes
  (1458 s, about 97 s per page: one bounded extraction call per page on the fast slot, and
  the local provider runs the pages one after another). That is a coffee break, not a demo
  step. Show it on OpenRouter (131 s for the same file in ticket 11, four pages in flight)
  or open a profile where it was imported beforehand and show the reconciliation sentence on
  the Imports overview. Before ticket 17 the same extraction ran away until the context was
  full; the sub-agent output ceiling is what makes it finish at all.
- **The doughnut.** Asked for one, the fast model's code pass never gives `radialArc` its
  `color` channel, three rounds running, so the card says the chart could not be drawn and the
  answer gives the six figures instead (the twelve categories are folded to five plus "Other"
  in code first). It is honest and it costs two minutes, so it is not in the script. On
  OpenRouter the same request draws (ticket 25's benchmark), and Qwen was not tried on it.
- **Context compression.** It starts at 60 percent of the 32k budget, about 20k tokens of
  conversation. On the local provider that is a quarter of an hour of turns, so the script
  shows the badge and says what happens past 60 percent instead of getting there. To show the
  divider live, start the server with `FINQUERY_CONTEXT_BUDGET=6000` for one conversation.
- **The A/B on a thumbs down.** It works (a second answer at a higher temperature with only
  the query tool, then a pick), and it costs another minute. Mention it, do it if time allows.

## If something goes wrong

- A turn is slow but the thinking panel moves: wait. The first token of a late turn in a long
  conversation can be 20 seconds behind Send, because the whole prompt is re-read. Nothing is
  stuck until Stop stops moving too.
- A chart card says it could not be drawn: the answer under it gives the figures instead, by
  design. Press Regenerate once; the second attempt usually draws.
- The model answers in the wrong language: onboarding's answer language (Settings, Setup, or
  the language rule in the prompt) is what fixes it, not repeating the question.
- The doughnut, the flatmate question or the lookup misfires: every one has a fallback in the
  same words one step earlier (the area chart, the rent question on Qwen, the second import).
