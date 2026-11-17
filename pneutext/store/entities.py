"""Storage for entity categories, entities and mentions."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pneutext.core.anchors import Span
from pneutext.store.notes import ReadingRange


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


# ---- Categories ---------------------------------------------------------------


def get_category(conn: sqlite3.Connection, category_id: int) -> CategoryRow | None:
    return next((c for c in list_categories(conn) if c.id == category_id), None)


def update_category(
    conn: sqlite3.Connection, category_id: int, name: str | None, color: str | None
) -> None:
    if name is not None:
        conn.execute("UPDATE entity_category SET name = ? WHERE id = ?", (name, category_id))
    if color is not None:
        conn.execute("UPDATE entity_category SET color = ? WHERE id = ?", (color, category_id))


def merge_category(conn: sqlite3.Connection, source_id: int, target_id: int) -> None:
    """Fold one category into another; entities of the same name become one entity."""
    for row in conn.execute(
        "SELECT id, name FROM entity WHERE category_id = ?", (source_id,)
    ).fetchall():
        twin = conn.execute(
            "SELECT id FROM entity WHERE category_id = ? AND LOWER(name) = LOWER(?)",
            (target_id, row["name"]),
        ).fetchone()
        if twin is None:
            conn.execute("UPDATE entity SET category_id = ? WHERE id = ?", (target_id, row["id"]))
        else:
            conn.execute(
                "UPDATE mention SET entity_id = ? WHERE entity_id = ?", (twin["id"], row["id"])
            )
            conn.execute("DELETE FROM entity WHERE id = ?", (row["id"],))
    conn.execute("UPDATE mention SET category_id = ? WHERE category_id = ?", (target_id, source_id))
    conn.execute("DELETE FROM entity_category WHERE id = ?", (source_id,))


# ---- Entities -------------------------------------------------------------------


@dataclass(frozen=True)
class EntityRow:
    id: int
    category_id: int
    name: str
    value: str | None


@dataclass(frozen=True)
class EntityPlace:
    entity_id: int
    mention_id: int
    page: int | None
    line_no: int | None


def get_entity(conn: sqlite3.Connection, entity_id: int) -> EntityRow | None:
    row = conn.execute(
        "SELECT id, category_id, name, value FROM entity WHERE id = ?", (entity_id,)
    ).fetchone()
    return None if row is None else EntityRow(**dict(row))


def list_entities(
    conn: sqlite3.Connection, category_id: int | None = None, starting: str | None = None
) -> list[EntityRow]:
    rows = conn.execute(
        """
        SELECT e.id, e.category_id, e.name, e.value
        FROM entity e JOIN entity_category c ON c.id = e.category_id
        WHERE (:category IS NULL OR e.category_id = :category)
          AND (:starting IS NULL OR LOWER(e.name) LIKE LOWER(:starting) || '%')
        ORDER BY c.sort, c.id, LOWER(e.name), e.id
        """,
        {"category": category_id, "starting": starting},
    ).fetchall()
    return [EntityRow(**dict(row)) for row in rows]


def entity_places(
    conn: sqlite3.Connection, version_id: int, pagination_id: int
) -> list[EntityPlace]:
    """Where each entity is mentioned in a version, in reading order."""
    rows = conn.execute(
        """
        SELECT m.entity_id, m.id AS mention_id,
               (SELECT l.page FROM line l
                 WHERE l.pagination_id = :pagination AND l.segment_id = k.start_segment_id
                   AND l.start_offset <= k.start_offset
                 ORDER BY l.start_offset DESC LIMIT 1) AS page,
               (SELECT l.line_no FROM line l
                 WHERE l.pagination_id = :pagination AND l.segment_id = k.start_segment_id
                   AND l.start_offset <= k.start_offset
                 ORDER BY l.start_offset DESC LIMIT 1) AS line_no
        FROM mention m
        JOIN anchor k ON k.id = m.anchor_id
        JOIN segment s ON s.id = k.start_segment_id
        WHERE k.version_id = :version AND m.entity_id IS NOT NULL
        ORDER BY s.position, k.start_offset, m.id
        """,
        {"version": version_id, "pagination": pagination_id},
    ).fetchall()
    return [EntityPlace(**dict(row)) for row in rows]


def update_entity(conn: sqlite3.Connection, entity_id: int, name: str, value: str | None) -> None:
    conn.execute("UPDATE entity SET name = ?, value = ? WHERE id = ?", (name, value, entity_id))


def name_taken(conn: sqlite3.Connection, category_id: int, name: str, except_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM entity WHERE category_id = ? AND name = ? AND id != ?",
        (category_id, name, except_id),
    ).fetchone()
    return row is not None


def merge_entity(conn: sqlite3.Connection, source_id: int, target_id: int) -> None:
    conn.execute("UPDATE mention SET entity_id = ? WHERE entity_id = ?", (target_id, source_id))
    conn.execute("DELETE FROM entity WHERE id = ?", (source_id,))


def delete_unused_entities(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM entity WHERE id NOT IN"
        " (SELECT entity_id FROM mention WHERE entity_id IS NOT NULL)"
    )


# ---- Mentions -------------------------------------------------------------------


@dataclass(frozen=True)
class MentionDetail:
    id: int
    anchor_id: int
    version_id: int
    category_id: int
    entity_id: int | None


def get_mention(conn: sqlite3.Connection, mention_id: int) -> MentionDetail | None:
    row = conn.execute(
        "SELECT m.id, m.anchor_id, k.version_id, m.category_id, m.entity_id"
        " FROM mention m JOIN anchor k ON k.id = m.anchor_id WHERE m.id = ?",
        (mention_id,),
    ).fetchone()
    return None if row is None else MentionDetail(**dict(row))


def delete_mention(conn: sqlite3.Connection, mention_id: int) -> None:
    """Delete a mention and its anchor (the anchor owns the row)."""
    conn.execute(
        "DELETE FROM anchor WHERE id = (SELECT anchor_id FROM mention WHERE id = ?)", (mention_id,)
    )


def mention_spans(conn: sqlite3.Connection, version_id: int, within: ReadingRange) -> list[Span]:
    """Mentions over a stretch of text, as spans: id = mention, type = category. No text."""
    rows = conn.execute(
        """
        SELECT m.id, m.category_id, s1.position AS start_position, k.start_offset,
               s2.position AS end_position, k.end_offset
        FROM mention m
        JOIN anchor k ON k.id = m.anchor_id
        JOIN segment s1 ON s1.id = k.start_segment_id
        JOIN segment s2 ON s2.id = k.end_segment_id
        WHERE k.version_id = :version AND k.status = 'ok'
          AND (s1.position, k.start_offset) < (:end_position, :end_offset)
          AND (s2.position, k.end_offset) > (:start_position, :start_offset)
        """,
        {
            "version": version_id,
            "start_position": within.start_position,
            "start_offset": within.start_offset,
            "end_position": within.end_position,
            "end_offset": within.end_offset,
        },
    ).fetchall()
    return [
        Span(
            annotation_id=row["id"],
            type_id=row["category_id"],
            level=1,
            start_position=row["start_position"],
            start_offset=row["start_offset"],
            end_position=row["end_position"],
            end_offset=row["end_offset"],
        )
        for row in rows
    ]


# ---- Time -------------------------------------------------------------------------


@dataclass(frozen=True)
class TimeMentionRow:
    """A time mention in reading order, with its value if it has one."""

    mention_id: int
    start_segment_id: int
    start_offset: int
    position: int  # its segment's place in reading order
    kind: str | None
    at: str | None
    offset: str | None
    relative_to_id: int | None
    label: str | None
    remark: str


def time_mentions(conn: sqlite3.Connection, version_id: int) -> list[TimeMentionRow]:
    rows = conn.execute(
        """
        SELECT m.id AS mention_id, k.start_segment_id, k.start_offset, s.position,
               t.kind, t.at, t."offset" AS "offset", t.relative_to_id, t.label,
               COALESCE(t.remark, '') AS remark
        FROM mention m
        JOIN entity_category c ON c.id = m.category_id AND c.is_time = 1
        JOIN anchor k ON k.id = m.anchor_id
        JOIN segment s ON s.id = k.start_segment_id
        LEFT JOIN time_point t ON t.mention_id = m.id
        WHERE k.version_id = ?
        ORDER BY s.position, k.start_offset, m.id
        """,
        (version_id,),
    ).fetchall()
    return [TimeMentionRow(**dict(row)) for row in rows]


def set_time_point(
    conn: sqlite3.Connection,
    mention_id: int,
    kind: str,
    at: str | None,
    offset: str | None,
    relative_to_id: int | None,
    label: str | None,
    remark: str,
) -> None:
    conn.execute(
        """
        INSERT INTO time_point (mention_id, kind, at, "offset", relative_to_id, label, remark)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (mention_id) DO UPDATE SET
            kind = excluded.kind, at = excluded.at, "offset" = excluded."offset",
            relative_to_id = excluded.relative_to_id, label = excluded.label,
            remark = excluded.remark
        """,
        (mention_id, kind, at, offset, relative_to_id, label, remark),
    )


def clear_time_point(conn: sqlite3.Connection, mention_id: int) -> None:
    conn.execute("DELETE FROM time_point WHERE mention_id = ?", (mention_id,))
