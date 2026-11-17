"""Importing the legacy commentary files for an already-imported version.

The import always runs first as a dry run that writes nothing and returns a report
grouped by problem. Only what is unambiguous is repaired, and each repair is listed.
Everything else is imported as found: every note arrives as a draft, and a note the
importer could not place, or a span with no note, arrives flagged with a ``TODO:``
remark so it shows up in the to-do list. Nothing typed is lost.

No report entry quotes more than the offending tag with its page and line.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pneutext.core import anchors
from pneutext.core.corpus import TEXT_KINDS
from pneutext.core.errors import InvalidInput, NotFound
from pneutext.importers import legacy_body, legacy_commentary, paged_corpus
from pneutext.importers.legacy_body import BodyFormat
from pneutext.importers.legacy_commentary import CommentaryFormat, ParsedPage, Position
from pneutext.services import links as links_service
from pneutext.services.extents import WHOLE_UNIT, Extent, chapter_extent, page_extent
from pneutext.store import corpus as corpus_store
from pneutext.store import db, entities, figures, legacy
from pneutext.store import notes as notes_store
from pneutext.store.corpus import LineTextRow, VersionRow
from pneutext.store.library import Library
from pneutext.store.notes import NoteTypeRow

DEFAULT_TYPE_CODE = "c"
"""The type given to remarks that stand outside any note, when a type has this code."""

# Flags are TODO remarks: shown in the app, listed among the to-dos, never exported.
FLAG_NO_SPAN = "TODO: Imported without a span. Attach this note to its passage."
FLAG_NO_NOTE = "TODO: Imported span with no note. Write the note, or delete this highlight."
FLAG_UNCLOSED = "TODO: Imported from a span that was never closed. Check where the passage ends."
FLAG_NO_CHAPTER = "TODO: No chapter opens on or before this page. Attach this to its chapter."

# Report groups, in the order they are shown, and the problem codes each gathers.
_GROUPS: list[tuple[str, str]] = [
    ("malformed_tags", "Unclosed or malformed tags"),
    ("span_without_note", "Spans without a note"),
    ("note_without_span", "Notes without a span"),
    ("type_disagreement", "Types that do not agree"),
    ("wrong_page", "Ids naming another page"),
    ("unknown_category", "Entity categories"),
    ("missing_figure", "Figure files"),
    ("text_differs", "Text that differs from the corpus"),
    ("unknown_latex", "LaTeX commands left in place"),
]

_MESSAGES: dict[str, tuple[str, str]] = {
    "stray_closing_tag": (
        "malformed_tags",
        "{tag} closes something that was never opened; it was ignored.",
    ),
    "malformed_tag": ("malformed_tags", "{tag} is not a complete tag; it was left in the text."),
    "unclosed_span": (
        "malformed_tags",
        "{tag} is never closed; it was taken to end with its line, and its note is flagged.",
    ),
    "unclosed_entity": ("malformed_tags", "{tag} is never closed; the tag was dropped."),
    "stray_entity_end": (
        "malformed_tags",
        "{tag} ends an entity tag that was never opened; it was ignored.",
    ),
    "unclosed_block": (
        "malformed_tags",
        "The note block {tag} is never closed; it was taken to end where the next begins.",
    ),
    "malformed_id": (
        "malformed_tags",
        "{tag} does not look like a note id, so it names no type or page.",
    ),
    "odd_header_field": (
        "malformed_tags",
        "A block header has an extra field, {tag}; it was ignored.",
    ),
    "duplicate_id": ("malformed_tags", "{tag} is used more than once on this page."),
    "empty_span": (
        "malformed_tags",
        "{tag} encloses nothing; its note was attached to the page and flagged.",
    ),
    "empty_entity": ("malformed_tags", "{tag} encloses nothing; it was skipped."),
    "no_chapter": (
        "malformed_tags",
        "{tag}: no chapter opens on or before this page; it was attached to the page, flagged.",
    ),
    "span_without_note": (
        "span_without_note",
        "{tag} has no note block; it was imported as a flagged highlight.",
    ),
    "note_without_span": (
        "note_without_span",
        "The note {tag} has no span in the text; it was attached to the page and flagged.",
    ),
    "type_mismatch": (
        "type_disagreement",
        "{tag}: the block says {detail}, which disagrees with the id's prefix; {detail} was used.",
    ),
    "new_note_type": (
        "type_disagreement",
        "{tag}: {detail} is not a note type yet; it was created. If it is a slip, merge it "
        "into the right type under Note types.",
    ),
    "unknown_prefix": (
        "type_disagreement",
        "{tag}: the block names no type and the id's prefix is not the code of any; the "
        "default type was used.",
    ),
    "bad_level": (
        "type_disagreement",
        "{tag}: {detail} is not a reading level (1 or 2); level 1 was used.",
    ),
    "wrong_page": ("wrong_page", "{tag} names page {detail}, not the page of the file it is in."),
    "unknown_category": (
        "unknown_category",
        "{tag} is not a known category; the category was created.",
    ),
    "time_value": (
        "unknown_category",
        "{tag}: a value on a time tag is not imported; set the time in the app.",
    ),
    "missing_figure": (
        "missing_figure",
        "The figure file {tag} was not found; its figure has no image yet.",
    ),
    "figure_label_clash": (
        "missing_figure",
        "{tag} would share a label with a different file; it was skipped.",
    ),
    "text_differs": ("text_differs", "The text differs from the corpus here ({tag})."),
    "line_count": ("text_differs", "The page has {tag}."),
    "page_not_in_corpus": (
        "text_differs",
        "The corpus has no such page; nothing in {tag} was imported.",
    ),
    "unknown_latex": ("unknown_latex", "{tag} is not a known LaTeX command; it was left in place."),
    # Repairs
    "closing_tag_slash": ("repairs", "{tag} was read as a closing tag missing its slash."),
    "category_name": ("repairs", "{tag} was read as the category {detail}."),
}


@dataclass(frozen=True)
class LegacyImportRequest:
    folder: str
    file_pattern: str | None = None
    # LaTeX commands that cite a page of the work, such as a macro of the author's own.
    page_ref_commands: tuple[str, ...] = ()
    figures_folder: str | None = None


@dataclass(frozen=True)
class ReportItem:
    code: str
    page: int
    line: int | None
    tag: str
    message: str


@dataclass(frozen=True)
class ReportGroup:
    code: str
    title: str
    items: list[ReportItem]


@dataclass(frozen=True)
class LegacyReport:
    files: int
    pages: list[int]
    notes: int
    flagged_notes: int
    chapter_notes: int
    remarks: int
    mentions: int
    new_categories: list[str]
    new_types: list[str]
    figures: int
    replaced_notes: int
    replaced_mentions: int
    groups: list[ReportGroup]
    repairs: list[ReportItem]


@dataclass(frozen=True)
class _PlannedNote:
    page: int
    type_id: int
    scope: str
    level: int
    body_md: str
    legacy_id: str | None
    extent: Extent
    kind: str  # "note", "chapter" or "remark"
    flagged: bool


@dataclass(frozen=True)
class _PlannedMention:
    page: int
    category: str
    name: str | None  # None for a time mention
    value: str | None
    extent: Extent


@dataclass(frozen=True)
class _PlannedFigure:
    label: str
    file: str
    caption: str
    source: Path | None


@dataclass
class _Plan:
    files: int = 0
    pages: list[int] = field(default_factory=list)
    notes: list[_PlannedNote] = field(default_factory=list)
    mentions: list[_PlannedMention] = field(default_factory=list)
    new_categories: list[str] = field(default_factory=list)
    new_types: list[str] = field(default_factory=list)
    figures: dict[str, _PlannedFigure] = field(default_factory=dict)
    problems: list[ReportItem] = field(default_factory=list)
    repairs: list[ReportItem] = field(default_factory=list)
    types: _Types | None = None  # holds the note types this import will create


def _item(code: str, page: int, line: int | None, tag: str, detail: str = "") -> ReportItem:
    where = f"Page {page}" + (f", line {line}" if line is not None else "")
    message = _MESSAGES[code][1].format(tag=tag, detail=detail)
    return ReportItem(code, page, line, tag, f"{where}: {message}")


_NEW_TYPE_COLORS = ("#7f8fa6", "#b08968", "#6d9773", "#a37aa3", "#8c8c6a", "#5f8d96")
_TYPE_CODE = re.compile(r"[a-z][a-z0-9]*")


class _Types:
    """Note types as the legacy format refers to them: by id prefix and by name.

    A type a block names that the library does not have yet is planned here (with a
    negative id until the import commits and creates it), so its notes keep their type.
    """

    def __init__(self, rows: list[NoteTypeRow]) -> None:
        self.by_code = {row.code.lower(): row for row in rows}
        self.by_name = {row.name.lower(): row for row in rows}
        self.by_role: dict[str, NoteTypeRow] = {}
        for row in rows:
            self.by_role.setdefault(row.role, row)
        fallback = self.by_code.get(DEFAULT_TYPE_CODE) or self.by_role.get("note") or rows[0]
        self.default = fallback
        self.new: list[NoteTypeRow] = []

    def plan(self, name: str, prefix: str | None) -> NoteTypeRow:
        """Plan a new type called ``name``, coded by the id's prefix if that is free."""
        wanted = [prefix.lower()] if prefix else []
        wanted.append(re.sub(r"[^a-z0-9]", "", name.lower()))
        code = next((c for c in wanted if _TYPE_CODE.fullmatch(c) and c not in self.by_code), None)
        if code is None:
            stem = wanted[-1] if _TYPE_CODE.fullmatch(wanted[-1]) else "type"
            code = next(f"{stem}{n}" for n in range(2, 10_000) if f"{stem}{n}" not in self.by_code)
        row = NoteTypeRow(
            id=-(len(self.new) + 1),
            name=name,
            code=code,
            color=_NEW_TYPE_COLORS[len(self.new) % len(_NEW_TYPE_COLORS)],
            sort=0,
            role="note",
        )
        self.new.append(row)
        self.by_name[name.lower()] = row
        self.by_code[code] = row
        return row


