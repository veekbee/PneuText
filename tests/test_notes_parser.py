from __future__ import annotations

from typing import Any

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
