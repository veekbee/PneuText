"""Library-level operations used by the API."""

from __future__ import annotations

from pneutext.store.library import Library, LibraryInfo, read_info


def describe(library: Library) -> LibraryInfo:
    return read_info(library)
