from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Response

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import (
    BacklinkOut,
    PageLinksOut,
    PassageEndOut,
    PassageLinkIn,
    PassageLinkOut,
    SpanIn,
)
from pneutext.services import links as links_service
from pneutext.services.links import PassageLink, SpanEnds

router = APIRouter(prefix="/api", tags=["links"])


def _passage(link: PassageLink) -> PassageLinkOut:
    return PassageLinkOut(
        id=link.id,
        relation=link.relation,
        source=PassageEndOut(**asdict(link.source)),
        target=PassageEndOut(**asdict(link.target)),
    )


def _ends(span: SpanIn) -> SpanEnds:
    return SpanEnds(**span.model_dump())


@router.get("/versions/{version_id}/pages/{page}/links", operation_id="listPageLinks")
def list_page_links(version_id: int, page: int, library: LibraryDep) -> PageLinksOut:
    """What points at a page: notes that refer to it, and passage links that touch it."""
    return PageLinksOut(
        backlinks=[
            BacklinkOut(**asdict(backlink))
            for backlink in links_service.page_backlinks(library, version_id, page)
        ],
        passages=[
            _passage(link) for link in links_service.page_passage_links(library, version_id, page)
        ],
    )


@router.post("/versions/{version_id}/links", operation_id="createPassageLink", status_code=201)
def create_passage_link(
    version_id: int, body: PassageLinkIn, library: LibraryDep
) -> dict[str, int]:
    """Link one passage to another. Both passages are checked against the text."""
    link_id = links_service.create_passage_link(
        library, version_id, _ends(body.source), _ends(body.target)
    )
    return {"id": link_id}


@router.delete("/links/{link_id}", operation_id="deletePassageLink", status_code=204)
def delete_passage_link(link_id: int, library: LibraryDep) -> Response:
    links_service.delete_passage_link(library, link_id)
    return Response(status_code=204)
