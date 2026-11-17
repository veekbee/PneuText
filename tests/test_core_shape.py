from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import pytest

from pneutext.core import shape
from pneutext.core.shape import ShapeHighlight, ShapeLine
from tests.helpers import FIXTURES

CASES: list[dict[str, Any]] = json.loads(
    (FIXTURES / "shape_cases.json").read_text(encoding="utf-8")
)["cases"]


def test_measure_is_the_95th_percentile_line_length() -> None:
    assert shape.measure(list(range(1, 101))) == 95
    assert shape.measure([10] * 19 + [99]) == 10
    assert shape.measure([50, 60]) == 60


def test_measure_of_nothing_is_zero() -> None:
    assert shape.measure([]) == 0


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_shared_shape_cases(case: dict[str, Any]) -> None:
    lines = [
        ShapeLine(
            id=index,
            kind=line["kind"],
            page=1,
            line_no=line["line_no"],
            starts_paragraph=line["starts_paragraph"],
            ends_paragraph=line["ends_paragraph"],
            length=line["length"],
            highlights=[ShapeHighlight(**h) for h in line["highlights"]],
        )
        for index, line in enumerate(case["lines"])
    ]
    drawn = [asdict(line) for line in shape.layout_page(lines, case["measure"])]
    assert drawn == case["expected"]
