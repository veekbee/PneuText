from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import pneutext
from pneutext.api.app import create_app
from pneutext.api.openapi import render_schema
from pneutext.store import db
from pneutext.store.library import Library
from tests.conftest import BASE_URL

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_empty_library_is_described(client: TestClient) -> None:
    response = client.get("/api/library")
    assert response.status_code == 200
    body = response.json()
    assert body["app_version"] == pneutext.__version__
    assert body["schema_version"] == len(db.load_migrations())
    assert body["created_at"].endswith("Z")


def test_openapi_schema_is_served_under_api(client: TestClient) -> None:
    schema = client.get("/api/openapi.json").json()
    assert "/api/library" in schema["paths"]


def test_checked_in_openapi_schema_is_current() -> None:
    """The front end's types are generated from this file; it must match the routes."""
    checked_in = (REPO_ROOT / "frontend" / "src" / "api" / "openapi.json").read_text("utf-8")
    assert checked_in == render_schema(), "Run `npm run gen:api` in frontend/."


def test_front_end_files_and_page_urls_are_served(library: Library, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>index</title>", "utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", "utf-8")
    (tmp_path / "secret.txt").write_text("outside the front end", "utf-8")
    with TestClient(create_app(library, web_dist=dist), base_url=BASE_URL) as client:
        shell = client.get("/")
        assert "index" in shell.text
        # The shell is checked with the server on every visit, so a rebuild shows at once.
        assert shell.headers["cache-control"] == "no-cache"
        assert client.get("/assets/app.js").text == "console.log(1)"
        # A page URL is a client-side route: the server answers with the app shell.
        assert "index" in client.get("/v/1/p/45").text
        # Nothing outside the built folder is reachable.
        assert "outside" not in client.get("/%2e%2e/secret.txt").text
        # Unknown API routes stay JSON 404s and never fall through to the shell.
        missing = client.get("/api/nope")
        assert missing.status_code == 404
        assert missing.headers["content-type"].startswith("application/json")


def test_unbuilt_front_end_is_explained(library: Library, tmp_path: Path) -> None:
    with TestClient(create_app(library, web_dist=tmp_path / "absent"), base_url=BASE_URL) as client:
        response = client.get("/")
        assert response.status_code == 503
        assert "npm run build" in response.json()["detail"]
