from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pneutext.api.app import create_app
from pneutext.store.library import Library, open_library

BASE_URL = "http://127.0.0.1"


@pytest.fixture
def library(tmp_path: Path) -> Library:
    return open_library(tmp_path / "library")


@pytest.fixture
def client(library: Library) -> Iterator[TestClient]:
    with TestClient(create_app(library, web_dist=None), base_url=BASE_URL) as test_client:
        yield test_client
