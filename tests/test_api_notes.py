from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_api_corpus import IMPORT, page_text
from tests.test_api_shape import corpus_words, page_shape


@pytest.fixture
def version_id(client: TestClient) -> int:
    return client.post("/api/imports/corpus", json=IMPORT).json()["version_id"]


@pytest.fixture
def types(client: TestClient) -> dict[str, int]:
    return {t["name"]: t["id"] for t in client.get("/api/note-types").json()}


def segments_on(client: TestClient, version_id: int, *pages: int) -> dict[int, tuple[int, str]]:
    """Each segment seen on the given pages: where its visible text starts, and that text."""
    found: dict[int, tuple[int, str]] = {}
    for page in pages:
        for line in page_text(client, version_id, page)["lines"]:
            if line["line_no"] is None:
                continue
            start, text = found.get(line["segment_id"], (line["start_offset"], ""))
            found[line["segment_id"]] = (start, f"{text} {line['text']}" if text else line["text"])
    return found


def span_of(client: TestClient, version_id: int, phrase: str, *pages: int) -> dict[str, Any]:
    """The span covering a phrase that lies within one paragraph on the given pages."""
    for segment_id, (start, text) in segments_on(client, version_id, *pages).items():
        at = text.find(phrase)
        if at != -1:
            return {
                "start_segment_id": segment_id,
                "start_offset": start + at,
                "end_segment_id": segment_id,
                "end_offset": start + at + len(phrase),
                "exact": phrase,
            }
    raise AssertionError(f"phrase not found on pages {pages}")


