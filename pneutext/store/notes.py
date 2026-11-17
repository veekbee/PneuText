"""Storage for anchors, note types, annotations and tags."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pneutext.core.anchors import AnchorQuote, SegmentText, Span


@dataclass(frozen=True)
class NoteTypeRow:
    id: int
    name: str
    code: str
    color: str
    sort: int
    role: str


@dataclass(frozen=True)
class AnchorRow:
    id: int
    version_id: int
    start_segment_id: int
    start_offset: int
    end_segment_id: int
    end_offset: int
    status: str


@dataclass(frozen=True)
class NoteRow:
    id: int
    type_id: int
    scope: str
    level: int
    status: str
    body_md: str
    legacy_id: str | None
    created_at: str
    updated_at: str
    anchor: AnchorRow
    tags: list[str]


@dataclass(frozen=True)
class ReadingRange:
    """A stretch of text in reading order: (segment position, offset) to the same, exclusive."""

    start_position: int
    start_offset: int
    end_position: int
    end_offset: int


_NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def list_note_types(conn: sqlite3.Connection) -> list[NoteTypeRow]:
    rows = conn.execute(
        "SELECT id, name, code, color, sort, role FROM note_type ORDER BY sort, id"
    ).fetchall()
    return [NoteTypeRow(**dict(row)) for row in rows]


def note_type_exists(conn: sqlite3.Connection, type_id: int) -> bool:
    return conn.execute("SELECT 1 FROM note_type WHERE id = ?", (type_id,)).fetchone() is not None


def segments_between(
    conn: sqlite3.Connection, version_id: int, start_segment_id: int, end_segment_id: int
) -> list[SegmentText]:
    """Every segment from one to another, in reading order; empty if that is not a span."""
    rows = conn.execute(
        """
        SELECT s.id, s.position, s.text
        FROM segment s
        JOIN segment a ON a.id = :start AND a.version_id = :version
        JOIN segment b ON b.id = :end AND b.version_id = :version
        WHERE s.version_id = :version AND s.position BETWEEN a.position AND b.position
        ORDER BY s.position
        """,
        {"version": version_id, "start": start_segment_id, "end": end_segment_id},
    ).fetchall()
    return [SegmentText(row["id"], row["position"], row["text"]) for row in rows]


def division_extent(
    conn: sqlite3.Connection, version_id: int, division_id: int
) -> tuple[int, int, int] | None:
    """A division's first segment, last segment, and that last segment's length."""
    row = conn.execute(
        """
        SELECT d.first_segment_id AS first_id, last.id AS last_id, LENGTH(last.text) AS last_length
        FROM division d
        JOIN segment first ON first.id = d.first_segment_id
        JOIN segment last ON last.version_id = d.version_id
        WHERE d.id = :division AND d.version_id = :version
          AND last.position = (
              SELECT MAX(s.position) FROM segment s
              WHERE s.version_id = d.version_id
                AND s.position < COALESCE(
                    (SELECT MIN(n.position) FROM division other
                       JOIN segment n ON n.id = other.first_segment_id
                      WHERE other.version_id = d.version_id AND other.kind = d.kind
                        AND n.position > first.position),
                    9223372036854775807)
          )
        """,
        {"division": division_id, "version": version_id},
    ).fetchone()
    return None if row is None else (row["first_id"], row["last_id"], row["last_length"])


def insert_anchor(
    conn: sqlite3.Connection,
    version_id: int,
    start_segment_id: int,
    start_offset: int,
    end_segment_id: int,
    end_offset: int,
    quote: AnchorQuote,
) -> int:
    cursor = conn.execute(
        "INSERT INTO anchor (version_id, start_segment_id, start_offset, end_segment_id,"
        " end_offset, exact, prefix, suffix, resolved_seq)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, (SELECT edit_seq FROM version WHERE id = ?))",
        (
            version_id,
            start_segment_id,
            start_offset,
            end_segment_id,
            end_offset,
            quote.exact,
            quote.prefix,
            quote.suffix,
            version_id,
        ),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def move_anchor(
    conn: sqlite3.Connection,
    anchor_id: int,
    start_segment_id: int,
    start_offset: int,
    end_segment_id: int,
    end_offset: int,
    quote: AnchorQuote,
) -> None:
    conn.execute(
        "UPDATE anchor SET start_segment_id = ?, start_offset = ?, end_segment_id = ?,"
        " end_offset = ?, exact = ?, prefix = ?, suffix = ?, status = 'ok',"
        " resolved_seq = (SELECT edit_seq FROM version WHERE id = anchor.version_id)"
        " WHERE id = ?",
        (
            start_segment_id,
            start_offset,
            end_segment_id,
            end_offset,
            quote.exact,
            quote.prefix,
            quote.suffix,
            anchor_id,
        ),
    )


def insert_annotation(
    conn: sqlite3.Connection,
    anchor_id: int,
    type_id: int,
    scope: str,
    level: int,
    status: str,
    body_md: str,
    legacy_id: str | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO annotation (anchor_id, type_id, scope, level, status, body_md, legacy_id,"
        f" created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, {_NOW}, {_NOW})",
        (anchor_id, type_id, scope, level, status, body_md, legacy_id),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


_EDITABLE = ("type_id", "level", "status", "body_md")


def update_annotation(
    conn: sqlite3.Connection, annotation_id: int, changes: dict[str, object]
) -> None:
    """Change some of a note's own fields and stamp it as updated."""
    columns = [name for name in _EDITABLE if name in changes]
    assignments = ", ".join([f"{name} = ?" for name in columns] + [f"updated_at = {_NOW}"])
    conn.execute(
        f"UPDATE annotation SET {assignments} WHERE id = ?",
        (*[changes[name] for name in columns], annotation_id),
    )


