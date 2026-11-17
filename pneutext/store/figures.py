"""Storage for figures: rows here, image files in the library's figures/ folder."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class FigureRow:
    id: int
    label: str
    file: str
    caption: str
    credit: str


def upsert_figure(conn: sqlite3.Connection, label: str, file: str, caption: str) -> bool:
    """Create a figure, or refresh an existing one's file and caption. True if created.

    A caption the author has since edited is replaced only when the import brings one.
    """
    existing = conn.execute("SELECT id FROM figure WHERE label = ?", (label,)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO figure (label, file, caption) VALUES (?, ?, ?)", (label, file, caption)
        )
        return True
    conn.execute(
        "UPDATE figure SET file = ?, caption = CASE WHEN ? = '' THEN caption ELSE ? END"
        " WHERE id = ?",
        (file, caption, caption, existing["id"]),
    )
    return False


def get_figure(conn: sqlite3.Connection, label: str) -> FigureRow | None:
    row = conn.execute(
        "SELECT id, label, file, caption, credit FROM figure WHERE label = ?", (label,)
    ).fetchone()
    return None if row is None else FigureRow(**dict(row))


def list_figures(conn: sqlite3.Connection) -> list[FigureRow]:
    rows = conn.execute(
        "SELECT id, label, file, caption, credit FROM figure ORDER BY label"
    ).fetchall()
    return [FigureRow(**dict(row)) for row in rows]
