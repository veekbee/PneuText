"""Entities: categories the author defines, the entities in them, and their mentions.

Time mentions belong here too. A time mention has no entity; it has a value (see
``pneutext.core.timeline``), and the chronology lists what each resolves to.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from pneutext.core import anchors, timeline
from pneutext.core.anchors import LineGeometry
from pneutext.core.corpus import TEXT_KINDS
from pneutext.core.errors import Conflict, InvalidInput, NotFound
from pneutext.core.timeline import Resolved, TimePoint
from pneutext.store import corpus as corpus_store
from pneutext.store import db, entities
from pneutext.store import links as links_store
from pneutext.store import notes as notes_store
from pneutext.store.corpus import LineShapeRow, VersionRow
from pneutext.store.entities import CategoryRow, EntityRow, TimeMentionRow
from pneutext.store.library import Library
from pneutext.store.notes import ReadingRange

_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_LABEL = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass(frozen=True)
class MentionMark:
    """Where a mention crosses one print line, in code points within the line."""

    mention_id: int
    category_id: int
    start: int
    end: int


@dataclass(frozen=True)
class EntityView:
    entity: EntityRow
    places: list[tuple[int, int | None]]  # (page, line) of each mention in the version


@dataclass(frozen=True)
class SpanEnds:
    start_segment_id: int
    start_offset: int
    end_segment_id: int
    end_offset: int
    exact: str


@dataclass(frozen=True)
class TimeValue:
    """A time value as the author gives it."""

    kind: str  # "absolute" or "offset"
    at: str | None = None
    offset: str | None = None
    relative_to_label: str | None = None  # an offset counts from this labeled point
    label: str | None = None
    remark: str = ""


@dataclass(frozen=True)
class NewMention:
    span: SpanEnds
    category_id: int
    entity_id: int | None = None
    entity_name: str | None = None
    value: str | None = None
    time: TimeValue | None = None


@dataclass(frozen=True)
class Since:
    label: str
    iso: str
    words: str


@dataclass(frozen=True)
class ChronologyRow:
    mention_id: int
    page: int | None
    line_no: int | None
    kind: str | None
    at: str | None
    offset: str | None
    relative_to_label: str | None
    label: str | None
    remark: str
    date_iso: str | None  # the narrative date it resolves to
    date_words: str | None
    elapsed_iso: str | None  # for a chain with no date: time since the chain began
    elapsed_words: str | None
    problem: str | None
    since: list[Since] = field(default_factory=list)  # time since each earlier labeled point


def _require_version(conn: sqlite3.Connection, version_id: int) -> VersionRow:
    version = corpus_store.get_version(conn, version_id)
    if version is None:
        raise NotFound(f"There is no text with id {version_id} in this library.")
    return version


def _require_category(conn: sqlite3.Connection, category_id: int) -> CategoryRow:
    category = entities.get_category(conn, category_id)
    if category is None:
        raise NotFound("That category no longer exists.")
    return category


# ---- Mentions on a page ---------------------------------------------------------


def page_mentions(
    conn: sqlite3.Connection, version_id: int, lines: list[LineShapeRow]
) -> list[list[MentionMark]]:
    """For each line of a page, where entity mentions cross it. Reads geometry only."""
    if not lines:
        return []
    first, last = lines[0], lines[-1]
    within = ReadingRange(
        first.position, first.start_offset, last.position, last.start_offset + last.length
    )
    spans = entities.mention_spans(conn, version_id, within)
    geometry = [
        LineGeometry(line.position, line.start_offset, line.length, line.kind in TEXT_KINDS)
        for line in lines
    ]
    return [
        [MentionMark(mark.annotation_id, mark.type_id, mark.start, mark.end) for mark in marks]
        for marks in anchors.line_highlights(geometry, spans)
    ]


# ---- Categories -------------------------------------------------------------------


def list_categories(library: Library) -> list[CategoryRow]:
    with db.transaction(library.db_path) as conn:
        return entities.list_categories(conn)


def _clean_name(name: str, what: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InvalidInput(f"Give the {what} a name.")
    return cleaned


def _check_color(color: str | None) -> None:
    if color is not None and not _COLOR.fullmatch(color):
        raise InvalidInput("A color is written as #rrggbb.")


def create_category(library: Library, name: str) -> CategoryRow:
    name = _clean_name(name, "category")
    with db.transaction(library.db_path) as conn:
        if any(c.name.lower() == name.lower() for c in entities.list_categories(conn)):
            raise Conflict(f"There is already a category called {name}.")
        return _require_category(conn, entities.insert_category(conn, name))


def update_category(
    library: Library, category_id: int, name: str | None, color: str | None
) -> CategoryRow:
    _check_color(color)
    with db.transaction(library.db_path) as conn:
        _require_category(conn, category_id)
        if name is not None:
            name = _clean_name(name, "category")
            taken = [c for c in entities.list_categories(conn) if c.name.lower() == name.lower()]
            if any(c.id != category_id for c in taken):
                raise Conflict(f"There is already a category called {name}.")
        entities.update_category(conn, category_id, name, color)
        return _require_category(conn, category_id)


def merge_category(library: Library, source_id: int, target_id: int) -> None:
    with db.transaction(library.db_path) as conn:
        source, target = _require_category(conn, source_id), _require_category(conn, target_id)
        if source.id == target.id:
            raise InvalidInput("Choose a different category to merge into.")
        if source.is_time or target.is_time:
            raise InvalidInput("The time category cannot be merged: its mentions carry dates.")
        entities.merge_category(conn, source.id, target.id)


# ---- Entities ---------------------------------------------------------------------


def list_entities(
    library: Library, version_id: int, category_id: int | None = None, starting: str | None = None
) -> list[EntityView]:
    """Entities with every place they occur in a version, for the index."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        places: dict[int, list[tuple[int, int | None]]] = {}
        for place in entities.entity_places(conn, version.id, version.pagination_id):
            if place.page is not None:
                places.setdefault(place.entity_id, []).append((place.page, place.line_no))
        return [
            EntityView(entity, places.get(entity.id, []))
            for entity in entities.list_entities(conn, category_id, starting or None)
        ]


