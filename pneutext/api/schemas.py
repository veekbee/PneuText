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


class ShapeHighlightOut(BaseModel):
    """Where a note's span crosses a line: offsets within the line, in code points."""

    annotation_id: int
    type_id: int
    level: int = Field(description="The note's reading level: 1, or 2 for have-read notes.")
    start: int
    end: int


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
    highlights: list[ShapeHighlightOut]


class PageTextOut(BaseModel):
    version_id: int
    edit_seq: int
    page: int
    prev_page: int | None
    next_page: int | None
    division: DivisionOut | None
    lines: list[TextLineOut]


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


class NoteTypeOut(BaseModel):
    id: int
    name: str
    code: str
    color: str
    sort: int
    role: Literal["note", "definition", "chapter_title", "chapter_summary"]


class SpanIn(BaseModel):
    """A selected passage: where it runs (end exclusive) and the words it covers."""

    start_segment_id: int
    start_offset: int = Field(description="In code points.")
    end_segment_id: int
    end_offset: int
    exact: str = Field(description="The selected text; the server checks it against the corpus.")


class AnchorOut(BaseModel):
    """Where a note attaches. Carries positions only, never the words."""

    start_segment_id: int
    start_offset: int
    end_segment_id: int
    end_offset: int
    status: Literal["ok", "orphaned"]


class PlaceOut(BaseModel):
    page: int
    line_no: int | None


class NoteNode(BaseModel):
    """One node of a parsed note body."""

    type: str
    text: str | None = None
    attrs: dict[str, str | int | None] | None = None
    children: list[NoteNode] | None = None


class NoteOut(BaseModel):
    id: int
    version_id: int
    type_id: int
    scope: Literal["span", "page", "chapter"]
    level: int
    status: Literal["draft", "ready"]
    body_md: str
    body: NoteNode = Field(description="The body parsed into a syntax tree.")
    tags: list[str]
    legacy_id: str | None
    created_at: str
    updated_at: str
    anchor: AnchorOut
    start: PlaceOut | None = Field(description="Where the passage begins in print.")
    end: PlaceOut | None = Field(description="Where it ends.")


class NoteCreateIn(BaseModel):
    type_id: int
    scope: Literal["span", "page", "chapter"] = "span"
    level: int = 1
    status: Literal["draft", "ready"] = "draft"
    body_md: str = ""
    tags: list[str] = []
    span: SpanIn | None = None
    page: int | None = None
    division_id: int | None = None


class NoteUpdateIn(BaseModel):
    """Fields to change; anything left out stays as it is."""

    type_id: int | None = None
    level: int | None = None
    status: Literal["draft", "ready"] | None = None
    body_md: str | None = None
    tags: list[str] | None = None
    span: SpanIn | None = None


class RenderIn(BaseModel):
    body_md: str


class RenderOut(BaseModel):
    body: NoteNode


class LegacyImportIn(BaseModel):
    folder: str
    file_pattern: str | None = None
    page_ref_commands: list[str] = Field(
        default=[], description="LaTeX commands in the old notes that cite a page of the work."
    )
    figures_folder: str | None = None


class ReportItemOut(BaseModel):
    """One finding. Names the offending tag with its page and line; never quotes the text."""

    code: str
    page: int
    line: int | None
    tag: str
    message: str


class ReportGroupOut(BaseModel):
    code: str
    title: str
    items: list[ReportItemOut]


class LegacyReportOut(BaseModel):
    files: int
    pages: list[int]
    notes: int
    flagged_notes: int
    chapter_notes: int
    remarks: int
    mentions: int
    new_categories: list[str]
    figures: int
    replaced_notes: int = Field(description="Notes from an earlier import that this one replaces.")
    replaced_mentions: int
    groups: list[ReportGroupOut]
    repairs: list[ReportItemOut]
