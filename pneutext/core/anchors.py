"""Anchors: spans of text, validated against the stored text. No I/O.

An anchor runs from (start segment, start offset) to (end segment, end offset), end
exclusive, with offsets in Unicode code points. It knows nothing of pages or lines.
"""

from __future__ import annotations

from dataclasses import dataclass

from pneutext.core.errors import InvalidInput
from pneutext.core.shape import ShapeHighlight

CONTEXT = 32
"""Characters of context kept each side of an anchor, for re-locating it after an edit."""

SEGMENT_JOIN = "\n"
"""What stands between segments in the quoted text of an anchor that crosses them."""

_MISMATCH = (
    "The selected passage does not match the text as stored. Reload the page and select it again."
)


@dataclass(frozen=True)
class SegmentText:
    """A segment as the anchor code needs it: identity, reading order and text."""

    id: int
    position: int
    text: str


@dataclass(frozen=True)
class AnchorQuote:
    exact: str
    prefix: str
    suffix: str


@dataclass(frozen=True)
class Span:
    """A stored anchor reduced to what highlighting needs: reading-order coordinates."""

    annotation_id: int
    type_id: int
    level: int
    start_position: int
    start_offset: int
    end_position: int
    end_offset: int


@dataclass(frozen=True)
class LineGeometry:
    """A print line placed in reading order: its segment's position and its extent."""

    position: int
    start_offset: int
    length: int
    is_text: bool


def quote(segments: list[SegmentText], start_offset: int, end_offset: int) -> str:
    """The text an anchor covers. ``segments`` runs from its first segment to its last."""
    if len(segments) == 1:
        return segments[0].text[start_offset:end_offset]
    parts = [segments[0].text[start_offset:]]
    parts += [segment.text for segment in segments[1:-1]]
    parts.append(segments[-1].text[:end_offset])
    return SEGMENT_JOIN.join(parts)


def validate_span(
    segments: list[SegmentText], start_offset: int, end_offset: int, exact: str
) -> AnchorQuote:
    """Check a span sent by the client and return what to store with it.

    ``segments`` holds every segment from the span's first to its last, in reading order.
    Rejects offsets out of range, an empty or backwards span, and a quotation that does
    not match the stored text. Error messages never quote the text.
    """
    if not segments:
        raise InvalidInput("The passage does not belong to this text.")
    first, last = segments[0], segments[-1]
    if not 0 <= start_offset <= len(first.text) or not 0 <= end_offset <= len(last.text):
        raise InvalidInput("The passage reaches outside the text. Select it again.")
    if len(segments) == 1 and end_offset <= start_offset:
        raise InvalidInput("The passage is empty. Select at least one character.")
    stored = requote(segments, start_offset, end_offset)
    if stored.exact != exact:
        raise InvalidInput(_MISMATCH)
    return stored


def requote(segments: list[SegmentText], start_offset: int, end_offset: int) -> AnchorQuote:
    """What to store with a span: its text as it stands, and the context each side."""
    return AnchorQuote(
        exact=quote(segments, start_offset, end_offset),
        prefix=segments[0].text[max(0, start_offset - CONTEXT) : start_offset],
        suffix=segments[-1].text[end_offset : end_offset + CONTEXT],
    )


def line_highlights(lines: list[LineGeometry], spans: list[Span]) -> list[list[ShapeHighlight]]:
    """For each line, where each span crosses it, as offsets within the line.

    Uses reading-order coordinates only, so it serves the shape projection, which has no
    text. Furniture lines take no highlights.
    """
    result: list[list[ShapeHighlight]] = []
    for line in lines:
        found: list[ShapeHighlight] = []
        if line.is_text:
            line_start = (line.position, line.start_offset)
            line_end = (line.position, line.start_offset + line.length)
            for span in spans:
                span_start = (span.start_position, span.start_offset)
                span_end = (span.end_position, span.end_offset)
                if span_end <= line_start or span_start >= line_end:
                    continue
                start = max(span_start, line_start)[1] - line.start_offset
                end = min(span_end, line_end)[1] - line.start_offset
                if end > start:
                    found.append(
                        ShapeHighlight(span.annotation_id, span.type_id, start, end, span.level)
                    )
        found.sort(key=lambda h: (h.start, -h.end, h.annotation_id))
        result.append(found)
    return result
