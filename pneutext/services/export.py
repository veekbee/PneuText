"""Exports: the monograph (LaTeX) and the backup (JSON).

The monograph is built from the shape projection and the notes. This service gathers
that material, none of it corpus text, into an ``ExportBook`` and hands it to the
writer, which cannot reach the store.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pneutext import notes as note_parser
from pneutext.core import anchors, shape
from pneutext.core.anchors import LineGeometry
from pneutext.core.corpus import TEXT_KINDS
from pneutext.core.errors import Conflict, InvalidInput, NotFound
from pneutext.core.shape import ShapeLine
from pneutext.export import backup as backup_writer
from pneutext.export import latex
from pneutext.export.model import (
    EntityIndex,
    ExportBook,
    ExportChapter,
    ExportFigure,
    ExportNote,
    ExportPage,
    GlossaryEntry,
    IndexEntry,
    Marker,
    NoteTypeColor,
    Tree,
)
from pneutext.services import links as links_service
from pneutext.store import backup as backup_store
from pneutext.store import corpus as corpus_store
from pneutext.store import db, entities, exports, figures
from pneutext.store import notes as notes_store
from pneutext.store.corpus import VersionRow
from pneutext.store.exports import ProfileRow
from pneutext.store.library import Library
from pneutext.store.notes import NoteRow, ReadingRange

STATUSES = ("draft", "ready")
LEVELS = (1, 2)
BUILD_TIMEOUT_SECONDS = 600


@dataclass(frozen=True)
class ProfileInput:
    name: str
    type_ids: list[int] | None  # None means every note type
    levels: list[int]
    statuses: list[str]


@dataclass(frozen=True)
class MonographResult:
    folder: str
    files: list[str]
    notes: int
    pages: int
    pdf: str | None
    build: str  # what happened with the PDF, in plain words
    warnings: list[str]


@dataclass(frozen=True)
class BackupResult:
    folder: str
    files: list[str]
    includes_text: bool


# ---- Profiles ---------------------------------------------------------------------


def list_profiles(library: Library) -> list[ProfileRow]:
    with db.transaction(library.db_path) as conn:
        return exports.list_profiles(conn)


def _checked(
    conn: sqlite3.Connection, profile: ProfileInput, except_id: int | None
) -> ProfileInput:
    name = " ".join(profile.name.split())
    if not name:
        raise InvalidInput("Give the edition a name.")
    if exports.name_taken(conn, name, except_id):
        raise Conflict(f"There is already an edition called {name}.")
    if not profile.levels or any(level not in LEVELS for level in profile.levels):
        raise InvalidInput("Choose which reading levels the edition includes: 1, 2 or both.")
    if not profile.statuses or any(status not in STATUSES for status in profile.statuses):
        raise InvalidInput("Choose which notes the edition includes: ready, draft or both.")
    if profile.type_ids is not None:
        known = {row.id for row in notes_store.list_note_types(conn)}
        if not profile.type_ids or not set(profile.type_ids) <= known:
            raise InvalidInput("Choose at least one note type that exists.")
    return ProfileInput(name, profile.type_ids, profile.levels, profile.statuses)


def _require_profile(conn: sqlite3.Connection, profile_id: int) -> ProfileRow:
    profile = exports.get_profile(conn, profile_id)
    if profile is None:
        raise NotFound("That edition no longer exists.")
    return profile


def create_profile(library: Library, profile: ProfileInput) -> ProfileRow:
    with db.transaction(library.db_path) as conn:
        checked = _checked(conn, profile, None)
        profile_id = exports.insert_profile(
            conn, checked.name, checked.type_ids, checked.levels, checked.statuses
        )
        return _require_profile(conn, profile_id)


def update_profile(library: Library, profile_id: int, profile: ProfileInput) -> ProfileRow:
    with db.transaction(library.db_path) as conn:
        _require_profile(conn, profile_id)
        checked = _checked(conn, profile, profile_id)
        exports.update_profile(
            conn, profile_id, checked.name, checked.type_ids, checked.levels, checked.statuses
        )
        return _require_profile(conn, profile_id)


def delete_profile(library: Library, profile_id: int) -> None:
    with db.transaction(library.db_path) as conn:
        _require_profile(conn, profile_id)
        exports.delete_profile(conn, profile_id)


# ---- Gathering the book -------------------------------------------------------------


def _walk(node: Tree) -> list[Tree]:
    found = [node]
    for child in node.get("children") or []:
        found.extend(_walk(child))
    return found


def _plain(node: Tree) -> str:
    if node["type"] in ("text", "code"):
        return str(node.get("text") or "")
    return "".join(_plain(child) for child in node.get("children") or [])


def _term(body: Tree) -> str:
    """A definition's term: the bold words its body opens with."""
    blocks = body.get("children") or []
    first = (blocks[0].get("children") or [None])[0] if blocks else None
    if first is not None and first.get("type") == "strong":
        return " ".join(_plain(first).split())
    return " ".join(_plain(body).split())[:40]


