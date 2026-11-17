"""The single write path for segment text.

Every write of ``segment.text`` goes through this module. When source editing arrives,
this is where the old text is recorded, the sequence numbers are bumped and anchors are
re-located; nothing else may write the column.
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
