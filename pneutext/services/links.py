"""Cross-references: resolving them, deriving links from note bodies, and backlinks.

A reference written in a note body is syntax until it is resolved against the library:
``{{bn:45.12}}`` leads somewhere only if the work ``bn`` has a page 45 with a line 12.
Resolved references become ``inline`` links, re-derived every time the note is saved, so
backlinks never go stale. An unresolvable reference is kept in the body and marked as
broken.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pneutext import notes as note_parser
from pneutext.core import anchors, timeline
from pneutext.core.errors import InvalidInput, NotFound
from pneutext.core.references import Place, format_citation, parse_reference
from pneutext.services.entities import NarrativeMoment, Timeline
from pneutext.services.extents import WHOLE_UNIT, Extent, line_extent, page_extent
from pneutext.store import corpus as corpus_store
from pneutext.store import db, figures
from pneutext.store import links as links_store
from pneutext.store import notes as notes_store
from pneutext.store.corpus import VersionRow
from pneutext.store.library import Library
from pneutext.store.notes import ReadingRange


@dataclass(frozen=True)
class ResolvedReference:
    version_id: int
    extent: Extent
    start: Place
    end: Place


@dataclass(frozen=True)
class Backlink:
    """A note that refers to a page, a passage or another note."""

    note_id: int
    type_id: int
    level: int
    status: str
    page: int | None  # where the referring note sits
    line_no: int | None
    target: str | None  # for a reference to a passage: how it reads, such as "p. 45.12"


@dataclass(frozen=True)
class PassageEnd:
    page: int | None
    line_no: int | None
    end_page: int | None
    end_line_no: int | None
    here: bool  # whether this end lies on the page being shown


@dataclass(frozen=True)
class PassageLink:
    id: int
    relation: str
    source: PassageEnd
    target: PassageEnd


@dataclass(frozen=True)
class SpanEnds:
    """A passage as the client sends it, with the words it believes it covers."""

    start_segment_id: int
    start_offset: int
    end_segment_id: int
    end_offset: int
    exact: str


# ---- Resolving ----------------------------------------------------------------


def _target_version(conn: sqlite3.Connection, home: VersionRow, work: str) -> VersionRow | None:
    """The text a reference points into: the note's own, when the work code is its own."""
    if work == home.work_code:
        return home
    return corpus_store.newest_version_of_work(conn, work)


def resolve_reference(
    conn: sqlite3.Connection, home: VersionRow, work: str, target: str
) -> ResolvedReference | None:
    """Find the stretch of text a page reference names, or None if it names nothing."""
    reference = parse_reference(target)
    version = _target_version(conn, home, work)
    if reference is None or version is None:
        return None

    def extent_of(place: Place) -> Extent | None:
        if place.line is None:
            return page_extent(conn, version, place.page)
        return line_extent(conn, version, place.page, place.line)

    first, last = extent_of(reference.start), extent_of(reference.end)
    if first is None or last is None:
        return None
    return ResolvedReference(
        version.id, (first[0], first[1], last[2], last[3]), reference.start, reference.end
    )


def _locate(
    conn: sqlite3.Connection, version: VersionRow, segment_id: int, offset: int
) -> tuple[int | None, int | None]:
    found = notes_store.locate(conn, version.pagination_id, segment_id, offset)
    return (None, None) if found is None else found