def _has_content(body_md: str) -> bool:
    """Whether a body has anything to print once its TODO remarks are set aside."""
    blocks = note_parser.parse(body_md).get("children") or []
    return any(block["type"] != "todo" for block in blocks)


def _included(note: NoteRow, profile: ProfileRow) -> bool:
    return (
        note.level in profile.levels
        and note.status in profile.statuses
        and (profile.type_ids is None or note.type_id in profile.type_ids)
    )


def build_book(
    conn: sqlite3.Connection, library: Library, version: VersionRow, profile: ProfileRow
) -> ExportBook:
    """Gather an edition: page shapes and notes, and no corpus text."""
    types = {row.id: row for row in notes_store.list_note_types(conn)}
    # A note with nothing to print (a bare highlight, or only TODO remarks, which are
    # never exported) is left out, so no number points at an empty entry.
    chosen = [
        note
        for note in notes_store.find_notes(conn, version.id)
        if _included(note, profile) and _has_content(note.body_md)
    ]

    def page_of(note: NoteRow) -> int | None:
        found = notes_store.locate(
            conn, version.pagination_id, note.anchor.start_segment_id, note.anchor.start_offset
        )
        return None if found is None else found[0]

    # Number the notes of each print page, in reading order.
    numbers: dict[int, tuple[int, int]] = {}
    by_page: dict[int, list[NoteRow]] = {}
    chapter_notes: list[NoteRow] = []
    for note in chosen:
        page = page_of(note)
        if note.scope == "chapter" or page is None:
            chapter_notes.append(note)
            continue
        by_page.setdefault(page, []).append(note)
        numbers[note.id] = (page, len(by_page[page]))

    book = ExportBook(
        title=version.title,
        author=version.author,
        edition=profile.name,
        measure=shape.measure(corpus_store.text_line_lengths(conn, version.pagination_id)),
        show_level_marks=2 in profile.levels,
        types=[NoteTypeColor(row.id, row.name, row.color) for row in types.values()],
        chapters=[],
        numbers=numbers,
        pages=set(by_page),
    )

    def export_note(note: NoteRow) -> ExportNote:
        page, number = numbers.get(note.id, (page_of(note) or 0, 0))
        tree = links_service.resolve_tree(
            conn,
            version,
            note_parser.parse(note.body_md),
            (note.anchor.start_position, note.anchor.start_offset),
        )
        return ExportNote(
            note.id,
            number,
            page,
            note.type_id,
            types[note.type_id].name,
            note.level,
            note.scope,
            tree,
        )

    def export_page(page: int) -> ExportPage:
        rows = corpus_store.page_line_shapes(conn, version.pagination_id, page)
        first, last = rows[0], rows[-1]
        within = ReadingRange(
            first.position, first.start_offset, last.position, last.start_offset + last.length
        )
        ids = {note.id for note in chosen}
        spans = [
            span
            for span in notes_store.spans_in_range(conn, version.id, within)
            if span.annotation_id in ids
        ]
        geometry = [
            LineGeometry(row.position, row.start_offset, row.length, row.kind in TEXT_KINDS)
            for row in rows
        ]
        marks = anchors.line_highlights(geometry, spans)
        drawn = shape.layout_page(
            [
                ShapeLine(
                    id=row.id,
                    kind=row.kind,
                    page=row.page,
                    line_no=row.line_no,
                    starts_paragraph=row.starts_paragraph,
                    ends_paragraph=row.ends_paragraph,
                    length=row.length if row.kind in TEXT_KINDS else 0,
                    highlights=found,
                )
                for row, found in zip(rows, marks, strict=True)
            ],
            book.measure,
        )
        notes = [export_note(note) for note in by_page[page]]
        markers = []
        for note in notes:
            # The marker sits where the note's highlight first appears on the page.
            place = next(
                (
                    (index, mark.x0)
                    for index, line in enumerate(drawn)
                    for mark in line.highlights
                    if mark.annotation_id == note.id
                ),
                None,
            )
            if place is not None:
                markers.append(Marker(place[0], place[1], note.number, note.id))
        return ExportPage(page, drawn, markers, notes)

    # Chapters, each with the pages that fall in it; pages before the first chapter
    # form an unnumbered opening.
    divisions = [
        d
        for d in corpus_store.list_divisions(conn, version.id, version.pagination_id)
        if d.kind == "chapter" and d.page is not None
    ]
    ranges = {d.id: notes_store.division_range(conn, version.id, d.id) for d in divisions}

    def chapter_of_page(page: int) -> int | None:
        current = None
        for division in divisions:
            if division.page is not None and division.page <= page:
                current = division.id
        return current

    def chapter_of_note(note: NoteRow) -> int | None:
        start = (note.anchor.start_position, note.anchor.start_offset)
        for division in divisions:
            within = ranges[division.id]
            if within is not None and (
                (within.start_position, within.start_offset)
                <= start
                < (within.end_position, within.end_offset)
            ):
                return division.id
        return None

    groups: list[tuple[int | None, str]] = [(None, "")] + [(d.id, d.label) for d in divisions]
    for index, (division_id, label) in enumerate(groups):
        own = [note for note in chapter_notes if chapter_of_note(note) == division_id]
        pages = [page for page in sorted(by_page) if chapter_of_page(page) == division_id]
        title = next((n for n in own if types[n.type_id].role == "chapter_title"), None)
        summary = next((n for n in own if types[n.type_id].role == "chapter_summary"), None)
        others = [n for n in own if n is not title and n is not summary]
        if division_id is None and not pages and not own:
            continue  # nothing before the first chapter
        book.chapters.append(
            ExportChapter(
                key=f"{index:02d}",
                label=label,
                title=None if title is None else export_note(title).body,
                summary=None if summary is None else export_note(summary).body,
                notes=[export_note(note) for note in others],
                pages=[export_page(page) for page in pages],
            )
        )

    _collect(conn, library, version, book, types)
    return book


