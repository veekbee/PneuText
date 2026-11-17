"""Importer for a paged corpus: one text file per print page, one print line per file line.

Blank lines separate paragraphs. A file that does not end with a blank line leaves its last
paragraph open, and the next file's first lines continue it. Whole-line ``<<name>>`` or
``<<name=value>>`` directives describe page furniture and chapter openings; what each
directive means is configuration (``CorpusFormat``), not code.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pneutext.core.corpus import (
    ImportProblem,
    ParsedCorpus,
    ParsedDivision,
    ParsedLine,
    ParsedSegment,
    SegmentKind,
)
from pneutext.core.errors import InvalidInput

SOURCE_FORMAT = "paged-text"
# The page number may be followed by a suffix, as in ..._corp_p016_ch2.txt.
DEFAULT_FILE_PATTERN = r"_corp_p(?P<page>\d+)(?:_[A-Za-z0-9]+)?\.txt$"

_DIRECTIVE = re.compile(r"<<\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:=(.*?))?>>")
_ONLY_DIRECTIVES = re.compile(r"(?:\s*<<.*?>>\s*)+")


@dataclass(frozen=True)
class DirectiveRule:
    """What one directive does when met in a corpus file."""

    furniture: SegmentKind | None = None  # emit a furniture segment of this kind
    division: str | None = None  # open a division of this kind, labeled by the value
    region: Literal["open", "close"] | None = None  # start or end a run of ``region_kind``
    region_kind: SegmentKind = "synopsis"
    commentary: bool = False  # belongs to the commentary, not the corpus; skipped here


def _default_directives() -> dict[str, DirectiveRule]:
    return {
        "chapter": DirectiveRule(furniture="chapter_number", division="chapter"),
        "chapter_ornament": DirectiveRule(furniture="ornament"),
        "section_decoration": DirectiveRule(furniture="ornament"),
        "section_ornament": DirectiveRule(furniture="ornament"),
        "top_bar": DirectiveRule(furniture="rule", region="open"),
        "bottom_bar": DirectiveRule(furniture="rule", region="close"),
        "my_title": DirectiveRule(commentary=True),
        "chsum": DirectiveRule(commentary=True),
    }


@dataclass(frozen=True)
class CorpusFormat:
    """How to read a folder of page files."""

    file_pattern: str = DEFAULT_FILE_PATTERN
    directives: dict[str, DirectiveRule] = field(default_factory=_default_directives)


@dataclass(frozen=True)
class PageSource:
    page: int
    name: str
    data: bytes


def read_folder(folder: Path, file_pattern: str = DEFAULT_FILE_PATTERN) -> list[PageSource]:
    """Find the page files in a folder, ordered by page number."""
    try:
        pattern = re.compile(file_pattern)
    except re.error as error:
        raise InvalidInput(f"The file-name pattern is not a valid expression: {error}.") from None
    if "page" not in pattern.groupindex:
        raise InvalidInput("The file-name pattern must capture the page number as (?P<page>...).")
    if not folder.is_dir():
        raise InvalidInput(f"There is no folder at {folder}.")

    sources: dict[int, PageSource] = {}
    for path in sorted(folder.iterdir()):
        match = pattern.search(path.name)
        if match is None or not path.is_file():
            continue
        try:
            page = int(match.group("page"))
        except ValueError:
            raise InvalidInput(
                f"The page number in the file name {path.name} is not a number."
            ) from None
        if page in sources:
            raise InvalidInput(
                f"Two files claim page {page}: {sources[page].name} and {path.name}."
            )
        sources[page] = PageSource(page, path.name, path.read_bytes())
    if not sources:
        raise InvalidInput(f"No page files matching the file-name pattern were found in {folder}.")
    return [sources[page] for page in sorted(sources)]


def content_hash(sources: list[PageSource]) -> str:
    """A fingerprint of the imported files: their page numbers and exact bytes."""
    digest = hashlib.sha256()
    for source in sources:
        digest.update(f"{source.page}:{len(source.data)}:".encode())
        digest.update(source.data)
    return digest.hexdigest()


def decode_page(source: PageSource) -> list[str]:
    """A page file's lines: UTF-8, NFC-normalized, with surrounding whitespace removed."""
    try:
        text = source.data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidInput(f"The file {source.name} is not UTF-8 text.") from None
    return [unicodedata.normalize("NFC", line).strip() for line in text.splitlines()]


