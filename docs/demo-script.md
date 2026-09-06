# Demo script

The live demo of Monday 2026-09-07, on the local provider, from a clean database. The timed
steps below were run on 2026-09-05 on the 24 GB M4 Pro with `FINQUERY_PROVIDER=local`, and the
time next to such a step is what it took there, measured on the chat request itself (from Send
to the last byte of the stream, so it includes the follow-up suggestions and the memory
distillation that close every turn). Steps added after that measurement say **to time on the
local provider** instead of a number: they were driven on OpenRouter, not on the laptop.
Budget about 40 minutes of talking for the whole script, of which roughly 20 are the models
working.

Two numbers moved under the timed steps and neither has been re-measured locally. A query now
checks its own result (ticket 40), which is one more fast-slot call on most questions, so a
question with one query runs a little longer than the table says. The sub-agent prompts grew
worked examples and a reasoning field (tickets 40 and 42), which is a few hundred more tokens to
evaluate per call. Read the table as a floor, not a promise.

Four models in the picker, two of them on this laptop: **Qwen3.5 9B (local)**, **Qwen3.5 9B
(cloud)**, **Gemma 4 12B (local)** and **Gemma 4 26B (cloud)**. Whichever one a chat runs on,
its sub-agents (SQL, chart, categorizer, extraction, memory, and the result check) run on the
fast model of that same provider: **Gemma 4 E4B** locally, the hosted fast model in the cloud.
Nobody picks the fast model; it is a model the app runs, listed on the Settings card.

The script stays on Gemma 4 E4B for the ordinary questions and switches to a chat entry for
exactly one prepared question, because a Qwen turn is two to three minutes. A fast turn with one
query is about a minute, most of it prompt evaluation: llama.cpp's multimodal handler re-reads
the whole prompt on every request and a turn is four to six requests (the chat model, the query
sub-agent, the check, the chat model again, then follow-ups and distillation).

Two models are resident at once and no more: E4B plus one chat model, 13.5 GB with Qwen3.5 9B
and about 12.9 GB with Gemma 4 12B. The two local chat models share one seat, so switching from
one to the other unloads the first and loads the second, which costs the turn that asks for it
about 20 seconds. Close everything else heavy before you start.

Both providers are live at the same time. `FINQUERY_PROVIDER=local` only decides which entry a
new chat starts on, so with `OPENROUTER_API_KEY` in `.env` the two cloud entries are one click
away in the same picker. Either hosted id can be pointed somewhere else without a code change
(`FINQUERY_OPENROUTER_QUALITY_MODEL`, `FINQUERY_OPENROUTER_SECOND_CHAT_MODEL`,
`FINQUERY_OPENROUTER_FAST_MODEL`). That is the escape hatch behind the fallbacks at the end of
this script: a laptop that will not cooperate runs the same chat on a cloud entry, one switch in
the composer, without restarting anything.

## Before you start

```sh
cd finquery
cp .env.example .env                      # FINQUERY_PROVIDER=local, no key needed
# optional: FINQUERY_PARKED_MODELS_DIR=/path/to/already-downloaded/ggufs
cd frontend && npm install && npm run build && cd ..
mv data/finquery.db data/finquery.before-demo.db 2>/dev/null   # a clean database
uv run finquery-check                     # every local model answers, thinks, calls a tool, sees
uv run finquery                           # http://127.0.0.1:8000
```

`finquery-check` covers the fast slot and every local chat model whose weights are on disk, one
seat at a time (about 3 seconds to load each), and takes two to three minutes, nearly all of it
Qwen thinking about a three-number sum. Green means the demo can start. Open Settings once
before the audience arrives: the Models card lists all four entries with their availability,
which local model is in the seat, where each file came from (a parked copy or Hugging Face), and
the sanity check button.

Have the browser at 1440 wide, the theme you prefer (both are fine), and these two files in a
Finder window: `fixtures/synthetic/bill-edeka-2025-03-14.png` and
`fixtures/synthetic/sparkasse-2025.csv`.

## The script

Times are for the fast slot unless the step says Qwen. "Instant" means no model runs.

### 1. Onboarding (no model, about 2 minutes of talking)

A fresh database opens `/onboarding`. It is skippable on every step, resumable (the step is in
the URL, so a reload lands back on it) and reopenable later from Settings; a profile sees it
once.

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
   The CSV sits on the first message as a file chip, the same chip a dropped file gets.

