"""SQLite connections and the migration runner.

All SQL in PneuText lives in the ``store`` package. Schema changes are new numbered
``.sql`` files in ``migrations/``; applied files are never edited.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True)
class Migration:
    number: int
    name: str
    sql: str


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with the settings every PneuText connection uses."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def transaction(db_path: Path) -> Iterator[sqlite3.Connection]:
    """A connection whose work is committed on success and rolled back on error."""
    conn = connect(db_path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def load_migrations() -> list[Migration]:
    """Read the packaged migration files, in order, checking the numbering is gapless."""
    found: list[Migration] = []
    for entry in resources.files("pneutext.store").joinpath("migrations").iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match is None:
            continue
        found.append(Migration(int(match.group(1)), entry.name, entry.read_text(encoding="utf-8")))
    found.sort(key=lambda m: m.number)
    for expected, migration in enumerate(found, start=1):
        if migration.number != expected:
            raise RuntimeError(
                f"Migration numbering is broken at {migration.name}: expected {expected:04d}"
            )
    return found


def schema_version(conn: sqlite3.Connection) -> int:
    """The number of the last applied migration; 0 for a fresh database."""
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0])


def migrate(db_path: Path, migrations: list[Migration] | None = None) -> int:
    """Apply every migration not yet applied, each in its own transaction.

    Returns the schema version afterwards. A database newer than this code is refused
    rather than opened, so an older PneuText never writes to a schema it does not know.
    """
    pending = load_migrations() if migrations is None else migrations
    latest = pending[-1].number if pending else 0
    conn = connect(db_path)
    try:
        current = schema_version(conn)
        if current > latest:
            raise RuntimeError(
                f"This library was made by a newer PneuText (schema {current}; "
                f"this version understands up to {latest})."
            )
        conn.isolation_level = None  # explicit transactions, so DDL rolls back too
        for migration in pending:
            if migration.number <= current:
                continue
            conn.execute("BEGIN")
            try:
                for statement in _statements(migration.sql):
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {migration.number:d}")
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return schema_version(conn)
    finally:
        conn.close()


def _statements(sql: str) -> Iterator[str]:
    """Split a migration file into complete statements (handles triggers' inner ``;``)."""
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement:
                yield statement
    if buffer.strip():
        raise RuntimeError("Migration file ends with an incomplete SQL statement")
