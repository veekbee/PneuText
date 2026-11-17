from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pneutext.store import db
from pneutext.store.db import Migration
from pneutext.store.library import open_library


def test_packaged_migrations_are_numbered_without_gaps() -> None:
    migrations = db.load_migrations()
    assert [m.number for m in migrations] == list(range(1, len(migrations) + 1))


def test_open_library_creates_folder_database_and_figures(tmp_path: Path) -> None:
    library = open_library(tmp_path / "new" / "library")
    assert library.db_path.is_file()
    assert library.figures_dir.is_dir()
    with db.transaction(library.db_path) as conn:
        assert db.schema_version(conn) == len(db.load_migrations())


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    first = db.migrate(path)
    assert db.migrate(path) == first


def test_failed_migration_rolls_back_entirely(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    good = Migration(1, "0001_good.sql", "CREATE TABLE a (x INTEGER);")
    bad = Migration(
        2, "0002_bad.sql", "CREATE TABLE b (x INTEGER);\nINSERT INTO missing VALUES (1);"
    )
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(path, [good, bad])
    with db.transaction(path) as conn:
        assert db.schema_version(conn) == 1
        tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert tables == {"a"}


def test_statements_containing_semicolons_are_kept_whole(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    sql = (
        "CREATE TABLE a (x INTEGER);\n"
        "CREATE TABLE log (x INTEGER);\n"
        "CREATE TRIGGER a_ai AFTER INSERT ON a BEGIN\n"
        "  INSERT INTO log VALUES (new.x);\n"
        "  INSERT INTO log VALUES (new.x + 1);\n"
        "END;\n"
        "INSERT INTO a VALUES (1);\n"
    )
    db.migrate(path, [Migration(1, "0001_trigger.sql", sql)])
    with db.transaction(path) as conn:
        assert [r["x"] for r in conn.execute("SELECT x FROM log ORDER BY x")] == [1, 2]


def test_newer_database_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "library.db"
    conn = db.connect(path)
    conn.execute("PRAGMA user_version = 9999")
    conn.close()
    with pytest.raises(RuntimeError, match="newer PneuText"):
        db.migrate(path)


def test_foreign_keys_are_enforced_on_every_connection(tmp_path: Path) -> None:
    conn = db.connect(tmp_path / "library.db")
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()
