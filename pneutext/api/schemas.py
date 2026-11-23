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
    note_count: int = Field(default=0, description="How many notes begin in it.")


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


class MentionMarkOut(BaseModel):
    """Where an entity mention crosses a line: offsets within the line, in code points."""

    mention_id: int
    category_id: int
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
    mentions: list[MentionMarkOut]


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
    mentions: list[MentionMarkOut]


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
    source_format: Literal["paged", "tagged"] = Field(
        default="paged",
        description="A folder of page files, or the whole text in one tagged file.",
    )
    first_page: int = Field(default=1, description="Tagged: the page the file begins on.")
    page_break: str | None = Field(
        default=None, description="Tagged: a pattern matching the end-of-page marker."
    )
    line_width: int | None = Field(
        default=None, description="Tagged: characters per estimated print line."
    )


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
    attrs: dict[str, bool | int | str | None] | None = None
    children: list[NoteNode] | None = None


class BacklinkOut(BaseModel):
    """A note that refers to a page, a passage or another note."""

    note_id: int
    type_id: int
    level: int
    status: Literal["draft", "ready"]
    page: int | None = Field(description="Where the referring note sits.")
    line_no: int | None
    target: str | None = Field(description="What it cites, such as 'p. 45.12'.")


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
    backlinks: list[BacklinkOut] = Field(description="The notes that refer to this one.")


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
    version_id: int | None = Field(
        default=None, description="The text the note belongs to, so its references resolve."
    )
    note_id: int | None = Field(
        default=None, description="The note being edited, so dates are worked out for its place."
    )


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
    new_types: list[str] = Field(description="Note types the files name that will be created.")
    figures: int
    replaced_notes: int = Field(description="Notes from an earlier import that this one replaces.")
    replaced_mentions: int
    groups: list[ReportGroupOut]
    repairs: list[ReportItemOut]


class PassageEndOut(BaseModel):
    page: int | None
    line_no: int | None
    end_page: int | None
    end_line_no: int | None
    here: bool = Field(description="Whether this end lies on the page being shown.")


class PassageLinkOut(BaseModel):
    """A link made passage to passage."""

    id: int
    relation: str
    source: PassageEndOut
    target: PassageEndOut


class PassageLinkIn(BaseModel):
    source: SpanIn
    target: SpanIn


class PageLinksOut(BaseModel):
    backlinks: list[BacklinkOut] = Field(description="Notes that refer to this page.")
    passages: list[PassageLinkOut] = Field(description="Passage links touching this page.")


class ReferenceHitOut(BaseModel):
    page: int
    line_no: int | None


class CorpusHitOut(BaseModel):
    """A place in the text where the query was found, with its print line."""

    page: int
    line_no: int | None
    before: str
    match: str
    after: str


class NoteHitOut(BaseModel):
    note_id: int
    type_id: int
    level: int
    status: Literal["draft", "ready"]
    page: int | None
    line_no: int | None
    excerpt: str


class SearchOut(BaseModel):
    query: str
    reference: ReferenceHitOut | None = Field(description="Set when the query names a place.")
    corpus: list[CorpusHitOut] | None = Field(
        description="Hits in the text; null when the text was not searched, as in blank mode."
    )
    notes: list[NoteHitOut]


class FigureUseOut(BaseModel):
    note_id: int
    type_id: int
    version_id: int
    page: int | None
    line_no: int | None
    placed: bool = Field(description="Placed in the note, as opposed to referred to.")


class FigureOut(BaseModel):
    id: int
    label: str
    file: str
    caption: str
    credit: str
    has_file: bool
    uses: list[FigureUseOut] = Field(description="Where the figure is used; empty if unused.")


class FigureIn(BaseModel):
    label: str
    caption: str = ""
    credit: str = ""


class FigureUpdateIn(BaseModel):
    label: str | None = None
    caption: str | None = None
    credit: str | None = None


RoleName = Literal["note", "definition", "chapter_title", "chapter_summary"]


class NoteTypeIn(BaseModel):
    name: str
    code: str
    color: str = "#8a8a8a"
    role: RoleName = "note"


class NoteTypeUpdateIn(BaseModel):
    name: str | None = None
    code: str | None = None
    color: str | None = None
    role: RoleName | None = None


class MergeIn(BaseModel):
    into_id: int = Field(description="The one that remains and takes over everything.")