def resolve_tree(
    conn: sqlite3.Connection,
    home: VersionRow,
    tree: note_parser.Node,
    at: tuple[int, int] | None = None,
) -> note_parser.Node:
    """A copy of a parsed body with every reference resolved, or marked as broken.

    ``at`` is the note's place in the text (segment position, offset). The dynamic forms
    ``{{when}}`` and ``{{since:label}}`` are worked out for that place, so they follow
    every change to a time value.
    """
    times: Timeline | None = None

    def moment() -> NarrativeMoment | None:
        nonlocal times
        if at is None:
            return None
        if times is None:
            times = Timeline(conn, home.id)
        return times.at(*at)

    def resolve(node: note_parser.Node) -> note_parser.Node:
        node = dict(node)
        kind = node["type"]
        attrs = dict(node.get("attrs") or {})
        if kind == "reference":
            found = resolve_reference(conn, home, str(attrs["work"]), str(attrs["target"]))
            reference = parse_reference(str(attrs["target"]))
            attrs["label"] = format_citation(reference) if reference else str(attrs["target"])
            attrs["broken"] = found is None
            if found is not None:
                attrs.update(
                    version_id=found.version_id,
                    page=found.start.page,
                    line=found.start.line,
                    end_page=found.end.page,
                    end_line=found.end.line,
                )
        elif kind == "note_ref":
            target = notes_store.get_note(conn, int(attrs["id"]))
            attrs["broken"] = target is None
            if target is not None:
                version = corpus_store.get_version(conn, target.anchor.version_id)
                assert version is not None
                page, line = _locate(
                    conn, version, target.anchor.start_segment_id, target.anchor.start_offset
                )
                attrs.update(version_id=version.id, page=page, line=line, type_id=target.type_id)
                attrs["level"] = target.level
        elif kind in ("figure", "figure_ref"):
            figure = figures.get_figure(conn, str(attrs["label"]))
            attrs["broken"] = figure is None
            if figure is not None:
                attrs["file"] = figure.file
                if kind == "figure_ref" or not attrs.get("caption"):
                    attrs["caption"] = figure.caption
                attrs["credit"] = figure.credit
        elif kind == "when":
            now = moment()
            attrs["broken"] = now is None
            if now is not None and now.resolved.date is not None:
                attrs["value"] = now.resolved.date.words()
            elif now is not None and now.resolved.elapsed is not None:
                attrs["value"] = now.resolved.elapsed.words() + " in"
        elif kind == "since":
            now = moment()
            origin = times.labeled(str(attrs["label"])) if times is not None else None
            elapsed = (
                timeline.elapsed_between(origin, now.resolved)
                if now is not None and origin is not None
                else None
            )
            attrs["broken"] = elapsed is None
            if elapsed is not None:
                attrs["value"] = elapsed.words()
        if attrs:
            node["attrs"] = attrs
        if "children" in node:
            node["children"] = [resolve(child) for child in node["children"]]
        return node

    return resolve(tree)


def _walk(node: note_parser.Node) -> list[note_parser.Node]:
    found = [node]
    for child in node.get("children", []):
        found.extend(_walk(child))
    return found


# ---- Deriving links from a note body --------------------------------------------


def refresh_inline_links(
    conn: sqlite3.Connection, home: VersionRow, note_id: int, body_md: str
) -> None:
    """Replace a note's inline links with those its body now makes."""
    links_store.delete_inline_links(conn, note_id)
    seen: set[tuple[str, object]] = set()
    for node in _walk(note_parser.parse(body_md)):
        attrs = node.get("attrs") or {}
        if node["type"] == "reference":
            found = resolve_reference(conn, home, str(attrs["work"]), str(attrs["target"]))
            if found is None or ("anchor", (found.version_id, found.extent)) in seen:
                continue
            seen.add(("anchor", (found.version_id, found.extent)))
            anchor_id = notes_store.insert_anchor(conn, found.version_id, *found.extent, WHOLE_UNIT)
            links_store.insert_link(
                conn, origin="inline", source_annotation_id=note_id, target_anchor_id=anchor_id
            )
        elif node["type"] == "note_ref":
            target_id = int(attrs["id"])
            if ("note", target_id) in seen or notes_store.get_note(conn, target_id) is None:
                continue
            seen.add(("note", target_id))
            links_store.insert_link(
                conn, origin="inline", source_annotation_id=note_id, target_annotation_id=target_id
            )


# ---- Backlinks ------------------------------------------------------------------


def backlinks_to_note(
    conn: sqlite3.Connection, version: VersionRow, note_id: int
) -> list[Backlink]:
    out = []
    for row in links_store.backlinks_to_note(conn, note_id):
        page, line = _locate(conn, version, row.start_segment_id, row.start_offset)
        out.append(Backlink(row.note_id, row.type_id, row.level, row.status, page, line, None))
    return out


def _page_range(conn: sqlite3.Connection, version: VersionRow, page: int) -> ReadingRange:
    lines = corpus_store.page_line_shapes(conn, version.pagination_id, page)
    if not lines:
        raise NotFound(f"This text has no page {page}.")
    first, last = lines[0], lines[-1]
    return ReadingRange(
        first.position, first.start_offset, last.position, last.start_offset + last.length
    )


def _passage_label(
    conn: sqlite3.Connection, version: VersionRow, extent: tuple[int, int, int, int]
) -> tuple[int | None, int | None, int | None, int | None]:
    page, line = _locate(conn, version, extent[0], extent[1])
    end_page, end_line = _locate(conn, version, extent[2], max(extent[3] - 1, 0))
    return page, line, end_page, end_line


