from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import (
    BrokenReferenceOut,
    BulkStatusIn,
    NoteSummaryOut,
    TodoListOut,
    TodoRemarkOut,
    UnusedFigureOut,
    UnvaluedTimeOut,
)
from pneutext.services import review as review_service
from pneutext.services.review import NoteFilter, NoteSummary

router = APIRouter(prefix="/api", tags=["review"])


def _summary(note: NoteSummary) -> NoteSummaryOut:
    return NoteSummaryOut(**asdict(note))


@router.get("/versions/{version_id}/notes", operation_id="listNotes")
def list_notes(
    version_id: int,
    library: LibraryDep,
    division_id: int | None = None,
    type_id: int | None = None,
    level: int | None = None,
    status: Literal["draft", "ready"] | None = None,
    tag: str | None = None,
) -> list[NoteSummaryOut]:
    """Notes filtered by chapter, type, level, status and tag, in reading order."""
    wanted = NoteFilter(division_id, type_id, level, status, tag)
    return [_summary(note) for note in review_service.list_notes(library, version_id, wanted)]


@router.post("/versions/{version_id}/notes/status", operation_id="setNotesStatus")
def set_notes_status(version_id: int, body: BulkStatusIn, library: LibraryDep) -> dict[str, int]:
    """Mark several notes draft or ready at once."""
    changed = review_service.set_status(library, version_id, body.note_ids, body.status)
    return {"changed": changed}


@router.get("/tags", operation_id="listTags")
def list_tags(library: LibraryDep) -> list[str]:
    return review_service.list_tags(library)


@router.get("/versions/{version_id}/todo", operation_id="getTodoList")
def get_todo_list(version_id: int, library: LibraryDep) -> TodoListOut:
    """Every TODO remark, draft note, broken reference, orphaned anchor, unused figure and
    time without a value."""
    found = review_service.todo_list(library, version_id)
    return TodoListOut(
        remarks=[TodoRemarkOut(note=_summary(r.note), text=r.text) for r in found.remarks],
        drafts=[_summary(note) for note in found.drafts],
        broken_references=[
            BrokenReferenceOut(note=_summary(b.note), form=b.form) for b in found.broken_references
        ],
        orphaned=[_summary(note) for note in found.orphaned],
        unused_figures=[UnusedFigureOut(**asdict(f)) for f in found.unused_figures],
        times_without_value=[UnvaluedTimeOut(**asdict(t)) for t in found.times_without_value],
    )
