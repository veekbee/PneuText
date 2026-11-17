"""Notes: creating, editing and listing annotations anchored to the text."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from pneutext import notes as note_parser
from pneutext.core import anchors
from pneutext.core.anchors import AnchorQuote, LineGeometry
from pneutext.core.corpus import TEXT_KINDS
from pneutext.core.errors import Conflict, InvalidInput, NotFound
from pneutext.core.shape import ShapeHighlight
from pneutext.services import links as links_service
from pneutext.services.extents import WHOLE_UNIT, chapter_extent, page_extent
from pneutext.services.links import Backlink
from pneutext.store import corpus as corpus_store
from pneutext.store import db
from pneutext.store import links as links_store
from pneutext.store import notes as notes_store
from pneutext.store.corpus import LineShapeRow, VersionRow
from pneutext.store.library import Library
from pneutext.store.notes import NoteRow, NoteTypeRow, ReadingRange

SCOPES = ("span", "page", "chapter")
STATUSES = ("draft", "ready")
LEVELS = (1, 2)


@dataclass(frozen=True)
class SpanInput:
    """A span as the client sends it: where it runs, and the words it believes it covers."""

    start_segment_id: int
    start_offset: int
    end_segment_id: int
    end_offset: int
    exact: str


@dataclass(frozen=True)
class NewNote:
    type_id: int
    scope: str = "span"
    level: int = 1
    status: str = "draft"
    body_md: str = ""
    tags: list[str] = field(default_factory=list)
    span: SpanInput | None = None  # for scope "span"
    page: int | None = None  # for scope "page"
    division_id: int | None = None  # for scope "chapter"


@dataclass(frozen=True)
class NoteChanges:
    """Fields to change; ``None`` leaves a field as it is."""

    type_id: int | None = None
    level: int | None = None
    status: str | None = None
    body_md: str | None = None
    tags: list[str] | None = None
    span: SpanInput | None = None  # re-select the passage without retyping the note


@dataclass(frozen=True)
class Place:
    """Where a point of the text falls in print."""

    page: int
    line_no: int | None


@dataclass(frozen=True)
class NoteView:
    note: NoteRow
    body: note_parser.Node  # parsed, with each reference resolved against the library
    start: Place | None
    end: Place | None
    backlinks: list[Backlink]  # the notes that refer to this one


def _require_version(conn: sqlite3.Connection, version_id: int) -> VersionRow:
    version = corpus_store.get_version(conn, version_id)
    if version is None:
        raise NotFound(f"There is no text with id {version_id} in this library.")
    return version


def _check_fields(
    conn: sqlite3.Connection, type_id: int | None, level: int | None, status: str | None
) -> None:
    if type_id is not None and not notes_store.note_type_exists(conn, type_id):
        raise InvalidInput("That note type does not exist.")
    if level is not None and level not in LEVELS:
        raise InvalidInput("A note's level is 1 (first reading) or 2 (have read).")
    if status is not None and status not in STATUSES:
        raise InvalidInput("A note's status is draft or ready.")


def _clean_tags(tags: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for tag in tags:
        name = " ".join(tag.split())
        if name:
            seen.setdefault(name)
    return list(seen)


def _validated_span(conn: sqlite3.Connection, version_id: int, span: SpanInput) -> AnchorQuote:
    segments = notes_store.segments_between(
        conn, version_id, span.start_segment_id, span.end_segment_id
    )
    return anchors.validate_span(segments, span.start_offset, span.end_offset, span.exact)


def _view(conn: sqlite3.Connection, note: NoteRow) -> NoteView:
    version = _require_version(conn, note.anchor.version_id)
    anchor = note.anchor

    def place(segment_id: int, offset: int) -> Place | None:
        found = notes_store.locate(conn, version.pagination_id, segment_id, offset)
        return None if found is None else Place(*found)

    return NoteView(
        note=note,
        body=links_service.resolve_tree(
            conn,
            version,
            note_parser.parse(note.body_md),
            (anchor.start_position, anchor.start_offset),
        ),
        start=place(anchor.start_segment_id, anchor.start_offset),
        # The end is exclusive, so the last character covered is one before it.
        end=place(anchor.end_segment_id, max(anchor.end_offset - 1, 0)),
        backlinks=links_service.backlinks_to_note(conn, version, note.id),
    )


def _require_note(conn: sqlite3.Connection, note_id: int) -> NoteRow:
    note = notes_store.get_note(conn, note_id)
    if note is None:
        raise NotFound("That note no longer exists.")
    return note


def list_note_types(library: Library) -> list[NoteTypeRow]:
    with db.transaction(library.db_path) as conn:
        return notes_store.list_note_types(conn)


def render_body(
    library: Library, body_md: str, version_id: int | None, note_id: int | None = None
) -> note_parser.Node:
    """Parse a note body for the editor's live preview, resolving its references.

    Given the note being edited, the dynamic date forms are worked out for its place.
    """
    tree = note_parser.parse(body_md)
    if version_id is None:
        return tree
    with db.transaction(library.db_path) as conn:
        note = None if note_id is None else notes_store.get_note(conn, note_id)
        at = None if note is None else (note.anchor.start_position, note.anchor.start_offset)
        return links_service.resolve_tree(conn, _require_version(conn, version_id), tree, at)


# ---- Note types are data: the author can add, rename, recolor and merge them ----

ROLES = ("note", "definition", "chapter_title", "chapter_summary")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_CODE = re.compile(r"[a-z][a-z0-9]*")


def _check_type_fields(
    conn: sqlite3.Connection,
    type_id: int | None,
    name: str | None,
    code: str | None,
    color: str | None,
    role: str | None,
) -> None:
    existing = [t for t in notes_store.list_note_types(conn) if t.id != type_id]
    if name is not None:
        if not name.strip():
            raise InvalidInput("Give the note type a name.")
        if any(t.name.lower() == name.strip().lower() for t in existing):
            raise Conflict(f"There is already a note type called {name.strip()}.")
    if code is not None:
        if not _CODE.fullmatch(code):
            raise InvalidInput("A type's code is lower-case letters and digits, such as cl.")
        if any(t.code == code for t in existing):
            raise Conflict(f"Another note type already uses the code {code}.")
    if color is not None and not _COLOR.fullmatch(color):
        raise InvalidInput("A color is written as #rrggbb.")
    if role is not None and role not in ROLES:
        raise InvalidInput("A note type is a note, a definition, a chapter title or a summary.")


def _require_type(conn: sqlite3.Connection, type_id: int) -> NoteTypeRow:
    found = notes_store.get_note_type(conn, type_id)
    if found is None:
        raise NotFound("That note type no longer exists.")
    return found


def create_note_type(library: Library, name: str, code: str, color: str, role: str) -> NoteTypeRow:
    with db.transaction(library.db_path) as conn:
        _check_type_fields(conn, None, name, code, color, role)
        type_id = notes_store.insert_note_type(conn, name.strip(), code, color, role)
        return _require_type(conn, type_id)


def update_note_type(
    library: Library,
    type_id: int,
    name: str | None = None,
    code: str | None = None,
    color: str | None = None,
    role: str | None = None,
) -> NoteTypeRow:
    with db.transaction(library.db_path) as conn:
        _require_type(conn, type_id)
        _check_type_fields(conn, type_id, name, code, color, role)
        changes: dict[str, object] = {
            key: value
            for key, value in (
                ("name", name.strip() if name is not None else None),
                ("code", code),
                ("color", color),
                ("role", role),
            )
            if value is not None
        }
        notes_store.update_note_type(conn, type_id, changes)
        return _require_type(conn, type_id)


def merge_note_type(library: Library, source_id: int, target_id: int) -> None:
    """Give one type's notes to another type and remove it."""
    with db.transaction(library.db_path) as conn:
        _require_type(conn, source_id)
        _require_type(conn, target_id)
        if source_id == target_id:
            raise InvalidInput("Choose a different note type to merge into.")
        notes_store.merge_note_type(conn, source_id, target_id)


