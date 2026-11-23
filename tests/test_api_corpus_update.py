from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.helpers import BOOK
from tests.test_api_corpus import page_text
from tests.test_api_notes import create, page_notes, span_of


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A private copy of the fixture book's page files, free to be corrected."""
    target = tmp_path / "pages"
    target.mkdir()
    for source in BOOK.glob("FX_corp_p*.txt"):
        shutil.copy(source, target / source.name)
    return target


@pytest.fixture
def version_id(client: TestClient, folder: Path) -> int:
    body = {"folder": str(folder), "work_code": "fx", "title": "The Fixture Book"}
    response = client.post("/api/imports/corpus", json=body)
    assert response.status_code == 201, response.text
    return response.json()["version_id"]


@pytest.fixture
def types(client: TestClient) -> dict[str, int]:
    return {t["name"]: t["id"] for t in client.get("/api/note-types").json()}


def correct(folder: Path, page: int, old: str, new: str) -> None:
    path = folder / f"FX_corp_p{page:03d}.txt"
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1
    path.write_text(text.replace(old, new), encoding="utf-8")


def update(
    client: TestClient, version_id: int, folder: Path, preview: bool = False
) -> dict[str, Any]:
    url = f"/api/versions/{version_id}/update" + ("/preview" if preview else "")
    response = client.post(url, json={"folder": str(folder)})
    assert response.status_code == 200, response.text
    return response.json()


def words(client: TestClient, version_id: int, page: int) -> str:
    return " ".join(line["text"] for line in page_text(client, version_id, page)["lines"])


def test_unchanged_files_are_up_to_date(client: TestClient, version_id: int, folder: Path) -> None:
    before = client.get(f"/api/versions/{version_id}").json()["edit_seq"]
    report = update(client, version_id, folder)
    assert report["up_to_date"] is True
    assert report["changed_pages"] == [] and report["new_pages"] == []
    assert client.get(f"/api/versions/{version_id}").json()["edit_seq"] == before


def test_preview_reports_and_writes_nothing(
    client: TestClient, version_id: int, folder: Path
) -> None:
    correct(folder, 8, "single heron", "lone heron")
    report = update(client, version_id, folder, preview=True)
    assert report["up_to_date"] is False
    assert report["changed_pages"] == [8]
    assert report["changed_paragraphs"] == 1
    assert "single heron" in words(client, version_id, 8)


def test_search_follows_the_corrected_text(
    client: TestClient, version_id: int, folder: Path
) -> None:
    correct(folder, 8, "single heron", "single bittern")
    update(client, version_id, folder)

    def pages(term: str) -> list[int]:
        found = client.get(
            f"/api/versions/{version_id}/search", params={"q": term, "corpus": "true"}
        ).json()
        return [hit["page"] for hit in found["corpus"]]

    assert pages("bittern") == [8]
    assert 8 not in pages("heron")


def test_pages_added_at_the_end_are_taken_in(
    client: TestClient, version_id: int, folder: Path
) -> None:
    (folder / "FX_corp_p013.txt").write_text(
        "\nThe next sheet took her a week, and she did not\nhurry it.\n", encoding="utf-8"
    )
    report = update(client, version_id, folder)
    assert report["new_pages"] == [13]
    assert report["new_paragraphs"] == 1
    assert report["changed_pages"] == []
    assert "did not hurry it." in words(client, version_id, 13)
    assert client.get(f"/api/versions/{version_id}").json()["last_page"] == 13


def test_added_or_missing_paragraphs_are_refused_without_quoting_the_text(
    client: TestClient, version_id: int, folder: Path
) -> None:
    correct(folder, 8, "patient as a fence post. By\n", "patient as a fence post.\n\nBy\n")
    response = client.post(f"/api/versions/{version_id}/update", json={"folder": str(folder)})
    assert response.status_code == 409
    message = response.json()["detail"]
    assert "page 8" in message
    assert "heron" not in message and "fence" not in message
    assert "single heron" in words(client, version_id, 8)


def test_a_folder_with_pages_missing_is_refused(
    client: TestClient, version_id: int, folder: Path
) -> None:
    (folder / "FX_corp_p012.txt").unlink()
    response = client.post(f"/api/versions/{version_id}/update", json={"folder": str(folder)})
    assert response.status_code == 409


