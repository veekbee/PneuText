from __future__ import annotations

from fastapi import APIRouter

import pneutext
from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import LibraryOut
from pneutext.services import library as library_service

router = APIRouter(prefix="/api", tags=["library"])


@router.get("/library", operation_id="getLibrary")
def get_library_info(library: LibraryDep) -> LibraryOut:
    info = library_service.describe(library)
    return LibraryOut(
        app_version=pneutext.__version__,
        schema_version=info.schema_version,
        created_at=info.created_at,
    )
