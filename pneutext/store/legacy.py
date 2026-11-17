"""A record of what legacy commentary imports produced, page by page."""

from __future__ import annotations

import sqlite3


def count_items(conn: sqlite3.Connection, version_id: int, pages: list[int]) -> tuple[int, int]:
    """How many notes and mentions earlier imports of these pages left behind."""
    marks = ",".join("?" * len(pages))
    row = conn.execute(
        f"SELECT COUNT(annotation_id), COUNT(mention_id) FROM legacy_item"
        f" WHERE version_id = ? AND page IN ({marks})",
        (version_id, *pages),
    ).fetchone()
    return row[0], row[1]


def delete_items(conn: sqlite3.Connection, version_id: int, pages: list[int]) -> None:
    """Remove what earlier imports of these pages produced. Notes made in the app stay."""
    marks = ",".join("?" * len(pages))
    scope = f"version_id = ? AND page IN ({marks})"
    params = (version_id, *pages)
    # Deleting an anchor removes its note or mention, and with it the record here.
    conn.execute(
        f"""
        DELETE FROM anchor WHERE id IN (
            SELECT a.anchor_id FROM legacy_item i JOIN annotation a ON a.id = i.annotation_id
             WHERE i.{scope}
            UNION
            SELECT m.anchor_id FROM legacy_item i JOIN mention m ON m.id = i.mention_id
             WHERE i.{scope}
        )
        """,
        (*params, *params),
    )
    conn.execute("DELETE FROM tag WHERE id NOT IN (SELECT tag_id FROM annotation_tag)")


def record_annotation(
    conn: sqlite3.Connection, version_id: int, page: int, annotation_id: int
) -> None:
    conn.execute(
        "INSERT INTO legacy_item (version_id, page, annotation_id) VALUES (?, ?, ?)",
        (version_id, page, annotation_id),
    )


def record_mention(conn: sqlite3.Connection, version_id: int, page: int, mention_id: int) -> None:
    conn.execute(
        "INSERT INTO legacy_item (version_id, page, mention_id) VALUES (?, ?, ?)",
        (version_id, page, mention_id),
    )