class _PagePlanner:
    """Turns one parsed commentary page into planned notes and mentions."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        version: VersionRow,
        plan: _Plan,
        types: _Types,
        categories: dict[str, str],
        fmt: CommentaryFormat,
        body_fmt: BodyFormat,
        figure_folders: list[Path],
    ) -> None:
        self.conn = conn
        self.version = version
        self.plan = plan
        self.types = types
        self.categories = categories  # lower-cased name -> name as stored
        self.id_pattern = re.compile(fmt.id_pattern)
        self.body_fmt = body_fmt
        self.figure_folders = figure_folders

    # -- reporting -------------------------------------------------------------

    def problem(self, code: str, page: int, line: int | None, tag: str, detail: str = "") -> None:
        self.plan.problems.append(_item(code, page, line, tag, detail))

    # -- geometry --------------------------------------------------------------

    def point(self, lines: list[LineTextRow], position: Position) -> tuple[int, int, int]:
        """A position in the stripped text as (segment position, segment id, offset)."""
        if position.line >= len(lines):
            last = lines[-1].shape
            return last.position, last.segment_id, last.start_offset + last.length
        shape = lines[position.line].shape
        column = min(position.column, shape.length)
        return shape.position, shape.segment_id, shape.start_offset + column

    def extent(self, lines: list[LineTextRow], start: Position, end: Position) -> Extent | None:
        first, last = self.point(lines, start), self.point(lines, end)
        if (last[0], last[2]) <= (first[0], first[2]):
            return None
        return first[1], first[2], last[1], last[2]

    def line_end(self, lines: list[LineTextRow], start: Position) -> Position:
        length = lines[min(start.line, len(lines) - 1)].shape.length
        return Position(start.line, length)

    # -- one page --------------------------------------------------------------

    def plan_page(self, parsed: ParsedPage) -> None:
        page = parsed.page
        for found in parsed.problems:
            self.problem(found.code, found.page, found.line, found.tag)
        self.plan.repairs += [_item(r.code, r.page, r.line, r.tag) for r in parsed.repairs]

        lines = [
            row
            for row in corpus_store.page_line_texts(self.conn, self.version.pagination_id, page)
            if row.shape.kind in TEXT_KINDS
        ]
        whole_page = page_extent(self.conn, self.version, page)
        if not lines or whole_page is None:
            self.problem("page_not_in_corpus", page, None, parsed.name)
            return
        self.plan.pages.append(page)
        self._compare(parsed, lines)

        spans = {}
        for span in parsed.spans:
            spans.setdefault(span.id, span)
        used: set[str] = set()

        for block in parsed.blocks:
            tag = f"{{{block.id}}}"
            body = self._body(block.body, page, block.body_line)
            type_row = self._type(block.id, block.type_name, page, block.file_line)
            if body.is_definition and "definition" in self.types.by_role:
                type_row = self.types.by_role["definition"]
            level = 1
            if block.level is not None:
                if block.level in (1, 2):
                    level = block.level
                else:
                    self.problem("bad_level", page, block.file_line, tag, str(block.level))

            span = spans.get(block.id)
            flags: list[str] = []
            extent: Extent | None = None
            if span is None or block.id in used:
                if span is None:
                    self.problem("note_without_span", page, block.file_line, tag)
                flags.append(FLAG_NO_SPAN)
            else:
                used.add(block.id)
                end = span.end
                if end is None:
                    end = self.line_end(lines, span.start)
                    flags.append(FLAG_UNCLOSED)
                extent = self.extent(lines, span.start, end)
                if extent is None:
                    self.problem("empty_span", page, span.file_line, tag)
                    flags.append(FLAG_NO_SPAN)
            self._note(
                page,
                type_row.id,
                "span" if extent is not None else "page",
                level,
                body.markdown,
                block.id,
                extent or whole_page,
                "note",
                flags,
            )

        for span in parsed.spans:
            if span.id in used:
                continue
            used.add(span.id)
            tag = f"{{{span.id}}}"
            self.problem("span_without_note", page, span.file_line, tag)
            flags = [FLAG_NO_NOTE]
            end = span.end
            if end is None:
                end = self.line_end(lines, span.start)
                flags.append(FLAG_UNCLOSED)
            extent = self.extent(lines, span.start, end)
            if extent is None:
                self.problem("empty_span", page, span.file_line, tag)
            type_row = self._type(span.id, None, page, span.file_line)
            self._note(
                page,
                type_row.id,
                "span" if extent is not None else "page",
                1,
                "",
                span.id,
                extent or whole_page,
                "note",
                flags,
            )

        self._chapter_matter(parsed, whole_page)
        for remark in parsed.remarks:
            body = self._body(remark.body, page, remark.file_line)
            self._note(
                page,
                self.types.default.id,
                "page",
                1,
                body.markdown,
                None,
                whole_page,
                "remark",
                [],
            )
        self._mentions(parsed, lines)

    def _compare(self, parsed: ParsedPage, lines: list[LineTextRow]) -> None:
        """Check the stripped commentary text against the corpus, line by line."""
        page = parsed.page
        if len(parsed.lines) != len(lines):
            counts = f"{len(parsed.lines)} lines of text where the corpus has {len(lines)}"
            self.problem("line_count", page, None, counts)
        for theirs, ours in zip(parsed.lines, lines, strict=False):
            if theirs.text != ours.text:
                self.problem(
                    "text_differs", page, theirs.file_line, f"corpus line {ours.shape.line_no}"
                )

    def _body(self, body: str, page: int, first_line: int) -> legacy_body.ConvertedBody:
        converted = legacy_body.convert(body, self.body_fmt)
        for found in converted.problems:
            self.problem(found.code, page, first_line + found.line, found.tag)
        for use in converted.figures:
            self._figure(use, page, first_line + use.line)
        return converted

    def _figure(self, use: legacy_body.FigureUse, page: int, line: int) -> None:
        file_name = Path(use.file).name
        source = next(
            (folder / use.file for folder in self.figure_folders if (folder / use.file).is_file()),
            None,
        )
        existing = self.plan.figures.get(use.label)
        if existing is not None:
            if existing.file != file_name:
                self.problem("figure_label_clash", page, line, file_name)
            return
        if source is None:
            self.problem("missing_figure", page, line, file_name)
        self.plan.figures[use.label] = _PlannedFigure(use.label, file_name, use.caption, source)

    def _type(self, note_id: str, type_name: str | None, page: int, line: int) -> NoteTypeRow:
        """A note's type: the block header's name, falling back to the id's prefix."""
        tag = f"{{{note_id}}}"
        match = self.id_pattern.fullmatch(note_id)
        from_prefix: NoteTypeRow | None = None
        if match is None:
            self.problem("malformed_id", page, line, tag)
        else:
            if int(match.group("page")) != page:
                self.problem("wrong_page", page, line, tag, match.group("page"))
            from_prefix = self.types.by_code.get(match.group("prefix").lower())

        from_name: NoteTypeRow | None = None
        if type_name is not None:
            from_name = self.types.by_name.get(type_name.lower())
            if from_name is None:
                # A type the library does not have yet: it is created, coded by this id's
                # prefix when that code is free, so the notes of this type keep it.
                free = match.group("prefix") if match is not None and from_prefix is None else None
                from_name = self.types.plan(type_name, free)
                self.plan.new_types.append(from_name.name)
                self.problem("new_note_type", page, line, tag, type_name)
            elif from_prefix is not None and from_prefix.id != from_name.id:
                self.problem("type_mismatch", page, line, tag, from_name.name)
        elif match is not None and from_prefix is None:
            self.problem("unknown_prefix", page, line, tag)
        return from_name or from_prefix or self.types.default

    def _note(
        self,
        page: int,
        type_id: int,
        scope: str,
        level: int,
        body_md: str,
        legacy_id: str | None,
        extent: Extent,
        kind: str,
        flags: list[str],
    ) -> None:
        body = "\n\n".join([*flags, body_md]).strip() if flags else body_md
        self.plan.notes.append(
            _PlannedNote(page, type_id, scope, level, body, legacy_id, extent, kind, bool(flags))
        )

    def _chapter_matter(self, parsed: ParsedPage, whole_page: Extent) -> None:
        page = parsed.page
        divisions = corpus_store.list_divisions(
            self.conn, self.version.id, self.version.pagination_id
        )
        chapter = next(
            (d for d in reversed(divisions) if d.page is not None and d.page <= page), None
        )
        for matter in parsed.chapter_matter:
            type_row = self.types.by_role.get(matter.role, self.types.default)
            body = self._body(matter.body, page, matter.file_line)
            extent = (
                None if chapter is None else chapter_extent(self.conn, self.version, chapter.id)
            )
            if extent is None:
                self.problem("no_chapter", page, matter.file_line, matter.role)
                self._note(
                    page,
                    type_row.id,
                    "page",
                    1,
                    body.markdown,
                    None,
                    whole_page,
                    "chapter",
                    [FLAG_NO_CHAPTER],
                )
            else:
                self._note(
                    page, type_row.id, "chapter", 1, body.markdown, None, extent, "chapter", []
                )

    def _category(self, name: str, page: int, line: int, tag: str) -> str:
        """The category a tag names, repairing a singular or plural variant of a known one."""
        key = name.lower()
        if key in self.categories:
            return self.categories[key]
        variants = [key + "s", key[:-1]] if key.endswith("s") else [key + "s"]
        for variant in variants:
            if variant in self.categories:
                known = self.categories[variant]
                self.plan.repairs.append(_item("category_name", page, line, tag, known))
                return known
        self.problem("unknown_category", page, line, tag)
        self.categories[key] = name
        self.plan.new_categories.append(name)
        return name

    def _mentions(self, parsed: ParsedPage, lines: list[LineTextRow]) -> None:
        page = parsed.page
        time_categories = {c.name for c in entities.list_categories(self.conn) if c.is_time}
        for entity in parsed.entities:
            tag = f"|{entity.category}|" if entity.value is None else f"|{entity.category}=…|"
            category = self._category(
                entity.category, page, entity.file_line, f"|{entity.category}|"
            )
            extent = self.extent(lines, entity.start, entity.end)
            if extent is None:
                self.problem("empty_entity", page, entity.file_line, tag)
                continue
            if category in time_categories:
                if entity.value:
                    self.problem("time_value", page, entity.file_line, f"|{entity.category}|")
                self.plan.mentions.append(_PlannedMention(page, category, None, None, extent))
                continue
            segments = notes_store.segments_between(
                self.conn, self.version.id, extent[0], extent[2]
            )
            words = " ".join(anchors.quote(segments, extent[1], extent[3]).split())
            value = entity.value or None
            self.plan.mentions.append(_PlannedMention(page, category, words, value, extent))


