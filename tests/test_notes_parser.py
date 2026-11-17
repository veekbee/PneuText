from __future__ import annotations

from typing import Any

import pytest

from pneutext.notes import parse


def paragraph(*children: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "children": list(children)}


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


def body(source: str) -> list[dict[str, Any]]:
    tree = parse(source)
    assert tree["type"] == "document"
    return tree["children"]


def test_an_empty_body_is_an_empty_document() -> None:
    assert parse("") == {"type": "document", "children": []}


def test_paragraphs_and_inline_formatting() -> None:
    assert body("Plain *soft* and **loud** and `code`.\n\nSecond.") == [
        paragraph(
            text("Plain "),
            {"type": "emphasis", "children": [text("soft")]},
            text(" and "),
            {"type": "strong", "children": [text("loud")]},
            text(" and "),
            {"type": "code", "text": "code"},
            text("."),
        ),
        paragraph(text("Second.")),
    ]


def test_headings_quotes_lists_rules_and_code_blocks() -> None:
    nodes = body("## Title\n\n> said\n\n- a\n- b\n\n3. c\n\n---\n\n```py\nx = 1\n```\n")
    assert nodes == [
        {"type": "heading", "attrs": {"level": 2}, "children": [text("Title")]},
        {"type": "blockquote", "children": [paragraph(text("said"))]},
        {
            "type": "bullet_list",
            "children": [
                {"type": "list_item", "children": [paragraph(text("a"))]},
                {"type": "list_item", "children": [paragraph(text("b"))]},
            ],
        },
        {
            "type": "ordered_list",
            "attrs": {"start": 3},
            "children": [{"type": "list_item", "children": [paragraph(text("c"))]}],
        },
        {"type": "thematic_break"},
        {"type": "code_block", "attrs": {"info": "py"}, "text": "x = 1\n"},
    ]


def test_links_images_and_line_breaks() -> None:
    nodes = body('See [the *map*](https://example.test/a "Map").  \nNext\nline ![a **pic**](p.png)')
    assert nodes == [
        paragraph(
            text("See "),
            {
                "type": "link",
                "attrs": {"href": "https://example.test/a", "title": "Map"},
                "children": [text("the "), {"type": "emphasis", "children": [text("map")]}],
            },
            text("."),
            {"type": "hardbreak"},
            text("Next"),
            {"type": "softbreak"},
            text("line "),
            {"type": "image", "attrs": {"src": "p.png", "alt": "a pic", "title": ""}},
        )
    ]


def test_raw_html_is_kept_as_text_never_as_markup() -> None:
    nodes = body('<script>alert(1)</script>\n\nA <b onclick="x()">bold</b> claim.')
    assert nodes == [
        paragraph(text("<script>alert(1)</script>")),
        paragraph(text('A <b onclick="x()">bold</b> claim.')),
    ]


def test_unsafe_link_targets_are_not_links() -> None:
    (node,) = body("[click](javascript:alert(1))")
    assert all(child["type"] == "text" for child in node["children"])


def test_every_node_uses_only_the_documented_keys() -> None:
    def check(node: dict[str, Any]) -> None:
        assert set(node) <= {"type", "text", "attrs", "children"}
        for child in node.get("children", []):
            check(child)

    check(parse("# H\n\n- *a* [b](c) `d`\n\n> ![e](f)\n\n```\ng\n```"))


def form(source: str) -> dict[str, Any]:
    (node,) = body(source)
    (only,) = node["children"]
    return only


def test_references_to_pages_lines_and_ranges() -> None:
    assert form("{{bn:292}}") == {
        "type": "reference",
        "attrs": {"work": "bn", "target": "292"},
        "text": "{{bn:292}}",
    }
    assert form("{{bn:292-293}}")["attrs"]["target"] == "292-293"
    assert form("{{bn:45.12}}")["attrs"]["target"] == "45.12"
    assert form("{{ bn : 45.12-46.3 }}")["attrs"] == {"work": "bn", "target": "45.12-46.3"}


def test_references_to_notes_and_figures() -> None:
    assert form("{{note:123}}")["attrs"] == {"id": 123}
    assert form("{{note:123}}")["type"] == "note_ref"
    assert form("{{fig:tang}}") == {
        "type": "figure_ref",
        "attrs": {"label": "tang"},
        "text": "{{fig:tang}}",
    }


def test_a_placed_figure() -> None:
    assert form("![A *fine* map](fig:tang)") == {
        "type": "figure",
        "attrs": {"label": "tang", "caption": "A fine map"},
    }


def test_a_gloss_has_a_word_and_a_meaning() -> None:
    assert form("{{gloss:camino|road, way}}")["attrs"] == {"word": "camino", "meaning": "road, way"}
    assert form("{{gloss:camino|a | b}}")["attrs"]["meaning"] == "a | b"


def test_forms_sit_inside_running_text_and_formatting() -> None:
    (node,) = body("See *{{bn:45}}* and {{note:7}}.")
    kinds = [child["type"] for child in node["children"]]
    assert kinds == ["text", "emphasis", "text", "note_ref", "text"]
    assert node["children"][1]["children"][0]["type"] == "reference"


def test_a_citation_is_reserved_and_reported_as_unsupported() -> None:
    assert form("{{cite:smith1999}}") == {
        "type": "unsupported",
        "attrs": {"form": "cite", "key": "smith1999"},
        "text": "{{cite:smith1999}}",
    }


@pytest.mark.parametrize(
    "source",
    [
        "{{nope}}",
        "{{bn:9-2}}",
        "{{bn:}}",
        "{{note:abc}}",
        "{{gloss:|meaning}}",
        "{{BN:45}}",
        "{{fig:}}",
    ],
)
def test_a_form_that_is_not_understood_is_kept_and_marked_broken(source: str) -> None:
    assert form(source) == {"type": "broken", "text": source}


def test_unclosed_or_multi_line_braces_are_ordinary_text() -> None:
    assert body("{{bn:45 and more") == [paragraph(text("{{bn:45 and more"))]
    assert body("a {single} brace") == [paragraph(text("a {single} brace"))]


def test_a_paragraph_starting_todo_is_an_editorial_remark() -> None:
    assert body("A note.\n\nTODO: check *this*\nand that\n\nMore.") == [
        paragraph(text("A note.")),
        {
            "type": "todo",
            "children": [
                text("check "),
                {"type": "emphasis", "children": [text("this")]},
                {"type": "softbreak"},
                text("and that"),
            ],
        },
        paragraph(text("More.")),
    ]
    assert body("TODO:") == [{"type": "todo", "children": []}]


def test_todo_elsewhere_in_a_paragraph_is_not_a_remark() -> None:
    assert body("Not a TODO: here")[0]["type"] == "paragraph"
    assert body("todo: lower case")[0]["type"] == "paragraph"
