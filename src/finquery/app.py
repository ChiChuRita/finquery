"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from finquery.api import (
    attachments,
    changesets,
    charts,
    chat,
    conversations,
    imports,
    memories,
    onboarding,
    preferences,
    profiles,
    taxonomy,
    transactions,
)
from finquery.api import models as models_api
from finquery.api import settings as settings_api
from finquery.changesets import ChangesetError, ChangesetStale
from finquery.context import context_budget
from finquery.db import SplitSumError, ensure_default_profile, make_session_factory
from finquery.edits import TransactionEditError
from finquery.providers import MODEL_SLOTS, ModelResolver, build_local_stack, build_resolver, subagent_settings
from finquery.settings import Settings
from finquery.weblookup import HttpWebClient, WebClient

if TYPE_CHECKING:
    from finquery.local.runtime import LocalStack

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(
    settings: Settings,
    *,
    resolve_model: ModelResolver | None = None,
    local: "LocalStack | None" = None,
    web_client: WebClient | None = None,
    serve_frontend: bool = True,
) -> FastAPI:
    """Build the app.

    Tests pass `resolve_model` to replace both slots with scripted models, `local` to replace
    the local provider's downloader and loaded models with stubs, and `web_client` to replace
    the search and page fetch of the web lookup, which is the only thing here that would
    otherwise leave the machine.
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
        app.state.context_budget = context_budget(settings, app.state.local)
        # Nothing calls it until a profile switches web lookup on. See finquery.weblookup.
        app.state.web_client = web_client if web_client is not None else HttpWebClient()
        app.state.running_turns = {}
        yield

    app = FastAPI(title="FinQuery", lifespan=lifespan)

    @app.middleware("http")
    async def allow_sandboxed_assets(request, call_next):  # type: ignore[no-untyped-def]
        """Let the chart runtime frame load its bundle.

        Charts render inside `sandbox="allow-scripts"`, so that document has an opaque origin
        and its `crossorigin` module script becomes a CORS request. The built assets are public
        static files with no credentials, so the header costs nothing.
        """
        response = await call_next(request)
        if request.url.path.startswith("/assets/"):
            response.headers["access-control-allow-origin"] = "*"
        return response

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {"provider": settings.provider, "slots": list(MODEL_SLOTS)}

    # A refused write is a validation error the UI shows where it happened, not a 500. One
    # handler for both, so no endpoint has to catch what the data model says no to.
    async def refused(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    # A changeset whose rows moved under it is a conflict, not a bad request: the client can
    # ask for a fresh proposal and try again.
    async def conflicted(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    app.add_exception_handler(TransactionEditError, refused)
    app.add_exception_handler(SplitSumError, refused)
    app.add_exception_handler(ChangesetError, refused)
    app.add_exception_handler(ChangesetStale, conflicted)

    app.include_router(profiles.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(memories.router, prefix="/api")
    app.include_router(imports.router, prefix="/api")
    app.include_router(attachments.router, prefix="/api")
    app.include_router(transactions.router, prefix="/api")
    app.include_router(taxonomy.router, prefix="/api")
    app.include_router(changesets.router, prefix="/api")
    app.include_router(preferences.router, prefix="/api")
    app.include_router(charts.router, prefix="/api")
    app.include_router(models_api.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")
    app.include_router(onboarding.router, prefix="/api")

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
