"""Reading the whole library out as plain rows, for a backup."""

from __future__ import annotations

import sqlite3
from typing import Any

# Tables in an order that reads well; search indexes are derived and left out.
TABLES = (
    "library_meta",
    "work",
    "version",
    "segment",
    "division",
    "pagination",
    "line",
    "anchor",
    "note_type",
    "annotation",
    "tag",
    "annotation_tag",
    "entity_category",
    "entity",
    "mention",
    "time_point",
    "figure",
    "link",
    "legacy_item",
    "export_profile",
)


def dump(conn: sqlite3.Connection, include_text: bool) -> dict[str, list[dict[str, Any]]]:
    """Every table as a list of rows.

    Without the text, a segment keeps only its length and an anchor keeps only its
    offsets: the words of the corpus are in neither.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for table in TABLES:
        rows = [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2")]
        if not include_text:
            if table == "segment":
                for row in rows:
                    row["length"] = len(row.pop("text"))
            elif table == "anchor":
                for row in rows:
                    row["exact"] = row["prefix"] = row["suffix"] = ""
        out[table] = rows
    return out
