from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import CorpusHitOut, NoteHitOut, ReferenceHitOut, SearchOut
from pneutext.services import search as search_service

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/versions/{version_id}/search", operation_id="search")
def search(version_id: int, q: str, library: LibraryDep, corpus: bool = False) -> SearchOut:
    """Search a text. The corpus is searched only when `corpus` is true: never in blank mode."""
    found = search_service.search(library, version_id, q, include_corpus=corpus)
    return SearchOut(
        query=found.query,
        reference=None if found.reference is None else ReferenceHitOut(**asdict(found.reference)),
        corpus=None if found.corpus is None else [CorpusHitOut(**asdict(h)) for h in found.corpus],
        notes=[NoteHitOut(**asdict(hit)) for hit in found.notes],
    )
