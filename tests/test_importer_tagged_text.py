from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from pneutext.core.errors import InvalidInput
from pneutext.importers.paged_corpus import PageSource
from pneutext.importers.tagged_text import TaggedFormat, parse_text, read_file
from tests.helpers import FIXTURES
from tests.test_api_corpus import IMPORT, page_text

TAGGED = FIXTURES / "book_tagged" / "FX_tagged.txt"
NARROW = TaggedFormat(first_page=5, line_width=20)


def parse(
    text: str, fmt: TaggedFormat = NARROW
) -> list[tuple[str, str, list[tuple[int, int, int | None]]]]:
    corpus = parse_text(PageSource(0, "t.txt", text.encode("utf-8")), fmt)
    return [
        (s.kind, s.text, [(line.start_offset, line.page, line.line_no) for line in s.lines])
        for s in corpus.segments
    ]


def codes(text: str, fmt: TaggedFormat = NARROW) -> list[str]:
    return [p.code for p in parse_text(PageSource(0, "t.txt", text.encode("utf-8")), fmt).problems]


def test_each_line_of_the_file_is_a_paragraph_filled_into_estimated_lines() -> None:
    assert parse("alpha beta gamma delta epsilon zeta\n\nsecond paragraph\n") == [
        # The first line of a paragraph is shorter by the indent.
        ("paragraph", "alpha beta gamma delta epsilon zeta", [(0, 5, 1), (17, 5, 2)]),
        ("paragraph", "second paragraph", [(0, 5, 3)]),
    ]


def test_every_line_start_points_at_a_word_and_lines_are_joined_by_one_space() -> None:
    ((_, text, lines),) = parse("one two three four five six seven eight nine ten eleven twelve\n")
    starts = [start for start, _, _ in lines]
    assert all(start == 0 or text[start - 1] == " " for start in starts)
    assert all(not text[start].isspace() for start in starts)
    pieces = [
        text[a : (b - 1 if b else None)] for a, b in zip(starts, [*starts[1:], 0], strict=True)
    ]
    assert " ".join(pieces) == text and all(len(piece) <= 20 for piece in pieces)


def test_a_page_marker_ends_the_page_also_inside_a_paragraph() -> None:
    assert parse("alpha beta{p} gamma delta\n\nnext{p}\n\nlast\n") == [
        ("paragraph", "alpha beta gamma delta", [(0, 5, 1), (11, 6, 1)]),
        ("paragraph", "next", [(0, 6, 2)]),
        ("paragraph", "last", [(0, 7, 1)]),
    ]


def test_a_word_the_page_break_falls_inside_stays_whole_on_the_page_where_it_begins() -> None:
    text = "alpha be{p}ta, gamma\n"
    assert parse(text) == [("paragraph", "alpha beta, gamma", [(0, 5, 1), (12, 6, 1)])]
    assert codes(text) == ["words_across_pages", "estimated_lines"]


def test_chapter_tags_open_divisions_and_synopsis_tags_mark_the_synopsis() -> None:
    corpus = parse_text(
        PageSource(
            0,
            "t.txt",
            b"<chapter>CHAPTER 4</chapter>\n\n<chapter_sections>One - Two</chapter_sections>\n\n"
            b"body\n\n<epilogue>EPILOGUE</epilogue>\n\nend\n",
        ),
        NARROW,
    )
    assert [(s.kind, s.text) for s in corpus.segments] == [
        ("chapter_number", "CHAPTER 4"),
        ("synopsis", "One - Two"),
        ("paragraph", "body"),
        ("chapter_number", "EPILOGUE"),
        ("paragraph", "end"),
    ]
    assert [(d.kind, d.label, d.first_segment) for d in corpus.divisions] == [
        ("chapter", "CHAPTER 4", 0),
        ("chapter", "EPILOGUE", 3),
    ]
    assert corpus.summary().chapters == 2


def test_a_synopsis_block_may_run_over_several_lines() -> None:
    kinds = [kind for kind, _, _ in parse("<chapter_sections>One\nTwo</chapter_sections>\nbody\n")]
    assert kinds == ["synopsis", "synopsis", "paragraph"]
    assert "region_not_closed" in codes("<chapter_sections>One\nTwo\n")


def test_a_section_break_is_an_ornament_and_plain_block_tags_are_set_aside() -> None:
    assert parse(
        "<epigraph>A motto.\n- Somebody</epigraph>{p}\n\n{section_break}\n\n<c>centered</c>\n"
    ) == [
        ("paragraph", "A motto.", [(0, 5, 1)]),
        ("paragraph", "- Somebody", [(0, 5, 2)]),
        ("ornament", "", [(0, 6, None)]),
        ("paragraph", "centered", [(0, 6, 1)]),
    ]


def test_an_unknown_tag_is_reported_by_name_and_its_text_kept() -> None:
    corpus = parse_text(PageSource(0, "t.txt", b"<mystery>private words</mystery>\n"), NARROW)
    assert [s.text for s in corpus.segments] == ["private words"]
    problem = corpus.problems[0]
    assert (problem.code, problem.page, problem.line) == ("unknown_tag", 5, 1)
    assert "<mystery>" in problem.message and "private" not in problem.message


def test_a_page_with_no_text_is_reported_and_keeps_its_number() -> None:
    corpus = parse_text(PageSource(0, "t.txt", b"alpha{p}\n\n{p}\n\nbeta\n"), NARROW)
    assert corpus.pages == [5, 7]
    assert [(p.code, p.page) for p in corpus.problems][:1] == [("empty_page", 6)]


