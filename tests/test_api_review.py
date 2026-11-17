from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from pneutext.store import db
from pneutext.store.library import Library
from tests.helpers import BOOK
from tests.test_api_corpus import IMPORT
from tests.test_api_notes import create, page_notes, span_of

COMMENTARY = {"folder": str(BOOK), "page_ref_commands": ["pref"]}
PNG = (BOOK / "harbor.png").read_bytes()


@pytest.fixture
def version_id(client: TestClient) -> int:
    """The fixture book with its old commentary imported: sixteen notes, all drafts."""
    version = client.post("/api/imports/corpus", json=IMPORT).json()["version_id"]
    client.post(f"/api/versions/{version}/imports/commentary", json=COMMENTARY)
    return version


@pytest.fixture
def types(client: TestClient) -> dict[str, int]:
    return {t["name"]: t["id"] for t in client.get("/api/note-types").json()}


def notes(client: TestClient, version_id: int, **filters: object) -> list[dict[str, Any]]:
    response = client.get(f"/api/versions/{version_id}/notes", params=filters)
    assert response.status_code == 200, response.text
    return response.json()


def todo(client: TestClient, version_id: int) -> dict[str, Any]:
    response = client.get(f"/api/versions/{version_id}/todo")
    assert response.status_code == 200, response.text
    return response.json()


# ---- Review -----------------------------------------------------------------------


