from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Response

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import (
    BackupIn,
    BackupOut,
    ExportDefaultsOut,
    MonographIn,
    MonographOut,
    ProfileIn,
    ProfileOut,
)
from pneutext.core.errors import NotFound
from pneutext.services import export as export_service
from pneutext.services.export import ProfileInput
from pneutext.store import corpus as corpus_store
from pneutext.store import db, exports

router = APIRouter(prefix="/api", tags=["export"])


def _input(body: ProfileIn) -> ProfileInput:
    return ProfileInput(body.name, body.type_ids, body.levels, list(body.statuses))


@router.get("/export-profiles", operation_id="listProfiles")
def list_profiles(library: LibraryDep) -> list[ProfileOut]:
    return [ProfileOut(**asdict(row)) for row in export_service.list_profiles(library)]


@router.post("/export-profiles", operation_id="createProfile", status_code=201)
def create_profile(body: ProfileIn, library: LibraryDep) -> ProfileOut:
    return ProfileOut(**asdict(export_service.create_profile(library, _input(body))))


@router.put("/export-profiles/{profile_id}", operation_id="updateProfile")
def update_profile(profile_id: int, body: ProfileIn, library: LibraryDep) -> ProfileOut:
    return ProfileOut(**asdict(export_service.update_profile(library, profile_id, _input(body))))


@router.delete("/export-profiles/{profile_id}", operation_id="deleteProfile", status_code=204)
def delete_profile(profile_id: int, library: LibraryDep) -> Response:
    export_service.delete_profile(library, profile_id)
    return Response(status_code=204)


@router.get(
    "/versions/{version_id}/exports/monograph/defaults", operation_id="getMonographDefaults"
)
def get_monograph_defaults(
    version_id: int, profile_id: int, library: LibraryDep
) -> ExportDefaultsOut:
    """Where an edition would be written, and whether a PDF can be built here."""
    with db.transaction(library.db_path) as conn:
        version = corpus_store.get_version(conn, version_id)
        profile = exports.get_profile(conn, profile_id)
    if version is None or profile is None:
        raise NotFound("That text or edition no longer exists.")
    return ExportDefaultsOut(
        folder=str(export_service.default_folder(library, version, profile)),
        pdf_builder=export_service.pdf_builder(),
    )


@router.post("/versions/{version_id}/exports/monograph", operation_id="exportMonograph")
def export_monograph(version_id: int, body: MonographIn, library: LibraryDep) -> MonographOut:
    """Write the monograph as a LaTeX project, and build the PDF if LaTeX is installed."""
    result = export_service.export_monograph(
        library, version_id, body.profile_id, body.folder, body.build_pdf
    )
    return MonographOut(**asdict(result))


@router.post("/exports/backup", operation_id="exportBackup")
def export_backup(body: BackupIn, library: LibraryDep) -> BackupOut:
    """Write the whole library as JSON plus figures, with or without the corpus text."""
    return BackupOut(
        **asdict(export_service.export_backup(library, body.folder, body.include_text))
    )