def _citation(
    place: tuple[int | None, int | None, int | None, int | None], whole_pages: bool
) -> str:
    page, line, end_page, end_line = place
    if page is None:
        return ""
    if whole_pages:
        return f"p. {page}" if end_page in (None, page) else f"p. {page}-{end_page}"
    start = f"{page}.{line}" if line is not None else str(page)
    end = f"{end_page}.{end_line}" if end_line is not None else str(end_page)
    return f"p. {start}" if start == end else f"p. {start}-{end}"


def page_backlinks(library: Library, version_id: int, page: int) -> list[Backlink]:
    """The notes that refer to a page or to a passage on it, with what each cites."""
    with db.transaction(library.db_path) as conn:
        version = corpus_store.get_version(conn, version_id)
        if version is None:
            raise NotFound(f"There is no text with id {version_id} in this library.")
        out = []
        for row in links_store.backlinks_to_range(
            conn, version.id, _page_range(conn, version, page)
        ):
            source_page, source_line = _locate(
                conn, version, row.start_segment_id, row.start_offset
            )
            assert row.target_start_segment_id is not None and row.target_start_offset is not None
            assert row.target_end_segment_id is not None and row.target_end_offset is not None
            extent = (
                row.target_start_segment_id,
                row.target_start_offset,
                row.target_end_segment_id,
                row.target_end_offset,
            )
            place = _passage_label(conn, version, extent)
            # A reference to whole pages starts at a page's first line and ends at a last.
            whole = _covers_whole_pages(conn, version, extent, place)
            out.append(
                Backlink(
                    row.note_id,
                    row.type_id,
                    row.level,
                    row.status,
                    source_page,
                    source_line,
                    _citation(place, whole),
                )
            )
        return out


def _covers_whole_pages(
    conn: sqlite3.Connection,
    version: VersionRow,
    extent: tuple[int, int, int, int],
    place: tuple[int | None, int | None, int | None, int | None],
) -> bool:
    page, _, end_page, _ = place
    if page is None or end_page is None:
        return False
    first, last = page_extent(conn, version, page), page_extent(conn, version, end_page)
    return (
        first is not None
        and last is not None
        and (first[0], first[1]) == (extent[0], extent[1])
        and (last[2], last[3]) == (extent[2], extent[3])
    )


# ---- Links made passage to passage ----------------------------------------------


def _passage_anchor(conn: sqlite3.Connection, version_id: int, span: SpanEnds) -> int:
    segments = notes_store.segments_between(
        conn, version_id, span.start_segment_id, span.end_segment_id
    )
    quote = anchors.validate_span(segments, span.start_offset, span.end_offset, span.exact)
    return notes_store.insert_anchor(
        conn,
        version_id,
        span.start_segment_id,
        span.start_offset,
        span.end_segment_id,
        span.end_offset,
        quote,
    )


def create_passage_link(
    library: Library, version_id: int, source: SpanEnds, target: SpanEnds
) -> int:
    with db.transaction(library.db_path) as conn:
        if corpus_store.get_version(conn, version_id) is None:
            raise NotFound(f"There is no text with id {version_id} in this library.")
        if (
            source.start_segment_id,
            source.start_offset,
            source.end_segment_id,
            source.end_offset,
        ) == (
            target.start_segment_id,
            target.start_offset,
            target.end_segment_id,
            target.end_offset,
        ):
            raise InvalidInput("A passage cannot be linked to itself. Select a different passage.")
        return links_store.insert_link(
            conn,
            origin="manual",
            relation="related",
            source_anchor_id=_passage_anchor(conn, version_id, source),
            target_anchor_id=_passage_anchor(conn, version_id, target),
        )


def delete_passage_link(library: Library, link_id: int) -> None:
    with db.transaction(library.db_path) as conn:
        if not links_store.delete_manual_link(conn, link_id):
            raise NotFound("That link no longer exists.")


def page_passage_links(library: Library, version_id: int, page: int) -> list[PassageLink]:
    with db.transaction(library.db_path) as conn:
        version = corpus_store.get_version(conn, version_id)
        if version is None:
            raise NotFound(f"There is no text with id {version_id} in this library.")
        out = []
        within = _page_range(conn, version, page)
        for row in links_store.passage_links_in_range(conn, version.id, within):
            source = _passage_label(conn, version, row.source)
            target = _passage_label(conn, version, row.target)
            out.append(
                PassageLink(
                    row.id,
                    row.relation,
                    PassageEnd(*source, here=row.source_here),
                    PassageEnd(*target, here=row.target_here),
                )
            )
        return out
