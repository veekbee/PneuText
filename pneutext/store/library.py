"""A library: one folder holding ``library.db`` and a ``figures/`` folder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pneutext.store import db

DEFAULT_LIBRARY_DIR = Path.home() / ".pneutext"


@dataclass(frozen=True)
class Library:
    root: Path

    @property
    def db_path(self) -> Path:
        return self.root / "library.db"

    @property
    def figures_dir(self) -> Path:
        return self.root / "figures"


@dataclass(frozen=True)
class LibraryInfo:
    schema_version: int
    created_at: str


def open_library(root: Path) -> Library:
    """Create the library folder if needed and bring its database up to date."""
    library = Library(root.expanduser().resolve())
    library.root.mkdir(parents=True, exist_ok=True)
    library.figures_dir.mkdir(exist_ok=True)
    db.migrate(library.db_path)
    return library


def read_info(library: Library) -> LibraryInfo:
    with db.transaction(library.db_path) as conn:
        row = conn.execute("SELECT value FROM library_meta WHERE key = 'created_at'").fetchone()
        return LibraryInfo(schema_version=db.schema_version(conn), created_at=row["value"])
