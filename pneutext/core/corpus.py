"""Plain data describing a parsed corpus, before it is stored. No I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SegmentKind = Literal["paragraph", "synopsis", "chapter_number", "ornament", "rule"]

TEXT_KINDS: frozenset[str] = frozenset({"paragraph", "synopsis"})
"""Segment kinds that hold running text; the rest are page furniture."""

POSITION_STEP = 1000
"""Gap between segment positions, leaving room to insert segments later."""


@dataclass
class ParsedLine:
    """One print line: where it starts within its segment, and where it sits in print."""

    start_offset: int
    page: int
    line_no: int | None  # numbered among the page's text lines; None for furniture


@dataclass
class ParsedSegment:
    kind: SegmentKind
    text: str
    lines: list[ParsedLine] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedDivision:
    kind: str
    label: str
    first_segment: int  # index into ParsedCorpus.segments


@dataclass(frozen=True)
class ImportProblem:
    """Something the importer noticed. Carries a location and a tag, never corpus text."""

    code: str
    page: int | None
    line: int | None  # line within the source file, counting from 1
    message: str


@dataclass(frozen=True)
class CorpusSummary:
    pages: int
    lines: int
    paragraphs: int
    chapters: int
    first_page: int | None
    last_page: int | None


@dataclass
class ParsedCorpus:
    segments: list[ParsedSegment] = field(default_factory=list)
    divisions: list[ParsedDivision] = field(default_factory=list)
    problems: list[ImportProblem] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)

    def summary(self) -> CorpusSummary:
        return CorpusSummary(
            pages=len(self.pages),
            lines=sum(len(s.lines) for s in self.segments if s.kind in TEXT_KINDS),
            paragraphs=sum(1 for s in self.segments if s.kind == "paragraph"),
            chapters=sum(1 for d in self.divisions if d.kind == "chapter"),
            first_page=self.pages[0] if self.pages else None,
            last_page=self.pages[-1] if self.pages else None,
        )
