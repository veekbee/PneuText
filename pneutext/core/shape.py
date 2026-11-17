"""Page shape: the geometry of a print page, derived from line lengths alone. No I/O.

Blank mode and every publishable export are drawn from these values, which contain no
corpus text. The drawing rules here are implemented a second time in TypeScript
(``frontend/src/lib/pageLayout.ts``); both are held to ``tests/fixtures/shape_cases.json``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

INDENT = 3
"""How far a paragraph's first line is indented, in characters of the measure."""

_INDENTED_KINDS = frozenset({"paragraph"})


@dataclass(frozen=True)
class ShapeHighlight:
    """Where a note's span crosses one line: offsets within the line, in code points."""

    annotation_id: int
    type_id: int
    start: int
    end: int
    level: int = 1  # the note's reading level, so a reader can hide level 2


@dataclass(frozen=True)
class ShapeLine:
    """One print line without its words."""

    id: int
    kind: str
    page: int
    line_no: int | None
    starts_paragraph: bool
    ends_paragraph: bool
    length: int
    highlights: list[ShapeHighlight] = field(default_factory=list)


@dataclass(frozen=True)
class DrawnHighlight:
    annotation_id: int
    type_id: int
    x0: float  # as fractions of the measure, like the bar they lie on
    x1: float
    band: int  # overlapping highlights stack as offset bands; this is the band's index


@dataclass(frozen=True)
class DrawnLine:
    kind: str
    line_no: int | None
    x0: float  # the bar runs from x0 to x1, as fractions of the measure
    x1: float
    bands: int  # how many bands the line's highlights need
    highlights: list[DrawnHighlight]


def measure(line_lengths: list[int]) -> int:
    """The measure of a text: its 95th-percentile line length (nearest-rank), in code points."""
    if not line_lengths:
        return 0
    ordered = sorted(line_lengths)
    rank = math.ceil(0.95 * len(ordered))
    return ordered[rank - 1]


def _round4(value: float) -> float:
    # Round half up, spelled out so Python and TypeScript agree to the last digit.
    return math.floor(value * 10000 + 0.5) / 10000


def layout_line(line: ShapeLine, measure_: int) -> DrawnLine:
    """Where one line's bar and highlights fall, as fractions of the measure."""
    width = max(measure_, 1)
    is_text = line.kind in ("paragraph", "synopsis")
    if not is_text:
        # Furniture is drawn as a fixed placeholder for its kind, across the measure.
        return DrawnLine(line.kind, line.line_no, 0.0, 1.0, 0, [])

    indented = line.starts_paragraph and line.kind in _INDENTED_KINDS
    x0 = min(INDENT / width, 1.0) if indented else 0.0
    # Print is justified: every line runs the full measure except a paragraph's last.
    x1 = min(x0 + line.length / width, 1.0) if line.ends_paragraph else 1.0

    ordered = sorted(
        line.highlights,
        key=lambda h: (_clamp(h.start, line), -_clamp(h.end, line), h.annotation_id),
    )
    band_ends: list[int] = []  # for each band, where its last highlight ends
    drawn: list[DrawnHighlight] = []
    for highlight in ordered:
        start, end = _clamp(highlight.start, line), _clamp(highlight.end, line)
        end = max(start, end)
        band = next((i for i, taken in enumerate(band_ends) if taken <= start), len(band_ends))
        if band == len(band_ends):
            band_ends.append(end)
        else:
            band_ends[band] = end
        scale = (x1 - x0) / line.length if line.length else 0.0
        drawn.append(
            DrawnHighlight(
                highlight.annotation_id,
                highlight.type_id,
                _round4(x0 + start * scale),
                _round4(x0 + end * scale),
                band,
            )
        )
    return DrawnLine(line.kind, line.line_no, _round4(x0), _round4(x1), len(band_ends), drawn)


def _clamp(offset: int, line: ShapeLine) -> int:
    return max(0, min(offset, line.length))


def layout_page(lines: list[ShapeLine], measure_: int) -> list[DrawnLine]:
    return [layout_line(line, measure_) for line in lines]
