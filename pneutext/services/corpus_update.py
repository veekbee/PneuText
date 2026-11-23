"""Updating a stored text from its page files after they were corrected.

The folder is read again and compared with the version paragraph by paragraph. Words
may change, line and page breaks may move within a paragraph, and pages may be added at
the end. Every span stored over a changed paragraph follows its words; a span whose
words are gone is kept and marked orphaned. Nothing here logs or reports the text.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from pneutext.core import anchors
from pneutext.core.anchors import AnchorQuote, SegmentText
from pneutext.core.corpus import POSITION_STEP, ImportProblem, ParsedCorpus, ParsedLine
from pneutext.core.errors import Conflict, InvalidInput, NotFound
from pneutext.core.realign import OffsetMap
from pneutext.importers import paged_corpus
from pneutext.importers.paged_corpus import CorpusFormat
from pneutext.store import corpus as corpus_store
from pneutext.store import db
from pneutext.store import notes as notes_store
from pneutext.store.corpus import StoredSegment, VersionRow
from pneutext.store.library import Library

_STRUCTURE = (
    "The files no longer match the stored text paragraph for paragraph; the first "
    "difference is on page {page}. An update can correct words, move line and page breaks "
    "within a paragraph, and add pages at the end. To add, remove, split or join "
    "paragraphs, import the folder as a new text instead."
)
_SHORTER = (
    "The folder holds less text than is stored: it ends before page {page} does. An update "
    "cannot remove pages. Check that the folder has every page file."
)


_LEAST_KEPT = 0.5
"""The share of a paragraph that must survive for a change to count as a correction."""


@dataclass(frozen=True)
class CorpusUpdateRequest:
    folder: str
    file_pattern: str | None = None


@dataclass(frozen=True)
class CorpusUpdateReport:
    """What an update changes. Pages and counts only, never the text."""

    up_to_date: bool
    changed_pages: list[int]
    new_pages: list[int]
    changed_paragraphs: int
    new_paragraphs: int
    moved_passages: int  # marked passages that shifted but read the same
    reworded_passages: int  # marked passages whose own words changed
    reworded_pages: list[int]
    lost_passages: int  # marked passages whose words are gone
    lost_pages: list[int]
    problems: list[ImportProblem]


@dataclass(frozen=True)
class _AnchorMove:
    anchor_id: int
    start_offset: int
    end_offset: int
    quote: AnchorQuote | None  # None: the words are gone


@dataclass
class _Plan:
    corpus: ParsedCorpus
    content_hash: str
    stored: list[StoredSegment]
    rewrites: list[tuple[int, bool]] = field(default_factory=list)  # (index, text changed)
    relabels: list[tuple[int, str]] = field(default_factory=list)  # (division id, label)
    new_divisions: list[int] = field(default_factory=list)  # indexes into corpus.divisions
    moves: list[_AnchorMove] = field(default_factory=list)
    changed_pages: set[int] = field(default_factory=set)
    new_pages: set[int] = field(default_factory=set)
    moved: int = 0
    reworded_pages: list[int] = field(default_factory=list)
    lost_pages: list[int] = field(default_factory=list)

    @property
    def up_to_date(self) -> bool:
        appended = len(self.corpus.segments) > len(self.stored)
        return not (self.rewrites or self.relabels or self.new_divisions or appended)

    def report(self) -> CorpusUpdateReport:
        return CorpusUpdateReport(
            up_to_date=self.up_to_date,
            changed_pages=sorted(self.changed_pages - self.new_pages),
            new_pages=sorted(self.new_pages),
            changed_paragraphs=sum(1 for _, text_changed in self.rewrites if text_changed),
            new_paragraphs=sum(
                1 for s in self.corpus.segments[len(self.stored) :] if s.kind == "paragraph"
            ),
            moved_passages=self.moved,
            reworded_passages=len(self.reworded_pages),
            reworded_pages=sorted(set(self.reworded_pages)),
            lost_passages=len(self.lost_pages),
            lost_pages=sorted(set(self.lost_pages)),
            problems=self.corpus.problems,
        )


def _printed(text: str, lines: list[ParsedLine]) -> set[tuple[int, int | None, int, str]]:
    """A segment as print lines: page, line number, place among its lines, words."""
    found = set()
    for index, line in enumerate(lines):
        end = lines[index + 1].start_offset - 1 if index + 1 < len(lines) else len(text)
        found.add((line.page, line.line_no, index, text[line.start_offset : end]))
    return found


def _page_at(lines: list[ParsedLine], offset: int) -> int:
    page = lines[0].page
    for line in lines:
        if line.start_offset <= offset:
            page = line.page
    return page


def _first_page(lines: list[ParsedLine], fallback: int) -> int:
    return lines[0].page if lines else fallback


def _first_difference(plan: _Plan) -> int:
    """The page where the files and the stored text stop lining up."""
    stored, parsed = plan.stored, plan.corpus.segments
    last_page = max((line.page for s in stored for line in s.lines), default=0)
    for old, new in zip(stored, parsed, strict=False):
        there = (new.kind, [(line.page, line.line_no) for line in new.lines[:1]])
        here = (old.kind, [(line.page, line.line_no) for line in old.lines[:1]])
        if here != there:
            return _first_page(old.lines, last_page)
    return last_page


def _compare_structure(plan: _Plan) -> None:
    stored, parsed = plan.stored, plan.corpus.segments
    last_page = max((line.page for s in stored for line in s.lines), default=0)
    if len(parsed) < len(stored):
        missing = stored[len(parsed)]
        raise Conflict(_SHORTER.format(page=_first_page(missing.lines, last_page)))
    lined_up = all(
        new.kind == old.kind and new.lines for old, new in zip(stored, parsed, strict=False)
    )
    # Whatever follows the stored text must lie on pages it did not have.
    added_later = all(
        segment.lines and segment.lines[0].page > last_page for segment in parsed[len(stored) :]
    )
    if not (lined_up and added_later):
        raise Conflict(_STRUCTURE.format(page=_first_difference(plan)))


def _compare_divisions(plan: _Plan, conn: sqlite3.Connection, version: VersionRow) -> None:
    stored_divisions = corpus_store.stored_divisions(conn, version.id)
    index_of = {segment.id: index for index, segment in enumerate(plan.stored)}
    parsed = plan.corpus.divisions
    for place, old in enumerate(stored_divisions):
        at = index_of[old.first_segment_id]
        new = parsed[place] if place < len(parsed) else None
        if new is None or new.kind != old.kind or new.first_segment != at:
            page = _first_page(plan.stored[at].lines, 0)
            raise Conflict(_STRUCTURE.format(page=page))
        if new.label != old.label:
            plan.relabels.append((old.id, new.label))
    for place in range(len(stored_divisions), len(parsed)):
        if parsed[place].first_segment < len(plan.stored):
            page = _first_page(plan.corpus.segments[parsed[place].first_segment].lines, 0)
            raise Conflict(_STRUCTURE.format(page=page))
        plan.new_divisions.append(place)


def _compare_text(plan: _Plan) -> dict[int, OffsetMap]:
    """Find the paragraphs that differ; return an offset map for each whose words do."""
    maps: dict[int, OffsetMap] = {}
    old_pages = {line.page for segment in plan.stored for line in segment.lines}
    for index, old in enumerate(plan.stored):
        new = plan.corpus.segments[index]
        text_changed = new.text != old.text
        if not text_changed and new.lines == old.lines:
            continue
        plan.rewrites.append((index, text_changed))
        before, after = _printed(old.text, old.lines), _printed(new.text, new.lines)
        plan.changed_pages |= {entry[0] for entry in before ^ after}
        if text_changed:
            maps[index] = OffsetMap(old.text, new.text)
            if maps[index].kept < _LEAST_KEPT * min(len(old.text), len(new.text)):
                # Not a correction: paragraphs have slipped against each other.
                raise Conflict(_STRUCTURE.format(page=_first_page(old.lines, 0)))
    for segment in plan.corpus.segments:
        plan.new_pages |= {line.page for line in segment.lines} - old_pages
    return maps


def _carry_anchors(plan: _Plan, conn: sqlite3.Connection, version: VersionRow) -> None:
    maps = _compare_text(plan)
    if not maps:
        return
    index_of = {segment.id: index for index, segment in enumerate(plan.stored)}
    parsed = plan.corpus.segments
    for anchor in notes_store.version_anchors(conn, version.id):
        first, last = index_of[anchor.start_segment_id], index_of[anchor.end_segment_id]
        if anchor.status != "ok" or not any(i in maps for i in range(first, last + 1)):
            continue
        start = maps[first].start(anchor.start_offset) if first in maps else anchor.start_offset
        end = maps[last].end(anchor.end_offset) if last in maps else anchor.end_offset
        page = _page_at(parsed[first].lines, start)
        if first == last and end <= start:
            plan.moves.append(_AnchorMove(anchor.id, start, start, None))
            plan.lost_pages.append(page)
            continue
        covered = [
            SegmentText(plan.stored[i].id, plan.stored[i].position, parsed[i].text)
            for i in range(first, last + 1)
        ]
        quote = anchors.requote(covered, start, end)
        plan.moves.append(_AnchorMove(anchor.id, start, end, quote))
        if not anchor.marks_words:
            continue  # a note on a whole page or chapter: its extent is not a quotation
        if quote.exact != anchor.exact:
            plan.reworded_pages.append(page)
        elif (start, end) != (anchor.start_offset, anchor.end_offset):
            plan.moved += 1


def _plan(conn: sqlite3.Connection, version_id: int, request: CorpusUpdateRequest) -> _Plan:
    version = corpus_store.get_version(conn, version_id)
    if version is None:
        raise NotFound(f"There is no text with id {version_id} in this library.")
    if not request.folder.strip():
        raise InvalidInput("Give the folder that holds the page files.")
    fmt = CorpusFormat(file_pattern=request.file_pattern or paged_corpus.DEFAULT_FILE_PATTERN)
    sources = paged_corpus.read_folder(Path(request.folder.strip()).expanduser(), fmt.file_pattern)
    plan = _Plan(
        corpus=paged_corpus.parse_pages(sources, fmt),
        content_hash=paged_corpus.content_hash(sources),
        stored=corpus_store.stored_segments(conn, version.id, version.pagination_id),
    )
    _compare_structure(plan)
    _compare_divisions(plan, conn, version)
    _carry_anchors(plan, conn, version)
    return plan


def preview_update(
    library: Library, version_id: int, request: CorpusUpdateRequest
) -> CorpusUpdateReport:
    """Compare the folder with the stored text and say what would change. Writes nothing."""
    with db.transaction(library.db_path) as conn:
        return _plan(conn, version_id, request).report()


def commit_update(
    library: Library, version_id: int, request: CorpusUpdateRequest
) -> CorpusUpdateReport:
    """Bring the stored text into line with the folder, in one transaction."""
    with db.transaction(library.db_path) as conn:
        plan = _plan(conn, version_id, request)
        if plan.up_to_date:
            return plan.report()
        version = corpus_store.get_version(conn, version_id)
        assert version is not None
        seq = corpus_store.begin_edit(conn, version.id, plan.content_hash)
        parsed = plan.corpus.segments
        for index, text_changed in plan.rewrites:
            corpus_store.rewrite_segment(
                conn, version.pagination_id, plan.stored[index].id, parsed[index], seq, text_changed
            )
        segment_ids = [segment.id for segment in plan.stored]
        position = plan.stored[-1].position if plan.stored else 0
        for segment in parsed[len(plan.stored) :]:
            position += POSITION_STEP
            segment_ids.append(
                corpus_store.append_segment(
                    conn, version.id, version.pagination_id, position, segment
                )
            )
        for division_id, label in plan.relabels:
            corpus_store.relabel_division(conn, division_id, label)
        for place in plan.new_divisions:
            division = plan.corpus.divisions[place]
            corpus_store.insert_division(
                conn, version.id, division, segment_ids[division.first_segment]
            )
        for move in plan.moves:
            notes_store.relocate_anchor(
                conn, move.anchor_id, move.start_offset, move.end_offset, move.quote
            )
        return plan.report()
