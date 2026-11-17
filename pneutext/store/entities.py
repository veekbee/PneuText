"""Storage for entity categories, entities and mentions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryRow:
    id: int
    name: str
    color: str
    sort: int
    is_time: bool


@dataclass(frozen=True)
class MentionRow:
    id: int
    category: str
    entity: str | None
    value: str | None
    start_segment_id: int
    start_offset: int
    end_segment_id: int
    end_offset: int


# New categories take the next of these colors in turn.
_CATEGORY_COLORS = ("#8a7f5b", "#5b7f9a", "#9a5b8c", "#6a8f6a", "#a0764f", "#6f6f9c")


def list_categories(conn: sqlite3.Connection) -> list[CategoryRow]:
    rows = conn.execute(
        "SELECT id, name, color, sort, is_time FROM entity_category ORDER BY sort, id"
    ).fetchall()
    return [
        CategoryRow(row["id"], row["name"], row["color"], row["sort"], bool(row["is_time"]))
        for row in rows
    ]


def insert_category(conn: sqlite3.Connection, name: str) -> int:
    count, top = conn.execute(
        "SELECT COUNT(*), COALESCE(MAX(sort), 0) FROM entity_category"
    ).fetchone()
    cursor = conn.execute(
        "INSERT INTO entity_category (name, color, sort) VALUES (?, ?, ?)",
        (name, _CATEGORY_COLORS[count % len(_CATEGORY_COLORS)], top + 10),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def find_or_create_entity(
    conn: sqlite3.Connection, category_id: int, name: str, value: str | None
) -> tuple[int, bool]:
    """The entity a mention belongs to, and whether it had to be created.

    A mention with a normalized value belongs to the entity with that value; otherwise
    to the entity with that name, compared without regard to case.
    """
    if value is not None:
        row = conn.execute(
            "SELECT id FROM entity WHERE category_id = ? AND value = ? ORDER BY id LIMIT 1",
            (category_id, value),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM entity WHERE category_id = ? AND LOWER(name) = LOWER(?)"
            " ORDER BY id LIMIT 1",
            (category_id, name),
        ).fetchone()
    if row is not None:
        return row["id"], False
    taken = conn.execute(
        "SELECT 1 FROM entity WHERE category_id = ? AND name = ?", (category_id, name)
    ).fetchone()
    if taken is not None and value is not None:
        name = f"{name} ({value})"  # same words, different value: keep the two apart
    cursor = conn.execute(
        "INSERT INTO entity (category_id, name, value) VALUES (?, ?, ?)",
        (category_id, name, value),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid, True


def insert_mention(
    conn: sqlite3.Connection, anchor_id: int, category_id: int, entity_id: int | None
) -> int:
    cursor = conn.execute(
        "INSERT INTO mention (anchor_id, category_id, entity_id) VALUES (?, ?, ?)",
        (anchor_id, category_id, entity_id),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def list_mentions(conn: sqlite3.Connection, version_id: int) -> list[MentionRow]:
    """Every mention in a version, in reading order."""
    rows = conn.execute(
        """
        SELECT m.id, c.name AS category, e.name AS entity, e.value,
               k.start_segment_id, k.start_offset, k.end_segment_id, k.end_offset
        FROM mention m
        JOIN anchor k ON k.id = m.anchor_id
        JOIN segment s ON s.id = k.start_segment_id
        JOIN entity_category c ON c.id = m.category_id
        LEFT JOIN entity e ON e.id = m.entity_id
        WHERE k.version_id = ?
        ORDER BY s.position, k.start_offset, m.id
        """,
        (version_id,),
    ).fetchall()
    return [MentionRow(**dict(row)) for row in rows]