class CategoryOut(BaseModel):
    id: int
    name: str
    color: str
    sort: int
    is_time: bool


class CategoryIn(BaseModel):
    name: str


class CategoryUpdateIn(BaseModel):
    name: str | None = None
    color: str | None = None


class EntityPlaceOut(BaseModel):
    page: int
    line_no: int | None


class EntityOut(BaseModel):
    id: int
    category_id: int
    name: str
    value: str | None
    places: list[EntityPlaceOut] = Field(description="Every place it occurs in this text.")


class EntityUpdateIn(BaseModel):
    name: str | None = None
    value: str | None = Field(default=None, description="A normalized form; empty to clear it.")


class TimeValueIn(BaseModel):
    """A time: an absolute date at any precision, or an offset from another time."""

    kind: Literal["absolute", "offset"]
    at: str | None = Field(default=None, description="1871, 1871-10, 1871-10-28 or with a time.")
    offset: str | None = Field(default=None, description="An ISO 8601 duration, such as P5D.")
    relative_to_label: str | None = Field(
        default=None, description="The labeled time it counts from; the previous time if empty."
    )
    label: str | None = None
    remark: str = ""


class MentionIn(BaseModel):
    span: SpanIn
    category_id: int
    entity_id: int | None = None
    entity_name: str | None = None
    value: str | None = None
    time: TimeValueIn | None = None


class SinceOut(BaseModel):
    label: str
    iso: str
    words: str


class ChronologyRowOut(BaseModel):
    """A time point in reading order, with the narrative date it resolves to."""

    mention_id: int
    page: int | None
    line_no: int | None
    kind: Literal["absolute", "offset"] | None = Field(description="Null until a value is given.")
    at: str | None
    offset: str | None
    relative_to_label: str | None
    label: str | None
    remark: str
    date_iso: str | None
    date_words: str | None
    elapsed_iso: str | None = Field(description="For a chain with no date: time since it began.")
    elapsed_words: str | None
    problem: str | None
    since: list[SinceOut] = Field(description="Time elapsed since each earlier labeled point.")


class NoteSummaryOut(BaseModel):
    id: int
    type_id: int
    scope: Literal["span", "page", "chapter"]
    level: int
    status: Literal["draft", "ready"]
    tags: list[str]
    page: int | None
    line_no: int | None
    excerpt: str


class BulkStatusIn(BaseModel):
    note_ids: list[int]
    status: Literal["draft", "ready"]


class TodoRemarkOut(BaseModel):
    note: NoteSummaryOut
    text: str


class BrokenReferenceOut(BaseModel):
    note: NoteSummaryOut
    form: str


class UnvaluedTimeOut(BaseModel):
    mention_id: int
    page: int | None
    line_no: int | None


class UnusedFigureOut(BaseModel):
    id: int
    label: str
    caption: str


class TodoListOut(BaseModel):
    """Everything still to be dealt with before the notes can be published."""

    remarks: list[TodoRemarkOut]
    drafts: list[NoteSummaryOut]
    broken_references: list[BrokenReferenceOut]
    orphaned: list[NoteSummaryOut]
    unused_figures: list[UnusedFigureOut]
    times_without_value: list[UnvaluedTimeOut]


class ProfileOut(BaseModel):
    """An edition: which notes an export includes."""

    id: int
    name: str
    type_ids: list[int] | None = Field(description="Note types included; null means all.")
    levels: list[int]
    statuses: list[Literal["draft", "ready"]]


class ProfileIn(BaseModel):
    name: str
    type_ids: list[int] | None = None
    levels: list[int] = [1]
    statuses: list[Literal["draft", "ready"]] = ["ready"]


class ExportDefaultsOut(BaseModel):
    folder: str = Field(description="Where the export is written unless another folder is given.")
    pdf_builder: str | None = Field(description="The installed program that can build the PDF.")


class MonographIn(BaseModel):
    profile_id: int
    folder: str | None = None
    build_pdf: bool = True


class MonographOut(BaseModel):
    folder: str
    files: list[str]
    notes: int
    pages: int
    pdf: str | None
    build: str = Field(description="What happened with the PDF, in plain words.")
    warnings: list[str]


class BackupIn(BaseModel):
    folder: str | None = None
    include_text: bool = Field(description="False leaves the corpus text out.")


class BackupOut(BaseModel):
    folder: str
    files: list[str]
    includes_text: bool