def _collect(
    conn: sqlite3.Connection,
    library: Library,
    version: VersionRow,
    book: ExportBook,
    types: dict[int, notes_store.NoteTypeRow],
) -> None:
    """Fill in the glossary, the indexes, the figures and the warnings."""
    listed = [note for chapter in book.chapters for page in chapter.pages for note in page.notes]
    trees = [
        tree
        for chapter in book.chapters
        for tree in (
            *(t for t in (chapter.title, chapter.summary) if t is not None),
            *(note.body for note in chapter.notes),
            *(note.body for page in chapter.pages for note in page.notes),
        )
    ]

    book.glossary = sorted(
        (
            GlossaryEntry(_term(note.body), note)
            for note in listed
            if types[note.type_id].role == "definition"
        ),
        key=lambda entry: (entry.term.casefold(), entry.note.page, entry.note.number),
    )

    places: dict[int, list[int]] = {}
    for place in entities.entity_places(conn, version.id, version.pagination_id):
        if place.page is not None:
            places.setdefault(place.entity_id, []).append(place.page)
    for category in entities.list_categories(conn):
        if category.is_time:
            continue
        entries = sorted(
            (
                IndexEntry(entity.name, entity.value, sorted(set(places[entity.id])))
                for entity in entities.list_entities(conn, category.id)
                if entity.id in places
            ),
            key=lambda entry: (entry.name.casefold(), entry.name),
        )
        if entries:
            book.indexes.append(EntityIndex(category.name, entries))

    root = library.figures_dir.resolve()
    page_of_tree = {id(note.body): note.page for note in listed}
    broken = 0
    for tree in trees:
        for node in _walk(tree):
            attrs = node.get("attrs") or {}
            if node["type"] in ("broken", "unsupported") or attrs.get("broken") is True:
                broken += 1
            if node["type"] != "figure" or attrs.get("broken") is not False:
                continue
            label = str(attrs["label"])
            if any(figure.label == label for figure in book.figures):
                continue
            row = figures.get_figure(conn, label)
            if row is None:
                continue
            source = (root / row.file).resolve() if row.file else None
            usable = (
                source is not None
                and source.is_relative_to(root)
                and source.is_file()
                and latex.includable(row.file)
            )
            if not usable:
                reason = (
                    "has no image"
                    if source is None or not source.is_file()
                    else "is not PNG, JPEG or PDF"
                )
                book.warnings.append(f"The figure {label} {reason}; a placeholder is printed.")
            book.figures.append(
                ExportFigure(
                    number=len(book.figures) + 1,
                    label=label,
                    caption=row.caption,
                    credit=row.credit,
                    file=row.file if usable else None,
                    source=source if usable else None,
                    page=page_of_tree.get(id(tree), 0),
                )
            )
    if broken:
        what = "reference leads" if broken == 1 else "references lead"
        book.warnings.append(
            f"{broken} {what} nowhere and is printed as typed. See the to-do list."
        )


