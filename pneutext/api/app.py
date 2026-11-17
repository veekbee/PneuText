"""The FastAPI application: the JSON API under /api, and the built front end beside it."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

import pneutext
from pneutext.api.routers import (
    corpus,
    entities,
    export,
    figures,
    legacy,
    library,
    links,
    notes,
    review,
    search,
)
from pneutext.core.errors import PneuTextError
from pneutext.store.library import Library

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"

# Requests must name this machine. A page on another site that points a look-alike host
# name at 127.0.0.1 is refused, so it cannot read the library through the browser.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


def create_app(library_: Library, web_dist: Path | None = WEB_DIST) -> FastAPI:
    app = FastAPI(
        title="PneuText",
        version=pneutext.__version__,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.library = library_
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    @app.exception_handler(PneuTextError)
    def explain(_: Request, error: PneuTextError) -> JSONResponse:
        return JSONResponse(status_code=error.status, content={"detail": error.message})

    app.include_router(library.router)
    app.include_router(corpus.router)
    app.include_router(notes.router)
    app.include_router(legacy.router)
    app.include_router(links.router)
    app.include_router(search.router)
    app.include_router(figures.router)
    app.include_router(entities.router)
    app.include_router(review.router)
    app.include_router(export.router)
    if web_dist is not None:
        _serve_front_end(app, web_dist)
    return app


def _serve_front_end(app: FastAPI, web_dist: Path) -> None:
    """Serve built files, falling back to index.html so page URLs survive a reload."""
    root = web_dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def front_end(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="No such API route.")
        index = root / "index.html"
        if not index.is_file():
            raise HTTPException(
                status_code=503,
                detail="The front end has not been built. Run `npm run build` in frontend/.",
            )
        candidate = (root / path).resolve()
        if path and candidate.is_relative_to(root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)
