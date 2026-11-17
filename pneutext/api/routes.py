"""API routers. Routers call services and never touch SQL."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

import pneutext
from pneutext.api.schemas import LibraryOut
from pneutext.services import library as library_service
from pneutext.store.library import Library

router = APIRouter(prefix="/api")


def get_library(request: Request) -> Library:
    return request.app.state.library


LibraryDep = Annotated[Library, Depends(get_library)]


@router.get("/library", operation_id="getLibrary")
def get_library_info(library: LibraryDep) -> LibraryOut:
    info = library_service.describe(library)
    return LibraryOut(
        app_version=pneutext.__version__,
        schema_version=info.schema_version,
        created_at=info.created_at,
    )
