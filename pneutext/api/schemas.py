"""Pydantic models for API requests and responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SegmentKind = Literal["paragraph", "synopsis", "chapter_number", "ornament", "rule"]


class LibraryOut(BaseModel):
    """What the app shows about the open library."""

    app_version: str
    schema_version: int
    created_at: str


class WorkOut(BaseModel):
    code: str
    title: str
    author: str


class VersionSummaryOut(BaseModel):
    id: int
    work: WorkOut
    label: str
    language: str
    imported_at: str
    edit_seq: int
    first_page: int | None
    last_page: int | None
    page_count: int


class DivisionOut(BaseModel):
    id: int
    kind: str
    label: str
    page: int | None = Field(description="The page this division opens on.")


class VersionOut(VersionSummaryOut):
    measure: int = Field(description="95th-percentile line length, in code points.")
    pages: list[int] = Field(description="Every page number, in order.")
    divisions: list[DivisionOut]


class TextLineOut(BaseModel):
    """One print line with its words. Only the text projection carries this."""

    id: int
    segment_id: int
    kind: SegmentKind
    line_no: int | None
    start_offset: int = Field(description="Offset of the line within its segment, in code points.")
    length: int
    starts_paragraph: bool
    ends_paragraph: bool
    text: str


class PageTextOut(BaseModel):
    version_id: int
    edit_seq: int
    page: int
    prev_page: int | None
    next_page: int | None
    division: DivisionOut | None
    lines: list[TextLineOut]


class ShapeHighlightOut(BaseModel):
    """Where a note's span crosses a line: offsets within the line, in code points."""

    annotation_id: int
    type_id: int
    start: int
    end: int


class ShapeLineOut(BaseModel):
    """One print line without its words. This model must never gain a text field."""

    id: int
    kind: SegmentKind
    page: int
    line_no: int | None
    starts_paragraph: bool
    ends_paragraph: bool
    length: int = Field(description="Length in code points; 0 for page furniture.")
    highlights: list[ShapeHighlightOut]


class PageShapeOut(BaseModel):
    """The shape projection: all that blank mode and publishable exports may see."""

    version_id: int
    edit_seq: int
    page: int
    prev_page: int | None
    next_page: int | None
    division: DivisionOut | None
    lines: list[ShapeLineOut]


class CorpusImportIn(BaseModel):
    folder: str
    work_code: str
    title: str
    author: str = ""
    label: str = ""
    language: str = ""
    file_pattern: str | None = None
    allow_duplicate: bool = False


class ImportProblemOut(BaseModel):
    code: str
    page: int | None
    line: int | None
    message: str


class CorpusSummaryOut(BaseModel):
    pages: int
    lines: int
    paragraphs: int
    chapters: int
    first_page: int | None
    last_page: int | None


class CorpusImportPreviewOut(BaseModel):
    summary: CorpusSummaryOut
    problems: list[ImportProblemOut]
    existing_version_id: int | None = Field(
        description="Set when these exact files were imported before."
    )


class CorpusImportOut(CorpusImportPreviewOut):
    version_id: int
