"""Full-text search queries over the corpus and over note bodies."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentHit:
    segment_id: int
    text: str


@dataclass(frozen=True)
class NoteHit:
    note_id: int
    type_id: int
    level: int
    status: str
    body_md: str
    start_segment_id: int
    start_offset: int


def search_segments(
    conn: sqlite3.Connection, version_id: int, match: str, limit: int
) -> list[SegmentHit]:
    """Paragraphs of a version that match, in reading order. Returns corpus text."""
    rows = conn.execute(
        """
        SELECT s.id, s.text
        FROM segment_fts f
        JOIN segment s ON s.id = f.rowid
        WHERE segment_fts MATCH ? AND s.version_id = ?
        ORDER BY s.position
        LIMIT ?
        """,
        (match, version_id, limit),
    ).fetchall()
    return [SegmentHit(row["id"], row["text"]) for row in rows]


def search_notes(
    conn: sqlite3.Connection, version_id: int, match: str, limit: int
) -> list[NoteHit]:
    """Notes of a version whose bodies match, in reading order of their spans."""
    rows = conn.execute(
        """
        SELECT a.id AS note_id, a.type_id, a.level, a.status, a.body_md,
               k.start_segment_id, k.start_offset
        FROM note_fts f
        JOIN annotation a ON a.id = f.rowid
        JOIN anchor k ON k.id = a.anchor_id
        JOIN segment s ON s.id = k.start_segment_id
        WHERE note_fts MATCH ? AND k.version_id = ?
        ORDER BY s.position, k.start_offset, a.id
        LIMIT ?
        """,
        (match, version_id, limit),
    ).fetchall()
    return [NoteHit(**dict(row)) for row in rows]
