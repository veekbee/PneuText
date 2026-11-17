from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Response

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import (
    AnchorOut,
    BacklinkOut,
    NoteCreateIn,
    NoteNode,
    NoteOut,
    NoteTypeOut,
    NoteUpdateIn,
    PlaceOut,
    RenderIn,
    RenderOut,
    SpanIn,
)
from pneutext.services import notes as notes_service
from pneutext.services.notes import NewNote, NoteChanges, NoteView, Place, SpanInput

router = APIRouter(prefix="/api", tags=["notes"])


def _span(span: SpanIn | None) -> SpanInput | None:
    return None if span is None else SpanInput(**span.model_dump())


def _place(place: Place | None) -> PlaceOut | None:
    return None if place is None else PlaceOut(page=place.page, line_no=place.line_no)


def _note(view: NoteView) -> NoteOut:
    note, anchor = view.note, view.note.anchor
    return NoteOut(
        id=note.id,
        version_id=anchor.version_id,
        type_id=note.type_id,
        scope=note.scope,
        level=note.level,
        status=note.status,
        body_md=note.body_md,
        body=NoteNode.model_validate(view.body),
        tags=note.tags,
        legacy_id=note.legacy_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
        anchor=AnchorOut(
            start_segment_id=anchor.start_segment_id,
            start_offset=anchor.start_offset,
            end_segment_id=anchor.end_segment_id,
            end_offset=anchor.end_offset,
            status=anchor.status,
        ),
        start=_place(view.start),
        end=_place(view.end),
        backlinks=[BacklinkOut(**asdict(backlink)) for backlink in view.backlinks],
    )


@router.get("/note-types", operation_id="listNoteTypes")
def list_note_types(library: LibraryDep) -> list[NoteTypeOut]:
    return [
        NoteTypeOut(id=t.id, name=t.name, code=t.code, color=t.color, sort=t.sort, role=t.role)
        for t in notes_service.list_note_types(library)
    ]


@router.get("/versions/{version_id}/pages/{page}/notes", operation_id="listPageNotes")
def list_page_notes(version_id: int, page: int, library: LibraryDep) -> list[NoteOut]:
    """The notes beside a page, in reading order. Carries no corpus text."""
    return [_note(view) for view in notes_service.list_page_notes(library, version_id, page)]


@router.post("/versions/{version_id}/notes", operation_id="createNote", status_code=201)
def create_note(version_id: int, body: NoteCreateIn, library: LibraryDep) -> NoteOut:
    new = NewNote(
        type_id=body.type_id,
        scope=body.scope,
        level=body.level,
        status=body.status,
        body_md=body.body_md,
        tags=body.tags,
        span=_span(body.span),
        page=body.page,
        division_id=body.division_id,
    )
    return _note(notes_service.create_note(library, version_id, new))


@router.post("/notes/render", operation_id="renderNoteBody")
def render_note_body(body: RenderIn, library: LibraryDep) -> RenderOut:
    """Parse a note body into its syntax tree, for the editor's live preview."""
    tree = notes_service.render_body(library, body.body_md, body.version_id)
    return RenderOut(body=NoteNode.model_validate(tree))


@router.get("/notes/{note_id}", operation_id="getNote")
def get_note(note_id: int, library: LibraryDep) -> NoteOut:
    return _note(notes_service.get_note(library, note_id))


@router.patch("/notes/{note_id}", operation_id="updateNote")
def update_note(note_id: int, body: NoteUpdateIn, library: LibraryDep) -> NoteOut:
    changes = NoteChanges(
        type_id=body.type_id,
        level=body.level,
        status=body.status,
        body_md=body.body_md,
        tags=body.tags,
        span=_span(body.span),
    )
    return _note(notes_service.update_note(library, note_id, changes))


@router.delete("/notes/{note_id}", operation_id="deleteNote", status_code=204)
def delete_note(note_id: int, library: LibraryDep) -> Response:
    notes_service.delete_note(library, note_id)
    return Response(status_code=204)