def _require_entity(conn: sqlite3.Connection, entity_id: int) -> EntityRow:
    entity = entities.get_entity(conn, entity_id)
    if entity is None:
        raise NotFound("That entry no longer exists.")
    return entity


def update_entity(
    library: Library, entity_id: int, name: str | None, value: str | None
) -> EntityRow:
    """Rename an entity or set its normalized value. An empty value clears it."""
    with db.transaction(library.db_path) as conn:
        entity = _require_entity(conn, entity_id)
        new_name = entity.name if name is None else _clean_name(name, "entry")
        new_value = entity.value if value is None else (value.strip() or None)
        if entities.name_taken(conn, entity.category_id, new_name, entity.id):
            raise Conflict(f"There is already an entry called {new_name}. Merge the two instead.")
        entities.update_entity(conn, entity.id, new_name, new_value)
        return _require_entity(conn, entity.id)


def merge_entity(library: Library, source_id: int, target_id: int) -> None:
    with db.transaction(library.db_path) as conn:
        source, target = _require_entity(conn, source_id), _require_entity(conn, target_id)
        if source.id == target.id:
            raise InvalidInput("Choose a different entry to merge into.")
        if source.category_id != target.category_id:
            raise InvalidInput("Only entries of the same category can be merged.")
        entities.merge_entity(conn, source.id, target.id)


# ---- Mentions ---------------------------------------------------------------------


