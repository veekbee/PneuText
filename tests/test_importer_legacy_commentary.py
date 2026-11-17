from __future__ import annotations

from pneutext.importers.legacy_commentary import (
    CommentaryFormat,
    ParsedPage,
    Position,
    parse_page,
)
from pneutext.importers.paged_corpus import PageSource


def parse(text: str, page: int = 45, fmt: CommentaryFormat | None = None) -> ParsedPage:
    return parse_page(PageSource(page, f"T_comm_p{page:03d}.txt", text.encode("utf-8")), fmt)


def codes(parsed: ParsedPage) -> list[tuple[str, int | None, str]]:
    return [(p.code, p.line, p.tag) for p in parsed.problems]


def test_inline_markup_is_stripped_and_spans_are_located_in_the_stripped_text() -> None:
    parsed = parse("alpha {c_p45_one}beta gamma{c_p45_one/} delta\n")
    assert [line.text for line in parsed.lines] == ["alpha beta gamma delta"]
    (span,) = parsed.spans
    assert (span.id, span.start, span.end) == ("c_p45_one", Position(0, 6), Position(0, 16))
    assert parsed.problems == []


def test_spans_cross_lines_nest_and_partly_overlap() -> None:
    parsed = parse(
        "{c_p45_outer}alpha {h_p45_inner}beta{h_p45_inner/}\n"
        "gamma{c_p45_outer/} {m_p45_a}delta {l_p45_b}epsilon{m_p45_a/} zeta{l_p45_b/}\n"
    )
    assert [line.text for line in parsed.lines] == ["alpha beta", "gamma delta epsilon zeta"]
    found = {span.id: (span.start, span.end) for span in parsed.spans}
    assert found == {
        "c_p45_outer": (Position(0, 0), Position(1, 5)),
        "h_p45_inner": (Position(0, 6), Position(0, 10)),
        "m_p45_a": (Position(1, 6), Position(1, 19)),
        "l_p45_b": (Position(1, 12), Position(1, 24)),
    }
    assert parsed.problems == []


def test_columns_count_code_points() -> None:
    parsed = parse("caf\u00e9 \U0001d11e {c_p45_x}mark{c_p45_x/}\n")
    assert parsed.spans[0].start == Position(0, 7)


def test_entity_tags_with_and_without_a_value() -> None:
    parsed = parse("at |places|Some Town|| were |numbers=46|forty-six|| of them\n")
    assert [line.text for line in parsed.lines] == ["at Some Town were forty-six of them"]
    assert [(e.category, e.value, e.start.column, e.end.column) for e in parsed.entities] == [
        ("places", None, 3, 12),
        ("numbers", "46", 18, 27),
    ]


def test_an_entity_may_sit_inside_a_span_and_cross_a_line() -> None:
    parsed = parse("{c_p45_x}the |places|Some\nTown|| itself{c_p45_x/}\n")
    (entity,) = parsed.entities
    assert (entity.start, entity.end) == (Position(0, 4), Position(1, 4))
    assert parsed.spans[0].end == Position(1, 11)


def test_layout_directives_are_skipped_and_chapter_matter_is_kept() -> None:
    parsed = parse(
        "<<chapter=IV>>\n<<my_title=A Title>>\n<<chsum=A summary that\nruns on.>>\n<<top_bar>>\n"
        "alpha\n<<bottom_bar>>\nbeta\n"
    )
    assert [line.text for line in parsed.lines] == ["alpha", "beta"]
    assert [(m.role, m.body, m.file_line) for m in parsed.chapter_matter] == [
        ("chapter_title", "A Title", 2),
        ("chapter_summary", "A summary that runs on.", 3),
    ]


def test_note_blocks_with_optional_type_and_level() -> None:
    parsed = parse(
        "{c_p45_a}x{c_p45_a/} {h_p45_b}y{h_p45_b/} {m_p45_c}z{m_p45_c/}\n\n@@ Metatext\n\n"
        "{c_p45_a}, Comment, 2\nFirst body.\n\nSecond paragraph.\n{c_p45_a/}\n\n"
        "{h_p45_b}\nNo header fields.\n{h_p45_b/}\n"
        "{m_p45_c}, 2, Meditation\nOrder does not matter. {m_p45_c/}\n"
    )
    assert [(b.id, b.type_name, b.level, b.body) for b in parsed.blocks] == [
        ("c_p45_a", "Comment", 2, "First body.\n\nSecond paragraph."),
        ("h_p45_b", None, None, "No header fields."),
        ("m_p45_c", "Meditation", 2, "Order does not matter."),
    ]
    assert [(b.file_line, b.body_line) for b in parsed.blocks] == [(5, 6), (11, 12), (14, 15)]
    assert parsed.problems == [] and parsed.remarks == []


def test_note_bodies_may_hold_braces_that_are_not_tags() -> None:
    parsed = parse(
        "{c_p45_a}x{c_p45_a/}\n\n@@ Metatext\n\n{c_p45_a}\n"
        "See {{bn:292-293}} and \\textbf{bold}.\n{aside}\n{c_p45_a/}\n"
    )
    assert parsed.blocks[0].body == "See {{bn:292-293}} and \\textbf{bold}.\n{aside}"
    assert parsed.problems == []