### 2. The Dashboard, straight after the import (no model)

4. **Open the Dashboard** in the sidebar. To time on the local provider; no model runs, it is
   queries only. Four tiles of the newest month of the data (Spent, Income, Net, Needs review
   with a link that opens the review chat) and four charts that were there from the first
   visit: spending per month, spending by category over the last three months, income against
   spending, and the top ten merchants of the year. The line worth saying out loud: **nothing
   on this page is a stored number**. Every tile and every card ran its statement through the
   same guard a chat question goes through, just now, on load. That is also why the defaults
   cost no model call: their SQL and their chart code are written in the repo, not by a model.
   Say that a card can be renamed, moved, refreshed and removed, and come back here in step 13
   with a chart from the chat.

### 3. Question cards (fast, two turns)

5. **Answer three rows** of the card (Jonas Keller: Dining, Max Schulz: Transfers, Anna Weber:
   Dining), leave Lea Hoffmann open, press **Send 3 answers**. The `Applied:` line appears on
   the card within a second: the rules were written by the server before the model spoke. The
   model then summarizes and asks the next card by itself. 67 s.
6. **Answer the last row** (Lea Hoffmann: Dining), **Send 1 answer**. "Nothing left to
   review." 54 s. Open Transactions in a new tab if you like: 0 rows Needs review.

### 4. Three questions with the query step (fast)

Press **New chat** first: a fresh conversation keeps the prompt short and every turn faster.

7. **"How much did I spend on groceries in May 2025?"** 63 s. Watch the thinking panel while
   it runs: after the statement comes **"Checking the result"**, which is a second fast-slot
   pass asking whether those rows answer that question. Then open the Query step: the request
   the model wrote, the SQL a sub-agent produced, the guard's `LIMIT 200`, the one row. The
   figure in the sentence is the figure in the row (440,72 EUR).
8. **"Und im Vergleich zum April?"** 72 s. A German follow-up in the same chat; the model
   rewrites it into a standalone request ("April 2025 compared with May 2025") because the SQL
   sub-agent sees no history. Two rows, two figures (252,70 EUR and 440,72 EUR).
9. **"Which merchants took the most money in 2025? Show me the top five."** 73 s. A five row
   table; the landlord first (13.800,00 EUR). Every number is one of the five rows.
10. **The check catching one**, if there is time: **"Was ist meine kleinste wiederkehrende
    Zahlung?"** To time on the local provider. This is the question that used to answer with
    the largest payment. When the check disagrees the panel says **"Rewriting: ..."** with its
    one-sentence reason, and the sub-agent writes the statement again with that reason in front
    of it. A query costs at most three model calls whatever happens: the statement, the check,
    one rewrite. If the first statement was already right, the panel says only "Checking the
    result", which is the honest outcome and still worth pointing at.

### 5. Two chart shapes, and one goes on the Dashboard (fast)

11. **"Show me my monthly spending in 2025 as a chart."** 96 s. Open the card's **Details**
    while it runs: the chart sub-agent's work is a chain of thought there, one step at a time
    (planned, queried, wrote, a step per repair round, checked), the current one active and the
    rest pending, and it stays as the finished chain afterwards. The card carries the shape
    badge, the SQL, its 12 rows and Add to dashboard. Hover a month.
12. **"Show my five biggest merchants of 2025 as horizontal bars."** 86 s. A ranking with
    long labels reads as horizontal bars; five bars, the landlord longest. Toggle the theme
    once here: the chart repaints in the other palette. (Not the doughnut, see below.)
13. **Press "Add to dashboard"** on the monthly spending card. Instant. The card reads "On the
    dashboard" with a Remove next to it and stays that way after a reload. Go to the Dashboard:
    the chart is the fifth card, drawn from its own statement re-run just now, not from a
    picture.
14. **"Track my spending on groceries per month."** The assistant decides for itself that this
    is a chart to keep: the card says "On the dashboard" as it is drawn and the answer says so
    in one line. Ask **"what is on my dashboard?"**, then **"show me the groceries one"** (it
    draws that card in the answer), then **"make it a bar chart"** (the card is replaced at once
    and the chat card carries an Undo), and **"take it off the dashboard"** (a line with an Undo
    too). On the page itself, rename a card inline, move it left once and press Refresh, which
    stamps "Refreshed ...".