def _plan(conn: sqlite3.Connection, version: VersionRow, request: LegacyImportRequest) -> _Plan:
    folder = Path(request.folder.strip()).expanduser()
    if not request.folder.strip():
        raise InvalidInput("Give the folder that holds the commentary files.")
    fmt = CommentaryFormat(
        file_pattern=request.file_pattern or legacy_commentary.DEFAULT_FILE_PATTERN
    )
    sources = paged_corpus.read_folder(folder, fmt.file_pattern)
    work_code = version.work_code
    body_fmt = BodyFormat(
        work_code=work_code,
        page_ref_commands=tuple(
            name.strip().lstrip("\\") for name in request.page_ref_commands if name.strip()
        ),
    )
    figure_folders = [folder, folder / "figures"]
    if request.figures_folder and request.figures_folder.strip():
        figure_folders.insert(0, Path(request.figures_folder.strip()).expanduser())

    plan = _Plan(files=len(sources))
    types = _Types(notes_store.list_note_types(conn))
    plan.types = types
    planner = _PagePlanner(
        conn,
        version,
        plan,
        types,
        {c.name.lower(): c.name for c in entities.list_categories(conn)},
        fmt,
        body_fmt,
        figure_folders,
    )
    for source in sources:
        planner.plan_page(legacy_commentary.parse_page(source, fmt))
    return plan


