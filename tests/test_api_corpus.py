from __future__ import annotations

import sqlite3
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pneutext.api.app import create_app
from pneutext.store import db
from pneutext.store.library import Library
from tests.helpers import BOOK

IMPORT = {"folder": str(BOOK), "work_code": "fx", "title": "The Fixture Book", "author": "Nobody"}


@pytest.fixture
def version_id(client: TestClient) -> int:
    response = client.post("/api/imports/corpus", json=IMPORT)
    assert response.status_code == 201, response.text
    return response.json()["version_id"]


def page_text(client: TestClient, version_id: int, page: int) -> dict[str, Any]:
    response = client.get(f"/api/versions/{version_id}/pages/{page}/text")
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_summarizes_without_writing(client: TestClient) -> None:
    response = client.post("/api/imports/corpus/preview", json=IMPORT)
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == {
        "pages": 6,
        "lines": 69,
        "paragraphs": 11,
        "chapters": 2,
        "first_page": 7,
        "last_page": 12,
    }
    assert body["problems"] == []
    assert body["existing_version_id"] is None
    assert client.get("/api/versions").json() == []


def test_import_creates_a_version_listed_with_its_page_range(
    client: TestClient, version_id: int
) -> None:
    (version,) = client.get("/api/versions").json()
    assert version["id"] == version_id
    assert version["work"] == {"code": "fx", "title": "The Fixture Book", "author": "Nobody"}
    assert (version["first_page"], version["last_page"], version["page_count"]) == (7, 12, 6)
    assert version["edit_seq"] == 0


def test_version_detail_lists_chapters_with_their_opening_pages(
    client: TestClient, version_id: int
) -> None:
    detail = client.get(f"/api/versions/{version_id}").json()
    assert [(d["kind"], d["label"], d["page"]) for d in detail["divisions"]] == [
        ("chapter", "I", 7),
        ("chapter", "II", 10),
    ]
    assert detail["measure"] == 56
    assert detail["pages"] == [7, 8, 9, 10, 11, 12]


def test_a_chapter_opening_page_has_furniture_synopsis_and_text(
    client: TestClient, version_id: int
) -> None:
    page = page_text(client, version_id, 7)
    assert (page["prev_page"], page["next_page"]) == (None, 8)
    assert page["division"]["label"] == "I"
    kinds = [line["kind"] for line in page["lines"]]
    assert kinds[:5] == ["chapter_number", "rule", "synopsis", "synopsis", "rule"]
    assert set(kinds[5:]) == {"paragraph"}
    assert [line["line_no"] for line in page["lines"]] == [None, None, 1, 2, None, *range(3, 14)]
    first_text = page["lines"][5]
    assert first_text["text"].startswith("The ferry came into Low Harbor")
    assert first_text["starts_paragraph"] is True
    assert first_text["ends_paragraph"] is False
    assert page["lines"][0]["text"] == "I"


def test_lines_carry_their_exact_words_and_lengths(client: TestClient, version_id: int) -> None:
    for number in range(7, 13):
        source = [
            line.strip()
            for line in (BOOK / f"FX_corp_p{number:03d}.txt").read_text("utf-8").splitlines()
            if line.strip() and not line.startswith("<<")
        ]
        lines = [line for line in page_text(client, version_id, number)["lines"] if line["line_no"]]
        assert [line["text"] for line in lines] == source
        assert [line["length"] for line in lines] == [len(text) for text in source]
        assert [line["line_no"] for line in lines] == list(range(1, len(source) + 1))


def test_a_paragraph_crossing_a_page_is_one_segment(client: TestClient, version_id: int) -> None:
    last_of_10 = page_text(client, version_id, 10)["lines"][-1]
    first_of_11 = page_text(client, version_id, 11)["lines"][0]
    assert last_of_10["segment_id"] == first_of_11["segment_id"]
    assert last_of_10["ends_paragraph"] is False
    assert first_of_11["starts_paragraph"] is False
    assert first_of_11["start_offset"] == last_of_10["start_offset"] + last_of_10["length"] + 1


def test_a_paragraph_ending_at_a_page_end_is_closed(client: TestClient, version_id: int) -> None:
    assert page_text(client, version_id, 7)["lines"][-1]["ends_paragraph"] is True
    assert page_text(client, version_id, 8)["lines"][0]["starts_paragraph"] is True


def test_last_page_has_no_next_and_keeps_its_chapter(client: TestClient, version_id: int) -> None:
    page = page_text(client, version_id, 12)
    assert (page["prev_page"], page["next_page"]) == (11, None)
    assert page["division"]["label"] == "II"


def test_missing_pages_and_versions_are_explained(client: TestClient, version_id: int) -> None:
    response = client.get(f"/api/versions/{version_id}/pages/99/text")
    assert (response.status_code, response.json()) == (404, {"detail": "This text has no page 99."})
    assert client.get("/api/versions/999").status_code == 404


def test_importing_the_same_files_twice_warns_and_needs_confirmation(
    client: TestClient, version_id: int
) -> None:
    preview = client.post("/api/imports/corpus/preview", json=IMPORT).json()
    assert preview["existing_version_id"] == version_id
    refused = client.post("/api/imports/corpus", json=IMPORT)
    assert refused.status_code == 409
    assert "already been imported" in refused.json()["detail"]
    confirmed = client.post("/api/imports/corpus", json={**IMPORT, "allow_duplicate": True})
    assert confirmed.status_code == 201
    assert len(client.get("/api/versions").json()) == 2


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"folder": "/no/such/folder"}, "no folder"),
        ({"folder": " "}, "Give the folder"),
        ({"work_code": "Not A Code"}, "work code"),
        ({"title": ""}, "title"),
        ({"file_pattern": "("}, "not a valid expression"),
    ],
)
def test_bad_import_requests_are_explained(
    client: TestClient, change: dict[str, str], expected: str
) -> None:
    response = client.post("/api/imports/corpus/preview", json={**IMPORT, **change})
    assert response.status_code == 400
    assert expected in response.json()["detail"]


def test_a_failed_import_leaves_nothing_behind(
    client: TestClient, library: Library, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pneutext.store import corpus as corpus_store

    real_insert = corpus_store.insert_segment
    calls = 0

    def fail_on_the_third_segment(
        conn: sqlite3.Connection, version_id: int, position: int, kind: str, text: str
    ) -> int:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("simulated failure part-way through")
        return real_insert(conn, version_id, position, kind, text)

    monkeypatch.setattr(corpus_store, "insert_segment", fail_on_the_third_segment)
    with pytest.raises(RuntimeError):
        client.post("/api/imports/corpus", json=IMPORT)
    assert calls == 3
    with db.transaction(library.db_path) as conn:
        for table in ("work", "version", "pagination", "segment", "line", "division"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_segment_positions_are_sparse(
    client: TestClient, version_id: int, library: Library
) -> None:
    with db.transaction(library.db_path) as conn:
        positions = [r[0] for r in conn.execute("SELECT position FROM segment ORDER BY position")]
    assert positions == [1000 * n for n in range(1, len(positions) + 1)]


def test_requests_naming_another_host_are_refused(library: Library) -> None:
    with TestClient(create_app(library, web_dist=None), base_url="http://evil.example") as other:
        assert other.get("/api/library").status_code == 400