15. **Narrow the range.** The bar above the tiles: press "Last 3 months", then pick two days by
    hand. Every tile and every card re-queries for those days, without a model call, and the URL
    carries the range, so a reload and the back button keep it. "All" puts it back.

### 6. A bulk changeset (fast)

16. **"Recategorize all Amazon Prime bookings as Shopping."** 66 s. A changeset card with the
    12 affected rows, old category struck through, "A preview. Nothing is written until you
    press Apply." Press **Apply**: instant, the card turns to Applied with an Undo.

### 7. A bill photo becomes a split (fast, vision)

17. Drop `bill-edeka-2025-03-14.png` on the composer. Before you send, point at the chip: a
    photo is a **thumbnail** you can hover for the picture at readable size, with a remove
    button that is always visible; a CSV or a PDF is an icon chip with its name. Send **"Here is
    the receipt for this payment."** 100 s. The sent message keeps the thumbnail, and it is a
    link to the copy the server stored, so the transcript still shows what was read a week
    later. The fast slot reads the photo: seven line items that add up to the printed total of
    20,73 EUR, matched against the EDEKA booking of 14.03.2025. A split proposal appears inside
    the import step: two legs, Groceries 11,75 EUR and Shopping 8,98 EUR. Press **Apply**. Say
    the rule: queries count the legs, never the parent.

### 8. Memory across two conversations (fast, two turns)

18. Still in this chat: **"Remember: my flatmate is Max Schulz."** 49 s to 84 s. A `remember`
    step and a one-line confirmation. Keep the sentence this short: the fast model stores a
    short fact nearly word for word, and it is the word "flatmate" in the stored fact that the
    next step needs. A longer sentence came back stored without that word, and the next
    question then missed.
19. **New chat.** **"How much did I send my flatmate in 2025?"** 59 s. "The total amount sent
    to your flatmate, Max Schulz, was 137,50 EUR", with "5 memories used" under it: the model
    wrote "Max Schulz" into its request, and the SQL matched the PayPal description. Open
    `/memory` in a tab: the fact, "you asked for it", edit and delete. Worth a sentence: a turn
    leaves at most two facts behind and never one carrying an amount or a date, which is why
    this list is short rather than a diary.

### 9. A model switch for one prepared question

20. Open the composer's model picker. Four entries: **Qwen3.5 9B (local)**, **Qwen3.5 9B
    (cloud)**, **Gemma 4 12B (local)** and **Gemma 4 26B (cloud)**, each saying where it runs,
    and any that is not ready is greyed out with the reason (no API key, or weights still coming
    down). Pick **Qwen3.5 9B (local)** and ask **"What was my largest single expense in 2025, and
    what was it for?"** 138 s, of which the first is the seat being loaded and about 12 are
    visible thinking. The answer names the rent (1.150,00 EUR, 01.01.2025). The turn chip reads
    "Qwen3.5 9B (local)" while every earlier turn keeps its own model's name: switching a chat
    never relabels a turn that is already on screen.

    If there is time and a key in `.env`, switch the same chat to **Qwen3.5 9B (cloud)** and ask
    it again: same weights, one second instead of two minutes, and the sub-agents move to the
    hosted fast model with it. Nothing was restarted, and the two turns sit next to each other
    with their own chips.

### 10. A turn keeps running when you walk away, then Stop (quality)

21. Ask Qwen something long: **"Explain in detail how my spending developed over 2025, month
    by month, and what might explain each change."** While it thinks, click another chat in the
    sidebar: that chat's row and its tab keep a small spinner, because the turn is a task on the
    server and not something this tab owns. The composer of that chat is closed while it
    answers, in every tab, and its line reads "This chat is answering. It keeps going if you
    switch chats or close the tab." Come back to it; the answer has carried on and the
    transcript picks it up mid-sentence. Reload the page for the same point twice as loudly: the
    question, the thinking and the tool steps are all still there and the stream reattaches.
    Then press **Stop**. The partial thinking, tool steps and text stay, chipped "Stopped": Stop
    is the only thing that ends a turn. Switch the composer back to **Gemma 4 E4B**.

### 11. The context badge and the download (fast)

