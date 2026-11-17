from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from pneutext.api.deps import LibraryDep
from pneutext.api.schemas import (
    CategoryIn,
    CategoryOut,
    CategoryUpdateIn,
    ChronologyRowOut,
    EntityOut,
    EntityPlaceOut,
    EntityUpdateIn,
    MentionIn,
    MergeIn,
    SinceOut,
    TimeValueIn,
)
from pneutext.services import entities as entities_service
from pneutext.services.entities import EntityView, NewMention, SpanEnds, TimeValue
from pneutext.store.entities import CategoryRow

router = APIRouter(prefix="/api", tags=["entities"])


def _category(row: CategoryRow) -> CategoryOut:
    return CategoryOut(**asdict(row))


def _entity(view: EntityView) -> EntityOut:
    return EntityOut(
        id=view.entity.id,
        category_id=view.entity.category_id,
        name=view.entity.name,
        value=view.entity.value,
        places=[EntityPlaceOut(page=page, line_no=line) for page, line in view.places],
    )


def _time(value: TimeValueIn) -> TimeValue:
    return TimeValue(**value.model_dump())


@router.get("/entity-categories", operation_id="listCategories")
def list_categories(library: LibraryDep) -> list[CategoryOut]:
    return [_category(row) for row in entities_service.list_categories(library)]


@router.post("/entity-categories", operation_id="createCategory", status_code=201)
def create_category(body: CategoryIn, library: LibraryDep) -> CategoryOut:
    return _category(entities_service.create_category(library, body.name))


@router.patch("/entity-categories/{category_id}", operation_id="updateCategory")
def update_category(category_id: int, body: CategoryUpdateIn, library: LibraryDep) -> CategoryOut:
    """Rename or recolor a category."""
    return _category(entities_service.update_category(library, category_id, body.name, body.color))


@router.post(
    "/entity-categories/{category_id}/merge", operation_id="mergeCategory", status_code=204
)
def merge_category(category_id: int, body: MergeIn, library: LibraryDep) -> Response:
    """Fold this category into another, with everything in it."""
    entities_service.merge_category(library, category_id, body.into_id)
    return Response(status_code=204)


@router.get("/versions/{version_id}/entities", operation_id="listEntities")
def list_entities(
    version_id: int,
    library: LibraryDep,
    category_id: int | None = None,
    starting: str | None = None,
) -> list[EntityOut]:
    """The index: each entity with every place it occurs. `starting` is for type-ahead."""
    found = entities_service.list_entities(library, version_id, category_id, starting)
    return [_entity(view) for view in found]


@router.patch("/entities/{entity_id}", operation_id="updateEntity", status_code=204)
def update_entity(entity_id: int, body: EntityUpdateIn, library: LibraryDep) -> Response:
    """Rename an entry or set its normalized value."""
    entities_service.update_entity(library, entity_id, body.name, body.value)
    return Response(status_code=204)


@router.post("/entities/{entity_id}/merge", operation_id="mergeEntity", status_code=204)
def merge_entity(entity_id: int, body: MergeIn, library: LibraryDep) -> Response:
    """Give this entry's mentions to another entry and remove it."""
    entities_service.merge_entity(library, entity_id, body.into_id)
    return Response(status_code=204)


@router.post("/versions/{version_id}/mentions", operation_id="createMention", status_code=201)
def create_mention(version_id: int, body: MentionIn, library: LibraryDep) -> dict[str, int]:
    """Tag a selection as an entity, or as a time."""
    mention_id = entities_service.create_mention(
        library,
        version_id,
        NewMention(
            span=SpanEnds(**body.span.model_dump()),
            category_id=body.category_id,
            entity_id=body.entity_id,
            entity_name=body.entity_name,
            value=body.value,
            time=None if body.time is None else _time(body.time),
        ),
    )
    return {"id": mention_id}


@router.delete("/mentions/{mention_id}", operation_id="deleteMention", status_code=204)
def delete_mention(mention_id: int, library: LibraryDep) -> Response:
    entities_service.delete_mention(library, mention_id)
    return Response(status_code=204)


@router.put("/mentions/{mention_id}/time", operation_id="setTime", status_code=204)
def set_time(mention_id: int, body: TimeValueIn, library: LibraryDep) -> Response:
    """Give a time mention its value: a date, or an offset from another time."""
    entities_service.set_time(library, mention_id, _time(body))
    return Response(status_code=204)


@router.delete("/mentions/{mention_id}/time", operation_id="clearTime", status_code=204)
def clear_time(mention_id: int, library: LibraryDep) -> Response:
    entities_service.clear_time(library, mention_id)
    return Response(status_code=204)


@router.get("/versions/{version_id}/chronology", operation_id="getChronology")
def get_chronology(version_id: int, library: LibraryDep) -> list[ChronologyRowOut]:
    """Every time point in reading order, with its resolved date and elapsed times."""
    return [
        ChronologyRowOut(
            **{key: value for key, value in asdict(row).items() if key != "since"},
            since=[SinceOut(**asdict(item)) for item in row.since],
        )
        for row in entities_service.chronology(library, version_id)
    ]


@router.get("/versions/{version_id}/entities/export", operation_id="exportEntities")
def export_entities(version_id: int, library: LibraryDep) -> JSONResponse:
    """Mentions and time points as data, for later map and timeline tools."""
    data = entities_service.export_data(library, version_id)
    return JSONResponse(
        data, headers={"content-disposition": 'attachment; filename="entities.json"'}
    )
