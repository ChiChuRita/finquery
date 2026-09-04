"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from finquery.api import chat, conversations, imports, memories, profiles, taxonomy, transactions
from finquery.api import models as models_api
from finquery.db import ensure_default_profile, make_session_factory
from finquery.providers import MODEL_SLOTS, ModelResolver, build_local_stack, build_resolver, subagent_settings
from finquery.settings import Settings

if TYPE_CHECKING:
    from finquery.local.runtime import LocalStack

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(
    settings: Settings,
    *,
    resolve_model: ModelResolver | None = None,
    local: "LocalStack | None" = None,
    serve_frontend: bool = True,
) -> FastAPI:
    """Build the app.

    Tests pass `resolve_model` to replace both slots with scripted models, and `local` to
    replace the local provider's downloader and loaded models with stubs.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.session_factory = make_session_factory(settings.db_path)
        with app.state.session_factory() as session:
            ensure_default_profile(session)
        app.state.local = local if local is not None else (build_local_stack(settings) if settings.provider == "local" else None)
        app.state.resolve_model = resolve_model or build_resolver(settings, local=app.state.local)
        app.state.subagent_settings = subagent_settings(settings)
        app.state.running_turns = {}
        yield

    app = FastAPI(title="FinQuery", lifespan=lifespan)

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {"provider": settings.provider, "slots": list(MODEL_SLOTS)}

    app.include_router(profiles.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(memories.router, prefix="/api")
    app.include_router(imports.router, prefix="/api")
    app.include_router(transactions.router, prefix="/api")
    app.include_router(taxonomy.router, prefix="/api")
    app.include_router(models_api.router, prefix="/api")

    if serve_frontend and FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str) -> FileResponse:
            candidate = (FRONTEND_DIST / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(FRONTEND_DIST):
                return FileResponse(candidate)
            return FileResponse(FRONTEND_DIST / "index.html")

    elif serve_frontend:

        @app.get("/{path:path}", include_in_schema=False)
        async def missing_frontend(path: str) -> JSONResponse:
            return JSONResponse(
                {"detail": "Frontend not built. Run `npm run build` in frontend/ or start `uv run finquery --dev`."},
                status_code=503,
            )

    return app
