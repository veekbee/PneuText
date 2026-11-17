"""Review: working through notes by chapter, type, level, status and tag, and the to-do list."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pneutext import notes as note_parser
from pneutext.core.errors import InvalidInput, NotFound
from pneutext.services import entities as entities_service
from pneutext.services import figures as figures_service
from pneutext.services import links as links_service
from pneutext.store import corpus as corpus_store
from pneutext.store import db
from pneutext.store import figures as figures_store
from pneutext.store import notes as notes_store
from pneutext.store.corpus import VersionRow
from pneutext.store.library import Library
from pneutext.store.notes import NoteRow

EXCERPT = 160


@dataclass(frozen=True)
class NoteFilter:
    division_id: int | None = None
    type_id: int | None = None
    level: int | None = None
    status: str | None = None
    tag: str | None = None


@dataclass(frozen=True)
class NoteSummary:
    """A note as a row in a list: where it is and how it begins."""

    id: int
    type_id: int
    scope: str
    level: int
    status: str
    tags: list[str]
    page: int | None
    line_no: int | None
    excerpt: str


@dataclass(frozen=True)
class TodoRemark:
    note: NoteSummary
    text: str


@dataclass(frozen=True)
class BrokenReference:
    note: NoteSummary
    form: str  # the reference as typed, such as {{bn:999}}


@dataclass(frozen=True)
class UnvaluedTime:
    mention_id: int
    page: int | None
    line_no: int | None


@dataclass(frozen=True)
class UnusedFigure:
    id: int
    label: str
    caption: str


@dataclass(frozen=True)
class TodoList:
    remarks: list[TodoRemark]  # every TODO: remark
    drafts: list[NoteSummary]  # every draft note
    broken_references: list[BrokenReference]
    orphaned: list[NoteSummary]  # notes whose anchor lost its place in the text
    unused_figures: list[UnusedFigure]
    times_without_value: list[UnvaluedTime]


def _require_version(conn: sqlite3.Connection, version_id: int) -> VersionRow:
    version = corpus_store.get_version(conn, version_id)
    if version is None:
        raise NotFound(f"There is no text with id {version_id} in this library.")
    return version


def _summary(conn: sqlite3.Connection, version: VersionRow, note: NoteRow) -> NoteSummary:
    located = notes_store.locate(
        conn, version.pagination_id, note.anchor.start_segment_id, note.anchor.start_offset
    )
    page, line = located if located is not None else (None, None)
    plain = " ".join(note.body_md.split())
    excerpt = plain[:EXCERPT] + ("…" if len(plain) > EXCERPT else "")
    return NoteSummary(
        note.id, note.type_id, note.scope, note.level, note.status, note.tags, page, line, excerpt
    )


def list_notes(library: Library, version_id: int, wanted: NoteFilter) -> list[NoteSummary]:
    """Notes of a version passing every filter, in reading order."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        within = None
        if wanted.division_id is not None:
            within = notes_store.division_range(conn, version.id, wanted.division_id)
            if within is None:
                raise NotFound("That chapter is not in this text.")
        rows = notes_store.find_notes(
            conn,
            version.id,
            within=within,
            type_id=wanted.type_id,
            level=wanted.level,
            status=wanted.status,
            tag=wanted.tag,
        )
        return [_summary(conn, version, row) for row in rows]


def set_status(library: Library, version_id: int, note_ids: list[int], status: str) -> int:
    """Mark several notes draft or ready at once."""
    if status not in ("draft", "ready"):
        raise InvalidInput("A note's status is draft or ready.")
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        return notes_store.set_status(conn, version.id, note_ids, status)


def list_tags(library: Library) -> list[str]:
    with db.transaction(library.db_path) as conn:
        return notes_store.list_tags(conn)


def _plain(node: note_parser.Node) -> str:
    if "text" in node and node["type"] in ("text", "code", "code_block"):
        return str(node["text"])
    if node["type"] in ("softbreak", "hardbreak"):
        return " "
    if "children" in node:
        return "".join(_plain(child) for child in node["children"])
    return str(node.get("text") or "")


def _walk(node: note_parser.Node) -> list[note_parser.Node]:
    found = [node]
    for child in node.get("children", []):
        found.extend(_walk(child))
    return found


def todo_list(library: Library, version_id: int) -> TodoList:
    """Everything still to be dealt with before a text's notes can be published."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        notes = notes_store.find_notes(conn, version.id)
        summaries = {note.id: _summary(conn, version, note) for note in notes}

        remarks: list[TodoRemark] = []
        broken: list[BrokenReference] = []
        for note in notes:
            if (
                "TODO:" not in note.body_md
                and "{{" not in note.body_md
                and "fig:" not in note.body_md
            ):
                continue
            at = (note.anchor.start_position, note.anchor.start_offset)
            tree = links_service.resolve_tree(conn, version, note_parser.parse(note.body_md), at)
            for node in _walk(tree):
                if node["type"] == "todo":
                    remarks.append(TodoRemark(summaries[note.id], " ".join(_plain(node).split())))
                elif node["type"] in ("broken", "unsupported") or (
                    (node.get("attrs") or {}).get("broken") is True
                ):
                    form = str(node.get("text") or "")
                    if node["type"] == "figure":
                        attrs = node.get("attrs") or {}
                        form = f"![{attrs.get('caption', '')}](fig:{attrs.get('label', '')})"
                    broken.append(BrokenReference(summaries[note.id], form))

        unused = [
            UnusedFigure(view.figure.id, view.figure.label, view.figure.caption)
            for view in (
                figures_service._view(conn, library, row)
                for row in figures_store.list_figures(conn)
            )
            if not view.uses
        ]
        times = [
            UnvaluedTime(row.mention_id, row.page, row.line_no)
            for row in entities_service._chronology(conn, version)
            if row.kind is None
        ]
        return TodoList(
            remarks=remarks,
            drafts=[summaries[note.id] for note in notes if note.status == "draft"],
            broken_references=broken,
            orphaned=[
                _summary(conn, version, note)
                for note in notes_store.orphaned_notes(conn, version.id)
            ],
            unused_figures=unused,
            times_without_value=times,
        )