def _report(conn: sqlite3.Connection, version: VersionRow, plan: _Plan) -> LegacyReport:
    replaced = legacy.count_items(conn, version.id, plan.pages) if plan.pages else (0, 0)
    groups = [
        ReportGroup(code, title, [p for p in plan.problems if _MESSAGES[p.code][0] == code])
        for code, title in _GROUPS
    ]
    return LegacyReport(
        files=plan.files,
        pages=plan.pages,
        notes=sum(1 for note in plan.notes if note.kind == "note"),
        flagged_notes=sum(1 for note in plan.notes if note.flagged),
        chapter_notes=sum(1 for note in plan.notes if note.kind == "chapter"),
        remarks=sum(1 for note in plan.notes if note.kind == "remark"),
        mentions=len(plan.mentions),
        new_categories=plan.new_categories,
        new_types=plan.new_types,
        figures=len(plan.figures),
        replaced_notes=replaced[0],
        replaced_mentions=replaced[1],
        groups=[group for group in groups if group.items],
        repairs=plan.repairs,
    )


def _require_version(conn: sqlite3.Connection, version_id: int) -> VersionRow:
    version = corpus_store.get_version(conn, version_id)
    if version is None:
        raise NotFound(f"There is no text with id {version_id} in this library.")
    return version


def preview_import(library: Library, version_id: int, request: LegacyImportRequest) -> LegacyReport:
    """The dry run: read and check everything, write nothing."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        return _report(conn, version, _plan(conn, version, request))


def _anchor(conn: sqlite3.Connection, version_id: int, extent: Extent, quoted: bool) -> int:
    start_segment, start_offset, end_segment, end_offset = extent
    quote = WHOLE_UNIT
    if quoted:
        segments = notes_store.segments_between(conn, version_id, start_segment, end_segment)
        exact = anchors.quote(segments, start_offset, end_offset)
        quote = anchors.validate_span(segments, start_offset, end_offset, exact)
    return notes_store.insert_anchor(
        conn, version_id, start_segment, start_offset, end_segment, end_offset, quote
    )


def commit_import(library: Library, version_id: int, request: LegacyImportRequest) -> LegacyReport:
    """Import the commentary. Repeatable: a page's earlier import is replaced, not doubled."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        plan = _plan(conn, version, request)
        report = _report(conn, version, plan)
        if plan.pages:
            legacy.delete_items(conn, version.id, plan.pages)

        for name in plan.new_categories:
            entities.insert_category(conn, name)
        category_ids = {c.name: c.id for c in entities.list_categories(conn)}

        # Note types the files name that the library did not have are created first.
        created: dict[int, int] = {}
        for new_type in plan.types.new if plan.types is not None else []:
            created[new_type.id] = notes_store.insert_note_type(
                conn, new_type.name, new_type.code, new_type.color, new_type.role
            )

        for note in plan.notes:
            anchor_id = _anchor(conn, version.id, note.extent, quoted=note.scope == "span")
            note_id = notes_store.insert_annotation(
                conn,
                anchor_id,
                created.get(note.type_id, note.type_id),
                note.scope,
                note.level,
                "draft",
                note.body_md,
                note.legacy_id,
            )
            legacy.record_annotation(conn, version.id, note.page, note_id)
            links_service.refresh_inline_links(conn, version, note_id, note.body_md)

        for mention in plan.mentions:
            category_id = category_ids[mention.category]
            entity_id = None
            if mention.name is not None:
                entity_id, _ = entities.find_or_create_entity(
                    conn, category_id, mention.name, mention.value
                )
            anchor_id = _anchor(conn, version.id, mention.extent, quoted=True)
            mention_id = entities.insert_mention(conn, anchor_id, category_id, entity_id)
            legacy.record_mention(conn, version.id, mention.page, mention_id)

        for figure in plan.figures.values():
            if figure.source is not None:
                library.figures_dir.mkdir(exist_ok=True)
                shutil.copyfile(figure.source, library.figures_dir / figure.file)
            figures.upsert_figure(conn, figure.label, figure.file, figure.caption)
        return report