def test_every_note_is_listed_in_reading_order_with_its_place(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    listed = notes(client, version_id)
    assert len(listed) == 16
    assert [(n["page"], n["line_no"]) for n in listed[:5]] == [
        (7, None),
        (7, None),
        (7, None),
        (7, 3),
        (7, 5),
    ]
    first_span = listed[3]
    assert first_span == {
        "id": first_span["id"],
        "type_id": types["Historical"],
        "scope": "span",
        "level": 1,
        "status": "draft",
        "tags": [],
        "page": 7,
        "line_no": 3,
        "excerpt": "Tide tables for the period survive; see {{fx:10}} and {{fx:12}}.",
    }


def test_notes_filter_by_chapter_type_level_status_and_tag(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    chapters = client.get(f"/api/versions/{version_id}").json()["divisions"]
    first = notes(client, version_id, division_id=chapters[0]["id"])
    second = notes(client, version_id, division_id=chapters[1]["id"])
    assert (len(first), len(second)) == (15, 1)
    assert {n["page"] for n in second} == {12}

    historical = notes(client, version_id, type_id=types["Historical"])
    assert [(n["page"], n["line_no"]) for n in historical] == [(7, 3), (8, 9), (9, 3)]
    assert [(n["page"], n["excerpt"][:20]) for n in notes(client, version_id, level=2)] == [
        (7, "The instrument retur"),
        (9, "TODO: Imported from "),
    ]
    assert notes(client, version_id, status="ready") == []
    assert len(notes(client, version_id, status="draft")) == 16

    one = historical[0]["id"]
    client.patch(f"/api/notes/{one}", json={"tags": ["tides", "sources"]})
    assert [n["id"] for n in notes(client, version_id, tag="tides")] == [one]
    assert client.get("/api/tags").json() == ["sources", "tides"]
    # Filters combine.
    both = notes(
        client, version_id, type_id=types["Historical"], division_id=chapters[0]["id"], tag="tides"
    )
    assert [n["id"] for n in both] == [one]
    assert notes(client, version_id, type_id=types["Spanish"], tag="tides") == []
    assert (
        client.get(f"/api/versions/{version_id}/notes", params={"division_id": 999}).status_code
        == 404
    )


def test_status_changes_in_bulk(client: TestClient, version_id: int, types: dict[str, int]) -> None:
    historical = [n["id"] for n in notes(client, version_id, type_id=types["Historical"])]
    response = client.post(
        f"/api/versions/{version_id}/notes/status", json={"note_ids": historical, "status": "ready"}
    )
    assert response.json() == {"changed": 3}
    assert [n["id"] for n in notes(client, version_id, status="ready")] == historical
    assert len(notes(client, version_id, status="draft")) == 13
    back = client.post(
        f"/api/versions/{version_id}/notes/status",
        json={"note_ids": historical[:1], "status": "draft"},
    )
    assert back.json() == {"changed": 1}
    # Notes of another text are not touched, and an empty list changes nothing.
    other = client.post("/api/imports/corpus", json={**IMPORT, "allow_duplicate": True}).json()
    stray = client.post(
        f"/api/versions/{other['version_id']}/notes/status",
        json={"note_ids": historical, "status": "draft"},
    )
    assert stray.json() == {"changed": 0}
    empty = client.post(
        f"/api/versions/{version_id}/notes/status", json={"note_ids": [], "status": "ready"}
    )
    assert empty.json() == {"changed": 0}


# ---- The to-do list ---------------------------------------------------------------


def test_the_to_do_list_gathers_everything_still_open(client: TestClient, version_id: int) -> None:
    found = todo(client, version_id)
    # Every TODO: remark, with the note it is in.
    assert [(r["note"]["page"], r["text"]) for r in found["remarks"]] == [
        (7, "whole page needs a second pass"),
        (7, "check the make of the theodolite"),
        (7, "compare the second sheet"),
        (8, "Imported without a span. Attach this note to its passage."),
        (8, "Imported span with no note. Write the note, or delete this highlight."),
        (9, "Imported from a span that was never closed. Check where the passage ends."),
    ]
    # Every draft note: after an import, all of them.
    assert len(found["drafts"]) == 16
    # Every reference the import brought in leads somewhere.
    assert found["broken_references"] == []
    assert found["orphaned"] == []
    # The figure whose file was missing is still used; nothing is unused yet.
    assert found["unused_figures"] == []
    assert [(t["page"], t["line_no"]) for t in found["times_without_value"]] == [(7, 4), (8, 7)]


def test_broken_references_and_unused_figures_are_listed(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    create(
        client,
        version_id,
        type_id=types["Comment"],
        span=span_of(client, version_id, "otters", 10),
        body_md=(
            "See {{fx:99}}, {{note:999}}, {{fig:nothing}}, {{nope}} and {{cite:k}}; "
            "{{fx:7}} is fine."
        ),
    )
    client.post("/api/figures", json={"label": "spare", "caption": "Never placed"})
    found = todo(client, version_id)
    assert [(b["note"]["page"], b["form"]) for b in found["broken_references"]] == [
        (10, "{{fx:99}}"),
        (10, "{{note:999}}"),
        (10, "{{fig:nothing}}"),
        (10, "{{nope}}"),
        (10, "{{cite:k}}"),
    ]
    assert [(f["label"], f["caption"]) for f in found["unused_figures"]] == [
        ("spare", "Never placed")
    ]


def test_marking_notes_ready_and_resolving_remarks_empties_the_list(
    client: TestClient, version_id: int
) -> None:
    for note in notes(client, version_id):
        full = client.get(f"/api/notes/{note['id']}").json()
        kept = "\n\n".join(p for p in full["body_md"].split("\n\n") if not p.startswith("TODO:"))
        client.patch(f"/api/notes/{note['id']}", json={"body_md": kept, "status": "ready"})
    found = todo(client, version_id)
    assert (found["remarks"], found["drafts"]) == ([], [])


def test_a_missing_text_is_explained(client: TestClient) -> None:
    assert client.get("/api/versions/999/todo").status_code == 404
    assert client.get("/api/versions/999/notes").status_code == 404


# ---- Figures ----------------------------------------------------------------------


def figures(client: TestClient) -> dict[str, dict[str, Any]]:
    return {f["label"]: f for f in client.get("/api/figures").json()}


def test_the_figures_view_lists_where_each_figure_is_used(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    listed = figures(client)
    assert [(u["page"], u["line_no"], u["placed"]) for u in listed["harbor"]["uses"]] == [
        (7, 9, True)
    ]
    assert [(u["page"], u["placed"]) for u in listed["chain"]["uses"]] == [(9, True)]
    assert (listed["harbor"]["has_file"], listed["chain"]["has_file"]) == (True, False)
    # A figure that is only cited counts as used, but not as placed.
    create(
        client,
        version_id,
        type_id=types["Comment"],
        span=span_of(client, version_id, "otters", 10),
        body_md="As {{fig:chain}} shows.",
    )
    uses = figures(client)["chain"]["uses"]
    assert [(u["page"], u["placed"]) for u in uses] == [(9, True), (10, False)]


def test_a_figure_is_created_given_an_image_and_edited(
    client: TestClient, version_id: int, library: Library
) -> None:
    created = client.post(
        "/api/figures", json={"label": "tang", "caption": "A map", "credit": "A. Quill"}
    )
    assert created.status_code == 201, created.text
    figure = created.json()
    assert (figure["label"], figure["has_file"], figure["uses"]) == ("tang", False, [])

    uploaded = client.put(
        f"/api/figures/{figure['id']}/image", content=PNG, headers={"content-type": "image/png"}
    )
    assert uploaded.status_code == 200, uploaded.text
    assert (uploaded.json()["file"], uploaded.json()["has_file"]) == ("tang.png", True)
    assert (library.figures_dir / "tang.png").read_bytes() == PNG
    assert client.get("/api/figures/tang/file").content == PNG

    edited = client.patch(
        f"/api/figures/{figure['id']}", json={"caption": "The marsh", "credit": ""}
    )
    assert (edited.json()["caption"], edited.json()["credit"]) == ("The marsh", "")
    # A new image in another format replaces the old file.
    client.put(
        f"/api/figures/{figure['id']}/image", content=PNG, headers={"content-type": "image/jpeg"}
    )
    assert sorted(p.name for p in library.figures_dir.iterdir()) == ["harbor.png", "tang.jpg"]


@pytest.mark.parametrize(
    ("body", "status", "expected"),
    [
        ({"label": "Not A Label"}, 400, "label is"),
        ({"label": "harbor"}, 409, "already labeled"),
        ({"label": ""}, 400, "label is"),
    ],
)
def test_bad_figures_are_explained(
    client: TestClient, version_id: int, body: dict[str, str], status: int, expected: str
) -> None:
    response = client.post("/api/figures", json=body)
    assert response.status_code == status
    assert expected in response.json()["detail"]


def test_only_images_are_accepted(client: TestClient, version_id: int) -> None:
    figure = figures(client)["chain"]
    text = client.put(
        f"/api/figures/{figure['id']}/image",
        content=b"hello",
        headers={"content-type": "text/plain"},
    )
    assert (text.status_code, "not an image" in text.json()["detail"]) == (400, True)
    empty = client.put(
        f"/api/figures/{figure['id']}/image", content=b"", headers={"content-type": "image/png"}
    )
    assert empty.status_code == 400
    assert (
        client.put(
            "/api/figures/999/image", content=PNG, headers={"content-type": "image/png"}
        ).status_code
        == 404
    )


def test_relabeling_a_figure_is_followed_in_the_notes(client: TestClient, version_id: int) -> None:
    figure = figures(client)["harbor"]
    renamed = client.patch(f"/api/figures/{figure['id']}", json={"label": "low-water"})
    assert renamed.status_code == 200, renamed.text
    assert [(u["page"], u["placed"]) for u in renamed.json()["uses"]] == [(7, True)]
    tin = next(n for n in page_notes(client, version_id, 7) if n["legacy_id"] == "l_p7_tin")
    assert tin["body_md"] == (
        "![The harbor at low water](fig:low-water)\n\n"
        "The tin is the first container in the story; see {{fig:low-water}}."
    )
    placed = tin["body"]["children"][0]["children"][0]
    assert (placed["type"], placed["attrs"]["broken"]) == ("figure", False)
    assert client.get("/api/figures/low-water/file").status_code == 200
    assert todo(client, version_id)["broken_references"] == []


def test_deleting_a_figure_removes_its_image_and_leaves_references_broken(
    client: TestClient, version_id: int, library: Library
) -> None:
    figure = figures(client)["harbor"]
    assert client.delete(f"/api/figures/{figure['id']}").status_code == 204
    assert "harbor" not in figures(client)
    assert list(library.figures_dir.iterdir()) == []
    forms = [b["form"] for b in todo(client, version_id)["broken_references"]]
    assert forms == ["![The harbor at low water](fig:harbor)", "{{fig:harbor}}"]
    assert client.delete(f"/api/figures/{figure['id']}").status_code == 404


# ---- Note types are data ------------------------------------------------------------


def test_the_author_can_add_rename_and_recolor_note_types(client: TestClient) -> None:
    created = client.post(
        "/api/note-types", json={"name": "Geography", "code": "g", "color": "#446688"}
    )
    assert created.status_code == 201, created.text
    geography = created.json()
    assert (geography["name"], geography["code"], geography["role"]) == ("Geography", "g", "note")
    assert client.get("/api/note-types").json()[-1]["name"] == "Geography"

    edited = client.patch(
        f"/api/note-types/{geography['id']}",
        json={"name": "Places", "color": "#112233", "role": "definition"},
    ).json()
    assert (edited["name"], edited["color"], edited["role"], edited["code"]) == (
        "Places",
        "#112233",
        "definition",
        "g",
    )


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"name": "comment", "code": "zz"}, 409),
        ({"name": "Fresh", "code": "c"}, 409),
        ({"name": "Fresh", "code": "Not A Code"}, 400),
        ({"name": " ", "code": "zz"}, 400),
        ({"name": "Fresh", "code": "zz", "color": "red"}, 400),
    ],
)
def test_note_type_names_and_codes_must_be_usable(
    client: TestClient, body: dict[str, str], status: int
) -> None:
    assert client.post("/api/note-types", json=body).status_code == status


def test_merging_note_types_moves_their_notes(
    client: TestClient, version_id: int, types: dict[str, int], library: Library
) -> None:
    before = len(notes(client, version_id, type_id=types["Comment"]))
    meditations = len(notes(client, version_id, type_id=types["Meditation"]))
    assert meditations == 2
    merged = client.post(
        f"/api/note-types/{types['Meditation']}/merge", json={"into_id": types["Comment"]}
    )
    assert merged.status_code == 204
    assert "Meditation" not in [t["name"] for t in client.get("/api/note-types").json()]
    assert len(notes(client, version_id, type_id=types["Comment"])) == before + meditations
    same = client.post(
        f"/api/note-types/{types['Comment']}/merge", json={"into_id": types["Comment"]}
    )
    assert same.status_code == 400
    assert (
        client.post("/api/note-types/999/merge", json={"into_id": types["Comment"]}).status_code
        == 404
    )
    with db.transaction(library.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM annotation").fetchone()[0] == 16
