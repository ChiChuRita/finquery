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

| Variable             | Default            | Meaning                                        |
| -------------------- | ------------------ | ---------------------------------------------- |
| `FINQUERY_PROVIDER`  | `openrouter`       | `openrouter` or `local` (local: ticket 16)     |
| `OPENROUTER_API_KEY` |                    | Required for `openrouter`                      |
| `FINQUERY_DB_PATH`   | `data/finquery.db` | SQLite file                                    |
| `FINQUERY_HOST`      | `127.0.0.1`        | Bind address                                   |
| `FINQUERY_PORT`      | `8000`             | Port                                           |

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
calls OpenRouter. See `docs/adr/0003-single-http-test-seam.md`.

## Data

Import a bank CSV export on `/import`: drop the file, check the mapping, commit. Sparkasse, DKB,
ING, N26, comdirect and Trade Republic are recognized by their headers; any other bank gets a
mapping proposed by the fast slot and edited in the preview.

Then ask in the chat. The query sub-agent writes the SQL on the fast slot, a guard admits only a
single read-only SELECT over your own transactions, and the tool step in the transcript shows the
statement and the rows behind every number.

`fixtures/synthetic/` holds the shipped demo dataset, one canonical year of a German household
as a Sparkasse CSV, a renamed-header CSV, a text PDF statement and four bill images. Regenerate
it with `uv run python scripts/generate_synthetic.py`.

## Layout

- `src/finquery/`: `main.py` (CLI), `app.py` (factory), `settings.py`, `providers.py` (slots),
  `db.py` (SQLAlchemy models and the query view), `taxonomy.py` (default categories),
  `agent.py` (chat agent and its tools), `query/` (query sub-agent, SQL guard, execution),
  `ingest/` (CSV reader, presets, mapping sub-agent, commit), `api/` (REST and chat endpoints)
- `frontend/`: Vite, React 19, Tailwind 4, shadcn, AI Elements, TanStack Router and Query
- `tests/`: HTTP-seam tests
- `fixtures/synthetic/`: shipped demo dataset. `scripts/`: its generator
- `CONTEXT.md`: domain glossary. `docs/adr/`: architecture decisions
- `.scratch/finquery/`: spec and tickets
