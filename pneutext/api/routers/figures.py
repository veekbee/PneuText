from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import FigureIn, FigureOut, FigureUpdateIn, FigureUseOut
from pneutext.services import figures as figures_service
from pneutext.services.figures import FigureView

router = APIRouter(prefix="/api", tags=["figures"])


def _figure(view: FigureView) -> FigureOut:
    return FigureOut(
        id=view.figure.id,
        label=view.figure.label,
        file=view.figure.file,
        caption=view.figure.caption,
        credit=view.figure.credit,
        has_file=view.has_file,
        uses=[FigureUseOut(**asdict(use)) for use in view.uses],
    )


@router.get("/figures", operation_id="listFigures")
def list_figures(library: LibraryDep) -> list[FigureOut]:
    """Every figure, with where each is used."""
    return [_figure(view) for view in figures_service.list_figures(library)]


@router.post("/figures", operation_id="createFigure", status_code=201)
def create_figure(body: FigureIn, library: LibraryDep) -> FigureOut:
    return _figure(figures_service.create_figure(library, body.label, body.caption, body.credit))


@router.patch("/figures/{figure_id}", operation_id="updateFigure")
def update_figure(figure_id: int, body: FigureUpdateIn, library: LibraryDep) -> FigureOut:
    """Edit a figure's label, caption or credit. A new label is followed in the notes."""
    return _figure(
        figures_service.update_figure(library, figure_id, body.label, body.caption, body.credit)
    )


@router.delete("/figures/{figure_id}", operation_id="deleteFigure", status_code=204)
def delete_figure(figure_id: int, library: LibraryDep) -> Response:
    figures_service.delete_figure(library, figure_id)
    return Response(status_code=204)


@router.put("/figures/{figure_id}/image", operation_id="uploadFigureImage")
async def upload_figure_image(figure_id: int, request: Request, library: LibraryDep) -> FigureOut:
    """Store the request body as the figure's image. The content type names its format."""
    data = await request.body()
    content_type = request.headers.get("content-type", "")
    return _figure(figures_service.save_image(library, figure_id, content_type, data))


@router.get("/figures/{label}/file", operation_id="getFigureFile")
def get_figure_file(label: str, library: LibraryDep) -> FileResponse:
    """The image of a figure, from the library's figures folder."""
    return FileResponse(figures_service.figure_file(library, label))
