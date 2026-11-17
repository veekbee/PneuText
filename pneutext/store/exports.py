"""Storage for export profiles."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileRow:
    id: int
    name: str
    type_ids: list[int] | None  # None means every note type
    levels: list[int]
    statuses: list[str]


def _row(row: sqlite3.Row) -> ProfileRow:
    return ProfileRow(
        id=row["id"],
        name=row["name"],
        type_ids=None if row["type_ids"] is None else json.loads(row["type_ids"]),
        levels=json.loads(row["levels"]),
        statuses=json.loads(row["statuses"]),
    )


def list_profiles(conn: sqlite3.Connection) -> list[ProfileRow]:
    rows = conn.execute("SELECT * FROM export_profile ORDER BY id").fetchall()
    return [_row(row) for row in rows]


def get_profile(conn: sqlite3.Connection, profile_id: int) -> ProfileRow | None:
    row = conn.execute("SELECT * FROM export_profile WHERE id = ?", (profile_id,)).fetchone()
    return None if row is None else _row(row)


def name_taken(conn: sqlite3.Connection, name: str, except_id: int | None) -> bool:
    row = conn.execute(
        "SELECT id FROM export_profile WHERE LOWER(name) = LOWER(?)", (name,)
    ).fetchone()
    return row is not None and row["id"] != except_id


def _values(
    name: str, type_ids: list[int] | None, levels: list[int], statuses: list[str]
) -> tuple[str, str | None, str, str]:
    return (
        name,
        None if type_ids is None else json.dumps(sorted(type_ids)),
        json.dumps(sorted(levels)),
        json.dumps(sorted(statuses)),
    )


def insert_profile(
    conn: sqlite3.Connection,
    name: str,
    type_ids: list[int] | None,
    levels: list[int],
    statuses: list[str],
) -> int:
    cursor = conn.execute(
        "INSERT INTO export_profile (name, type_ids, levels, statuses) VALUES (?, ?, ?, ?)",
        _values(name, type_ids, levels, statuses),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def update_profile(
    conn: sqlite3.Connection,
    profile_id: int,
    name: str,
    type_ids: list[int] | None,
    levels: list[int],
    statuses: list[str],
) -> None:
    conn.execute(
        "UPDATE export_profile SET name = ?, type_ids = ?, levels = ?, statuses = ? WHERE id = ?",
        (*_values(name, type_ids, levels, statuses), profile_id),
    )


def delete_profile(conn: sqlite3.Connection, profile_id: int) -> None:
    conn.execute("DELETE FROM export_profile WHERE id = ?", (profile_id,))
