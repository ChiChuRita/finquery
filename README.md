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
SQLite database lives in `data/finquery.db` (override with `FINQUERY_DB_PATH`).

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
| `FINQUERY_LOCAL_N_CTX`       | `16384`            | Context cap per resident local model          |

## Run on the local models

`llama-cpp-python` ships as a source distribution, so the first install compiles it. On macOS
build it with Metal:

```sh
CMAKE_ARGS="-DGGML_METAL=on" uv sync
FINQUERY_PROVIDER=local uv run finquery
```

The two slots become Gemma 4 E4B (fast) and Gemma 4 12B (quality), running in this process
through llama-cpp-python with Metal. Startup begins downloading the four GGUF files (13.3 GB)
into `models/`; watch it on the Settings page, which also has a sanity check button. A file
already sitting in `FINQUERY_PARKED_MODELS_DIR` whose sha256 matches is linked in instead of
downloaded. Each model loads on its first use and then stays resident.

Prove the setup before a demo:

```sh
uv run finquery-check    # both slots: answer, thinking, tool call, vision
```

See `docs/adr/0006-local-gemma-4-through-llama-cpp.md`, including why the context cap is 16k
and not 32k on a 24 GB Mac.

## Develop

```sh
uv run finquery --dev           # API only on :8000 with auto reload
cd frontend && npm run dev      # Vite on :5173, proxies /api to :8000
```

Type-check the frontend with `npx tsc -b` in `frontend/`. AI Elements components live in
`frontend/src/components/ai-elements` and are added with
`npx shadcn@latest add https://elements.ai-sdk.dev/api/registry/<name>.json`.

## Test

```sh
uv run pytest
```

Tests drive the FastAPI app over HTTP with both model slots replaced by scripted models. No test
calls OpenRouter and none loads a real model. See `docs/adr/0003-single-http-test-seam.md`.

One suite is opt-in because it does load the real local models:

```sh
FINQUERY_PROVIDER=local FINQUERY_SMOKE=1 uv run pytest tests/test_local_smoke.py -s
```

## Data

Import a bank CSV export on `/import`: drop the file, check the mapping, commit. Sparkasse, DKB,
ING, N26, comdirect and Trade Republic are recognized by their headers; any other bank gets a
mapping proposed by the fast slot and edited in the preview.

The commit is followed by categorization in stages: your own category rules, a dictionary
of about sixty German merchants, then, if you switched web lookup on, a web lookup of the
merchants nobody recognizes, and finally the categorizer sub-agent on the fast slot with a
confidence per merchant. Every row gets a friendly title and a short description. What stays
below the confidence threshold is Needs review, and the page hands those merchants to a new
conversation that asks about them in Question cards. Each answer becomes a category rule and
recategorizes every booking of that merchant, and telling the assistant "PayPal to Anna is
always Dining" in chat does the same.

A CSV can also go straight into the chat: drop it on the composer, send it, and the assistant
runs the same pipeline as a tool call, with the rows read, imported and categorized ticking past
in the tool step and the uncertain merchants asked about right there. An unknown bank layout is
confirmed on a Question card first. PDFs and photos are accepted and stored, but reading them
lands in ticket 11. Typing "I paid 12 EUR cash for lunch today" or pasting a few statement lines
gives a preview card to confirm, and confirming writes the booking and categorizes it.

Then ask in the chat. The query sub-agent writes the SQL on the fast slot, a guard admits only a
single read-only SELECT over your own transactions, and the tool step in the transcript shows the
statement and the rows behind every number.

Ask for a chart and the chart sub-agent plans it, gets its rows the same way, writes a TanStack
Charts definition in plain JavaScript and checks it in-process before it is drawn in a sandboxed
frame. The plan and any repairs show up in the thinking panel; the card carries the SQL and the
rows behind the drawing. The contract is `docs/chart-runtime.md`.

`fixtures/synthetic/` holds the shipped demo dataset, one canonical year of a German household
as a Sparkasse CSV, a renamed-header CSV, a text PDF statement and four bill images. Regenerate
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
  `changesets.py` and `edits.py` (proposed changes and the rules about what may be written),
  `categorize/` (rules, merchant dictionary, categorizer sub-agent, review queue),
  `weblookup/` (the merchant token scrubber, the keyless search client, the self-directed
  lookup loop, the outbound log and the lookup cache),
  `ask_user.py` (the Question card tool), `followups.py` (post-turn suggestions),
  `memory.py` (durable facts: the `remember` tool, the distillation pass, prompt selection),
  `context.py` (token budget, per-turn prompt assembly, rolling summary),
  `attachments.py` (files dropped into a chat), `progress.py` (a tool's live progress part),
  `ingest/` (CSV reader, presets, mapping sub-agent, commit, the chat import and typed
  transactions),
  `api/` (REST and chat endpoints),
  `local/` (the local provider: catalog, downloads, runtime, model, Gemma wire format, check)
- `frontend/`: Vite, React 19, Tailwind 4, shadcn, AI Elements, TanStack Router, Query and
  Charts. `src/chart-runtime/` is a second page: the sandboxed frame charts render in
- `tests/`: HTTP-seam tests
- `fixtures/synthetic/`: shipped demo dataset. `scripts/`: its generator, and
  `measure_categorization.py`, which imports a CSV into a running app and prints what each
  categorization stage placed
- `CONTEXT.md`: domain glossary. `docs/adr/`: architecture decisions.
  `docs/chart-runtime.md`: the contract generated chart code is written against
- `.scratch/finquery/`: spec and tickets
