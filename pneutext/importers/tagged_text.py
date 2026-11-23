"""Importer for a whole text in one tagged file: one paragraph per line.

Blank lines separate paragraphs. A marker such as ``{p25}`` stands wherever a print page
ends, also in the middle of a paragraph. Block tags such as ``<chapter>IV</chapter>`` and
``<chapter_sections>...</chapter_sections>`` mark chapter openings; a line holding only
``{section_break}`` is a section ornament. What each tag means is configuration
(``TaggedFormat``), not code.

Such a file records where pages break but not where print lines do, so lines are
estimated by filling each to a given width. Page numbers are those of the print edition;
line numbers are not, and the import says so.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pneutext.core.corpus import (
    ImportProblem,
    ParsedCorpus,
    ParsedDivision,
    ParsedLine,
    ParsedSegment,
    SegmentKind,
)
from pneutext.core.errors import InvalidInput
from pneutext.core.shape import INDENT
from pneutext.importers.paged_corpus import PageSource, content_hash

SOURCE_FORMAT = "tagged-text"
DEFAULT_PAGE_BREAK = r"\{p\d*\}"
DEFAULT_LINE_WIDTH = 65

_TAG = re.compile(r"<(/?)([A-Za-z_][A-Za-z0-9_]*)>")
_MARKER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class TaggedFormat:
    """How to read a tagged single-file text."""

    page_break: str = DEFAULT_PAGE_BREAK  # a pattern matching the end-of-page marker
    first_page: int = 1  # the number of the page the file begins on
    line_width: int = DEFAULT_LINE_WIDTH  # characters per estimated print line
    # Tags whose line opens a division of this kind, labeled by the line's words.
    divisions: dict[str, str] = field(
        default_factory=lambda: {"chapter": "chapter", "epilogue": "chapter"}
    )
    # Tags whose text is a chapter synopsis.
    synopsis: tuple[str, ...] = ("chapter_sections",)
    # Markers that stand alone on a line as page furniture.
    furniture: dict[str, SegmentKind] = field(default_factory=lambda: {"section_break": "ornament"})
    # Tags that only set a block apart; their text is kept as ordinary paragraphs.
    plain: tuple[str, ...] = ("acknowledgments", "epigraph", "title_page", "c")


def read_file(path: Path) -> PageSource:
    """Read the file as one source; its fingerprint is that of its bytes."""
    if path.is_dir():
        raise InvalidInput(f"{path} is a folder. Give the text file itself.")
    if not path.is_file():
        raise InvalidInput(f"There is no file at {path}.")
    return PageSource(0, path.name, path.read_bytes())


def file_hash(source: PageSource) -> str:
    return content_hash([source])


def _wrap(words: list[str], width: int, first_width: int) -> list[list[str]]:
    """Fill lines with words, greedily. The first line may be narrower (an indent)."""
    lines: list[list[str]] = []
    current: list[str] = []
    length = 0
    limit = first_width
    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and length + extra > limit:
            lines.append(current)
            current, length, limit = [], 0, width
            extra = len(word)
        current.append(word)
        length += extra
    if current:
        lines.append(current)
    return lines


def parse_text(source: PageSource, fmt: TaggedFormat | None = None) -> ParsedCorpus:
    """Turn a tagged file into segments, estimated print lines and divisions. Pure."""
    fmt = fmt or TaggedFormat()
    if fmt.line_width < 20:
        raise InvalidInput("Give at least 20 characters per line.")
    try:
        page_break = re.compile(fmt.page_break)
    except re.error as error:
        raise InvalidInput(f"The page-break marker is not a valid expression: {error}.") from None
    if page_break.match("") is not None:
        raise InvalidInput("The page-break marker must not match nothing.")
    try:
        text = source.data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidInput(f"The file {source.name} is not UTF-8 text.") from None

    corpus = ParsedCorpus()
    page = fmt.first_page
    line_no = 0  # text lines so far on the current page
    pages_with_lines: set[int] = set()
    split_words = 0
    synopsis_open = False  # inside a synopsis block that runs over several lines
    known = {*fmt.divisions, *fmt.synopsis, *fmt.plain}

    def problem(code: str, at: int | None, file_line: int | None, message: str) -> None:
        corpus.problems.append(ImportProblem(code, at, file_line, message))

    def turn_page() -> None:
        nonlocal page, line_no
        if page not in pages_with_lines:
            problem("empty_page", page, None, f"Page {page} has no text.")
        page += 1
        line_no = 0

    for file_line, raw in enumerate(text.splitlines(), start=1):
        row = unicodedata.normalize("NFC", raw).strip()
        if not row:
            continue

        # What the line is: read its tags, then set them aside.
        opened = [m.group(2) for m in _TAG.finditer(row) if not m.group(1)]
        closed = [m.group(2) for m in _TAG.finditer(row) if m.group(1)]
        for name in dict.fromkeys(opened + closed):
            if name not in known:
                problem(
                    "unknown_tag",
                    page,
                    file_line,
                    f"Page {page}, line {file_line} of the file: unknown tag <{name}>; "
                    "its text was kept as an ordinary paragraph.",
                )
        division = next((name for name in opened if name in fmt.divisions), None)
        is_synopsis = synopsis_open or any(name in fmt.synopsis for name in opened)
        if any(name in fmt.synopsis for name in opened):
            synopsis_open = True
        if any(name in fmt.synopsis for name in closed):
            synopsis_open = False
        row = _TAG.sub("", row).strip()

        # Page furniture standing alone on its line.
        alone = _MARKER.fullmatch(row)
        if alone is not None and alone.group(1) in fmt.furniture and not page_break.fullmatch(row):
            segment = ParsedSegment(fmt.furniture[alone.group(1)], "")
            segment.lines.append(ParsedLine(0, page, None))
            corpus.segments.append(segment)
            pages_with_lines.add(page)
            continue

        # Cut the paragraph where pages end. A word the page break falls inside of is
        # kept whole, on the page where it begins.
        parts = page_break.split(row)
        for index in range(len(parts) - 1):
            head, tail = parts[index], parts[index + 1]
            if head[-1:].isalnum() and tail[:1].isalnum():
                rest = re.match(r"[^\W_]+[^\s]*", tail)
                assert rest is not None
                parts[index], parts[index + 1] = head + rest.group(0), tail[rest.end() :]
                split_words += 1

        if division is not None:
            label = " ".join(" ".join(parts).split())
            segment = ParsedSegment("chapter_number", label)
            segment.lines.append(ParsedLine(0, page, None))
            corpus.segments.append(segment)
            corpus.divisions.append(
                ParsedDivision(fmt.divisions[division], label, len(corpus.segments) - 1)
            )
            pages_with_lines.add(page)
            for _ in parts[1:]:
                turn_page()
            continue

        kind: SegmentKind = "synopsis" if is_synopsis else "paragraph"
        segment = ParsedSegment(kind, "")
        for index, part in enumerate(parts):
            if index > 0:
                turn_page()
            words = part.split()
            if not words:
                continue
            starts_paragraph = not segment.text
            indent = INDENT if starts_paragraph and kind == "paragraph" else 0
            for line_words in _wrap(words, fmt.line_width, fmt.line_width - indent):
                line_no += 1
                # One space stands where a line break falls, as in the paged format.
                start = len(segment.text) + (1 if segment.text else 0)
                segment.lines.append(ParsedLine(start, page, line_no))
                segment.text += (" " if segment.text else "") + " ".join(line_words)
            pages_with_lines.add(page)
        if segment.lines:
            corpus.segments.append(segment)

    if synopsis_open:
        problem("region_not_closed", None, None, "A synopsis block is opened and never closed.")
    corpus.pages = sorted(pages_with_lines)
    if split_words:
        said = "1 word runs" if split_words == 1 else f"{split_words} words run"
        problem(
            "words_across_pages",
            None,
            None,
            f"{said} across a page break; each was kept whole on the page where it begins.",
        )
    problem(
        "estimated_lines",
        None,
        None,
        f"This file marks pages but not print lines. Lines were filled to {fmt.line_width} "
        "characters, so page numbers match the print edition and line numbers do not.",
    )
    return corpus
