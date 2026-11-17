"""The note-body parser: CommonMark Markdown to a JSON-ready syntax tree.

One parser feeds both the in-app view and the monograph export. Raw HTML in note bodies
is disabled: it arrives in the tree as plain text and is never rendered as markup.

Every node is a dict with a ``type``; containers have ``children``, leaves that carry
words have ``text``, and anything else a node needs sits in ``attrs``.

Beyond CommonMark, a body may hold PneuText's own forms:

- ``{{bn:292}}``, ``{{bn:292-293}}``, ``{{bn:45.12}}``: a reference into the work ``bn``
- ``{{note:123}}``: a reference to another note
- ``![Caption](fig:tang)``: the figure labeled ``tang``, placed here
- ``{{fig:tang}}``: a reference to that figure
- ``{{gloss:word|meaning}}``: a foreign word with its translation
- a paragraph starting ``TODO:``: an editorial remark, never exported

The parser only reads syntax. Whether a reference leads anywhere is decided later, by
the service that knows the library.
"""

from __future__ import annotations

import re
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.tree import SyntaxTreeNode

from pneutext.core.references import parse_reference

Node = dict[str, Any]

_FORM_OPEN, _FORM_CLOSE = "{{", "}}"
_WORK_CODE = re.compile(r"[a-z][a-z0-9]*")
_FIGURE_SOURCE = "fig:"
_TODO = re.compile(r"TODO:\s*")


def _form_rule(state: StateInline, silent: bool) -> bool:
    """Recognize ``{{...}}``, PneuText's inline forms, as one token."""
    start = state.pos
    if not state.src.startswith(_FORM_OPEN, start):
        return False
    end = state.src.find(_FORM_CLOSE, start + len(_FORM_OPEN))
    if end == -1 or "\n" in state.src[start:end]:
        return False
    if not silent:
        token = state.push("pneu_form", "", 0)
        token.content = state.src[start + len(_FORM_OPEN) : end]
    state.pos = end + len(_FORM_CLOSE)
    return True


_MARKDOWN = MarkdownIt("commonmark", {"html": False})
_MARKDOWN.inline.ruler.before("emphasis", "pneu_form", _form_rule)

# markdown-it node type -> PneuText node type, for nodes that only wrap children.
_CONTAINERS = {
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
    if kind == "pneu_form":
        return [_form(node.content)]
    if kind == "paragraph":
        return [_paragraph(_children(node))]
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
        source = str(node.attrs.get("src", ""))
        if source.startswith(_FIGURE_SOURCE):
            # ![Caption](fig:label) places a figure from the library here.
            label = source[len(_FIGURE_SOURCE) :]
            return [{"type": "figure", "attrs": {"label": label, "caption": _plain_text(node)}}]
        attrs = {"src": source, "alt": _plain_text(node), "title": str(node.attrs.get("title", ""))}
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


def _paragraph(children: list[Node]) -> Node:
    """A paragraph, or an editorial remark if it starts with ``TODO:``."""
    first = children[0] if children else None
    if first is not None and first["type"] == "text":
        match = _TODO.match(first["text"])
        if match is not None:
            rest = first["text"][match.end() :]
            body = ([{"type": "text", "text": rest}] if rest else []) + children[1:]
            return {"type": "todo", "children": body}
    return {"type": "paragraph", "children": children}


def _form(content: str) -> Node:
    """One ``{{...}}`` form. Anything not understood is kept, marked as broken."""
    source = _FORM_OPEN + content + _FORM_CLOSE
    name, colon, rest = content.partition(":")
    name, rest = name.strip(), rest.strip()
    if colon and name == "note" and rest.isdigit():
        return {"type": "note_ref", "attrs": {"id": int(rest)}, "text": source}
    if colon and name == "fig" and rest:
        return {"type": "figure_ref", "attrs": {"label": rest}, "text": source}
    if colon and name == "gloss":
        word, bar, meaning = rest.partition("|")
        if bar and word.strip():
            attrs = {"word": word.strip(), "meaning": meaning.strip()}
            return {"type": "gloss", "attrs": attrs, "text": source}
    if colon and name == "cite" and rest:
        # Reserved for bibliography citations, which this version does not support.
        return {"type": "unsupported", "attrs": {"form": "cite", "key": rest}, "text": source}
    if colon and _WORK_CODE.fullmatch(name):
        reference = parse_reference(rest)
        if reference is not None:
            attrs = {"work": name, "target": str(reference)}
            return {"type": "reference", "attrs": attrs, "text": source}
    return {"type": "broken", "text": source}
