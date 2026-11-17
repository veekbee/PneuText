"""Storage for cross-references between notes and passages."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pneutext.store.notes import ReadingRange


@dataclass(frozen=True)
class NoteBacklinkRow:
    """A note that refers to something: enough to list it as a backlink."""

    note_id: int
    type_id: int
    level: int
    status: str
    start_segment_id: int
    start_offset: int
    # For a reference to a passage: where that passage is.
    target_start_segment_id: int | None = None
    target_start_offset: int | None = None
    target_end_segment_id: int | None = None
    target_end_offset: int | None = None


@dataclass(frozen=True)
class PassageLinkRow:
    """A link made passage to passage, with both ends."""

    id: int
    relation: str
    source: tuple[int, int, int, int]  # start segment, start offset, end segment, end offset
    target: tuple[int, int, int, int]
    source_here: bool
    target_here: bool


def delete_unowned_anchors(conn: sqlite3.Connection) -> None:
    """Remove anchors that no note, mention or link holds any more."""
    conn.execute(
        """
        DELETE FROM anchor
        WHERE id NOT IN (SELECT anchor_id FROM annotation)
          AND id NOT IN (SELECT anchor_id FROM mention)
          AND id NOT IN (SELECT source_anchor_id FROM link WHERE source_anchor_id IS NOT NULL)
          AND id NOT IN (SELECT target_anchor_id FROM link WHERE target_anchor_id IS NOT NULL)
        """
    )


def delete_inline_links(conn: sqlite3.Connection, annotation_id: int) -> None:
    """Drop the references a note's body made, ready to be derived again."""
    conn.execute(
        "DELETE FROM link WHERE source_annotation_id = ? AND origin = 'inline'", (annotation_id,)
    )
    delete_unowned_anchors(conn)


def insert_link(
    conn: sqlite3.Connection,
    *,
    origin: str,
    relation: str = "reference",
    source_annotation_id: int | None = None,
    source_anchor_id: int | None = None,
    target_annotation_id: int | None = None,
    target_anchor_id: int | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO link (source_annotation_id, source_anchor_id, target_annotation_id,"
        " target_anchor_id, relation, origin) VALUES (?, ?, ?, ?, ?, ?)",
        (
            source_annotation_id,
            source_anchor_id,
            target_annotation_id,
            target_anchor_id,
            relation,
            origin,
        ),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def delete_manual_link(conn: sqlite3.Connection, link_id: int) -> bool:
    cursor = conn.execute("DELETE FROM link WHERE id = ? AND origin = 'manual'", (link_id,))
    delete_unowned_anchors(conn)
    return cursor.rowcount > 0


_SOURCE_NOTE = """
    SELECT a.id AS note_id, a.type_id, a.level, a.status,
           sk.start_segment_id, sk.start_offset
"""


def backlinks_to_note(conn: sqlite3.Connection, annotation_id: int) -> list[NoteBacklinkRow]:
    """The notes whose bodies refer to a note, in reading order."""
    rows = conn.execute(
        _SOURCE_NOTE
        + """
        FROM link l
        JOIN annotation a ON a.id = l.source_annotation_id
        JOIN anchor sk ON sk.id = a.anchor_id
        JOIN segment ss ON ss.id = sk.start_segment_id
        WHERE l.target_annotation_id = ?
        GROUP BY a.id
        ORDER BY ss.position, sk.start_offset, a.id
        """,
        (annotation_id,),
    ).fetchall()
    return [NoteBacklinkRow(**dict(row)) for row in rows]


def backlinks_to_range(
    conn: sqlite3.Connection, version_id: int, within: ReadingRange
) -> list[NoteBacklinkRow]:
    """The notes whose bodies refer to a passage that reaches into a stretch of text."""
    rows = conn.execute(
        _SOURCE_NOTE
        + """,
               tk.start_segment_id AS target_start_segment_id,
               tk.start_offset AS target_start_offset,
               tk.end_segment_id AS target_end_segment_id,
               tk.end_offset AS target_end_offset
        FROM link l
        JOIN annotation a ON a.id = l.source_annotation_id
        JOIN anchor sk ON sk.id = a.anchor_id
        JOIN segment ss ON ss.id = sk.start_segment_id
        JOIN anchor tk ON tk.id = l.target_anchor_id
        JOIN segment t1 ON t1.id = tk.start_segment_id
        JOIN segment t2 ON t2.id = tk.end_segment_id
        WHERE tk.version_id = :version
          AND (t1.position, tk.start_offset) < (:end_position, :end_offset)
          AND (t2.position, tk.end_offset) > (:start_position, :start_offset)
        ORDER BY ss.position, sk.start_offset, a.id, t1.position, tk.start_offset
        """,
        {
            "version": version_id,
            "start_position": within.start_position,
            "start_offset": within.start_offset,
            "end_position": within.end_position,
            "end_offset": within.end_offset,
        },
    ).fetchall()
    return [NoteBacklinkRow(**dict(row)) for row in rows]


def passage_links_in_range(
    conn: sqlite3.Connection, version_id: int, within: ReadingRange
) -> list[PassageLinkRow]:
    """Links made passage to passage with either end in a stretch of text."""
    overlap = """
        ({k}.version_id = :version
         AND ({a}.position, {k}.start_offset) < (:end_position, :end_offset)
         AND ({b}.position, {k}.end_offset) > (:start_position, :start_offset))
    """
    source_here = overlap.format(k="sk", a="s1", b="s2")
    target_here = overlap.format(k="tk", a="t1", b="t2")
    rows = conn.execute(
        f"""
        SELECT l.id, l.relation,
               sk.start_segment_id AS s_a, sk.start_offset AS s_b,
               sk.end_segment_id AS s_c, sk.end_offset AS s_d,
               tk.start_segment_id AS t_a, tk.start_offset AS t_b,
               tk.end_segment_id AS t_c, tk.end_offset AS t_d,
               {source_here} AS source_here, {target_here} AS target_here
        FROM link l
        JOIN anchor sk ON sk.id = l.source_anchor_id
        JOIN segment s1 ON s1.id = sk.start_segment_id
        JOIN segment s2 ON s2.id = sk.end_segment_id
        JOIN anchor tk ON tk.id = l.target_anchor_id
        JOIN segment t1 ON t1.id = tk.start_segment_id
        JOIN segment t2 ON t2.id = tk.end_segment_id
        WHERE l.origin = 'manual' AND ({source_here} OR {target_here})
        ORDER BY s1.position, sk.start_offset, l.id
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
        PassageLinkRow(
            id=row["id"],
            relation=row["relation"],
            source=(row["s_a"], row["s_b"], row["s_c"], row["s_d"]),
            target=(row["t_a"], row["t_b"], row["t_c"], row["t_d"]),
            source_here=bool(row["source_here"]),
            target_here=bool(row["target_here"]),
        )
        for row in rows
    ]
