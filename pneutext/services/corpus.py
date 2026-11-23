"""Importing a paged corpus and reading it back page by page."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from pneutext.core import shape
from pneutext.core.corpus import TEXT_KINDS, CorpusSummary, ImportProblem
from pneutext.core.errors import Conflict, InvalidInput, NotFound
from pneutext.core.shape import ShapeHighlight, ShapeLine
from pneutext.importers import paged_corpus
from pneutext.importers.paged_corpus import CorpusFormat
from pneutext.services import entities as entities_service
from pneutext.services import notes as notes_service
from pneutext.services.entities import MentionMark
from pneutext.store import corpus as corpus_store
from pneutext.store import db
from pneutext.store import notes as notes_store
from pneutext.store.corpus import DivisionRow, LineTextRow, NewVersion, VersionRow
from pneutext.store.library import Library

_WORK_CODE = re.compile(r"[a-z][a-z0-9]*")


@dataclass(frozen=True)
class CorpusImportRequest:
    folder: str
    work_code: str
    title: str
    author: str = ""
    label: str = ""
    language: str = ""
    file_pattern: str | None = None


@dataclass(frozen=True)
class CorpusImportPreview:
    summary: CorpusSummary
    problems: list[ImportProblem]
    content_hash: str
    existing_version_id: int | None


@dataclass(frozen=True)
class VersionDetail:
    version: VersionRow
    measure: int
    pages: list[int]
    divisions: list[DivisionRow]
    note_counts: dict[int, int]  # notes beginning in each division, by division id


@dataclass(frozen=True)
class PageText:
    version_id: int
    edit_seq: int
    page: int
    prev_page: int | None
    next_page: int | None
    division: DivisionRow | None
    lines: list[LineTextRow]
    highlights: list[list[ShapeHighlight]]  # one list per line, in the same order
    mentions: list[list[MentionMark]]


@dataclass(frozen=True)
class PageShape:
    """The shape projection of a page: line geometry and highlight positions, no text."""

    version_id: int
    edit_seq: int
    page: int
    prev_page: int | None
    next_page: int | None
    division: DivisionRow | None
    lines: list[ShapeLine]
    mentions: list[list[MentionMark]]  # one list per line, in the same order


def _validated(request: CorpusImportRequest) -> CorpusImportRequest:
    if not request.folder.strip():
        raise InvalidInput("Give the folder that holds the page files.")
    if not _WORK_CODE.fullmatch(request.work_code):
        raise InvalidInput(
            "The work code is the short name used in references: lower-case letters and "
            "digits, starting with a letter (for example, ab)."
        )
    if not request.title.strip():
        raise InvalidInput("Give the work a title.")
    return request


def _parse(request: CorpusImportRequest) -> tuple[paged_corpus.ParsedCorpus, str]:
    fmt = CorpusFormat(file_pattern=request.file_pattern or paged_corpus.DEFAULT_FILE_PATTERN)
    folder = Path(request.folder.strip()).expanduser()
    sources = paged_corpus.read_folder(folder, fmt.file_pattern)
    return paged_corpus.parse_pages(sources, fmt), paged_corpus.content_hash(sources)


def preview_import(library: Library, request: CorpusImportRequest) -> CorpusImportPreview:
    """Read and check the folder without writing anything."""
    corpus, content_hash = _parse(_validated(request))
    with db.transaction(library.db_path) as conn:
        existing = corpus_store.find_version_by_hash(conn, content_hash)
    return CorpusImportPreview(corpus.summary(), corpus.problems, content_hash, existing)


def commit_import(
    library: Library, request: CorpusImportRequest, allow_duplicate: bool = False
) -> tuple[int, CorpusImportPreview]:
    """Import the folder as a new version, in one transaction."""
    request = _validated(request)
    corpus, content_hash = _parse(request)
    with db.transaction(library.db_path) as conn:
        existing = corpus_store.find_version_by_hash(conn, content_hash)
        if existing is not None and not allow_duplicate:
            raise Conflict(
                "These files have already been imported. Open the existing version, or "
                "confirm that you want a second copy."
            )
        version_id = corpus_store.insert_corpus(
            conn,
            NewVersion(
                work_code=request.work_code,
                title=request.title.strip(),
                author=request.author.strip(),
                label=request.label.strip() or "First import",
                language=request.language.strip(),
                source_format=paged_corpus.SOURCE_FORMAT,
                content_hash=content_hash,
            ),
            corpus,
        )
    return version_id, CorpusImportPreview(
        corpus.summary(), corpus.problems, content_hash, existing
    )


def list_versions(library: Library) -> list[VersionRow]:
    with db.transaction(library.db_path) as conn:
        return corpus_store.list_versions(conn)


def _require_version(conn: sqlite3.Connection, version_id: int) -> VersionRow:
    version = corpus_store.get_version(conn, version_id)
    if version is None:
        raise NotFound(f"There is no text with id {version_id} in this library.")
    return version


def get_version(library: Library, version_id: int) -> VersionDetail:
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        divisions = corpus_store.list_divisions(conn, version.id, version.pagination_id)
        counts: dict[int, int] = {}
        for division in divisions:
            within = notes_store.division_range(conn, version.id, division.id)
            counts[division.id] = (
                0
                if within is None
                else notes_store.count_notes_starting_in(conn, version.id, within)
            )
        return VersionDetail(
            version=version,
            measure=shape.measure(corpus_store.text_line_lengths(conn, version.pagination_id)),
            pages=corpus_store.list_pages(conn, version.pagination_id),
            divisions=divisions,
            note_counts=counts,
        )


def get_page_text(library: Library, version_id: int, page: int) -> PageText:
    """The text projection of one page."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        lines = corpus_store.page_line_texts(conn, version.pagination_id, page)
        if not lines:
            raise NotFound(f"This text has no page {page}.")
        prev_page, next_page = corpus_store.neighbouring_pages(conn, version.pagination_id, page)
        return PageText(
            version_id=version.id,
            edit_seq=version.edit_seq,
            page=page,
            prev_page=prev_page,
            next_page=next_page,
            division=corpus_store.division_at_page(conn, version.id, version.pagination_id, page),
            lines=lines,
            highlights=notes_service.page_highlights(
                conn, version.id, [line.shape for line in lines]
            ),
            mentions=entities_service.page_mentions(
                conn, version.id, [line.shape for line in lines]
            ),
        )


def get_page_shape(library: Library, version_id: int, page: int) -> PageShape:
    """The shape projection of one page. Reads line geometry only; never segment text."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        rows = corpus_store.page_line_shapes(conn, version.pagination_id, page)
        if not rows:
            raise NotFound(f"This text has no page {page}.")
        prev_page, next_page = corpus_store.neighbouring_pages(conn, version.pagination_id, page)
        highlights = notes_service.page_highlights(conn, version.id, rows)
        return PageShape(
            version_id=version.id,
            edit_seq=version.edit_seq,
            page=page,
            prev_page=prev_page,
            next_page=next_page,
            division=corpus_store.division_at_page(conn, version.id, version.pagination_id, page),
            lines=[
                ShapeLine(
                    id=row.id,
                    kind=row.kind,
                    page=row.page,
                    line_no=row.line_no,
                    starts_paragraph=row.starts_paragraph,
                    ends_paragraph=row.ends_paragraph,
                    # Furniture is a fixed placeholder: its label's length is not shape.
                    length=row.length if row.kind in TEXT_KINDS else 0,
                    highlights=marks,
                )
                for row, marks in zip(rows, highlights, strict=True)
            ],
            mentions=entities_service.page_mentions(conn, version.id, rows),
        )
