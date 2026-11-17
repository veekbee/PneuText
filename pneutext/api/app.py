"""The FastAPI application: the JSON API under /api, and the built front end beside it."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import pneutext
from pneutext.api.routes import router
from pneutext.store.library import Library

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


def create_app(library: Library, web_dist: Path | None = WEB_DIST) -> FastAPI:
    app = FastAPI(
        title="PneuText",
        version=pneutext.__version__,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.library = library
    app.include_router(router)
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
