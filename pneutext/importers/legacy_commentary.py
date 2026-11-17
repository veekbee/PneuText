"""Parser for the legacy commentary format: one file per print page. Pure: no storage.

A commentary file is the page's text with inline markup, then a ``@@ Metatext`` line,
then one block per note::

    The ferry came into |places|Some Town|| on the {c_p45_tide}last tide{c_p45_tide/}.

    @@ Metatext

    {c_p45_tide}, Comment, 2
    The body of the note.
    {c_p45_tide/}

The files were typed by hand, so the parser reports problems instead of stopping at
them, and repairs only what is unambiguous. Nothing here quotes the text: a problem
carries its page, its line and the offending tag.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pneutext.importers.paged_corpus import PageSource, decode_page

DEFAULT_FILE_PATTERN = r"_comm_p(?P<page>\d+)(?:_[A-Za-z0-9]+)?\.txt$"

_TOKEN = re.compile(
    r"\{(?P<id>[^{}\s/|]+)(?P<slash>/)?\}"  # {id} or {id/}
    r"|(?P<entity_close>\|\|)"  # ||
    r"|\|(?P<category>[A-Za-z_]+)(?:=(?P<value>[^|\n]*))?\|"  # |category| or |category=value|
)
_DIRECTIVE = re.compile(r"<<\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:=(.*?))?>>", re.DOTALL)
_ONLY_DIRECTIVES = re.compile(r"(?:\s*<<.*?>>\s*)+", re.DOTALL)
_STRAY_BRACE = re.compile(r"\{[^\s{}]*|\}")
_HEADER = re.compile(r"\{(?P<id>[^{}\s/|]+)\}\s*(?:,(?P<fields>.*))?")
_CLOSING = re.compile(r"\{(?P<id>[^{}\s/|]+)/\}")


@dataclass(frozen=True)
class CommentaryFormat:
    """How to read a folder of legacy commentary files."""

    file_pattern: str = DEFAULT_FILE_PATTERN
    metatext_marker: str = r"@@\s*metatext"
    # Ids look like "c_p45_slug": a type prefix, the page, a short slug. Hand-typed ids
    # sometimes lack the "p" or the slug; the prefix and page are still clear.
    id_pattern: str = r"(?P<prefix>[A-Za-z]+)_p?(?P<page>\d+)(?:_(?P<slug>\S+))?"
    # Header fields written as key=value in older files: which key names the type, and
    # which the reading level.
    type_keys: tuple[str, ...] = ("type",)
    level_keys: tuple[str, ...] = ("read", "level")
    # Directives that hold the author's own chapter matter, and the note role each becomes.
    chapter_matter: dict[str, str] = field(
        default_factory=lambda: {"my_title": "chapter_title", "chsum": "chapter_summary"}
    )


@dataclass(frozen=True)
class Position:
    """A place in a page's stripped text: a text line (from 0) and a column in code points."""

    line: int
    column: int


@dataclass(frozen=True)
class Problem:
    code: str
    page: int
    line: int | None  # line in the commentary file, counting from 1
    tag: str  # the offending tag, id or name; never the text around it


@dataclass
class LegacySpan:
    id: str
    start: Position
    end: Position | None  # None when the span was never closed
    file_line: int


@dataclass(frozen=True)
class LegacyEntity:
    category: str
    value: str | None
    start: Position
    end: Position
    file_line: int


@dataclass(frozen=True)
class ChapterMatter:
    role: str
    body: str
    file_line: int


@dataclass
class LegacyBlock:
    id: str
    type_name: str | None
    level: int | None
    body: str
    file_line: int  # the header's line
    body_line: int  # the first line of the body


@dataclass(frozen=True)
class LegacyRemark:
    body: str
    file_line: int


@dataclass(frozen=True)
class TextLine:
    text: str  # the print line with all markup removed
    file_line: int


@dataclass
class ParsedPage:
    page: int
    name: str
    lines: list[TextLine] = field(default_factory=list)
    spans: list[LegacySpan] = field(default_factory=list)
    entities: list[LegacyEntity] = field(default_factory=list)
    chapter_matter: list[ChapterMatter] = field(default_factory=list)
    blocks: list[LegacyBlock] = field(default_factory=list)
    remarks: list[LegacyRemark] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    repairs: list[Problem] = field(default_factory=list)


