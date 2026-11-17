from __future__ import annotations

from pneutext.core import shape


def test_measure_is_the_95th_percentile_line_length() -> None:
    assert shape.measure(list(range(1, 101))) == 95
    assert shape.measure([10] * 19 + [99]) == 10
    assert shape.measure([50, 60]) == 60


def test_measure_of_nothing_is_zero() -> None:
    assert shape.measure([]) == 0