def test_the_page_marker_and_the_meaning_of_tags_are_configuration() -> None:
    fmt = TaggedFormat(
        page_break=r"\[\[page\]\]",
        first_page=1,
        line_width=40,
        divisions={"part": "part"},
        furniture={"stars": "ornament"},
    )
    assert parse("<part>One</part>\na[[page]] b\n{stars}\n", fmt) == [
        ("chapter_number", "One", [(0, 1, None)]),
        ("paragraph", "a b", [(0, 1, 1), (2, 2, 1)]),
        ("ornament", "", [(0, 2, None)]),
    ]
    # A marker of the default shape is then only text.
    assert parse("a{p25} b\n", fmt)[0][1] == "a{p25} b"


def test_the_import_always_says_that_lines_are_estimated() -> None:
    corpus = parse_text(PageSource(0, "t.txt", b"alpha\n"), TaggedFormat(line_width=66))
    (problem,) = corpus.problems
    assert problem.code == "estimated_lines"
    assert "66 characters" in problem.message and "line numbers do not" in problem.message


@pytest.mark.parametrize(
    ("fmt", "expected"),
    [
        (TaggedFormat(page_break="("), "not a valid expression"),
        (TaggedFormat(page_break="x*"), "must not match nothing"),
        (TaggedFormat(line_width=5), "at least 20 characters"),
    ],
)
def test_bad_settings_are_explained(fmt: TaggedFormat, expected: str) -> None:
    with pytest.raises(InvalidInput, match=expected):
        parse_text(PageSource(0, "t.txt", b"alpha\n"), fmt)


def test_a_folder_or_a_missing_file_is_explained(tmp_path: Path) -> None:
    with pytest.raises(InvalidInput, match="is a folder"):
        read_file(tmp_path)
    with pytest.raises(InvalidInput, match="no file"):
        read_file(tmp_path / "absent.txt")


# ---- Through the API, against the paged fixture book --------------------------------

TAGGED_IMPORT = {
    "folder": str(TAGGED),
    "work_code": "fx",
    "title": "The Fixture Book",
    "source_format": "tagged",
    "first_page": 6,
    "page_break": r"\{p\}",
    "line_width": 56,
}


def words_on(client: TestClient, version_id: int, page: int) -> list[str]:
    lines = page_text(client, version_id, page)["lines"]
    return " ".join(line["text"] for line in lines if line["line_no"] is not None).split()


def test_the_tagged_fixture_imports_with_the_same_pages_as_the_paged_one(
    client: TestClient,
) -> None:
    preview = client.post("/api/imports/corpus/preview", json=TAGGED_IMPORT)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["summary"] == {
        "pages": 8,
        "lines": 74,
        "paragraphs": 14,
        "chapters": 3,
        "first_page": 6,
        "last_page": 14,
    }
    assert [(p["code"], p["page"], p["line"]) for p in body["problems"]] == [
        ("empty_page", 13, None),
        ("unknown_tag", 14, 41),
        ("words_across_pages", None, None),
        ("estimated_lines", None, None),
    ]
    assert client.get("/api/versions").json() == []  # the preview wrote nothing

    tagged = client.post("/api/imports/corpus", json=TAGGED_IMPORT).json()["version_id"]
    paged = client.post("/api/imports/corpus", json=IMPORT).json()["version_id"]
    detail = client.get(f"/api/versions/{tagged}").json()
    assert detail["pages"] == [6, 7, 8, 9, 10, 11, 12, 14]
    assert [(d["label"], d["page"]) for d in detail["divisions"]] == [
        ("CHAPTER I", 7),
        ("CHAPTER II", 10),
        ("AFTERWORD", 14),
    ]
    # Page for page, the same words as the paged book (whose chapter II page has an
    # ornament the tagged file gives as a section break).
    for page in (7, 8, 9, 12):
        assert words_on(client, tagged, page) == words_on(client, paged, page)
    # The word the page break fell inside of is whole, on the page where it begins.
    assert words_on(client, tagged, 10)[-1] == "then"
    assert words_on(client, tagged, 11)[0] == "understood"
    assert words_on(client, tagged, 10) + words_on(client, tagged, 11) == (
        words_on(client, paged, 10) + words_on(client, paged, 11)
    )
    kinds = [line["kind"] for line in page_text(client, tagged, 7)["lines"]]
    assert kinds[:3] == ["chapter_number", "synopsis", "synopsis"] and set(kinds[3:]) == {
        "paragraph"
    }
    assert page_text(client, tagged, 10)["lines"][1]["kind"] == "ornament"


def test_the_same_file_twice_warns_and_a_tagged_import_needs_a_file(
    client: TestClient, tmp_path: Path
) -> None:
    client.post("/api/imports/corpus", json=TAGGED_IMPORT)
    again = client.post("/api/imports/corpus", json=TAGGED_IMPORT)
    assert again.status_code == 409
    folder = client.post(
        "/api/imports/corpus/preview", json={**TAGGED_IMPORT, "folder": str(tmp_path)}
    )
    assert (folder.status_code, "is a folder" in folder.json()["detail"]) == (400, True)
    empty = client.post("/api/imports/corpus/preview", json={**TAGGED_IMPORT, "folder": " "})
    assert "Give the file" in empty.json()["detail"]
