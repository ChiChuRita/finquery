# FinQuery

Local-first conversational personal-finance analyst. Import bank statements, ask questions in
natural language, get deterministic, auditable answers. Numbers always come from executed
queries, never from the model.

## Run

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22 (only to build the
frontend), an OpenRouter key while the provider is `openrouter`.

```sh
cp .env.example .env            # then put your key into OPENROUTER_API_KEY
cd frontend && npm install && npm run build && cd ..
uv run finquery                 # http://127.0.0.1:8000
```

One process serves the API under `/api` and the built frontend from `frontend/dist`. The
SQLite database lives in `data/finquery.db` (override with `FINQUERY_DB_PATH`). A fresh
database opens with onboarding; "Load the sample year" in its last step imports the shipped
synthetic dataset, which is also where the demo starts (`docs/demo-script.md`).

The provider is one switch. `FINQUERY_PROVIDER=openrouter` runs both slots on OpenRouter
(Gemma 4 26B fast, Qwen3.5 9B quality); `FINQUERY_PROVIDER=local` runs the same two slots in
this process (Gemma 4 E4B fast, Qwen3.5 9B quality, see below). Nothing else changes, and the
selector in the composer names the model the running provider really resolves each slot to.

Settings (environment or `.env`):

| Variable                     | Default            | Meaning                                       |
| ---------------------------- | ------------------ | --------------------------------------------- |
| `FINQUERY_PROVIDER`          | `openrouter`       | `openrouter` or `local`                       |
| `OPENROUTER_API_KEY`         |                    | Required for `openrouter`                     |
| `FINQUERY_DB_PATH`           | `data/finquery.db` | SQLite file                                   |
| `FINQUERY_HOST`              | `127.0.0.1`        | Bind address                                  |
| `FINQUERY_PORT`              | `8000`             | Port                                          |
| `FINQUERY_CONTEXT_BUDGET`    | `32768`            | Tokens per turn; compression starts at 60%    |
| `FINQUERY_MODELS_DIR`        | `models`           | Where the local GGUF files live               |
| `FINQUERY_PARKED_MODELS_DIR` |                    | Folder of GGUFs to reuse instead of download  |
| `FINQUERY_LOCAL_N_CTX`       | `32768`            | Context cap per resident local model          |

## Run on the local models

`llama-cpp-python` ships as a source distribution, so the first install compiles it. On macOS
build it with Metal:

```sh
CMAKE_ARGS="-DGGML_METAL=on" uv sync
FINQUERY_PROVIDER=local uv run finquery
```

The two slots become Gemma 4 E4B (fast, also the slot every sub-agent runs on) and Qwen3.5 9B
(quality), running in this process through llama-cpp-python with Metal. Startup begins
downloading the four GGUF files (12.6 GB) into `models/`; watch it on the Settings page, which
also has a sanity check button. A file already sitting in `FINQUERY_PARKED_MODELS_DIR` whose
sha256 matches is linked in instead of downloaded, and the Settings card says which of the two
happened per file. Each model loads on its first use and then stays resident: both together
take 13.5 GB at the 32k context cap, so run nothing else heavy beside them.

Prove the setup before a demo:

```sh
uv run finquery-check    # both slots: answer, thinking, tool call, vision
```

