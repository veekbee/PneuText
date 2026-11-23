from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import (
    CorpusImportIn,
    CorpusImportOut,
    CorpusImportPreviewOut,
    CorpusSummaryOut,
    DivisionOut,
    ImportProblemOut,
    MentionMarkOut,
    PageShapeOut,
    PageTextOut,
    ShapeHighlightOut,
    ShapeLineOut,
    TextLineOut,
    VersionOut,
    VersionSummaryOut,
    WorkOut,
)
from pneutext.services import corpus as corpus_service
from pneutext.services.corpus import CorpusImportPreview, CorpusImportRequest
from pneutext.store.corpus import DivisionRow, VersionRow

router = APIRouter(prefix="/api", tags=["corpus"])


def _summary_fields(version: VersionRow) -> dict[str, object]:
    return {
        "id": version.id,
        "work": WorkOut(code=version.work_code, title=version.title, author=version.author),
        "label": version.label,
        "language": version.language,
        "imported_at": version.imported_at,
        "edit_seq": version.edit_seq,
        "first_page": version.first_page,
        "last_page": version.last_page,
        "page_count": version.page_count,
    }


def _division(division: DivisionRow) -> DivisionOut:
    return DivisionOut(**asdict(division))


def _request(body: CorpusImportIn) -> CorpusImportRequest:
    return CorpusImportRequest(
        folder=body.folder,
        work_code=body.work_code,
        title=body.title,
        author=body.author,
        label=body.label,
        language=body.language,
        file_pattern=body.file_pattern,
    )


def _preview_fields(preview: CorpusImportPreview) -> dict[str, object]:
    return {
        "summary": CorpusSummaryOut(**asdict(preview.summary)),
        "problems": [ImportProblemOut(**asdict(p)) for p in preview.problems],
        "existing_version_id": preview.existing_version_id,
    }


@router.get("/versions", operation_id="listVersions")
def list_versions(library: LibraryDep) -> list[VersionSummaryOut]:
    return [VersionSummaryOut(**_summary_fields(v)) for v in corpus_service.list_versions(library)]


@router.get("/versions/{version_id}", operation_id="getVersion")
def get_version(version_id: int, library: LibraryDep) -> VersionOut:
    detail = corpus_service.get_version(library, version_id)
    return VersionOut(
        **_summary_fields(detail.version),
        measure=detail.measure,
        pages=detail.pages,
        divisions=[
            DivisionOut(**asdict(d), note_count=detail.note_counts.get(d.id, 0))
            for d in detail.divisions
        ],
    )


@router.get("/versions/{version_id}/pages/{page}/text", operation_id="getPageText")
def get_page_text(version_id: int, page: int, library: LibraryDep) -> PageTextOut:
    """The text projection of a page. Blank mode never requests this."""
    result = corpus_service.get_page_text(library, version_id, page)
    return PageTextOut(
        version_id=result.version_id,
        edit_seq=result.edit_seq,
        page=result.page,
        prev_page=result.prev_page,
        next_page=result.next_page,
        division=None if result.division is None else _division(result.division),
        lines=[
            TextLineOut(
                id=line.shape.id,
                segment_id=line.shape.segment_id,
                kind=line.shape.kind,
                line_no=line.shape.line_no,
                start_offset=line.shape.start_offset,
                length=line.shape.length,
                starts_paragraph=line.shape.starts_paragraph,
                ends_paragraph=line.shape.ends_paragraph,
                text=line.text,
                highlights=[ShapeHighlightOut(**asdict(h)) for h in marks],
                mentions=[MentionMarkOut(**asdict(m)) for m in tagged],
            )
            for line, marks, tagged in zip(
                result.lines, result.highlights, result.mentions, strict=True
            )
        ],
    )


@router.get("/versions/{version_id}/pages/{page}/shape", operation_id="getPageShape")
def get_page_shape(version_id: int, page: int, library: LibraryDep) -> PageShapeOut:
    """The shape projection of a page: line lengths and highlight positions, no text."""
    result = corpus_service.get_page_shape(library, version_id, page)
    return PageShapeOut(
        version_id=result.version_id,
        edit_seq=result.edit_seq,
        page=result.page,
        prev_page=result.prev_page,
        next_page=result.next_page,
        division=None if result.division is None else _division(result.division),
        lines=[
            ShapeLineOut(
                id=line.id,
                kind=line.kind,
                page=line.page,
                line_no=line.line_no,
                starts_paragraph=line.starts_paragraph,
                ends_paragraph=line.ends_paragraph,
                length=line.length,
                highlights=[ShapeHighlightOut(**asdict(h)) for h in line.highlights],
                mentions=[MentionMarkOut(**asdict(m)) for m in tagged],
            )
            for line, tagged in zip(result.lines, result.mentions, strict=True)
        ],
    )


@router.post("/imports/corpus/preview", operation_id="previewCorpusImport")
def preview_corpus_import(body: CorpusImportIn, library: LibraryDep) -> CorpusImportPreviewOut:
    """Read and check a folder of page files without writing anything."""
    return CorpusImportPreviewOut(
        **_preview_fields(corpus_service.preview_import(library, _request(body)))
    )


@router.post("/imports/corpus", operation_id="importCorpus", status_code=201)
def import_corpus(body: CorpusImportIn, library: LibraryDep) -> CorpusImportOut:
    version_id, preview = corpus_service.commit_import(
        library, _request(body), allow_duplicate=body.allow_duplicate
    )
    return CorpusImportOut(version_id=version_id, **_preview_fields(preview))