22. Click the percentage in the conversation header: used tokens over the 32k budget, the
    model, memories in the prompt, and the note that past 60 percent the older turns are
    summarized.
23. **Download this conversation** from the button next to that badge. Instant. It writes
    markdown, and it is not only the text: the query steps come with their SQL and row counts,
    the charts with their plan and SQL, the changesets with their status and rows, the Question
    cards with the answers given, the attachments as links. Open the file: the audit trail
    leaves the machine as a file you can read.
### 12. Web lookup with the outbound log (fast)

24. Settings, **Web lookup** on. The card says "Off" turned to "On" and the outbound log is
    still empty: "nothing has ever left this machine for this profile".
25. New chat: **"Was ist Combi Verbrauchermarkt?"** The lookup step shows the merchant token
    that left, "1 search, 1 page read" with the page as a link, the sentence it quoted out of
    that page with the host under it, and the category it suggests. The quote is checked in
    code to occur word for word in what the steps returned, and the page was read by the loop
    itself because one result was the shop's own site. Say the three sentences of explainer 15
    over this card. Keep away from "Hausverwaltung Bergmann": the loop finds a real property
    manager of that name in another city, and the card then says "unsure" for a reason nobody
    wants to explain on a stage.
26. Back to Settings: the outbound log lists both requests, their targets and the token, and
    nothing else. Ask the same merchant in a second chat: the card says "from the lookup cache
    of this profile, nothing left the machine" and the log has no new row. Then drop the Combi
    receipt (the private receipt set, `fixtures/private/`) on the composer, or the Saurüsselalm
    one: the draft is titled with the shop and
    carries its category, and the log still has the one token on it, never a line item. Switch
    web lookup off again.

### 13. A second import, in the background, then the Imports overview (fast)

27. Drop `sparkasse-2025.csv` on the composer a second time and send it. 58 s. **While it
    runs, switch to another conversation**: the spinner on its tab and its sidebar row is the
    import carrying on without you, and `/import` shows that row as **Still importing** with a
    Continue in chat button. Come back and watch the rest arrive. Every one of its 433 bookings
    is already there, so the import writes nothing and asks about the duplicates on a card.
    Leave the card unanswered.
28. Open `/import`. It imports nothing itself, it is the overview of what every past import
    produced. Two rows: the first with 433 imported, the second with "433 undecided" in amber
    and a **Continue in chat** link. Click it: the conversation with the open card. Back on
    `/import`, **Delete** the second import: the confirmation names what goes with it (its
    bookings, its candidates and the decisions on them), and the list is back to one. That is
    the way back from an import into the wrong profile.

### 14. The Transactions page with the split (no model)

29. Open `/transactions`. 433 rows. Type "edeka" into the search, set From 01.03.2025 to
    31.03.2025: the EDEKA row of 14.03.2025 has a chevron. Expand it: the two legs from step
    16, summing to the parent. Edit one category inline (click the cell, pick, click away: it
    saves). Clear the filters.

## What runs where, and how long

Measured on 2026-09-05 on the local provider, before the result check and the grown prompts.
"To time" means the step was driven on OpenRouter and has no local number yet.

| Step | Slot | Measured |
| --- | --- | --- |
| Load the sample year (import, categorizer) | fast | 32 s |
| The Dashboard: four tiles and four cards, every one a query | none | to time |
| Answer a Question card (3 rows, next card drawn) | fast | 67 s |
| Answer the last card row | fast | 54 s |
| Query question, import conversation | fast | 63 s |
| German follow-up, same conversation | fast | 72 s |
| Query question, fresh conversation | fast | 73 s |
| A query the check rewrites once | fast | to time |
| Area chart | fast | 96 s |
| Horizontal bars, five merchants | fast | 86 s |
| Add to dashboard, from a chat chart card | none | instant |
| A chart the assistant keeps on the dashboard by itself | fast | as a chart turn |
| Edit, rename or remove a dashboard card from a chat | fast for an edit, none otherwise | to time |
| Narrow the dashboard to a date range | none | instant |
| Refresh a dashboard card (re-runs its SQL) | none | to time |
| Doughnut per category (folded to six slices, then failed its check, not in the live script) | fast | 118 s |
| Bulk changeset proposal | fast | 66 s |
| Bill photo, split proposal (vision) | fast | 100 s |
| `remember` | fast | 49 s to 84 s |
| Question answered from memory, fresh conversation | fast | 59 s |
| Prepared question | Qwen | 138 s |
| Switch chat mid-turn and come back, reload mid-turn | either | instant, the turn is untouched |
| Stop | either | under a second after the click |
| Download the conversation as markdown | none | instant |
| Apply, Undo | none | instant |
| Web lookup (one search, one page read) | fast | 53 s |
| Second import of the same CSV (433 duplicate candidates) | fast | 58 s |
| Statement PDF, 15 pages, 433 bookings, reconciled (not in the live script) | fast | 1458 s |