def create_mention(library: Library, version_id: int, new: NewMention) -> int:
    """Tag a selection: assign it to an entity, or record it as a time."""
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        category = _require_category(conn, new.category_id)
        span = new.span
        segments = notes_store.segments_between(
            conn, version.id, span.start_segment_id, span.end_segment_id
        )
        quote = anchors.validate_span(segments, span.start_offset, span.end_offset, span.exact)

        entity_id: int | None = None
        if not category.is_time:
            if new.entity_id is not None:
                entity = _require_entity(conn, new.entity_id)
                if entity.category_id != category.id:
                    raise InvalidInput("That entry belongs to another category.")
                entity_id = entity.id
            else:
                # By default an entity is named by the words tagged.
                name = _clean_name(new.entity_name or " ".join(quote.exact.split()), "entry")
                value = (new.value or "").strip() or None
                entity_id, _ = entities.find_or_create_entity(conn, category.id, name, value)

        anchor_id = notes_store.insert_anchor(
            conn,
            version.id,
            span.start_segment_id,
            span.start_offset,
            span.end_segment_id,
            span.end_offset,
            quote,
        )
        mention_id = entities.insert_mention(conn, anchor_id, category.id, entity_id)
        if category.is_time and new.time is not None:
            _set_time(conn, version, mention_id, new.time)
        return mention_id


def delete_mention(library: Library, mention_id: int) -> None:
    with db.transaction(library.db_path) as conn:
        if entities.get_mention(conn, mention_id) is None:
            raise NotFound("That tag no longer exists.")
        entities.delete_mention(conn, mention_id)
        links_store.delete_unowned_anchors(conn)


# ---- Narrative time ---------------------------------------------------------------


def _set_time(
    conn: sqlite3.Connection, version: VersionRow, mention_id: int, value: TimeValue
) -> None:
    others = [
        row for row in entities.time_mentions(conn, version.id) if row.mention_id != mention_id
    ]
    label = (value.label or "").strip() or None
    if label is not None:
        if not _LABEL.fullmatch(label):
            raise InvalidInput(
                "A label is lower-case letters, digits and hyphens, such as expedition-start."
            )
        if any(row.label == label for row in others):
            raise Conflict(f"Another time is already labeled {label}.")

    if value.kind == "absolute":
        if timeline.parse_date(value.at or "") is None:
            raise InvalidInput(
                "Write the date as a year, a month, a day or a time: "
                "1871, 1871-10, 1871-10-28 or 1871-10-28T06:30."
            )
        entities.set_time_point(
            conn, mention_id, "absolute", (value.at or "").strip(), None, None, label, value.remark
        )
    elif value.kind == "offset":
        if timeline.parse_duration(value.offset or "") is None:
            raise InvalidInput(
                "Write the offset as a duration: P5D for five days, P3W for three weeks, "
                "P1Y2M for a year and two months, PT6H for six hours."
            )
        relative_to: int | None = None
        wanted = (value.relative_to_label or "").strip()
        if wanted:
            found = next((row for row in others if row.label == wanted), None)
            if found is None:
                raise InvalidInput(f"No time is labeled {wanted}.")
            relative_to = found.mention_id
        entities.set_time_point(
            conn,
            mention_id,
            "offset",
            None,
            (value.offset or "").strip().upper(),
            relative_to,
            label,
            value.remark,
        )
    else:
        raise InvalidInput("A time is either a date or an offset from another time.")

    resolved = _resolve(entities.time_mentions(conn, version.id))
    problem = resolved[mention_id].problem
    if problem is not None and "circle" in problem:
        raise InvalidInput("That would make this time count from itself. Choose another.")


def _require_time_mention(conn: sqlite3.Connection, mention_id: int) -> VersionRow:
    mention = entities.get_mention(conn, mention_id)
    category = None if mention is None else entities.get_category(conn, mention.category_id)
    if mention is None or category is None or not category.is_time:
        raise NotFound("That time tag no longer exists.")
    return _require_version(conn, mention.version_id)


def set_time(library: Library, mention_id: int, value: TimeValue) -> None:
    with db.transaction(library.db_path) as conn:
        _set_time(conn, _require_time_mention(conn, mention_id), mention_id, value)


def clear_time(library: Library, mention_id: int) -> None:
    with db.transaction(library.db_path) as conn:
        _require_time_mention(conn, mention_id)
        entities.clear_time_point(conn, mention_id)


def _resolve(rows: list[TimeMentionRow]) -> dict[int, Resolved]:
    return timeline.resolve(
        [
            TimePoint(row.mention_id, row.kind, row.at, row.offset, row.relative_to_id, row.label)
            for row in rows
        ]
    )


