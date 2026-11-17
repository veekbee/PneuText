from __future__ import annotations

from pathlib import Path

import pytest

from pneutext.core.errors import InvalidInput
from pneutext.importers import paged_corpus
from pneutext.importers.paged_corpus import CorpusFormat, DirectiveRule, parse_pages, read_folder
from tests.helpers import BOOK, assert_matches_golden, corpus_as_json, page


def test_lines_join_into_paragraphs_with_single_spaces() -> None:
    corpus = parse_pages([page(1, "alpha beta\ngamma\n\ndelta\n")])
    assert [s.text for s in corpus.segments] == ["alpha beta gamma", "delta"]
    first = corpus.segments[0]
    assert [(line.start_offset, line.page, line.line_no) for line in first.lines] == [
        (0, 1, 1),
        (11, 1, 2),
    ]
    assert [(line.start_offset, line.line_no) for line in corpus.segments[1].lines] == [(0, 3)]


def test_every_line_start_points_at_the_first_character_of_its_line() -> None:
    corpus = parse_pages([page(1, "one two\nthree\nfour five six\n")])
    segment = corpus.segments[0]
    starts = [line.start_offset for line in segment.lines]
    assert [segment.text[s:].split(" ")[0] for s in starts] == ["one", "three", "four"]


def test_a_page_starting_mid_paragraph_continues_the_previous_page() -> None:
    corpus = parse_pages([page(1, "alpha\nbeta\n"), page(2, "gamma\n\ndelta\n")])
    assert [s.text for s in corpus.segments] == ["alpha beta gamma", "delta"]
    assert [(line.page, line.line_no) for line in corpus.segments[0].lines] == [
        (1, 1),
        (1, 2),
        (2, 1),
    ]


def test_a_page_ending_with_a_blank_line_closes_its_paragraph() -> None:
    corpus = parse_pages([page(1, "alpha\nbeta\n\n"), page(2, "gamma\n")])
    assert [s.text for s in corpus.segments] == ["alpha beta", "gamma"]


def test_a_page_starting_with_a_blank_line_starts_a_new_paragraph() -> None:
    corpus = parse_pages([page(1, "alpha\n"), page(2, "\nbeta\n")])
    assert [s.text for s in corpus.segments] == ["alpha", "beta"]


def test_paragraphs_do_not_run_across_missing_pages() -> None:
    corpus = parse_pages([page(1, "alpha\n"), page(3, "beta\n")])
    assert [s.text for s in corpus.segments] == ["alpha", "beta"]
    assert [(p.code, p.page) for p in corpus.problems] == [("page_gap", 3)]


def test_chapter_opening_directives_become_furniture_and_a_division() -> None:
    corpus = parse_pages(
        [
            page(
                4,
                "<<chapter=IV>>\n<<chapter_ornament>>\n<<top_bar>>\nfirst part\nsecond part\n"
                "<<bottom_bar>>\n\nbody text\n",
            )
        ]
    )
    assert [(s.kind, s.text) for s in corpus.segments] == [
        ("chapter_number", "IV"),
        ("ornament", ""),
        ("rule", ""),
        ("synopsis", "first part second part"),
        ("rule", ""),
        ("paragraph", "body text"),
    ]
    assert [(d.kind, d.label, d.first_segment) for d in corpus.divisions] == [("chapter", "IV", 0)]
    assert corpus.problems == []


def test_a_section_ornament_within_a_page_is_furniture_between_paragraphs() -> None:
    assert parse_pages([page(27, "a\n<<section_ornament>>\nb\n")]).problems == []
    corpus = parse_pages([page(27, "alpha\nbeta\n\n<<section_decoration>>\n\ngamma\n")])
    assert [(s.kind, s.text) for s in corpus.segments] == [
        ("paragraph", "alpha beta"),
        ("ornament", ""),
        ("paragraph", "gamma"),
    ]
    assert [(line.page, line.line_no) for line in corpus.segments[2].lines] == [(27, 3)]
    assert corpus.problems == []


def test_furniture_has_one_unnumbered_line_and_text_lines_are_numbered_per_page() -> None:
    corpus = parse_pages([page(4, "<<chapter=IV>>\nalpha\nbeta\n"), page(5, "gamma\n")])
    furniture, paragraph = corpus.segments
    assert [(line.page, line.line_no) for line in furniture.lines] == [(4, None)]
    assert [(line.page, line.line_no) for line in paragraph.lines] == [(4, 1), (4, 2), (5, 1)]


def test_an_unknown_directive_is_reported_with_its_place_and_name_only() -> None:
    corpus = parse_pages([page(9, "alpha\n<<mystery=private words>>\nbeta\n")])
    assert [s.text for s in corpus.segments] == ["alpha", "beta"]
    (problem,) = corpus.problems
    assert (problem.code, problem.page, problem.line) == ("unknown_directive", 9, 2)
    assert "<<mystery>>" in problem.message
    assert "private words" not in problem.message


def test_commentary_directives_are_reported_and_kept_out_of_the_corpus() -> None:
    corpus = parse_pages([page(1, "<<my_title=A Title>>\n<<chsum=A summary.>>\nalpha\n")])
    assert [s.text for s in corpus.segments] == ["alpha"]
    assert [p.code for p in corpus.problems] == ["commentary_directive"] * 2
    assert all("A Title" not in p.message and "summary" not in p.message for p in corpus.problems)


