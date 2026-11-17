"""Storage for works, versions, segments, divisions and pagination."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pneutext.core.corpus import POSITION_STEP, TEXT_KINDS, ParsedCorpus
from pneutext.store.segments import insert_segment


@dataclass(frozen=True)
class NewVersion:
    work_code: str
    title: str
    author: str
    label: str
    language: str
    source_format: str
    content_hash: str


@dataclass(frozen=True)
class VersionRow:
    id: int
    work_code: str
    title: str
    author: str
    label: str
    language: str
    imported_at: str
    edit_seq: int
    pagination_id: int
    first_page: int | None
    last_page: int | None
    page_count: int


@dataclass(frozen=True)
class DivisionRow:
    id: int
    kind: str
    label: str
    page: int | None


@dataclass(frozen=True)
class LineShapeRow:
    """A print line without its words: everything the shape projection may know."""

    id: int
    segment_id: int
    position: int  # the segment's place in reading order
    kind: str
    page: int
    line_no: int | None
    start_offset: int
    length: int
    starts_paragraph: bool
    ends_paragraph: bool


@dataclass(frozen=True)
class LineTextRow:
    shape: LineShapeRow
    text: str


def insert_corpus(conn: sqlite3.Connection, new: NewVersion, corpus: ParsedCorpus) -> int:
    """Store a parsed corpus as a new version (and its work, if new). Returns the version id."""
    row = conn.execute("SELECT id FROM work WHERE code = ?", (new.work_code,)).fetchone()
    if row is None:
        cursor = conn.execute(
            "INSERT INTO work (code, title, author) VALUES (?, ?, ?)",
            (new.work_code, new.title, new.author),
        )
        work_id = cursor.lastrowid
    else:
        work_id = row["id"]

    cursor = conn.execute(
        "INSERT INTO version (work_id, label, language, source_format, content_hash, imported_at)"
        " VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))",
        (work_id, new.label, new.language, new.source_format, new.content_hash),
    )
    version_id = cursor.lastrowid
    assert version_id is not None
    cursor = conn.execute(
        "INSERT INTO pagination (version_id, label, is_default) VALUES (?, ?, 1)",
        (version_id, new.label),
    )
    pagination_id = cursor.lastrowid

    segment_ids: list[int] = []
    for index, segment in enumerate(corpus.segments, start=1):
        segment_id = insert_segment(
            conn, version_id, index * POSITION_STEP, segment.kind, segment.text
        )
        segment_ids.append(segment_id)
        conn.executemany(
            "INSERT INTO line (pagination_id, segment_id, start_offset, page, line_no)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (pagination_id, segment_id, line.start_offset, line.page, line.line_no)
                for line in segment.lines
            ],
        )
    conn.executemany(
        "INSERT INTO division (version_id, kind, label, first_segment_id) VALUES (?, ?, ?, ?)",
        [(version_id, d.kind, d.label, segment_ids[d.first_segment]) for d in corpus.divisions],
    )
    return version_id


def find_version_by_hash(conn: sqlite3.Connection, content_hash: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM version WHERE content_hash = ? ORDER BY id LIMIT 1", (content_hash,)
    ).fetchone()
    return None if row is None else row["id"]


_VERSION_SELECT = """
    SELECT v.id, w.code AS work_code, w.title, w.author, v.label, v.language, v.imported_at,
           v.edit_seq, p.id AS pagination_id,
           (SELECT MIN(page) FROM line WHERE pagination_id = p.id) AS first_page,
           (SELECT MAX(page) FROM line WHERE pagination_id = p.id) AS last_page,
           (SELECT COUNT(DISTINCT page) FROM line WHERE pagination_id = p.id) AS page_count
    FROM version v
    JOIN work w ON w.id = v.work_id
    JOIN pagination p ON p.version_id = v.id AND p.is_default = 1
