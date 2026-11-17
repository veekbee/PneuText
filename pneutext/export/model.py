"""What an exporter is given: page shapes and notes as plain data.

Nothing here holds corpus text. A page is its shape (bars and highlight positions); a
note is its number, type and parsed body. The writers in this package see only these
values, and this package never imports the store, so a publishable export cannot reach
the text of the corpus even by mistake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pneutext.core.shape import DrawnLine

Tree = dict[str, Any]
"""A parsed note body, with its references already resolved."""


@dataclass(frozen=True)
class ExportNote:
    id: int
    number: int  # its number on its print page; markers on the facsimile use the same
    page: int  # the print page it is listed under
    type_id: int
    type_name: str
    level: int
    scope: str  # "span", "page" or "chapter"
    body: Tree


@dataclass(frozen=True)
class Marker:
    """Where a note's numbered marker sits on a facsimile: a line and a place along it."""

    line: int  # index into the page's lines
    x: float  # as a fraction of the measure
    number: int
    note_id: int


@dataclass(frozen=True)
class ExportPage:
    """One print page: its blank shape, the markers on it, and the notes that follow."""

    page: int
    lines: list[DrawnLine]
    markers: list[Marker]
    notes: list[ExportNote]


@dataclass(frozen=True)
class ExportChapter:
    key: str  # a stable name for the chapter's file, such as "01"
    label: str  # the chapter's number as printed; empty for pages before the first chapter
    title: Tree | None  # the author's chapter title
    summary: Tree | None  # the author's chapter summary
    notes: list[ExportNote]  # other notes on the chapter as a whole
    pages: list[ExportPage]


@dataclass(frozen=True)
class GlossaryEntry:
    term: str
    note: ExportNote


@dataclass(frozen=True)
class IndexEntry:
    name: str
    value: str | None
    pages: list[int]


@dataclass(frozen=True)
class EntityIndex:
    category: str
    entries: list[IndexEntry]


@dataclass(frozen=True)
class ExportFigure:
    number: int
    label: str
    caption: str
    credit: str
    file: str | None  # its name in the export's figures/ folder, when it can be included
    source: Path | None  # where to copy it from
    page: int  # the print page of the note that places it


@dataclass(frozen=True)
class NoteTypeColor:
    id: int
    name: str
    color: str  # "#rrggbb"


@dataclass
class ExportBook:
    title: str
    author: str
    edition: str  # the name of the export profile
    measure: int
    show_level_marks: bool  # a full edition marks every level 2 note
    types: list[NoteTypeColor]
    chapters: list[ExportChapter]
    glossary: list[GlossaryEntry] = field(default_factory=list)
    indexes: list[EntityIndex] = field(default_factory=list)
    figures: list[ExportFigure] = field(default_factory=list)
    # Notes included in this edition: id -> (print page, number). A reference to a note
    # that is not here degrades to a plain page citation.
    numbers: dict[int, tuple[int, int]] = field(default_factory=dict)
    # Print pages that have a facsimile, so a page reference can link to it.
    pages: set[int] = field(default_factory=set)
    warnings: list[str] = field(default_factory=list)