def parse_pages(sources: list[PageSource], fmt: CorpusFormat | None = None) -> ParsedCorpus:
    """Turn page files into segments, print lines and divisions. Pure: touches no storage."""
    fmt = fmt or CorpusFormat()
    corpus = ParsedCorpus()
    open_segment: ParsedSegment | None = None  # the paragraph being built, if any
    region_kind: SegmentKind | None = None  # set while inside a region such as a synopsis
    region_opened_at: tuple[int, int] | None = None
    previous_page: int | None = None

    def problem(code: str, page: int | None, line: int | None, message: str) -> None:
        corpus.problems.append(ImportProblem(code, page, line, message))

    for source in sources:
        page = source.page
        corpus.pages.append(page)
        if previous_page is not None and page != previous_page + 1:
            problem(
                "page_gap",
                page,
                None,
                f"Page {page} follows page {previous_page}; the pages between are missing.",
            )
            open_segment = None  # never run a paragraph across missing pages
        previous_page = page

        lines = decode_page(source)
        if not any(lines):
            problem("empty_page", page, None, f"Page {page} ({source.name}) has no text.")
        line_no = 0

        for file_line, raw in enumerate(lines, start=1):
            if not raw:
                open_segment = None
                continue

            if _ONLY_DIRECTIVES.fullmatch(raw):
                open_segment = None
                for match in _DIRECTIVE.finditer(raw):
                    name, value = match.group(1), (match.group(2) or "").strip()
                    rule = fmt.directives.get(name)
                    if rule is None:
                        problem(
                            "unknown_directive",
                            page,
                            file_line,
                            f"Page {page}, line {file_line}: unknown directive <<{name}>>; "
                            "it was left out of the text.",
                        )
                        continue
                    if rule.commentary:
                        problem(
                            "commentary_directive",
                            page,
                            file_line,
                            f"Page {page}, line {file_line}: <<{name}>> belongs to the "
                            "commentary, not the corpus; it was left out of the text.",
                        )
                        continue
                    if rule.region == "close":
                        if region_kind is None:
                            problem(
                                "region_not_open",
                                page,
                                file_line,
                                f"Page {page}, line {file_line}: <<{name}>> closes a block "
                                "that was never opened.",
                            )
                        region_kind, region_opened_at = None, None
                    if rule.furniture is not None:
                        segment = ParsedSegment(rule.furniture, value if rule.division else "")
                        segment.lines.append(ParsedLine(0, page, None))
                        corpus.segments.append(segment)
                        if rule.division is not None:
                            if not value:
                                problem(
                                    "division_without_label",
                                    page,
                                    file_line,
                                    f"Page {page}, line {file_line}: <<{name}>> has no value.",
                                )
                            corpus.divisions.append(
                                ParsedDivision(rule.division, value, len(corpus.segments) - 1)
                            )
                    if rule.region == "open":
                        region_kind, region_opened_at = rule.region_kind, (page, file_line)
                continue

            if "<<" in raw or ">>" in raw:
                problem(
                    "marker_in_text",
                    page,
                    file_line,
                    f"Page {page}, line {file_line}: a directive marker appears inside a line "
                    "of text; the line was kept as text.",
                )

            line_no += 1
            kind: SegmentKind = region_kind or "paragraph"
            if open_segment is None or open_segment.kind != kind:
                open_segment = ParsedSegment(kind, raw)
                open_segment.lines.append(ParsedLine(0, page, line_no))
                corpus.segments.append(open_segment)
            else:
                # One space stands where the print line break fell.
                open_segment.lines.append(ParsedLine(len(open_segment.text) + 1, page, line_no))
                open_segment.text += " " + raw

    if region_kind is not None and region_opened_at is not None:
        page, file_line = region_opened_at
        problem(
            "region_not_closed",
            page,
            file_line,
            f"Page {page}, line {file_line}: a block opened here is never closed.",
        )
    return corpus
