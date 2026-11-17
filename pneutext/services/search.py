"""Search: a page reference, or free text over the corpus and over notes, separately."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from pneutext.core.errors import NotFound
from pneutext.core.references import parse_reference
from pneutext.services.extents import line_extent, page_extent
from pneutext.store import corpus as corpus_store
from pneutext.store import db
from pneutext.store import notes as notes_store
from pneutext.store import search as search_store
from pneutext.store.library import Library

MAX_HITS = 50
_WORD = re.compile(r"\w+")
_REFERENCE_LEAD = re.compile(r"^(?:[a-z][a-z0-9]*:|pp?\.?\s*)", re.IGNORECASE)


@dataclass(frozen=True)
class ReferenceHit:
    page: int
    line_no: int | None


@dataclass(frozen=True)
class CorpusHit:
    """One place in the text where the query was found. Carries a line of corpus text."""

    page: int
    line_no: int | None
    before: str
    match: str
    after: str


@dataclass(frozen=True)
class NoteSearchHit:
    note_id: int
    type_id: int
    level: int
    status: str
    page: int | None
    line_no: int | None
    excerpt: str


@dataclass(frozen=True)
class SearchResults:
    query: str
    reference: ReferenceHit | None
    corpus: list[CorpusHit] | None  # None when the corpus was not searched (blank mode)
    notes: list[NoteSearchHit]


def fold(text: str) -> tuple[str, list[int]]:
    """Text with case and accents removed, and for each folded character its source index."""
    folded: list[str] = []
    index: list[int] = []
    for position, character in enumerate(text):
        for piece in unicodedata.normalize("NFD", character).casefold():
            if not unicodedata.combining(piece):
                folded.append(piece)
                index.append(position)
    return "".join(folded), index


def match_query(query: str) -> str | None:
    """An FTS5 query: every word must occur, the last as a prefix; quotes ask for a phrase."""
    stripped = query.strip()
    words = _WORD.findall(stripped)
    if not words:
        return None
    if len(stripped) > 1 and stripped[0] == stripped[-1] == '"':
        return '"' + " ".join(words) + '"'
    quoted = [f'"{word}"' for word in words]
    quoted[-1] += "*"
    return " AND ".join(quoted)


def _occurrences(text: str, query: str) -> list[tuple[int, int]]:
    """Where a query's first word (or its whole phrase) starts and ends in a text."""
    stripped = query.strip()
    words = _WORD.findall(stripped)
    phrase = len(stripped) > 1 and stripped[0] == stripped[-1] == '"'
    folded, index = fold(text)
    needle = fold(" ".join(words) if phrase else words[0])[0]
    found = []
    start = folded.find(needle)
    while start != -1:
        at_word_start = start == 0 or not folded[start - 1].isalnum()
        end = start + len(needle)
        if at_word_start:
            # Extend a prefix match to the end of the word it found.
            while not phrase and end < len(folded) and folded[end].isalnum():
                end += 1
            found.append((index[start], index[end - 1] + 1))
        start = folded.find(needle, start + 1)
    return found


def _reference(query: str) -> tuple[int, int | None] | None:
    reference = parse_reference(_REFERENCE_LEAD.sub("", query.strip()))
    return None if reference is None else (reference.start.page, reference.start.line)


def _excerpt(body: str, query: str, width: int = 140) -> str:
    plain = " ".join(body.split())
    spots = _occurrences(plain, query)
    start = max(0, spots[0][0] - width // 3) if spots else 0
    excerpt = plain[start : start + width]
    return ("…" if start > 0 else "") + excerpt + ("…" if start + width < len(plain) else "")


def search(library: Library, version_id: int, query: str, include_corpus: bool) -> SearchResults:
    """Search one text. The corpus is searched only when asked: never in blank mode."""
    with db.transaction(library.db_path) as conn:
        version = corpus_store.get_version(conn, version_id)
        if version is None:
            raise NotFound(f"There is no text with id {version_id} in this library.")

        reference = None
        place = _reference(query)
        if place is not None:
            page, line = place
            exists = (
                page_extent(conn, version, page)
                if line is None
                else line_extent(conn, version, page, line)
            )
            if exists is not None:
                reference = ReferenceHit(page, line)

        match = match_query(query)
        corpus: list[CorpusHit] | None = [] if include_corpus else None
        notes: list[NoteSearchHit] = []
        if match is None:
            return SearchResults(query, reference, corpus, notes)

        if corpus is not None:
            for hit in search_store.search_segments(conn, version.id, match, MAX_HITS):
                for start, end in _occurrences(hit.text, query):
                    line_row = corpus_store.line_at_offset(
                        conn, version.pagination_id, hit.segment_id, start
                    )
                    if line_row is None or len(corpus) >= MAX_HITS:
                        continue
                    line_end = line_row.start_offset + line_row.length
                    corpus.append(
                        CorpusHit(
                            page=line_row.page,
                            line_no=line_row.line_no,
                            before=hit.text[line_row.start_offset : start],
                            match=hit.text[start : min(end, line_end)],
                            after=hit.text[min(end, line_end) : line_end],
                        )
                    )

        for found in search_store.search_notes(conn, version.id, match, MAX_HITS):
            located = notes_store.locate(
                conn, version.pagination_id, found.start_segment_id, found.start_offset
            )
            page, line = located if located is not None else (None, None)
            notes.append(
                NoteSearchHit(
                    found.note_id,
                    found.type_id,
                    found.level,
                    found.status,
                    page,
                    line,
                    _excerpt(found.body_md, query),
                )
            )
        return SearchResults(query, reference, corpus, notes)
