from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from pneutext.api.schemas import (
    DivisionOut,
    MentionMarkOut,
    PageShapeOut,
    ShapeHighlightOut,
    ShapeLineOut,
)
from pneutext.importers.paged_corpus import parse_pages, read_folder
from tests.helpers import BOOK
from tests.test_api_corpus import IMPORT, page_text

PAGES = range(7, 13)


@pytest.fixture
def version_id(client: TestClient) -> int:
    return client.post("/api/imports/corpus", json=IMPORT).json()["version_id"]


def page_shape(client: TestClient, version_id: int, page: int) -> dict[str, Any]:
    response = client.get(f"/api/versions/{version_id}/pages/{page}/shape")
    assert response.status_code == 200, response.text
    return response.json()


def strings_in(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)


def corpus_words() -> set[str]:
    """Every word of the fixture book, lower-cased, including furniture labels' text."""
    corpus = parse_pages(read_folder(BOOK))
    words: set[str] = set()
    for segment in corpus.segments:
        if segment.kind in ("paragraph", "synopsis"):
            words.update(re.findall(r"\w+", segment.text.lower()))
    return words


def test_shape_agrees_with_text_line_for_line(client: TestClient, version_id: int) -> None:
    for page in PAGES:
        text_lines = page_text(client, version_id, page)["lines"]
        shape_lines = page_shape(client, version_id, page)["lines"]
        assert len(shape_lines) == len(text_lines)
        for shape_line, text_line in zip(shape_lines, text_lines, strict=True):
            for key in ("id", "kind", "line_no", "starts_paragraph", "ends_paragraph"):
                assert shape_line[key] == text_line[key]
            assert shape_line["page"] == page
            is_text = text_line["kind"] in ("paragraph", "synopsis")
            assert shape_line["length"] == (len(text_line["text"]) if is_text else 0)
            assert shape_line["highlights"] == []


def test_shape_has_the_same_navigation_as_text(client: TestClient, version_id: int) -> None:
    for page in PAGES:
        text, shape = page_text(client, version_id, page), page_shape(client, version_id, page)
        for key in ("version_id", "edit_seq", "page", "prev_page", "next_page", "division"):
            assert shape[key] == text[key]


def test_no_shape_response_contains_corpus_text(client: TestClient, version_id: int) -> None:
    """Blank mode must not leak: the only words in a shape are field names and labels."""
    words = corpus_words()
    assert len(words) > 150
    allowed = {"paragraph", "synopsis", "chapter_number", "ornament", "rule", "chapter", "I", "II"}
    for page in PAGES:
        response = client.get(f"/api/versions/{version_id}/pages/{page}/shape")
        body = response.json()
        fields = set(PageShapeOut.model_fields) | set(ShapeLineOut.model_fields)
        fields |= set(ShapeHighlightOut.model_fields) | set(DivisionOut.model_fields)
        fields |= set(MentionMarkOut.model_fields)
        for value in strings_in(body):
            assert value in allowed or value in fields, f"unexpected string in shape: {value!r}"
        # Belt and braces: no word of four letters or more from the book appears anywhere.
        raw_words = set(re.findall(r"\w{4,}", response.text.lower()))
        structural = {w.lower() for w in fields | allowed}
        structural |= {part for w in fields | allowed for part in w.lower().split("_")}
        assert not (raw_words - structural) & words


def test_the_shape_models_have_no_text_field() -> None:
    for model in (PageShapeOut, ShapeLineOut, ShapeHighlightOut):
        assert "text" not in model.model_fields


def test_missing_shape_pages_are_explained(client: TestClient, version_id: int) -> None:
    response = client.get(f"/api/versions/{version_id}/pages/99/shape")
    assert (response.status_code, response.json()) == (404, {"detail": "This text has no page 99."})
