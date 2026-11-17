"""The note-body parser: CommonMark Markdown to a JSON-ready syntax tree.

One parser feeds both the in-app view and the monograph export. Raw HTML in note bodies
is disabled: it arrives in the tree as plain text and is never rendered as markup.

Every node is a dict with a ``type``; containers have ``children``, leaves that carry
words have ``text``, and anything else a node needs sits in ``attrs``.
"""

from __future__ import annotations

from typing import Any

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

Node = dict[str, Any]

_MARKDOWN = MarkdownIt("commonmark", {"html": False})

# markdown-it node type -> PneuText node type, for nodes that only wrap children.
_CONTAINERS = {
    "paragraph": "paragraph",
    "blockquote": "blockquote",
    "bullet_list": "bullet_list",
    "list_item": "list_item",
    "em": "emphasis",
    "strong": "strong",
}


def parse(body_md: str) -> Node:
    """Parse a note body into its syntax tree."""
    root = SyntaxTreeNode(_MARKDOWN.parse(body_md))
    return {"type": "document", "children": _children(root)}


def _children(node: SyntaxTreeNode) -> list[Node]:
    result: list[Node] = []
    for child in node.children:
        result.extend(_convert(child))
    return _merge_text(result)


def _merge_text(nodes: list[Node]) -> list[Node]:
    merged: list[Node] = []
    for node in nodes:
        if node["type"] == "text" and merged and merged[-1]["type"] == "text":
            merged[-1] = {"type": "text", "text": merged[-1]["text"] + node["text"]}
        elif node["type"] != "text" or node["text"]:
            merged.append(node)
    return merged


def _convert(node: SyntaxTreeNode) -> list[Node]:
    kind = node.type
    if kind == "inline":
        return _children(node)
    if kind == "text":
        return [{"type": "text", "text": node.content}]
    if kind in _CONTAINERS:
        return [{"type": _CONTAINERS[kind], "children": _children(node)}]
    if kind == "heading":
        level = int(node.tag[1:])
        return [{"type": "heading", "attrs": {"level": level}, "children": _children(node)}]
    if kind == "ordered_list":
        start = int(node.attrs.get("start", 1))
        return [{"type": "ordered_list", "attrs": {"start": start}, "children": _children(node)}]
    if kind in ("fence", "code_block"):
        info = node.info.strip() if kind == "fence" else ""
        return [{"type": "code_block", "attrs": {"info": info}, "text": node.content}]
    if kind == "code_inline":
        return [{"type": "code", "text": node.content}]
    if kind == "hr":
        return [{"type": "thematic_break"}]
    if kind == "softbreak":
        return [{"type": "softbreak"}]
    if kind == "hardbreak":
        return [{"type": "hardbreak"}]
    if kind == "link":
        attrs = {"href": str(node.attrs.get("href", "")), "title": str(node.attrs.get("title", ""))}
        return [{"type": "link", "attrs": attrs, "children": _children(node)}]
    if kind == "image":
        attrs = {
            "src": str(node.attrs.get("src", "")),
            "alt": _plain_text(node),
            "title": str(node.attrs.get("title", "")),
        }
        return [{"type": "image", "attrs": attrs}]
    if kind in ("html_block", "html_inline"):
        # Unreachable while HTML is disabled; kept so HTML could never become markup.
        return [{"type": "text", "text": node.content}]
    # An unknown construct keeps its words rather than vanishing.
    if node.children:
        return _children(node)
    return [{"type": "text", "text": node.content}] if node.content else []


def _plain_text(node: SyntaxTreeNode) -> str:
    if node.type in ("text", "code_inline"):
        return node.content
    return "".join(_plain_text(child) for child in node.children)