def create_note(library: Library, version_id: int, new: NewNote) -> NoteView:
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        _check_fields(conn, new.type_id, new.level, new.status)
        if not notes_store.note_type_exists(conn, new.type_id):
            raise InvalidInput("That note type does not exist.")

        if new.scope == "span":
            if new.span is None:
                raise InvalidInput("Select the passage the note attaches to.")
            span = new.span
            anchor_id = notes_store.insert_anchor(
                conn,
                version.id,
                span.start_segment_id,
                span.start_offset,
                span.end_segment_id,
                span.end_offset,
                _validated_span(conn, version.id, span),
            )
        elif new.scope == "page":
            extent = None if new.page is None else page_extent(conn, version, new.page)
            if extent is None:
                raise InvalidInput("Say which page the note is about.")
            anchor_id = notes_store.insert_anchor(conn, version.id, *extent, WHOLE_UNIT)
        elif new.scope == "chapter":
            extent = (
                None if new.division_id is None else chapter_extent(conn, version, new.division_id)
            )
            if extent is None:
                raise InvalidInput("Say which chapter the note is about.")
            anchor_id = notes_store.insert_anchor(conn, version.id, *extent, WHOLE_UNIT)
        else:
            raise InvalidInput("A note attaches to a passage, a page or a chapter.")

        note_id = notes_store.insert_annotation(
            conn, anchor_id, new.type_id, new.scope, new.level, new.status, new.body_md
        )
        notes_store.set_tags(conn, note_id, _clean_tags(new.tags))
        links_service.refresh_inline_links(conn, version, note_id, new.body_md)
        return _view(conn, _require_note(conn, note_id))


