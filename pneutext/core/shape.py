"""Page shape: the geometry of a print page, derived from line lengths alone. No I/O."""

from __future__ import annotations

import math


def measure(line_lengths: list[int]) -> int:
    """The measure of a text: its 95th-percentile line length (nearest-rank), in code points."""
    if not line_lengths:
        return 0
    ordered = sorted(line_lengths)
    rank = math.ceil(0.95 * len(ordered))
    return ordered[rank - 1]
