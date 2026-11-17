from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import LegacyImportIn, LegacyReportOut
from pneutext.services import legacy_import
from pneutext.services.legacy_import import LegacyImportRequest

router = APIRouter(prefix="/api", tags=["legacy import"])


def _request(body: LegacyImportIn) -> LegacyImportRequest:
    return LegacyImportRequest(
        folder=body.folder,
        file_pattern=body.file_pattern,
        page_ref_commands=tuple(body.page_ref_commands),
        figures_folder=body.figures_folder,
    )


@router.post(
    "/versions/{version_id}/imports/commentary/preview", operation_id="previewCommentaryImport"
)
def preview_commentary_import(
    version_id: int, body: LegacyImportIn, library: LibraryDep
) -> LegacyReportOut:
    """The dry run: check a folder of legacy commentary files and report, writing nothing."""
    report = legacy_import.preview_import(library, version_id, _request(body))
    return LegacyReportOut.model_validate(asdict(report))


@router.post(
    "/versions/{version_id}/imports/commentary", operation_id="importCommentary", status_code=201
)
def import_commentary(
    version_id: int, body: LegacyImportIn, library: LibraryDep
) -> LegacyReportOut:
    report = legacy_import.commit_import(library, version_id, _request(body))
    return LegacyReportOut.model_validate(asdict(report))
