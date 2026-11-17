from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from pneutext.store import db
from pneutext.store.library import Library
from tests.test_api_corpus import IMPORT
from tests.test_api_notes import create, page_notes, span_of


@pytest.fixture
def version_id(client: TestClient) -> int:
    return client.post("/api/imports/corpus", json=IMPORT).json()["version_id"]


@pytest.fixture
def types(client: TestClient) -> dict[str, int]:
    return {t["name"]: t["id"] for t in client.get("/api/note-types").json()}


def note_on(
    client: TestClient,
    version_id: int,
    types: dict[str, int],
    phrase: str,
    page: int,
    body: str,
    **more: object,
) -> dict[str, Any]:
    return create(
        client,
        version_id,
        type_id=types["Comment"],
        span=span_of(client, version_id, phrase, page),
        body_md=body,
        **more,
    )


def forms(note: dict[str, Any]) -> list[dict[str, Any]]:
    """The PneuText forms in a note's parsed body, in order."""
    found: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        if node["type"] not in ("document", "paragraph", "text", "emphasis", "strong"):
            found.append(node)
        for child in node.get("children") or []:
            walk(child)

    walk(note["body"])
    return found


def links(client: TestClient, version_id: int, page: int) -> dict[str, Any]:
    response = client.get(f"/api/versions/{version_id}/pages/{page}/links")
    assert response.status_code == 200, response.text
    return response.json()


def backlinks(client: TestClient, version_id: int, page: int) -> list[tuple[int, str]]:
    return [(b["note_id"], b["target"]) for b in links(client, version_id, page)["backlinks"]]