"""


def list_versions(conn: sqlite3.Connection) -> list[VersionRow]:
    rows = conn.execute(_VERSION_SELECT + " ORDER BY w.title, v.id").fetchall()
    return [VersionRow(**dict(row)) for row in rows]


def get_version(conn: sqlite3.Connection, version_id: int) -> VersionRow | None:
    row = conn.execute(_VERSION_SELECT + " WHERE v.id = ?", (version_id,)).fetchone()
    return None if row is None else VersionRow(**dict(row))


def list_divisions(
    conn: sqlite3.Connection, version_id: int, pagination_id: int
) -> list[DivisionRow]:
    rows = conn.execute(
        """
        SELECT d.id, d.kind, d.label,
               (SELECT MIN(l.page) FROM line l
                 WHERE l.segment_id = d.first_segment_id AND l.pagination_id = ?) AS page
        FROM division d
        JOIN segment s ON s.id = d.first_segment_id
        WHERE d.version_id = ?
        ORDER BY s.position
        """,
        (pagination_id, version_id),
    ).fetchall()
    return [DivisionRow(**dict(row)) for row in rows]


def division_at_page(
    conn: sqlite3.Connection, version_id: int, pagination_id: int, page: int
) -> DivisionRow | None:
    """The division in force at the end of a page: the last one opened on or before it."""
    divisions = [d for d in list_divisions(conn, version_id, pagination_id) if d.page is not None]
    current = None
    for division in divisions:
        if division.page is not None and division.page <= page:
            current = division
    return current


def list_pages(conn: sqlite3.Connection, pagination_id: int) -> list[int]:
    rows = conn.execute(
        "SELECT DISTINCT page FROM line WHERE pagination_id = ? ORDER BY page", (pagination_id,)
    ).fetchall()
    return [row["page"] for row in rows]


def neighbouring_pages(
    conn: sqlite3.Connection, pagination_id: int, page: int
) -> tuple[int | None, int | None]:
    row = conn.execute(
        """
        SELECT (SELECT MAX(page) FROM line WHERE pagination_id = :p AND page < :page) AS prev,
               (SELECT MIN(page) FROM line WHERE pagination_id = :p AND page > :page) AS next
        """,
        {"p": pagination_id, "page": page},
    ).fetchone()
    return row["prev"], row["next"]


# Line geometry is derived without reading any text: a line ends where the next line of
# its segment starts (less the joining space), or at the end of the segment.
_LINE_SHAPE_SELECT = """
    SELECT id, segment_id, position, kind, page, line_no, start_offset,
           COALESCE(next_start - 1, segment_length) - start_offset AS length,
           start_offset = 0 AS starts_paragraph,
           next_start IS NULL AS ends_paragraph
    FROM (
        SELECT l.id, l.segment_id, s.kind, s.position, l.page, l.line_no, l.start_offset,
               LENGTH(s.text) AS segment_length,
               LEAD(l.start_offset) OVER (
                   PARTITION BY l.segment_id ORDER BY l.start_offset
               ) AS next_start
        FROM line l
        JOIN segment s ON s.id = l.segment_id
        WHERE l.pagination_id = :pagination_id {scope}
    )
"""


def _shape_row(row: sqlite3.Row) -> LineShapeRow:
    return LineShapeRow(
        id=row["id"],
        segment_id=row["segment_id"],
        position=row["position"],
        kind=row["kind"],
        page=row["page"],
        line_no=row["line_no"],
        start_offset=row["start_offset"],
        length=row["length"],
        starts_paragraph=bool(row["starts_paragraph"]),
        ends_paragraph=bool(row["ends_paragraph"]),
    )


def page_line_shapes(conn: sqlite3.Connection, pagination_id: int, page: int) -> list[LineShapeRow]:
    """The lines of one page, in reading order, with no text."""
    scope = (
        "AND l.segment_id IN (SELECT segment_id FROM line"
        " WHERE pagination_id = :pagination_id AND page = :page)"
    )
    rows = conn.execute(
        _LINE_SHAPE_SELECT.format(scope=scope)
        + " WHERE page = :page ORDER BY position, start_offset",
        {"pagination_id": pagination_id, "page": page},
    ).fetchall()
    return [_shape_row(row) for row in rows]


def page_line_texts(conn: sqlite3.Connection, pagination_id: int, page: int) -> list[LineTextRow]:
    """The lines of one page with their words: the text projection."""
    shapes = page_line_shapes(conn, pagination_id, page)
    segment_ids = sorted({shape.segment_id for shape in shapes})
    marks = ",".join("?" * len(segment_ids))
    texts = {
        row["id"]: row["text"]
        for row in conn.execute(f"SELECT id, text FROM segment WHERE id IN ({marks})", segment_ids)
    }
    return [
        LineTextRow(
            shape,
            texts[shape.segment_id][shape.start_offset : shape.start_offset + shape.length],
        )
        for shape in shapes
    ]


def line_at_offset(
    conn: sqlite3.Connection, pagination_id: int, segment_id: int, offset: int
) -> LineShapeRow | None:
    """The print line of a segment that an offset falls on (the last line at or before it)."""
    scope = "AND l.segment_id = :segment_id"
    rows = conn.execute(
        _LINE_SHAPE_SELECT.format(scope=scope)
        + " WHERE start_offset <= :offset ORDER BY start_offset DESC LIMIT 1",
        {"pagination_id": pagination_id, "segment_id": segment_id, "offset": offset},
    ).fetchall()
    return _shape_row(rows[0]) if rows else None


def newest_version_of_work(conn: sqlite3.Connection, work_code: str) -> VersionRow | None:
    row = conn.execute(
        _VERSION_SELECT + " WHERE w.code = ? ORDER BY v.id DESC LIMIT 1", (work_code,)
    ).fetchone()
    return None if row is None else VersionRow(**dict(row))


def text_line_lengths(conn: sqlite3.Connection, pagination_id: int) -> list[int]:
    """The length of every line of running text in a pagination (for the measure)."""
    kinds = ",".join(f"'{kind}'" for kind in sorted(TEXT_KINDS))
    rows = conn.execute(
        _LINE_SHAPE_SELECT.format(scope="") + f" WHERE kind IN ({kinds})",
        {"pagination_id": pagination_id},
    ).fetchall()
    return [row["length"] for row in rows]