def update_note(library: Library, note_id: int, changes: NoteChanges) -> NoteView:
    with db.transaction(library.db_path) as conn:
        note = _require_note(conn, note_id)
        _check_fields(conn, changes.type_id, changes.level, changes.status)
        if changes.span is not None:
            if note.scope != "span":
                raise InvalidInput("Only a note on a passage can be moved to another passage.")
            span = changes.span
            notes_store.move_anchor(
                conn,
                note.anchor.id,
                span.start_segment_id,
                span.start_offset,
                span.end_segment_id,
                span.end_offset,
                _validated_span(conn, note.anchor.version_id, span),
            )
        fields = {
            name: value
            for name in ("type_id", "level", "status", "body_md")
            if (value := getattr(changes, name)) is not None
        }
        notes_store.update_annotation(conn, note_id, fields)
        if changes.tags is not None:
            notes_store.set_tags(conn, note_id, _clean_tags(changes.tags))
        if changes.body_md is not None:
            # Inline links are derived: saving re-parses the body and replaces them, so
            # backlinks never go stale.
            version = _require_version(conn, note.anchor.version_id)
            links_service.refresh_inline_links(conn, version, note_id, changes.body_md)
        return _view(conn, _require_note(conn, note_id))


def delete_note(library: Library, note_id: int) -> None:
    with db.transaction(library.db_path) as conn:
        _require_note(conn, note_id)
        # Its links go with it. A note that referred to this one keeps its reference,
        # which now shows as broken.
        notes_store.delete_annotation(conn, note_id)
        links_store.delete_unowned_anchors(conn)


def get_note(library: Library, note_id: int) -> NoteView:
    with db.transaction(library.db_path) as conn:
        return _view(conn, _require_note(conn, note_id))


def page_range(lines: list[LineShapeRow]) -> ReadingRange:
    """The stretch of text a page's lines cover, in reading order."""
    first, last = lines[0], lines[-1]
    return ReadingRange(
        first.position, first.start_offset, last.position, last.start_offset + last.length
    )


def page_highlights(
    conn: sqlite3.Connection, version_id: int, lines: list[LineShapeRow]
) -> list[list[ShapeHighlight]]:
    """For each line of a page, where notes' spans cross it. Reads geometry only."""
    if not lines:
        return []
    spans = notes_store.spans_in_range(conn, version_id, page_range(lines))
    geometry = [
        LineGeometry(line.position, line.start_offset, line.length, line.kind in TEXT_KINDS)
        for line in lines
    ]
    return anchors.line_highlights(geometry, spans)


def list_page_notes(library: Library, version_id: int, page: int) -> list[NoteView]:
    """The notes to show beside a page, in reading order of their spans."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        lines = corpus_store.page_line_shapes(conn, version.pagination_id, page)
        if not lines:
            raise NotFound(f"This text has no page {page}.")
        rows = notes_store.notes_in_range(conn, version.id, page_range(lines))
        return [_view(conn, row) for row in rows]