What to expect locally on a 24 GB M4 Pro: a question with one query is about a minute on the
fast slot and two to three on the quality slot, most of it thinking and prompt evaluation
(llama.cpp's multimodal handler re-reads the whole prompt every request). The demo script has
a measured time per step: `docs/demo-script.md`.

The two models speak different chat formats, which is why `src/finquery/local/` has one wire
module each. See `docs/adr/0006-local-gemma-4-through-llama-cpp.md`, including what the two
of them take out of a 24 GB Mac at 32k.

## Develop

```sh
uv run finquery --dev           # API only on :8000 with auto reload
cd frontend && npm run dev      # Vite on :5173, proxies /api to :8000
```

Type-check the frontend with `npm run build` in `frontend/` (`tsc -b` and Vite), which is also
what `uv run finquery` needs run before it serves a change. AI Elements components live in
`frontend/src/components/ai-elements` and are added with
`npx shadcn@latest add https://elements.ai-sdk.dev/api/registry/<name>.json`. Only ever add one
that is not there yet: most of the vendored files carry local edits (theme tokens instead of raw
palette colours, trimmed markdown plugins, a dropped dependency, a generic message type) and
`add` overwrites them without a word. To refresh one, diff against the registry JSON by hand.
See `.scratch/finquery/ai-elements-audit-2026-09-05.md` for the per-file list and for which of
the 48 components were deliberately rejected.

## Test

```sh
uv run pytest                    # the HTTP-seam suite
cd frontend && npx tsc --noEmit && npm run build
```

Tests drive the FastAPI app over HTTP with both model slots replaced by scripted models. No test
calls OpenRouter and none loads a real model. See `docs/adr/0003-single-http-test-seam.md`.

One suite is opt-in because it does load the real local models:

```sh
FINQUERY_PROVIDER=local FINQUERY_SMOKE=1 uv run pytest tests/test_local_smoke.py -s
```

## Onboarding

A new profile opens onboarding at `/onboarding` instead of an empty chat: which of the seeded
categories it uses (each one a toggle that really removes the category, plus adding and renaming
inline), how the assistant should answer (the answer language, the model new chats start on, and
the web lookup switch with its privacy note), and its first data. It is skippable on every step,
resumable (the step is in the URL), and reopenable from Settings; a profile sees it once.

Step three is the chat's own import path, not a second one: a file dropped there opens a new
conversation with that file as the first message, so the mapping confirmation, the duplicates and
the Needs review questions all happen on Question cards in the chat. "Load the sample year" posts
`fixtures/synthetic/sparkasse-2025.csv` through the same function the `import_file` tool calls and
seeds the turn it would have produced. Finish opens a chat with a welcome turn the server wrote
from what the profile holds, with three suggested questions under it. No model runs for either.

## Data

Import a bank CSV export by dropping it on the chat composer and sending it: the assistant runs
the import as a tool call, with the rows read, imported and categorized ticking past in the tool
step. Sparkasse, DKB, ING, N26, comdirect and Trade Republic are recognized by their CSV headers;
any other bank gets a mapping proposed by the fast slot and confirmed on a Question card before
anything is written. Statement PDFs and photos are dropped on the composer the same way, and the
Sparkasse and Trade Republic statement layouts are recognized by their page headers. Typing "I
paid 12 EUR cash for lunch today" or pasting a few statement lines gives a preview card to
confirm, and confirming writes the booking and categorizes it.

A commit never inserts a booking the profile may already have, and never drops one either.
A row that matches an existing booking exactly (same account, date, amount and normalized
description) or nearly (same amount, at most two days apart, a similar description) is held
aside as a duplicate candidate, and a Question card asks about each one with Keep both or Remove,
five candidates at a time. Keeping inserts the booking and categorizes it; removing leaves the
data as it was. Re-importing the same statement is hundreds of exact matches, so that card offers
to remove them all in one click.

The commit is followed by categorization in stages: your own category rules, a dictionary
of about sixty German merchants, then, if you switched web lookup on, a web lookup of the
merchants nobody recognizes, and finally the categorizer sub-agent on the fast slot with a
confidence per merchant. Every row gets a friendly title and a short description. What stays
below the confidence threshold is Needs review, and the assistant asks about those merchants in
Question cards right there. Each answer becomes a category rule and recategorizes every booking
of that merchant, and telling the assistant "PayPal to Anna is always Dining" in chat does the
same.

A statement PDF is read from the text layer with pdfplumber, four pages at a time, and the
extraction sub-agent answers with the literal spans it read each figure from. Two guards then
decide whether the rows can be trusted: every amount, balance and date has to occur in the text of
the page it was read from, and the statement has to reconcile, per row on its running balance, per
page and as a whole. A page with no text layer is rendered at 150 dpi and looked at by the vision
path instead. What passes is imported; what does not is asked about on a Question card with
Accept and Drop per flagged row, and the verdict is one sentence that stays on the import record.
See `docs/adr/0011-two-guards-on-every-extracted-figure.md`.

A photo is read as a receipt: when its total matches a booking within three days the assistant
proposes a split of that booking into the receipt's line items, grouped by category, and otherwise
it previews a new booking. The date is the one the till printed, parsed in code from the span the
model copied (`04.09.26 20:00` and `14:12 04.05.2019` are dates); a receipt whose date cannot be
read says so on the card and asks for it instead of quietly booking today. A subtotal line
(`ZWI.SUMME`) is not an article and is dropped where it repeats what came before it, a discount is
a negative line item so the items still add up, a receipt whose prices are printed before tax adds
up with the tax line, a `Leergutbon` books money in rather than out, and a receipt in another
currency is refused with a sentence rather than booked as euros.

`/import` is the overview of what all of this produced, and imports nothing itself: per past
import the file, its kind, the account, when it ran, how many rows were read and how many landed,
how many duplicates it found and how many of them are still undecided, the reconciliation verdict
and how many of its bookings are still Needs review. An import with something open carries a
"Continue in chat" link into the conversation it came from, and every import has a Delete that
takes its bookings, its candidates and the decisions on them with it, which is the way back from
an import into the wrong profile.

Then ask in the chat. The query sub-agent writes the SQL on the fast slot, a guard admits only a
single read-only SELECT over your own transactions, and the tool step in the transcript shows the
statement and the rows behind every number. A statement that runs and answers a different
question is the failure a guard cannot see, so the result is checked against the question before
you see it: an empty or degenerate result is rewritten once in code, and a second pass on the
fast slot says whether the rows answer what was asked. Both say so in the thinking panel
("Checking the result", "Rewriting: ..."), and a query costs at most three model calls.

Ask for a chart and the chart sub-agent plans it, gets its rows the same way, writes a TanStack
Charts definition in plain JavaScript and checks it in-process before it is drawn in a sandboxed
frame. The plan and any repairs show up in the thinking panel; the card carries the SQL and the
rows behind the drawing. The contract is `docs/chart-runtime.md`.

A chart worth keeping goes on the Dashboard (`/dashboard`), which is the page each profile opens
with four figures of its newest month (spent, earned, net, and how many bookings still need
review) and the charts it keeps. Four of them are there from the first visit: spending per month,
spending by category over the last three months, income against spending, and the top ten
merchants of the year. "Add to dashboard" on any chart card in a chat puts that chart there, and
the line at the top of the page ("spending on groceries per month") runs the same chart sub-agent
and shows the result with Keep and Discard. A card can be renamed, moved, refreshed and removed.
What is stored is the title, the shape, the statement and the checked definition, never a number:
every load runs the statement again through the same guard, so a card is as current as the data
and one whose query stopped running says so on itself instead of breaking the page.

Rate what comes back. Every answer has thumbs in its toolbar and every chart card has thumbs
plus a Regenerate, which draws the same request a second time and shows both charts side by
side with a Pick. A thumbs down on an answer offers an A/B: the same message is answered again
at a higher temperature with only the read-only query tool, and the pick stores the pair. Each
thumb and each pick is a preference record (prompt, chosen, rejected, kind, rating, slot), the
Feedback page (`/feedback`) lists them and exports them as JSONL, and `training/preference/`
turns that into a DPO dataset and a train script for the two fast-slot adapters. Running the
training is the phase after this build; see `training/preference/README.md`.

`fixtures/synthetic/` holds the shipped demo dataset, one canonical year of a German household
as a Sparkasse CSV, a renamed-header CSV, a 15 page text PDF statement that reconciles, and four
bill images whose line items sum to a booking in the CSV. Regenerate
it with `uv run python scripts/generate_synthetic.py`.

## Web lookup

Off by default, one switch per profile in Settings. With it on, the assistant can find out what
an unknown merchant is: the fast slot drives its own search loop (search, read a page, or finish,
at most four searches and three page reads), and what comes back is a suggested category with a
confidence plus the sources, which the transcript shows under the answer.

Only a scrubbed merchant token ever leaves the machine, never an amount, a date, an account or
reference number, and a booking whose merchant reads as a person is refused instead of sent.
Every request is written to the outbound log before it goes out, and the Settings card lists that
log, so "nothing left my machine" is something you can read rather than something we claim. A
merchant token leaves at most once per profile: the result is cached. Search needs no API key
(`ddgs` over DuckDuckGo, Bing and Brave in that order). See
`docs/adr/0010-web-lookup-behind-a-merchant-token.md`.

## Layout

- `src/finquery/`: `main.py` (CLI), `app.py` (factory), `settings.py`, `providers.py` (slots),
  `db.py` (SQLAlchemy models and the query view), `taxonomy.py` (default categories),
  `agent.py` (chat agent and its tools), `query/` (query sub-agent, SQL guard, execution),
  `chart/` (chart sub-agent, shapes, QuickJS self-check),
  `dashboard.py` (the tiles, the four default cards and the guarded run behind every card),
  `changesets.py` and `edits.py` (proposed changes and the rules about what may be written),
  `categorize/` (rules, merchant dictionary, categorizer sub-agent, review queue),
  `weblookup/` (the merchant token scrubber, the keyless search client, the self-directed
  lookup loop, the outbound log and the lookup cache),
  `ask_user.py` (the Question card tool) and `answers.py` (what its answers do, in code),
  `followups.py` (post-turn suggestions),
  `onboarding.py` (the state a profile is in, the welcome turn's copy and the language rule),
  `memory.py` (durable facts: the `remember` tool, the distillation pass, prompt selection),
  `preferences.py` (ratings and picks as training data),
  `nullish.py` (the one place that knows what a model writes when it means nothing),
  `context.py` (token budget, per-turn prompt assembly, rolling summary),
  `attachments.py` (files dropped into a chat), `progress.py` (a tool's live progress part),
  `ingest/` (CSV reader, presets, mapping sub-agent, commit, duplicate candidates, the chat
  import and typed transactions),
  `extract/` (PDF text and page rendering, statement layouts, the extraction sub-agent, the
  verbatim and reconciliation guards, the bill flow, the review card),
  `api/` (REST and chat endpoints; `api/chat.py` also owns the turn's end marker, which is what
  says a turn whose run stopped existing was interrupted rather than never asked, and
  `api/running.py` holds the turns being produced right now, each a task with a buffer its
  readers subscribe to),
  `local/` (the local provider: catalog, downloads, runtime, model, the Gemma 4 and Qwen3.5
  wire formats, check)
- `frontend/`: Vite, React 19, Tailwind 4, shadcn, AI Elements, TanStack Router, Query and
  Charts. `src/chart-runtime/` is a second page: the sandboxed frame charts render in
- `training/preference/`: the DPO export, the train script and the loop they belong to
- `tests/`: HTTP-seam tests
- `fixtures/synthetic/`: shipped demo dataset. `scripts/`: its generator, and
  `measure_categorization.py`, which imports a CSV into a running app and prints what each
  categorization stage placed
- `CONTEXT.md`: domain glossary. `docs/adr/`: architecture decisions.
  `docs/chart-runtime.md`: the contract generated chart code is written against
- `.scratch/finquery/`: spec and tickets