# ---- Writing -----------------------------------------------------------------------


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "edition"


def default_folder(library: Library, version: VersionRow, profile: ProfileRow) -> Path:
    return library.root / "exports" / f"{version.work_code}-{_slug(profile.name)}"


def pdf_builder() -> str | None:
    """The program that can build the PDF, if one is installed."""
    for name in ("latexmk", "tectonic"):
        if shutil.which(name):
            return name
    return None


def build_pdf(folder: Path) -> tuple[Path | None, str]:
    """Build main.pdf with latexmk (or Tectonic). Returns the PDF and what happened."""
    builder = pdf_builder()
    if builder is None:
        return None, "No LaTeX is installed, so only the source was written."
    command = (
        ["latexmk", "-lualatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
        if builder == "latexmk"
        else ["tectonic", "main.tex"]
    )
    try:
        done = subprocess.run(
            command, cwd=folder, capture_output=True, text=True, timeout=BUILD_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        return None, f"{builder} took too long and was stopped. The source is in place."
    pdf = folder / "main.pdf"
    if done.returncode != 0 or not pdf.is_file():
        tail = "\n".join((done.stdout + "\n" + done.stderr).strip().splitlines()[-12:])
        return None, f"{builder} could not build the PDF. The source is in place.\n{tail}"
    return pdf, f"Built with {builder}."


def _folder(given: str | None, fallback: Path) -> Path:
    folder = Path(given.strip()).expanduser() if given and given.strip() else fallback
    if folder.exists() and not folder.is_dir():
        raise InvalidInput(f"{folder} is a file, not a folder.")
    return folder


def export_monograph(
    library: Library, version_id: int, profile_id: int, folder: str | None, with_pdf: bool
) -> MonographResult:
    with db.transaction(library.db_path) as conn:
        version = corpus_store.get_version(conn, version_id)
        if version is None:
            raise NotFound(f"There is no text with id {version_id} in this library.")
        profile = _require_profile(conn, profile_id)
        book = build_book(conn, library, version, profile)
        target = _folder(folder, default_folder(library, version, profile))
    written = latex.write_project(book, target)
    pdf, build = build_pdf(target) if with_pdf else (None, "The PDF was not asked for.")
    return MonographResult(
        folder=str(target),
        files=written,
        notes=len(book.numbers),
        pages=len(book.pages),
        pdf=None if pdf is None else str(pdf),
        build=build,
        warnings=book.warnings,
    )


def export_backup(library: Library, folder: str | None, include_text: bool) -> BackupResult:
    """Write the whole library as JSON plus figures: complete, or without corpus text."""
    name = "backup-complete" if include_text else "backup-without-text"
    target = _folder(folder, library.root / "exports" / name)
    with db.transaction(library.db_path) as conn:
        tables = backup_store.dump(conn, include_text)
        schema = db.schema_version(conn)
    written = backup_writer.write_backup(tables, library.figures_dir, target, include_text, schema)
    return BackupResult(str(target), written, include_text)