def test_an_updated_text_no_longer_counts_as_already_imported_under_its_old_files(
    client: TestClient, version_id: int, folder: Path
) -> None:
    correct(folder, 8, "single heron", "lone heron")
    update(client, version_id, folder)
    preview = client.post(
        "/api/imports/corpus/preview",
        json={"folder": str(folder), "work_code": "fx", "title": "The Fixture Book"},
    ).json()
    assert preview["existing_version_id"] == version_id
    assert update(client, version_id, folder)["up_to_date"] is True


def test_a_split_paragraph_is_refused_even_when_the_kinds_still_line_up(
    client: TestClient, version_id: int, folder: Path
) -> None:
    # The last page has only paragraphs after it, so nothing but the count gives it away.
    correct(folder, 12, "station forty-seven. It was", "station forty-seven.\n\nIt was")
    response = client.post(f"/api/versions/{version_id}/update", json={"folder": str(folder)})
    assert response.status_code == 409
    assert "page 12" in response.json()["detail"]


def test_wholly_different_files_are_refused(
    client: TestClient, version_id: int, folder: Path
) -> None:
    path = folder / "FX_corp_p012.txt"
    lines = path.read_text(encoding="utf-8").splitlines()
    filler = "Nothing in this line was here before, not one word of it."
    path.write_text("\n".join(filler if line else line for line in lines) + "\n", encoding="utf-8")
    response = client.post(f"/api/versions/{version_id}/update", json={"folder": str(folder)})
    assert response.status_code == 409
    assert "page 12" in response.json()["detail"]


def test_a_correction_changes_the_page(client: TestClient, version_id: int, folder: Path) -> None:
    correct(folder, 8, "single heron", "solitary gray heron")
    report = update(client, version_id, folder)
    assert (report["changed_pages"], report["changed_paragraphs"]) == ([8], 1)
    assert "solitary gray heron" in words(client, version_id, 8)
    assert "single" not in words(client, version_id, 8)


def test_a_passage_can_be_marked_on_the_corrected_text(
    client: TestClient, version_id: int, folder: Path, types: dict[str, int]
) -> None:
    correct(folder, 8, "single heron", "solitary gray heron")
    update(client, version_id, folder)
    span = span_of(client, version_id, "solitary gray heron", 8)
    note = create(client, version_id, type_id=types["Comment"], span=span)
    assert [n["id"] for n in page_notes(client, version_id, 8)] == [note["id"]]


def test_moving_a_line_break_changes_the_lines_and_not_the_words(
    client: TestClient, version_id: int, folder: Path
) -> None:
    before = words(client, version_id, 8)
    correct(folder, 8, "a\nsingle heron", "a single\nheron")
    report = update(client, version_id, folder)
    assert (report["changed_pages"], report["changed_paragraphs"]) == ([8], 0)
    assert words(client, version_id, 8) == before
    starts = [line["text"].split()[0] for line in page_text(client, version_id, 8)["lines"]]
    assert "heron" in starts and "single" not in starts


def test_text_continuing_the_last_paragraph_onto_a_new_page_is_taken_in(
    client: TestClient, version_id: int, folder: Path
) -> None:
    (folder / "FX_corp_p013.txt").write_text("She did not hurry it.\n", encoding="utf-8")
    report = update(client, version_id, folder)
    assert (report["new_pages"], report["changed_pages"]) == ([13], [])
    assert report["new_paragraphs"] == 0
    assert words(client, version_id, 13) == "She did not hurry it."


def test_a_text_with_a_note_can_no_longer_be_updated(
    client: TestClient, version_id: int, folder: Path, types: dict[str, int]
) -> None:
    span = span_of(client, version_id, "Tomás", 8)
    note = create(client, version_id, type_id=types["Comment"], span=span)
    correct(folder, 8, "single heron", "lone heron")
    for step in ("update/preview", "update"):
        response = client.post(f"/api/versions/{version_id}/{step}", json={"folder": str(folder)})
        assert response.status_code == 409
        assert "1 marked passage " in response.json()["detail"]
    assert "single heron" in words(client, version_id, 8)

    # With the note gone the text is free to be updated again.
    assert client.delete(f"/api/notes/{note['id']}").status_code == 204
    assert update(client, version_id, folder)["changed_pages"] == [8]


def test_imported_commentary_also_closes_the_text_to_updates(
    client: TestClient, version_id: int, folder: Path
) -> None:
    imported = client.post(
        f"/api/versions/{version_id}/imports/commentary",
        json={"folder": str(BOOK), "page_ref_commands": ["pref"]},
    )
    assert imported.status_code == 201, imported.text
    response = client.post(f"/api/versions/{version_id}/update", json={"folder": str(folder)})
    assert response.status_code == 409
    assert "marked passages" in response.json()["detail"]
