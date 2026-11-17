from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import FigureOut
from pneutext.services import figures as figures_service

router = APIRouter(prefix="/api", tags=["figures"])


@router.get("/figures", operation_id="listFigures")
def list_figures(library: LibraryDep) -> list[FigureOut]:
    return [
        FigureOut(
            id=view.figure.id,
            label=view.figure.label,
            file=view.figure.file,
            caption=view.figure.caption,
            credit=view.figure.credit,
            has_file=view.has_file,
        )
        for view in figures_service.list_figures(library)
    ]


@router.get("/figures/{label}/file", operation_id="getFigureFile")
def get_figure_file(label: str, library: LibraryDep) -> FileResponse:
    """The image of a figure, from the library's figures folder."""
    return FileResponse(figures_service.figure_file(library, label))