def test_unbalanced_regions_are_reported() -> None:
    never_closed = parse_pages([page(1, "<<top_bar>>\nalpha\n")])
    assert [(p.code, p.page, p.line) for p in never_closed.problems] == [
        ("region_not_closed", 1, 1)
    ]
    never_opened = parse_pages([page(1, "alpha\n<<bottom_bar>>\n")])
    assert [(p.code, p.page, p.line) for p in never_opened.problems] == [("region_not_open", 1, 2)]


def test_a_marker_inside_a_line_of_text_is_kept_and_reported_without_the_text() -> None:
    corpus = parse_pages([page(2, "alpha <<chapter=I>> beta\n")])
    assert corpus.segments[0].text == "alpha <<chapter=I>> beta"
    (problem,) = corpus.problems
    assert (problem.code, problem.page, problem.line) == ("marker_in_text", 2, 1)
    assert "alpha" not in problem.message


def test_directive_meanings_are_configuration() -> None:
    fmt = CorpusFormat(
        directives={"part": DirectiveRule(furniture="chapter_number", division="part")}
    )
    corpus = parse_pages([page(1, "<<part=One>>\nalpha\n<<chapter=I>>\n")], fmt)
    assert [(d.kind, d.label) for d in corpus.divisions] == [("part", "One")]
    assert [p.code for p in corpus.problems] == ["unknown_directive"]


def test_text_is_nfc_normalized_and_offsets_count_code_points() -> None:
    decomposed = "café \U0001d11e\nnext\n"  # e + combining acute; a non-BMP character
    corpus = parse_pages([page(1, decomposed)])
    segment = corpus.segments[0]
    assert segment.text == "café \U0001d11e next"
    assert [line.start_offset for line in segment.lines] == [0, 7]
    assert segment.text[7:] == "next"


def test_surrounding_whitespace_windows_line_ends_and_a_bom_are_ignored() -> None:
    source = paged_corpus.PageSource(1, "x", "﻿  alpha  \r\n\tbeta\r\n".encode())
    assert [s.text for s in parse_pages([source]).segments] == ["alpha beta"]


def test_an_empty_page_is_reported() -> None:
    corpus = parse_pages([page(1, "alpha\n\n"), page(2, "\n"), page(3, "beta\n")])
    assert [(p.code, p.page) for p in corpus.problems] == [("empty_page", 2)]
    assert corpus.pages == [1, 2, 3]


def test_summary_counts_pages_text_lines_paragraphs_and_chapters() -> None:
    corpus = parse_pages([page(4, "<<chapter=IV>>\n<<top_bar>>\nsyn\n<<bottom_bar>>\na\nb\n\nc\n")])
    summary = corpus.summary()
    assert (summary.pages, summary.lines, summary.paragraphs, summary.chapters) == (1, 4, 2, 1)
    assert (summary.first_page, summary.last_page) == (4, 4)


def test_read_folder_orders_files_by_page_number_from_the_pattern(tmp_path: Path) -> None:
    for name in ("B_corp_p010.txt", "B_corp_p9.txt", "B_comm_p009.txt", "notes.md"):
        (tmp_path / name).write_text("x\n", "utf-8")
    (tmp_path / "B_corp_p011_ch2.txt").write_text("x\n", "utf-8")  # a suffix after the page
    assert [(s.page, s.name) for s in read_folder(tmp_path)] == [
        (9, "B_corp_p9.txt"),
        (10, "B_corp_p010.txt"),
        (11, "B_corp_p011_ch2.txt"),
    ]
    custom = read_folder(tmp_path, r"_comm_p(?P<page>\d+)\.txt$")
    assert [s.page for s in custom] == [9]


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [("(", "not a valid expression"), (r"p(\d+)", "must capture the page number")],
)
def test_read_folder_rejects_bad_patterns(tmp_path: Path, pattern: str, expected: str) -> None:
    with pytest.raises(InvalidInput, match=expected):
        read_folder(tmp_path, pattern)


def test_read_folder_explains_missing_folders_empty_folders_and_duplicates(tmp_path: Path) -> None:
    with pytest.raises(InvalidInput, match="no folder"):
        read_folder(tmp_path / "absent")
    with pytest.raises(InvalidInput, match="No page files"):
        read_folder(tmp_path)
    (tmp_path / "A_corp_p1.txt").write_text("x\n", "utf-8")
    (tmp_path / "A_corp_p01.txt").write_text("x\n", "utf-8")
    with pytest.raises(InvalidInput, match="Two files claim page 1"):
        read_folder(tmp_path)


def test_a_file_that_is_not_utf8_is_named_not_quoted() -> None:
    source = paged_corpus.PageSource(3, "B_corp_p003.txt", b"caf\xe9\n")
    with pytest.raises(InvalidInput, match=r"B_corp_p003\.txt is not UTF-8"):
        parse_pages([source])


def test_content_hash_depends_on_bytes_and_page_numbers() -> None:
    base = paged_corpus.content_hash([page(1, "a\n"), page(2, "b\n")])
    assert base == paged_corpus.content_hash([page(1, "a\n"), page(2, "b\n")])
    assert base != paged_corpus.content_hash([page(1, "a\n"), page(2, "c\n")])
    assert base != paged_corpus.content_hash([page(1, "a\n"), page(3, "b\n")])


def test_fixture_book_matches_its_golden_segments() -> None:
    corpus = parse_pages(read_folder(BOOK))
    assert corpus.problems == []
    summary = corpus.summary()
    assert (summary.pages, summary.chapters, summary.first_page, summary.last_page) == (6, 2, 7, 12)
    assert_matches_golden("book_corpus.json", corpus_as_json(corpus))
