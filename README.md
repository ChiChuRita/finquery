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

See `docs/adr/0005-local-gemma-4-through-llama-cpp.md`, including why the context cap is 16k
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

`fixtures/synthetic/` holds the shipped demo dataset, one canonical year of a German household
as a Sparkasse CSV, a renamed-header CSV, a text PDF statement and four bill images. Regenerate
it with `uv run python scripts/generate_synthetic.py`.

## Layout

- `src/finquery/`: `main.py` (CLI), `app.py` (factory), `settings.py`, `providers.py` (slots),
  `db.py` (SQLAlchemy models and the query view), `taxonomy.py` (default categories),
  `agent.py` (chat agent), `ingest/` (CSV reader, presets, mapping sub-agent, commit),
  `api/` (REST and chat endpoints),
  `local/` (the local provider: catalog, downloads, runtime, model, Gemma wire format, check)
- `frontend/`: Vite, React 19, Tailwind 4, shadcn, AI Elements, TanStack Router and Query
- `tests/`: HTTP-seam tests
- `fixtures/synthetic/`: shipped demo dataset. `scripts/`: its generator
- `CONTEXT.md`: domain glossary. `docs/adr/`: architecture decisions
- `.scratch/finquery/`: spec and tickets