def test_a_closing_tag_missing_its_slash_is_repaired_in_text_and_in_metatext() -> None:
    parsed = parse("{c_p45_a}x{c_p45_a} y\n\n@@ Metatext\n\n{c_p45_a}\nBody.\n{c_p45_a}\n")
    assert parsed.spans[0].end == Position(0, 1)
    assert parsed.blocks[0].body == "Body."
    assert [(r.code, r.line, r.tag) for r in parsed.repairs] == [
        ("closing_tag_slash", 1, "{c_p45_a}"),
        ("closing_tag_slash", 7, "{c_p45_a}"),
    ]
    assert parsed.problems == []


def test_unclosed_and_stray_tags_are_reported_by_tag_page_and_line() -> None:
    parsed = parse("alpha{c_p45_gone/} {c_p45_open}beta\ngamma || {c_p45_half delta\n")
    assert [line.text for line in parsed.lines] == ["alpha beta", "gamma  {c_p45_half delta"]
    assert codes(parsed) == [
        ("stray_closing_tag", 1, "{c_p45_gone/}"),
        ("stray_entity_end", 2, "||"),
        ("malformed_tag", 2, "{c_p45_half"),
        ("unclosed_span", 1, "{c_p45_open}"),
    ]
    assert parsed.spans[0].end is None


def test_an_entity_left_open_is_reported() -> None:
    parsed = parse("|places|Some Town |animals|heron||\n|plants|reeds\n")
    assert codes(parsed) == [("unclosed_entity", 1, "|places|"), ("unclosed_entity", 2, "|plants|")]
    assert [e.category for e in parsed.entities] == ["animals"]


def test_an_unclosed_block_ends_where_the_next_begins_or_the_file_ends() -> None:
    parsed = parse(
        "{c_p45_a}x{c_p45_a/} {c_p45_b}y{c_p45_b/}\n\n@@ Metatext\n\n"
        "{c_p45_a}, Comment\nFirst.\n{c_p45_b}, Comment\nSecond.\n"
    )
    assert [(b.id, b.body) for b in parsed.blocks] == [
        ("c_p45_a", "First."),
        ("c_p45_b", "Second."),
    ]
    assert codes(parsed) == [("unclosed_block", 5, "{c_p45_a}"), ("unclosed_block", 7, "{c_p45_b}")]


def test_a_closing_tag_for_another_id_closes_nothing() -> None:
    parsed = parse(
        "{c_p45_a}x{c_p45_a/}\n\n@@ Metatext\n\n{c_p45_a}\nBody.\n{c_p45_z/}\nMore.\n{c_p45_a/}\n"
    )
    assert parsed.blocks[0].body == "Body.\nMore."
    assert codes(parsed) == [("stray_closing_tag", 7, "{c_p45_z/}")]


def test_text_outside_any_block_becomes_remarks_one_per_paragraph() -> None:
    parsed = parse(
        "x\n\n@@ Metatext\n\nXXX first remark\nstill the first\n\n% second remark\n\n"
        "{c_p45_a}, Comment\nBody.\n{c_p45_a/} trailing words\n"
    )
    assert [(r.body, r.file_line) for r in parsed.remarks] == [
        ("XXX first remark\nstill the first", 5),
        ("% second remark", 8),
        ("trailing words", 12),
    ]


def test_duplicate_ids_and_odd_header_fields_are_reported() -> None:
    parsed = parse(
        "{c_p45_a}x{c_p45_a/} {c_p45_a}y{c_p45_a/}\n\n@@ Metatext\n\n"
        "{c_p45_a}, Comment, 2, 3, Extra\nOne.\n{c_p45_a/}\n{c_p45_a}\nTwo.\n{c_p45_a/}\n"
    )
    assert codes(parsed) == [
        ("duplicate_id", 1, "{c_p45_a}"),
        ("odd_header_field", 5, "3"),
        ("odd_header_field", 5, "Extra"),
        ("duplicate_id", 8, "{c_p45_a}"),
    ]
    assert len(parsed.spans) == 2 and len(parsed.blocks) == 2


def test_a_file_without_a_metatext_marker_is_all_text() -> None:
    parsed = parse("alpha |places|Town||\nbeta\n")
    assert [line.text for line in parsed.lines] == ["alpha Town", "beta"]
    assert parsed.blocks == [] and parsed.problems == []


def test_problems_never_carry_the_text_around_a_tag() -> None:
    parsed = parse("secret words {c_p45_open}more secret\n\n@@ Metatext\n\nXXX private remark\n")
    for problem in parsed.problems:
        assert "secret" not in problem.tag and "private" not in problem.tag


def test_the_marker_and_chapter_directives_are_configuration() -> None:
    fmt = CommentaryFormat(metatext_marker=r"--- notes ---", chapter_matter={"epigraph": "note"})
    parsed = parse(
        "<<epigraph=Words>>\nalpha\n--- NOTES ---\n{c_p45_a}, Comment\nB.\n{c_p45_a/}\n", fmt=fmt
    )
    assert [line.text for line in parsed.lines] == ["alpha"]
    assert [(m.role, m.body) for m in parsed.chapter_matter] == [("note", "Words")]
    assert [b.id for b in parsed.blocks] == ["c_p45_a"]
