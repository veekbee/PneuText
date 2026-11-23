"""Carrying positions in a text across a change to it. No I/O.

When a paragraph is corrected, every stored span over it has to follow the words it
marked. ``OffsetMap`` compares the old and new text once and then answers, for any
offset in the old text, where that place is in the new one.
"""

from __future__ import annotations

from difflib import SequenceMatcher


class OffsetMap:
    """Maps code-point offsets in ``old`` to offsets in ``new``."""

    def __init__(self, old: str, new: str) -> None:
        self._old_length = len(old)
        self._new_length = len(new)
        matcher = SequenceMatcher(None, old, new, autojunk=False)
        self._blocks = [
            (i1, i2, j1, j2, tag == "equal") for tag, i1, i2, j1, j2 in matcher.get_opcodes()
        ]
        self.kept = sum(i2 - i1 for i1, i2, _j1, _j2, equal in self._blocks if equal)
        """How many characters of the old text are still there."""

    def start(self, offset: int) -> int:
        """Where a span that began at ``offset`` begins now.

        Text inserted exactly at the start is left outside the span; a start that fell
        inside rewritten text moves to the beginning of the rewriting.
        """
        for i1, i2, j1, _j2, equal in self._blocks:
            if i1 <= offset < i2:
                return j1 + (offset - i1) if equal else j1
        return self._new_length

    def end(self, offset: int) -> int:
        """Where a span that ended (exclusive) at ``offset`` ends now.

        Text inserted exactly at the end is left outside the span; an end that fell
        inside rewritten text moves to the end of the rewriting.
        """
        for i1, i2, j1, j2, equal in self._blocks:
            if i1 < offset <= i2:
                return j1 + (offset - i1) if equal else j2
        return 0