def _chronology(conn: sqlite3.Connection, version: VersionRow) -> list[ChronologyRow]:
    rows = entities.time_mentions(conn, version.id)
    resolved = _resolve(rows)
    labels = {row.mention_id: row.label for row in rows}
    out: list[ChronologyRow] = []
    labeled: list[TimeMentionRow] = []
    for row in rows:
        found = resolved[row.mention_id]
        located = notes_store.locate(
            conn, version.pagination_id, row.start_segment_id, row.start_offset
        )
        page, line = located if located is not None else (None, None)
        since = []
        for earlier in labeled:
            elapsed = timeline.elapsed_between(resolved[earlier.mention_id], found)
            if elapsed is not None and earlier.label is not None:
                since.append(Since(earlier.label, elapsed.iso(), elapsed.words()))
        undated = found.date is None and found.elapsed is not None
        out.append(
            ChronologyRow(
                mention_id=row.mention_id,
                page=page,
                line_no=line,
                kind=row.kind,
                at=row.at,
                offset=row.offset,
                relative_to_label=labels.get(row.relative_to_id) if row.relative_to_id else None,
                label=row.label,
                remark=row.remark,
                date_iso=found.date.iso() if found.date else None,
                date_words=found.date.words() if found.date else None,
                elapsed_iso=found.elapsed.iso() if undated and found.elapsed else None,
                elapsed_words=found.elapsed.words() if undated and found.elapsed else None,
                problem=found.problem,
                since=since,
            )
        )
        if row.label is not None:
            labeled.append(row)
    return out


def chronology(library: Library, version_id: int) -> list[ChronologyRow]:
    """Every time point in reading order, with what it resolves to."""
    with db.transaction(library.db_path) as conn:
        return _chronology(conn, _require_version(conn, version_id))


@dataclass(frozen=True)
class NarrativeMoment:
    """The narrative time in force at a place in the text."""

    row: TimeMentionRow
    resolved: Resolved


class Timeline:
    """A version's time points, resolved once, for looking up the time at a place."""

    def __init__(self, conn: sqlite3.Connection, version_id: int) -> None:
        self.rows = entities.time_mentions(conn, version_id)
        self.resolved = _resolve(self.rows)

    def at(self, position: int, offset: int) -> NarrativeMoment | None:
        """The last time point with a value at or before a place in reading order."""
        found = None
        for row in self.rows:
            if (row.position, row.start_offset) > (position, offset):
                break
            if self.resolved[row.mention_id].problem is None:
                found = row
        return None if found is None else NarrativeMoment(found, self.resolved[found.mention_id])

    def labeled(self, label: str) -> Resolved | None:
        row = next((r for r in self.rows if r.label == label), None)
        return None if row is None else self.resolved[row.mention_id]


def export_data(library: Library, version_id: int) -> dict[str, object]:
    """Mentions and time points as plain data, for later map and timeline tools.

    Carries places and values, not the words of the text.
    """
    with db.transaction(library.db_path) as conn:
        version = _require_version(conn, version_id)
        categories = {c.id: c.name for c in entities.list_categories(conn)}
        index = []
        places: dict[int, list[tuple[int, int | None]]] = {}
        for place in entities.entity_places(conn, version.id, version.pagination_id):
            if place.page is not None:
                places.setdefault(place.entity_id, []).append((place.page, place.line_no))
        for entity in entities.list_entities(conn):
            if entity.id in places:
                index.append(
                    {
                        "category": categories[entity.category_id],
                        "name": entity.name,
                        "value": entity.value,
                        "mentions": [{"page": p, "line": ln} for p, ln in places[entity.id]],
                    }
                )
        times = [
            {
                "page": row.page,
                "line": row.line_no,
                "kind": row.kind,
                "at": row.at,
                "offset": row.offset,
                "relative_to": row.relative_to_label,
                "label": row.label,
                "remark": row.remark,
                "resolved": row.date_iso,
                "elapsed": row.elapsed_iso,
                "since": {item.label: item.iso for item in row.since},
            }
            for row in _chronology(conn, version)
        ]
        return {
            "work": version.work_code,
            "title": version.title,
            "version": version.label,
            "entities": index,
            "time_points": times,
        }