def string_values(value: object) -> list[str]:
    """Every string value in a JSON document (not its field names)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [found for item in value.values() for found in string_values(item)]
    if isinstance(value, list):
        return [found for item in value for found in string_values(item)]
    return []


def create(client: TestClient, version_id: int, **fields: object) -> dict[str, Any]:
    response = client.post(f"/api/versions/{version_id}/notes", json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def page_notes(client: TestClient, version_id: int, page: int) -> list[dict[str, Any]]:
    response = client.get(f"/api/versions/{version_id}/pages/{page}/notes")
    assert response.status_code == 200, response.text
    return response.json()


def marks(page: dict[str, Any]) -> dict[int, list[tuple[int, int, int]]]:
    """Highlights by line number: (note, start, end)."""
    return {
        line["line_no"]: [(h["annotation_id"], h["start"], h["end"]) for h in line["highlights"]]
        for line in page["lines"]
        if line["highlights"]
    }


def test_a_new_library_is_seeded_with_note_types(client: TestClient) -> None:
    listed = client.get("/api/note-types").json()
    assert [(t["name"], t["code"], t["role"]) for t in listed] == [
        ("Clarification", "cl", "note"),
        ("Comment", "c", "note"),
        ("Historical", "h", "note"),
        ("Meditation", "m", "note"),
        ("Literary", "l", "note"),
        ("Spanish", "s", "note"),
        ("Definition", "d", "definition"),
        ("Chapter title", "ct", "chapter_title"),
        ("Chapter summary", "cs", "chapter_summary"),
    ]
    assert all(re.fullmatch(r"#[0-9a-f]{6}", t["color"]) for t in listed)


def test_a_note_on_a_span_is_listed_and_highlighted_in_both_projections(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    span = span_of(client, version_id, "brass theodolite", 7)
    note = create(
        client, version_id, type_id=types["Comment"], span=span, body_md="An *instrument*."
    )

    assert (note["scope"], note["level"], note["status"]) == ("span", 1, "draft")
    assert note["start"] == {"page": 7, "line_no": 5}
    assert note["end"] == {"page": 7, "line_no": 6}
    assert note["anchor"] == {k: v for k, v in span.items() if k != "exact"} | {"status": "ok"}
    assert note["body"]["children"][0]["children"][1] == {
        "type": "emphasis",
        "text": None,
        "attrs": None,
        "children": [{"type": "text", "text": "instrument", "attrs": None, "children": None}],
    }
    assert [n["id"] for n in page_notes(client, version_id, 7)] == [note["id"]]

    text = page_text(client, version_id, 7)
    # "brass" ends line 5 and "theodolite" begins line 6: the joining space is not marked.
    assert marks(text) == {5: [(note["id"], 51, 56)], 6: [(note["id"], 0, 10)]}
    lines = {line["line_no"]: line["text"] for line in text["lines"]}
    assert lines[5][51:56] == "brass" and lines[6][0:10] == "theodolite"
    assert marks(page_shape(client, version_id, 7)) == marks(text)


def test_notes_of_several_types_on_nested_and_overlapping_spans_survive(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    outer = create(
        client,
        version_id,
        type_id=types["Historical"],
        span=span_of(client, version_id, "kept his ledgers in a biscuit tin", 7),
    )
    inner = create(
        client,
        version_id,
        type_id=types["Clarification"],
        level=2,
        span=span_of(client, version_id, "ledgers", 7),
    )
    overlapping = create(
        client,
        version_id,
        type_id=types["Literary"],
        span=span_of(client, version_id, "biscuit tin. He told her", 7),
    )
    bare = create(
        client, version_id, type_id=types["Spanish"], span=span_of(client, version_id, "tin", 7)
    )

    listed = page_notes(client, version_id, 7)
    # Reading order of the spans; where two start together, the longer comes first.
    assert [n["id"] for n in listed] == [outer["id"], inner["id"], overlapping["id"], bare["id"]]
    assert [n["type_id"] for n in listed] == [
        types["Historical"],
        types["Clarification"],
        types["Literary"],
        types["Spanish"],
    ]
    assert bare["body_md"] == ""  # a bare highlight

    line = next(ln for ln in page_text(client, version_id, 7)["lines"] if ln["line_no"] == 9)
    found = [
        (h["annotation_id"], line["text"][h["start"] : h["end"]], h["level"])
        for h in line["highlights"]
    ]
    assert found == [
        (outer["id"], "kept his ledgers in a biscuit tin", 1),
        (inner["id"], "ledgers", 2),
        (overlapping["id"], "biscuit tin. He told her", 1),
        (bare["id"], "tin", 1),
    ]


def test_a_span_may_cross_a_page(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    span = span_of(client, version_id, "and then understood that he had drawn north", 10, 11)
    note = create(client, version_id, type_id=types["Comment"], span=span)
    assert (note["start"]["page"], note["end"]["page"]) == (10, 11)
    assert [n["id"] for n in page_notes(client, version_id, 10)] == [note["id"]]
    assert [n["id"] for n in page_notes(client, version_id, 11)] == [note["id"]]
    assert page_notes(client, version_id, 12) == []

    last = page_text(client, version_id, 10)["lines"][-1]
    first = page_text(client, version_id, 11)["lines"][0]
    (mark_10,), (mark_11,) = last["highlights"], first["highlights"]
    assert last["text"][mark_10["start"] : mark_10["end"]] == "and then"
    assert first["text"][mark_11["start"] : mark_11["end"]] == "understood that he had drawn north"


def test_a_span_may_cross_paragraphs(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    first = span_of(client, version_id, "promised.", 7)
    second = span_of(client, version_id, "The harbormaster", 7)
    span = {
        "start_segment_id": first["start_segment_id"],
        "start_offset": first["start_offset"],
        "end_segment_id": second["end_segment_id"],
        "end_offset": second["end_offset"],
        "exact": "promised.\nThe harbormaster",
    }
    note = create(client, version_id, type_id=types["Meditation"], span=span)
    assert marks(page_text(client, version_id, 7)) == {
        7: [(note["id"], 47, 56)],
        8: [(note["id"], 0, 16)],
    }


def test_offsets_are_code_points(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    span = span_of(client, version_id, "beside it", 12)
    note = create(client, version_id, type_id=types["Comment"], span=span)
    line = next(ln for ln in page_text(client, version_id, 12)["lines"] if ln["highlights"])
    (mark,) = line["highlights"]
    assert "\U0001d11e" in line["text"][: mark["start"]]
    assert line["text"][mark["start"] : mark["end"]] == "beside it"
    assert mark["annotation_id"] == note["id"]

    # A client that counted UTF-16 units would be one too far along, and is refused.
    shifted = {
        **span,
        "start_offset": span["start_offset"] + 1,
        "end_offset": span["end_offset"] + 1,
    }
    refused = client.post(
        f"/api/versions/{version_id}/notes", json={"type_id": types["Comment"], "span": shifted}
    )
    assert refused.status_code == 400
    assert "does not match" in refused.json()["detail"]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"exact": "something else"}, "does not match"),
        ({"end_offset": 100000}, "outside the text"),
        ({"start_offset": -1}, "outside the text"),
        ({"start_segment_id": 987654}, "does not belong"),
    ],
)
def test_invalid_anchors_are_rejected_without_quoting_text(
    client: TestClient,
    version_id: int,
    types: dict[str, int],
    change: dict[str, object],
    expected: str,
) -> None:
    span = {**span_of(client, version_id, "brass theodolite", 7), **change}
    response = client.post(
        f"/api/versions/{version_id}/notes", json={"type_id": types["Comment"], "span": span}
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert expected in detail
    assert "brass" not in detail and "something else" not in detail
    assert page_notes(client, version_id, 7) == []


def test_a_span_must_run_forwards(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    later = span_of(client, version_id, "The harbormaster", 7)
    earlier = span_of(client, version_id, "The ferry came", 7)
    backwards = {
        "start_segment_id": later["start_segment_id"],
        "start_offset": 0,
        "end_segment_id": earlier["start_segment_id"],
        "end_offset": 3,
        "exact": "",
    }
    response = client.post(
        f"/api/versions/{version_id}/notes", json={"type_id": types["Comment"], "span": backwards}
    )
    assert response.status_code == 400


def test_a_span_in_another_text_is_refused(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    other = client.post("/api/imports/corpus", json={**IMPORT, "allow_duplicate": True}).json()
    span = span_of(client, other["version_id"], "brass theodolite", 7)
    response = client.post(
        f"/api/versions/{version_id}/notes", json={"type_id": types["Comment"], "span": span}
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"type_id": 999}, "note type"),
        ({"level": 3}, "level"),
        ({"scope": "span"}, "Select the passage"),
        ({"scope": "page"}, "which page"),
        ({"scope": "page", "page": 99}, "which page"),
        ({"scope": "chapter"}, "which chapter"),
        ({"scope": "chapter", "division_id": 999}, "which chapter"),
    ],
)
def test_incomplete_notes_are_explained(
    client: TestClient,
    version_id: int,
    types: dict[str, int],
    fields: dict[str, object],
    expected: str,
) -> None:
    response = client.post(
        f"/api/versions/{version_id}/notes", json={"type_id": types["Comment"], **fields}
    )
    assert response.status_code == 400
    assert expected in response.json()["detail"]


def test_page_notes_cover_their_page_and_are_not_highlighted(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    span_note = create(
        client,
        version_id,
        type_id=types["Comment"],
        span=span_of(client, version_id, "single heron", 8),
    )
    note = create(
        client, version_id, type_id=types["Comment"], scope="page", page=8, body_md="On this page."
    )
    assert (note["scope"], note["start"]["page"], note["end"]["page"]) == ("page", 8, 8)
    # The page note starts at the top of the page, so it is listed first.
    assert [n["id"] for n in page_notes(client, version_id, 8)] == [note["id"], span_note["id"]]
    assert page_notes(client, version_id, 7) == []
    assert page_notes(client, version_id, 9) == []
    assert set(marks(page_text(client, version_id, 8))) == {3}


def test_chapter_notes_are_listed_where_the_chapter_opens(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    chapters = client.get(f"/api/versions/{version_id}").json()["divisions"]
    first = create(
        client,
        version_id,
        type_id=types["Chapter title"],
        scope="chapter",
        division_id=chapters[0]["id"],
        body_md="Arrival",
    )
    second = create(
        client,
        version_id,
        type_id=types["Chapter summary"],
        scope="chapter",
        division_id=chapters[1]["id"],
        body_md="The flood.",
    )
    assert (first["start"]["page"], first["end"]["page"]) == (7, 9)
    assert (second["start"]["page"], second["end"]["page"]) == (10, 12)
    assert [n["id"] for n in page_notes(client, version_id, 7)] == [first["id"]]
    assert page_notes(client, version_id, 8) == []
    assert [n["id"] for n in page_notes(client, version_id, 10)] == [second["id"]]
    for page in range(7, 13):
        assert marks(page_text(client, version_id, page)) == {}


def test_a_note_can_be_edited(client: TestClient, version_id: int, types: dict[str, int]) -> None:
    note = create(
        client,
        version_id,
        type_id=types["Comment"],
        span=span_of(client, version_id, "single heron", 8),
    )
    response = client.patch(
        f"/api/notes/{note['id']}",
        json={
            "type_id": types["Literary"],
            "level": 2,
            "status": "ready",
            "body_md": "A **patient** bird.",
            "tags": ["birds", " marsh  life ", "birds", ""],
        },
    )
    assert response.status_code == 200, response.text
    edited = client.get(f"/api/notes/{note['id']}").json()
    assert (edited["type_id"], edited["level"], edited["status"]) == (types["Literary"], 2, "ready")
    assert edited["body_md"] == "A **patient** bird."
    assert edited["tags"] == ["birds", "marsh life"]
    assert edited["anchor"] == note["anchor"]

    # Leaving a field out leaves it alone; tags can be cleared.
    client.patch(f"/api/notes/{note['id']}", json={"tags": []})
    again = client.get(f"/api/notes/{note['id']}").json()
    assert (again["body_md"], again["tags"], again["level"]) == ("A **patient** bird.", [], 2)
    (mark,) = next(
        ln["highlights"] for ln in page_text(client, version_id, 8)["lines"] if ln["highlights"]
    )
    assert (mark["type_id"], mark["level"]) == (types["Literary"], 2)


def test_a_notes_span_can_be_reselected_without_retyping_it(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    note = create(
        client,
        version_id,
        type_id=types["Comment"],
        span=span_of(client, version_id, "single heron", 8),
        body_md="Kept.",
    )
    moved_to = span_of(client, version_id, "patient as a fence post", 8)
    response = client.patch(f"/api/notes/{note['id']}", json={"span": moved_to})
    assert response.status_code == 200, response.text
    moved = response.json()
    assert moved["body_md"] == "Kept."
    assert moved["anchor"]["start_offset"] == moved_to["start_offset"]
    line = next(ln for ln in page_text(client, version_id, 8)["lines"] if ln["highlights"])
    (mark,) = line["highlights"]
    assert line["text"][mark["start"] : mark["end"]] == "patient as a fence post"

    bad = client.patch(f"/api/notes/{note['id']}", json={"span": {**moved_to, "exact": "nope"}})
    assert bad.status_code == 400
    assert client.get(f"/api/notes/{note['id']}").json()["anchor"] == moved["anchor"]


def test_a_page_note_cannot_be_moved_to_a_passage(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    note = create(client, version_id, type_id=types["Comment"], scope="page", page=8)
    span = span_of(client, version_id, "single heron", 8)
    assert client.patch(f"/api/notes/{note['id']}", json={"span": span}).status_code == 400


def test_deleting_a_note_removes_it_and_its_highlight(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    note = create(
        client,
        version_id,
        type_id=types["Comment"],
        span=span_of(client, version_id, "single heron", 8),
        tags=["birds"],
    )
    assert client.delete(f"/api/notes/{note['id']}").status_code == 204
    assert client.get(f"/api/notes/{note['id']}").status_code == 404
    assert page_notes(client, version_id, 8) == []
    assert marks(page_text(client, version_id, 8)) == {}
    assert client.delete(f"/api/notes/{note['id']}").status_code == 404
    assert client.patch(f"/api/notes/{note['id']}", json={"level": 2}).status_code == 404


def test_a_note_body_can_be_rendered_for_preview(client: TestClient) -> None:
    response = client.post("/api/notes/render", json={"body_md": "One *two*."})
    assert response.status_code == 200
    kinds = [child["type"] for child in response.json()["body"]["children"][0]["children"]]
    assert kinds == ["text", "emphasis", "text"]


def test_notes_and_shapes_carry_no_corpus_text(
    client: TestClient, version_id: int, types: dict[str, int]
) -> None:
    """With notes in place, neither the notes list nor the shape leaks the passage."""
    for phrase, name in [
        ("kept his ledgers in a biscuit tin", "Historical"),
        ("ledgers", "Comment"),
    ]:
        create(
            client,
            version_id,
            type_id=types[name],
            span=span_of(client, version_id, phrase, 7),
            body_md="Zzyzx qwfp.",
        )
    words = corpus_words()
    # Words the API itself uses as values (kinds, scopes, statuses, node types).
    vocabulary = {"paragraph", "synopsis", "rule", "ornament", "chapter", "span", "draft"}
    vocabulary |= {"ready", "document", "text", "page"}
    for path in ("notes", "shape"):
        body = client.get(f"/api/versions/{version_id}/pages/7/{path}").json()
        values = " ".join(string_values(body)).lower()
        found = set(re.findall(r"[a-z]{3,}", values)) & words
        assert found <= vocabulary, f"{path} leaks {sorted(found - vocabulary)}"
    assert len(marks(page_shape(client, version_id, 7))[9]) == 2
