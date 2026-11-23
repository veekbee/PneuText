"""The single write path for segment text.

Every write of ``segment.text`` goes through this module; nothing else may write the
column. A change to stored text stamps the segment with the version's edit count, so
whatever depends on the text can tell that it moved.
"""

from __future__ import annotations

import sqlite3


def insert_segment(
    conn: sqlite3.Connection, version_id: int, position: int, kind: str, text: str
) -> int:
    cursor = conn.execute(
        "INSERT INTO segment (version_id, position, kind, text) VALUES (?, ?, ?, ?)",
        (version_id, position, kind, text),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def update_segment_text(conn: sqlite3.Connection, segment_id: int, text: str, seq: int) -> None:
    """Replace a segment's text. ``seq`` is the version's edit count after this edit."""
    conn.execute(
        "UPDATE segment SET text = ?, changed_seq = ? WHERE id = ?", (text, seq, segment_id)
    )
