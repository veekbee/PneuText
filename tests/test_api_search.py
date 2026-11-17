from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from pneutext.services.search import fold, match_query
from pneutext.store import db
from pneutext.store.library import Library
from pneutext.store.segments import insert_segment
from tests.helpers import BOOK
from tests.test_api_corpus import IMPORT
from tests.test_api_notes import create, span_of


@pytest.fixture
def version_id(client: TestClient) -> int:
    return client.post("/api/imports/corpus", json=IMPORT).json()["version_id"]


def search(client: TestClient, version_id: int, q: str, corpus: bool = True) -> dict[str, Any]:
    response = client.get(
        f"/api/versions/{version_id}/search", params={"q": q, "corpus": str(corpus).lower()}
    )
    assert response.status_code == 200, response.text
    return response.json()


def places(hits: list[dict[str, Any]]) -> list[tuple[int, int | None, str]]:
    return [(hit["page"], hit["line_no"], hit["match"]) for hit in hits]


def test_folding_removes_case_and_accents_and_keeps_positions() -> None:
    folded, index = fold("Señora É")
    assert folded == "senora e"
    assert index == [0, 1, 2, 3, 4, 5, 6, 7]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("heron", '"heron"*'),
        ("low harb", '"low" AND "harb"*'),
        ('"low harbor"', '"low harbor"'),
        ("  ", None),
        ('he said "x"', '"he" AND "said" AND "x"*'),
        ("o'clock (noon)", '"o" AND "clock" AND "noon"*'),
    ],
)
def test_queries_are_made_safe_for_the_index(query: str, expected: str | None) -> None:
    assert match_query(query) == expected


def test_free_text_finds_each_place_in_the_corpus(client: TestClient, version_id: int) -> None:
    found = search(client, version_id, "heron")
    # In a paragraph, in a chapter synopsis, and at the top of a page.
    assert places(found["corpus"]) == [(8, 3, "heron"), (10, 2, "heron"), (12, 1, "heron")]
    first = found["corpus"][0]
    assert first["before"] + first["match"] + first["after"] == (
        "single heron stood in them, patient as a fence post. By"
    )
    assert found["reference"] is None and found["notes"] == []


def test_search_ignores_case_and_accents_and_completes_the_last_word(
    client: TestClient, version_id: int
) -> None:
    assert places(search(client, version_id, "SENORA")["corpus"]) == [(8, 10, "señora")]
    assert places(search(client, version_id, "tomas")["corpus"]) == [
        (8, 8, "Tomás"),
        (10, 4, "Tomás"),
    ]
    assert places(search(client, version_id, "harbor")["corpus"])[0] == (7, 1, "Harbor")
    assert places(search(client, version_id, "theod")["corpus"]) == [(7, 6, "theodolite")]


def test_every_word_must_be_in_the_paragraph_and_quotes_ask_for_a_phrase(
    client: TestClient, version_id: int
) -> None:
    both = search(client, version_id, "heron marsh")["corpus"]
    assert places(both) == [(8, 3, "heron")]  # the only paragraph holding both words
    assert places(search(client, version_id, '"biscuit tin"')["corpus"]) == [
        (7, 9, "biscuit tin"),
        (10, 10, "biscuit tin"),
    ]
    assert search(client, version_id, '"tin biscuit"')["corpus"] == []
    assert search(client, version_id, "xylophone")["corpus"] == []


def test_a_page_reference_is_recognized(client: TestClient, version_id: int) -> None:
    assert search(client, version_id, "10")["reference"] == {"page": 10, "line_no": None}
    assert search(client, version_id, "8.3")["reference"] == {"page": 8, "line_no": 3}
    assert search(client, version_id, "p. 12")["reference"] == {"page": 12, "line_no": None}
    assert search(client, version_id, "fx:9.2")["reference"] == {"page": 9, "line_no": 2}
    assert search(client, version_id, "10-11")["reference"] == {"page": 10, "line_no": None}
    # A place that does not exist is not offered.
    assert search(client, version_id, "99")["reference"] is None
    assert search(client, version_id, "8.40")["reference"] is None
    assert search(client, version_id, "heron")["reference"] is None