def count(library: Library, table: str) -> int:
    with db.transaction(library.db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_a_reference_is_resolved_to_its_page_and_line(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    note = note_on(
        client,
        version_id,
        types,
        "single heron",
        8,
        "See {{fx:10}}, {{fx:7.5}} and {{fx:10.13-11.1}}.",
    )
    page, line, span = forms(note)
    assert page["attrs"] == {
        "work": "fx",
        "target": "10",
        "label": "p. 10",
        "broken": False,
        "version_id": version_id,
        "page": 10,
        "line": None,
        "end_page": 10,
        "end_line": None,
    }
    assert (line["attrs"]["label"], line["attrs"]["page"], line["attrs"]["line"]) == (
        "p. 7.5",
        7,
        5,
    )
    assert (span["attrs"]["label"], span["attrs"]["end_page"], span["attrs"]["end_line"]) == (
        "p. 10.13-11.1",
        11,
        1,
    )


def test_an_unresolvable_reference_is_kept_and_marked_broken(
    client: TestClient, version_id: int, types: dict[str, int], library: Library
) -> None:
    note = note_on(
        client,
        version_id,
        types,
        "single heron",
        8,
        "No such {{fx:99}}, {{fx:7.40}}, {{zz:7}}, {{note:999}}, {{fig:nothing}}.",
    )
    assert [(f["type"], f["attrs"]["broken"]) for f in forms(note)] == [
        ("reference", True),
        ("reference", True),
        ("reference", True),
        ("note_ref", True),
        ("figure_ref", True),
    ]
    assert note["body_md"].startswith("No such {{fx:99}}")  # nothing was rewritten
    assert count(library, "link") == 0


def test_a_reference_can_be_followed_both_ways(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    note = note_on(
        client, version_id, types, "single heron", 8, "Compare {{fx:10.3}} and {{fx:12}}."
    )
    # Forwards: the note's reference names its target.
    assert [(f["attrs"]["page"], f["attrs"]["line"]) for f in forms(note)] == [(10, 3), (12, None)]
    # Backwards: each target page lists the note, with where the note sits and what it cites.
    (on_10,) = links(client, version_id, 10)["backlinks"]
    assert on_10 == {
        "note_id": note["id"],
        "type_id": types["Comment"],
        "level": 1,
        "status": "draft",
        "page": 8,
        "line_no": 3,
        "target": "p. 10.3",
    }
    assert backlinks(client, version_id, 12) == [(note["id"], "p. 12")]
    assert backlinks(client, version_id, 11) == []
    assert backlinks(client, version_id, 8) == []


def test_a_range_is_a_backlink_on_every_page_it_reaches(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    note = note_on(client, version_id, types, "single heron", 8, "The flood, {{fx:10-11}}.")
    for page in (10, 11):
        assert backlinks(client, version_id, page) == [(note["id"], "p. 10-11")]
    assert backlinks(client, version_id, 12) == []


def test_backlinks_survive_and_follow_a_note_edit(
    client: TestClient, version_id: int, types: dict[str, int], library: Library
) -> None:
    note = note_on(client, version_id, types, "single heron", 8, "See {{fx:10}}.")
    assert backlinks(client, version_id, 10) == [(note["id"], "p. 10")]

    # Editing other words leaves the reference, and its backlink, in place.
    client.patch(f"/api/notes/{note['id']}", json={"body_md": "See also {{fx:10}}, again."})
    assert backlinks(client, version_id, 10) == [(note["id"], "p. 10")]
    assert count(library, "link") == 1

    # Changing where it points moves the backlink; nothing stale is left behind.
    client.patch(f"/api/notes/{note['id']}", json={"body_md": "See {{fx:12}} instead."})
    assert backlinks(client, version_id, 10) == []
    assert backlinks(client, version_id, 12) == [(note["id"], "p. 12")]
    assert (count(library, "link"), count(library, "anchor")) == (1, 2)

    # Editing something other than the body does not disturb the links.
    client.patch(f"/api/notes/{note['id']}", json={"status": "ready"})
    assert backlinks(client, version_id, 12) == [(note["id"], "p. 12")]

    client.patch(f"/api/notes/{note['id']}", json={"body_md": "No reference now."})
    assert backlinks(client, version_id, 12) == []
    assert (count(library, "link"), count(library, "anchor")) == (0, 1)


def test_the_same_reference_twice_is_one_backlink(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    note = note_on(client, version_id, types, "single heron", 8, "{{fx:10}} and again {{fx:10}}.")
    assert backlinks(client, version_id, 10) == [(note["id"], "p. 10")]


def test_notes_refer_to_notes_and_list_their_backlinks(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    target = note_on(client, version_id, types, "brass theodolite", 7, "The instrument.", level=2)
    source = note_on(
        client, version_id, types, "single heron", 8, f"As in {{{{note:{target['id']}}}}}."
    )
    (form,) = forms(source)
    assert form["type"] == "note_ref"
    assert form["attrs"] == {
        "id": target["id"],
        "broken": False,
        "version_id": version_id,
        "page": 7,
        "line": 5,
        "type_id": types["Comment"],
        "level": 2,
    }
    fetched = client.get(f"/api/notes/{target['id']}").json()
    assert fetched["backlinks"] == [
        {
            "note_id": source["id"],
            "type_id": types["Comment"],
            "level": 1,
            "status": "draft",
            "page": 8,
            "line_no": 3,
            "target": None,
        }
    ]
    assert source["backlinks"] == []
    listed = {n["id"]: n["backlinks"] for n in page_notes(client, version_id, 7)}
    assert [b["note_id"] for b in listed[target["id"]]] == [source["id"]]


def test_deleting_a_note_removes_its_links(
    client: TestClient, version_id: int, types: dict[str, int], library: Library
) -> None:
    target = note_on(client, version_id, types, "brass theodolite", 7, "The instrument.")
    source = note_on(
        client,
        version_id,
        types,
        "single heron",
        8,
        f"{{{{note:{target['id']}}}}} and {{{{fx:10}}}}.",
    )
    assert count(library, "link") == 2
    client.delete(f"/api/notes/{source['id']}")
    assert count(library, "link") == 0
    assert backlinks(client, version_id, 10) == []
    assert client.get(f"/api/notes/{target['id']}").json()["backlinks"] == []
    assert count(library, "anchor") == 1  # only the surviving note's own


def test_deleting_a_referenced_note_leaves_the_reference_broken(
    client: TestClient, version_id: int, types: dict[str, int], library: Library
) -> None:
    target = note_on(client, version_id, types, "brass theodolite", 7, "The instrument.")
    source = note_on(
        client, version_id, types, "single heron", 8, f"As in {{{{note:{target['id']}}}}}."
    )
    client.delete(f"/api/notes/{target['id']}")
    after = client.get(f"/api/notes/{source['id']}").json()
    assert after["body_md"] == f"As in {{{{note:{target['id']}}}}}."
    (form,) = forms(after)
    assert (form["type"], form["attrs"]["broken"]) == ("note_ref", True)
    assert count(library, "link") == 0


def test_a_reference_made_before_its_target_exists_resolves_on_the_next_save(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    source = note_on(client, version_id, types, "single heron", 8, "Later: {{note:2}}.")
    assert forms(source)[0]["attrs"]["broken"] is True
    target = note_on(client, version_id, types, "brass theodolite", 7, "Now it exists.")
    assert target["id"] == 2
    # Reading resolves against the library as it is now.
    assert forms(client.get(f"/api/notes/{source['id']}").json())[0]["attrs"]["broken"] is False


def test_the_preview_resolves_references_for_its_text(client: TestClient, version_id: int) -> None:
    body = {"body_md": "See {{fx:10}} and {{fx:99}}.", "version_id": version_id}
    tree = client.post("/api/notes/render", json=body).json()["body"]
    found = [
        child["attrs"]["broken"] for child in tree["children"][0]["children"] if child["attrs"]
    ]
    assert found == [False, True]
    # Without a text, nothing can be resolved, but the syntax is still parsed.
    bare = client.post("/api/notes/render", json={"body_md": "See {{fx:10}}."}).json()["body"]
    assert bare["children"][0]["children"][1]["attrs"] == {"work": "fx", "target": "10"}


def test_imported_notes_get_their_links_too(client: TestClient, version_id: int) -> None:
    from tests.helpers import BOOK

    client.post(
        f"/api/versions/{version_id}/imports/commentary",
        json={"folder": str(BOOK), "page_ref_commands": ["pref"]},
    )
    tide = next(n for n in page_notes(client, version_id, 7) if n["legacy_id"] == "h_p7_tide")
    assert backlinks(client, version_id, 10) == [(tide["id"], "p. 10")]
    assert backlinks(client, version_id, 12) == [(tide["id"], "p. 12")]
    # The figure the import brought in resolves where it is placed and where it is cited.
    tin = next(n for n in page_notes(client, version_id, 7) if n["legacy_id"] == "l_p7_tin")
    figure, cited = forms(tin)
    assert figure["attrs"] == {
        "label": "harbor",
        "caption": "The harbor at low water",
        "broken": False,
        "file": "harbor.png",
        "credit": "",
    }
    assert (cited["type"], cited["attrs"]["broken"], cited["attrs"]["caption"]) == (
        "figure_ref",
        False,
        "The harbor at low water",
    )


# ---- Links made passage to passage ----------------------------------------------


def test_a_passage_can_be_linked_to_another(
    client: TestClient, version_id: int, library: Library
) -> None:
    source = span_of(client, version_id, "single heron", 8)
    target = span_of(client, version_id, "At the end of it stood the", 11)
    response = client.post(
        f"/api/versions/{version_id}/links", json={"source": source, "target": target}
    )
    assert response.status_code == 201, response.text
    link_id = response.json()["id"]

    (here,) = links(client, version_id, 8)["passages"]
    assert here == {
        "id": link_id,
        "relation": "related",
        "source": {"page": 8, "line_no": 3, "end_page": 8, "end_line_no": 3, "here": True},
        "target": {"page": 11, "line_no": 13, "end_page": 11, "end_line_no": 13, "here": False},
    }
    (there,) = links(client, version_id, 11)["passages"]
    assert (there["source"]["here"], there["target"]["here"]) == (False, True)
    assert links(client, version_id, 9)["passages"] == []

    assert client.delete(f"/api/links/{link_id}").status_code == 204
    assert links(client, version_id, 8)["passages"] == []
    assert client.delete(f"/api/links/{link_id}").status_code == 404
    assert (count(library, "link"), count(library, "anchor")) == (0, 0)


def test_passage_links_are_validated_like_any_anchor(client: TestClient, version_id: int) -> None:
    source = span_of(client, version_id, "single heron", 8)
    wrong = {
        **span_of(client, version_id, "At the end of it stood the", 11),
        "exact": "other words",
    }
    refused = client.post(
        f"/api/versions/{version_id}/links", json={"source": source, "target": wrong}
    )
    assert refused.status_code == 400
    assert "does not match" in refused.json()["detail"]
    same = client.post(
        f"/api/versions/{version_id}/links", json={"source": source, "target": source}
    )
    assert same.status_code == 400
    assert "itself" in same.json()["detail"]
    assert links(client, version_id, 8)["passages"] == []


def test_links_of_a_missing_page_or_text_are_explained(client: TestClient, version_id: int) -> None:
    assert client.get(f"/api/versions/{version_id}/pages/99/links").status_code == 404
    assert client.get("/api/versions/999/pages/7/links").status_code == 404