def parse_page(source: PageSource, fmt: CommentaryFormat | None = None) -> ParsedPage:
    fmt = fmt or CommentaryFormat()
    parsed = ParsedPage(source.page, source.name)
    rows = decode_page(source)
    marker = re.compile(fmt.metatext_marker, re.IGNORECASE)
    split = next((i for i, row in enumerate(rows) if marker.fullmatch(row)), len(rows))
    _parse_text(parsed, rows[:split], fmt)
    _parse_metatext(parsed, rows[split + 1 :], split + 2, fmt)
    return parsed


# ---- The text part ----------------------------------------------------------


def _join_directives(rows: list[str]) -> list[tuple[int, str]]:
    """Number the rows from 1, joining a directive that runs over several lines into one."""
    joined: list[tuple[int, str]] = []
    pending: tuple[int, str] | None = None
    for number, row in enumerate(rows, start=1):
        if pending is not None:
            pending = (pending[0], pending[1] + " " + row)
            if ">>" in row:
                joined.append(pending)
                pending = None
        elif row.startswith("<<") and ">>" not in row:
            pending = (number, row)
        else:
            joined.append((number, row))
    if pending is not None:
        joined.append(pending)
    return joined


def _parse_text(parsed: ParsedPage, rows: list[str], fmt: CommentaryFormat) -> None:
    page = parsed.page
    open_spans: dict[str, LegacySpan] = {}
    open_entity: tuple[str, str | None, Position, int] | None = None

    for file_line, row in _join_directives(rows):
        if not row:
            continue
        if _ONLY_DIRECTIVES.fullmatch(row):
            for match in _DIRECTIVE.finditer(row):
                role = fmt.chapter_matter.get(match.group(1))
                if role is not None:
                    body = (match.group(2) or "").strip()
                    parsed.chapter_matter.append(ChapterMatter(role, body, file_line))
            continue

        line_index = len(parsed.lines)
        stripped: list[str] = []
        column = 0  # in code points of the stripped line
        cursor = 0
        for match in _TOKEN.finditer(row):
            piece = row[cursor : match.start()]
            stripped.append(piece)
            column += len(piece)
            cursor = match.end()
            here = Position(line_index, column)
            tag = match.group(0)

            if match.group("id") is not None:
                span_id = match.group("id")
                if match.group("slash"):
                    span = open_spans.pop(span_id, None)
                    if span is None:
                        parsed.problems.append(Problem("stray_closing_tag", page, file_line, tag))
                    else:
                        span.end = here
                elif span_id in open_spans:
                    # The same opening tag again can only be a closing tag missing its slash.
                    open_spans.pop(span_id).end = here
                    parsed.repairs.append(Problem("closing_tag_slash", page, file_line, tag))
                elif span_id.endswith("\\") and span_id[:-1] in open_spans:
                    # A backslash typed for the slash of a closing tag.
                    open_spans.pop(span_id[:-1]).end = here
                    parsed.repairs.append(Problem("closing_tag_slash", page, file_line, tag))
                else:
                    if any(span.id == span_id for span in parsed.spans):
                        parsed.problems.append(Problem("duplicate_id", page, file_line, tag))
                    span = LegacySpan(span_id, here, None, file_line)
                    open_spans[span_id] = span
                    parsed.spans.append(span)
            elif match.group("entity_close") is not None:
                if open_entity is None:
                    parsed.problems.append(Problem("stray_entity_end", page, file_line, tag))
                else:
                    category, value, start, opened_at = open_entity
                    parsed.entities.append(LegacyEntity(category, value, start, here, opened_at))
                    open_entity = None
            else:
                if open_entity is not None:
                    unclosed = f"|{open_entity[0]}|"
                    parsed.problems.append(
                        Problem("unclosed_entity", page, open_entity[3], unclosed)
                    )
                value = match.group("value")
                open_entity = (
                    match.group("category"),
                    value.strip() if value is not None else None,
                    here,
                    file_line,
                )

        stripped.append(row[cursor:])
        text = "".join(stripped)
        for stray in _STRAY_BRACE.finditer(text):
            parsed.problems.append(Problem("malformed_tag", page, file_line, stray.group(0)))
        parsed.lines.append(TextLine(text, file_line))

    for span in open_spans.values():
        parsed.problems.append(Problem("unclosed_span", page, span.file_line, f"{{{span.id}}}"))
    if open_entity is not None:
        parsed.problems.append(
            Problem("unclosed_entity", page, open_entity[3], f"|{open_entity[0]}|")
        )