## What is not in the live script

- **The PDF statement.** It works locally: `sparkasse-kontoauszug-2025.pdf` extracted all 433
  bookings with 0 flagged rows and reconciled to the printed closing balance, in 24 minutes
  (1458 s, about 97 s per page: one bounded extraction call per page on the fast slot, and
  the local provider asks for four pages at a time but one model answers them in turn). That is
  a coffee break, not a demo step. Show it on OpenRouter (131 s for the same file in ticket 11
  with four pages in flight; a hosted provider now runs twelve, and
  `FINQUERY_EXTRACTION_PAGE_CONCURRENCY` turns that down) or
  open a profile where it was imported beforehand and show the reconciliation sentence on the
  Imports overview. Before ticket 17 the same extraction ran away until the context was full;
  the sub-agent output ceiling is what makes it finish at all.
- **The doughnut, asked for in chat.** The fast model's code pass never gives `radialArc` its
  `color` channel, three rounds running, so the card says the chart could not be drawn and the
  answer gives the six figures instead (the twelve categories are folded to five plus "Other"
  in code first). It is honest and it costs two minutes, so it is not in the script. On
  OpenRouter the same request draws (88 to 100 percent on the chart benchmark), and Qwen is
  worst of all on this shape (12 percent). The Dashboard's own doughnut is a different thing
  and does draw: its code is in the repo, not written by a model, which is a point worth making
  if somebody asks why one works and the other does not.
- **Context compression.** It starts at 60 percent of the 32k budget, about 20k tokens of
  conversation. On the local provider that is a quarter of an hour of turns, so the script
  shows the badge and says what happens past 60 percent instead of getting there. To show the
  divider live, start the server with `FINQUERY_CONTEXT_BUDGET=6000` for one conversation.
- **The benchmarks.** They are numbers, not a screen: 152 SQL questions and 63 chart requests
  with gold rows computed from reference SQL. If somebody asks how good the models really are,
  the answer is `bench/README.md`, not a live run.

## If something goes wrong

- A turn is slow but the thinking panel moves: wait. The first token of a late turn in a long
  conversation can be 20 seconds behind Send, because the whole prompt is re-read. A query also
  pauses at "Checking the result" for one more model call now. Nothing is stuck until Stop
  stops moving too.
- The browser gets into a bad state mid-turn: **reload the page**. That is a real recovery, not
  a gamble. The turn is a task on the server, so reloading, switching chat or closing the tab
  costs nothing: the transcript reattaches to the same stream and the answer carries on where it
  was, in one message rather than two.
- The composer is closed and you wanted to type: that chat is still answering, in every tab.
  Wait for it or press Stop. Whatever you typed stays in the box as a draft.
- A chart card says it could not be drawn: the answer under it gives the figures instead, by
  design. The server already drew it a second time by itself; ask for the chart again if the
  picture matters more than the figures.
- The model answers in the wrong language: onboarding's answer language (Settings, Setup, or
  the language rule in the prompt) is what fixes it, not repeating the question.
- **Answer the open Question card before typing the next question.** A card left open while
  the conversation moves on still works, but the demo reads better in order.
- A step misfires: every one has a fallback in the same words one step earlier. The doughnut
  falls back to the horizontal bars of step 12, the flatmate question to the rent question on
  Qwen (step 20), the lookup to the second import (step 27), the chart the assistant keeps by
  itself to the one added by hand in step 13, and the PDF to the pre-imported profile. If the laptop itself
  gives up, `FINQUERY_PROVIDER=openrouter` runs the identical script hosted, and
  `FINQUERY_OPENROUTER_FAST_MODEL` points the fast slot at a stronger model for one step.