def test_notes_are_searched_separately(client: TestClient, version_id: int) -> None:
    types = {t["name"]: t["id"] for t in client.get("/api/note-types").json()}
    note = create(
        client,
        version_id,
        type_id=types["Literary"],
        level=2,
        span=span_of(client, version_id, "single heron", 8),
        body_md="A **patient** bird; compare the *theodolite* of the first page.",
    )
    found = search(client, version_id, "patient")
    assert found["notes"] == [
        {
            "note_id": note["id"],
            "type_id": types["Literary"],
            "level": 2,
            "status": "draft",
            "page": 8,
            "line_no": 3,
            "excerpt": "A **patient** bird; compare the *theodolite* of the first page.",
        }
    ]
    assert places(found["corpus"]) == [(8, 3, "patient")]  # the corpus has the word too
    # A word only the note uses finds the note and nothing in the text.
    only = search(client, version_id, "bird")
    assert [hit["note_id"] for hit in only["notes"]] == [note["id"]]
    assert only["corpus"] == []
    # Search follows edits to the note.
    client.patch(f"/api/notes/{note['id']}", json={"body_md": "Rewritten."})
    assert search(client, version_id, "bird")["notes"] == []
    assert [hit["note_id"] for hit in search(client, version_id, "rewritten")["notes"]] == [
        note["id"]
    ]
    client.delete(f"/api/notes/{note['id']}")
    assert search(client, version_id, "rewritten")["notes"] == []


def test_blank_mode_searches_notes_only_and_gets_no_corpus_text(
    client: TestClient, version_id: int
) -> None:
    found = search(client, version_id, "heron", corpus=False)
    assert found["corpus"] is None
    assert found == {"query": "heron", "reference": None, "corpus": None, "notes": []}
    # It is the default: the text is searched only when asked for.
    response = client.get(f"/api/versions/{version_id}/search", params={"q": "heron"})
    assert response.json()["corpus"] is None
    assert "stood in them" not in response.text


def test_search_stays_within_one_text(client: TestClient, version_id: int) -> None:
    other = client.post("/api/imports/corpus", json={**IMPORT, "allow_duplicate": True}).json()
    assert len(search(client, version_id, "heron")["corpus"]) == 3
    assert len(search(client, other["version_id"], "heron")["corpus"]) == 3
    assert client.get("/api/versions/999/search", params={"q": "heron"}).status_code == 404


def test_the_corpus_index_follows_the_text_by_itself(
    client: TestClient, version_id: int, library: Library
) -> None:
    """Triggers on `segment`, not import code, keep search in step with the text."""
    with db.transaction(library.db_path) as conn:
        segment_id = insert_segment(conn, version_id, 999_000, "paragraph", "A zeppelin passed.")
        pagination = conn.execute(
            "SELECT id FROM pagination WHERE version_id = ?", (version_id,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO line (pagination_id, segment_id, start_offset, page, line_no)"
            " VALUES (?, ?, 0, 13, 1)",
            (pagination, segment_id),
        )
    assert places(search(client, version_id, "zeppelin")["corpus"]) == [(13, 1, "zeppelin")]
    with db.transaction(library.db_path) as conn:
        conn.execute("UPDATE segment SET text = 'A dirigible passed.' WHERE id = ?", (segment_id,))
    assert search(client, version_id, "zeppelin")["corpus"] == []
    assert places(search(client, version_id, "dirigible")["corpus"]) == [(13, 1, "dirigible")]
    with db.transaction(library.db_path) as conn:
        conn.execute("DELETE FROM segment WHERE id = ?", (segment_id,))
    assert search(client, version_id, "dirigible")["corpus"] == []


def test_figures_are_listed_and_their_images_served(
    client: TestClient, version_id: int, library: Library
) -> None:
    client.post(
        f"/api/versions/{version_id}/imports/commentary",
        json={"folder": str(BOOK), "page_ref_commands": ["pref"]},
    )
    listed = client.get("/api/figures").json()
    assert [(f["label"], f["file"], f["caption"], f["has_file"]) for f in listed] == [
        ("chain", "chain.png", "A survey chain", False),
        ("harbor", "harbor.png", "The harbor at low water", True),
    ]
    image = client.get("/api/figures/harbor/file")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content == (BOOK / "harbor.png").read_bytes()
    assert client.get("/api/figures/chain/file").status_code == 404
    assert client.get("/api/figures/nothing/file").status_code == 404


def test_a_figure_cannot_point_outside_the_figures_folder(
    client: TestClient, library: Library
) -> None:
    (library.root / "secret.txt").write_text("outside the figures folder", "utf-8")
    with db.transaction(library.db_path) as conn:
        conn.execute("INSERT INTO figure (label, file) VALUES ('escape', '../secret.txt')")
    assert client.get("/api/figures/escape/file").status_code == 404
    assert client.get("/api/figures").json()[0]["has_file"] is False
