"""Page references: ``45``, ``45.12``, ``292-293``, ``45.12-46.3``. No I/O.

A reference names a page, or a line of a page, or a range from one such place to
another, against a pagination. It is stored as an anchor in the text, so it can be
shown with any pagination's page numbers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_PLACE = r"(\d+)(?:\.(\d+))?"
_REFERENCE = re.compile(rf"{_PLACE}(?:\s*[-\u2013]\s*{_PLACE})?")


@dataclass(frozen=True)
class Place:
    page: int
    line: int | None = None

    def __str__(self) -> str:
        return str(self.page) if self.line is None else f"{self.page}.{self.line}"


@dataclass(frozen=True)
class PageReference:
    start: Place
    end: Place  # the same as ``start`` for a single page or line

    @property
    def is_range(self) -> bool:
        return self.start != self.end

    def __str__(self) -> str:
        return f"{self.start}-{self.end}" if self.is_range else str(self.start)


def parse_reference(text: str) -> PageReference | None:
    """Read a reference, or return None if the text is not one (or runs backwards)."""
    match = _REFERENCE.fullmatch(text.strip())
    if match is None:
        return None
    page, line, end_page, end_line = match.groups()
    start = Place(int(page), int(line) if line else None)
    end = start if end_page is None else Place(int(end_page), int(end_line) if end_line else None)
    for place in (start, end):
        # Pages and lines are numbered from 1.
        if place.page < 1 or (place.line is not None and place.line < 1):
            return None
    if (end.page, end.line or 0) < (start.page, start.line or 0):
        return None
    return PageReference(start, end)


def format_citation(reference: PageReference) -> str:
    """How a reference reads in running text: ``p. 292-293``, ``p. 45.12``."""
    return f"p. {reference}"
