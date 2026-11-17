"""Stretches of text that whole units cover, shared by notes, references and imports."""

from __future__ import annotations

import sqlite3

from pneutext.core.anchors import AnchorQuote
from pneutext.store import corpus as corpus_store
from pneutext.store import notes as notes_store
from pneutext.store.corpus import VersionRow

WHOLE_UNIT = AnchorQuote(exact="", prefix="", suffix="")
"""A page or chapter anchor quotes nothing: a whole unit is not re-located by quotation."""

Extent = tuple[int, int, int, int]
"""Start segment, start offset, end segment, end offset."""


def page_extent(conn: sqlite3.Connection, version: VersionRow, page: int) -> Extent | None:
    """The stretch of text a page covers."""
    lines = corpus_store.page_line_shapes(conn, version.pagination_id, page)
    if not lines:
        return None
    first, last = lines[0], lines[-1]
    return first.segment_id, first.start_offset, last.segment_id, last.start_offset + last.length


def line_extent(
    conn: sqlite3.Connection, version: VersionRow, page: int, line_no: int
) -> Extent | None:
    """The stretch of text one numbered print line covers."""
    for line in corpus_store.page_line_shapes(conn, version.pagination_id, page):
        if line.line_no == line_no:
            return (
                line.segment_id,
                line.start_offset,
                line.segment_id,
                line.start_offset + line.length,
            )
    return None


def chapter_extent(
    conn: sqlite3.Connection, version: VersionRow, division_id: int
) -> Extent | None:
    """The stretch of text a chapter covers."""
    extent = notes_store.division_extent(conn, version.id, division_id)
    if extent is None:
        return None
    first_id, last_id, last_length = extent
    return first_id, 0, last_id, last_length