def delete_annotation(conn: sqlite3.Connection, annotation_id: int) -> None:
    """Delete a note and its anchor (the anchor owns the row; tags go with it)."""
    conn.execute(
        "DELETE FROM anchor WHERE id = (SELECT anchor_id FROM annotation WHERE id = ?)",
        (annotation_id,),
    )


def set_tags(conn: sqlite3.Connection, annotation_id: int, names: list[str]) -> None:
    conn.execute("DELETE FROM annotation_tag WHERE annotation_id = ?", (annotation_id,))
    for name in names:
        conn.execute("INSERT OR IGNORE INTO tag (name) VALUES (?)", (name,))
        conn.execute(
            "INSERT INTO annotation_tag (annotation_id, tag_id)"
            " SELECT ?, id FROM tag WHERE name = ?",
            (annotation_id, name),
        )
    conn.execute("DELETE FROM tag WHERE id NOT IN (SELECT tag_id FROM annotation_tag)")


_NOTE_SELECT = """
    SELECT a.id, a.type_id, a.scope, a.level, a.status, a.body_md, a.legacy_id,
           a.created_at, a.updated_at,
           k.id AS anchor_id, k.version_id, k.start_segment_id, k.start_offset,
           k.end_segment_id, k.end_offset, k.status AS anchor_status,
           s1.position AS start_position, s2.position AS end_position
    FROM annotation a
    JOIN anchor k ON k.id = a.anchor_id
    JOIN segment s1 ON s1.id = k.start_segment_id
    JOIN segment s2 ON s2.id = k.end_segment_id
"""


def _note(conn: sqlite3.Connection, row: sqlite3.Row) -> NoteRow:
    tags = conn.execute(
        "SELECT t.name FROM tag t JOIN annotation_tag j ON j.tag_id = t.id"
        " WHERE j.annotation_id = ? ORDER BY t.name",
        (row["id"],),
    ).fetchall()
    return NoteRow(
        id=row["id"],
        type_id=row["type_id"],
        scope=row["scope"],
        level=row["level"],
        status=row["status"],
        body_md=row["body_md"],
        legacy_id=row["legacy_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        anchor=AnchorRow(
            id=row["anchor_id"],
            version_id=row["version_id"],
            start_segment_id=row["start_segment_id"],
            start_offset=row["start_offset"],
            end_segment_id=row["end_segment_id"],
            end_offset=row["end_offset"],
            status=row["anchor_status"],
        ),
        tags=[tag["name"] for tag in tags],
    )


def get_note(conn: sqlite3.Connection, annotation_id: int) -> NoteRow | None:
    row = conn.execute(_NOTE_SELECT + " WHERE a.id = ?", (annotation_id,)).fetchone()
    return None if row is None else _note(conn, row)


_OVERLAPS = """
    k.version_id = :version
    AND (s1.position, k.start_offset) < (:end_position, :end_offset)
    AND (s2.position, k.end_offset) > (:start_position, :start_offset)
"""


def _range_params(version_id: int, within: ReadingRange) -> dict[str, int]:
    return {
        "version": version_id,
        "start_position": within.start_position,
        "start_offset": within.start_offset,
        "end_position": within.end_position,
        "end_offset": within.end_offset,
    }


def notes_in_range(
    conn: sqlite3.Connection, version_id: int, within: ReadingRange
) -> list[NoteRow]:
    """Notes to list for a stretch of text, in reading order of their spans.

    Span and page notes are listed wherever their span reaches; a chapter note is listed
    only where it begins, not on every page of its chapter.
    """
    rows = conn.execute(
        _NOTE_SELECT
        + " WHERE "
        + _OVERLAPS
        + """
          AND (a.scope != 'chapter'
               OR (s1.position, k.start_offset) >= (:start_position, :start_offset))
        ORDER BY s1.position, k.start_offset, s2.position DESC, k.end_offset DESC, a.id
        """,
        _range_params(version_id, within),
    ).fetchall()
    return [_note(conn, row) for row in rows]


def spans_in_range(conn: sqlite3.Connection, version_id: int, within: ReadingRange) -> list[Span]:
    """The spans to draw as highlights over a stretch of text. Reads no text."""
    rows = conn.execute(
        """
        SELECT a.id, a.type_id, a.level, s1.position AS start_position, k.start_offset,
               s2.position AS end_position, k.end_offset
        FROM annotation a
        JOIN anchor k ON k.id = a.anchor_id
        JOIN segment s1 ON s1.id = k.start_segment_id
        JOIN segment s2 ON s2.id = k.end_segment_id
        WHERE a.scope = 'span' AND k.status = 'ok' AND
        """
        + _OVERLAPS,
        _range_params(version_id, within),
    ).fetchall()
    return [
        Span(
            annotation_id=row["id"],
            type_id=row["type_id"],
            level=row["level"],
            start_position=row["start_position"],
            start_offset=row["start_offset"],
            end_position=row["end_position"],
            end_offset=row["end_offset"],
        )
        for row in rows
    ]


def locate(
    conn: sqlite3.Connection, pagination_id: int, segment_id: int, offset: int
) -> tuple[int, int | None] | None:
    """The page and line number where an offset in a segment falls."""
    row = conn.execute(
        "SELECT page, line_no FROM line WHERE pagination_id = ? AND segment_id = ?"
        " AND start_offset <= ? ORDER BY start_offset DESC LIMIT 1",
        (pagination_id, segment_id, offset),
    ).fetchone()
    return None if row is None else (row["page"], row["line_no"])