# ---- The metatext part ------------------------------------------------------


def _header_fields(
    fields: str | None, fmt: CommentaryFormat
) -> tuple[str | None, int | None, list[str]]:
    """A block header's optional type name and level, plus anything that is neither.

    The fields come in any order: ``Comment, 2``; and in older files as ``type=Comment,
    read=2``.
    """
    type_name: str | None = None
    level: int | None = None
    odd: list[str] = []
    for item in (fields or "").split(","):
        item = item.strip()
        key, equals, value = (part.strip() for part in item.partition("="))
        if not item:
            continue
        if equals and key.lower() in fmt.type_keys and value and type_name is None:
            type_name = value
        elif equals and key.lower() in fmt.level_keys and value.isdigit() and level is None:
            level = int(value)
        elif item.isdigit() and level is None:
            level = int(item)
        elif not equals and not item.isdigit() and type_name is None:
            type_name = item
        else:
            odd.append(item)
    return type_name, level, odd


def _parse_metatext(
    parsed: ParsedPage, rows: list[str], first_file_line: int, fmt: CommentaryFormat
) -> None:
    page = parsed.page
    id_pattern = re.compile(fmt.id_pattern)
    span_ids = {span.id for span in parsed.spans}
    block: LegacyBlock | None = None
    body: list[str] = []
    remark: list[str] = []
    remark_line = 0

    def is_header(match: re.Match[str] | None) -> bool:
        if match is None:
            return False
        note_id = match.group("id")
        return (
            match.group("fields") is not None
            or note_id in span_ids
            or id_pattern.fullmatch(note_id) is not None
        )

    def close_block() -> None:
        nonlocal block, body
        if block is not None:
            block.body = "\n".join(body).strip("\n")
            parsed.blocks.append(block)
        block, body = None, []

    def flush_remark() -> None:
        nonlocal remark
        if any(line.strip() for line in remark):
            parsed.remarks.append(LegacyRemark("\n".join(remark).strip("\n"), remark_line))
        remark = []

    def open_block(match: re.Match[str], file_line: int) -> None:
        nonlocal block
        flush_remark()
        type_name, level, odd = _header_fields(match.group("fields"), fmt)
        note_id = match.group("id")
        for item in odd:
            parsed.problems.append(Problem("odd_header_field", page, file_line, item))
        if any(existing.id == note_id for existing in parsed.blocks):
            parsed.problems.append(Problem("duplicate_id", page, file_line, f"{{{note_id}}}"))
        block = LegacyBlock(note_id, type_name, level, "", file_line, file_line + 1)

    for offset, row in enumerate(rows):
        file_line = first_file_line + offset
        header = _HEADER.fullmatch(row)

        if block is None:
            if is_header(header):
                assert header is not None
                open_block(header, file_line)
            elif _CLOSING.fullmatch(row):
                parsed.problems.append(Problem("stray_closing_tag", page, file_line, row))
            elif not row:
                flush_remark()
            else:
                if not remark:
                    remark_line = file_line
                remark.append(row)
            continue

        closing = _CLOSING.search(row)
        if closing is not None and closing.group("id") == block.id:
            before, after = row[: closing.start()].rstrip(), row[closing.end() :].strip()
            if before:
                body.append(before)
            close_block()
            if after:
                remark, remark_line = [after], file_line
        elif (
            header is not None
            and header.group("id").rstrip("\\") == block.id
            and not header.group("fields")
        ):
            # The block's own opening tag again can only be a closing tag missing its slash.
            parsed.repairs.append(Problem("closing_tag_slash", page, file_line, row))
            close_block()
        elif is_header(header):
            assert header is not None
            parsed.problems.append(
                Problem("unclosed_block", page, block.file_line, f"{{{block.id}}}")
            )
            close_block()
            open_block(header, file_line)
        elif _CLOSING.fullmatch(row):
            # A closing tag for some other id closes nothing; the block stays open.
            parsed.problems.append(Problem("stray_closing_tag", page, file_line, row))
        else:
            body.append(row)

    if block is not None:
        parsed.problems.append(Problem("unclosed_block", page, block.file_line, f"{{{block.id}}}"))
        close_block()
    flush_remark()
