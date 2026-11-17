from __future__ import annotations

import pytest

from pneutext.core.anchors import (
    CONTEXT,
    LineGeometry,
    SegmentText,
    Span,
    line_highlights,
    quote,
    validate_span,
)
from pneutext.core.errors import InvalidInput

ONE = [SegmentText(1, 1000, "alpha beta gamma delta")]
THREE = [
    SegmentText(1, 1000, "alpha beta"),
    SegmentText(2, 2000, "gamma"),
    SegmentText(3, 3000, "delta epsilon"),
]


def test_quote_within_one_segment() -> None:
    assert quote(ONE, 6, 16) == "beta gamma"


def test_quote_across_segments_joins_them_with_newlines() -> None:
    assert quote(THREE, 6, 5) == "beta\ngamma\ndelta"
    assert quote(THREE[:2], 6, 0) == "beta\n"


def test_a_valid_span_returns_its_quotation_and_context() -> None:
    found = validate_span(ONE, 6, 10, "beta")
    assert (found.exact, found.prefix, found.suffix) == ("beta", "alpha ", " gamma delta")


def test_context_is_limited_to_32_characters_each_side() -> None:
    text = "a" * 50 + "MID" + "z" * 50
    found = validate_span([SegmentText(1, 1000, text)], 50, 53, "MID")
    assert found.prefix == "a" * CONTEXT
    assert found.suffix == "z" * CONTEXT


def test_offsets_count_code_points_not_utf16_units() -> None:
    # U+1D11E is one code point but two UTF-16 units; a client that sent UTF-16 offsets
    # for the word after it would be off by one and must be refused.
    segment = [SegmentText(1, 1000, "red \U0001d11e beside it")]
    assert validate_span(segment, 6, 12, "beside").exact == "beside"
    with pytest.raises(InvalidInput, match="does not match"):
        validate_span(segment, 7, 13, "beside")


@pytest.mark.parametrize(
    ("start", "end", "exact", "expected"),
    [
        (6, 99, "beta", "outside the text"),
        (-1, 4, "alph", "outside the text"),
        (10, 10, "", "is empty"),
        (10, 6, "", "is empty"),
        (6, 10, "BETA", "does not match"),
        (6, 10, "beta ", "does not match"),
    ],
)
def test_bad_spans_are_refused(start: int, end: int, exact: str, expected: str) -> None:
    with pytest.raises(InvalidInput, match=expected):
        validate_span(ONE, start, end, exact)


def test_a_span_outside_the_version_is_refused() -> None:
    with pytest.raises(InvalidInput, match="does not belong"):
        validate_span([], 0, 1, "x")


def test_refusals_never_quote_the_text() -> None:
    with pytest.raises(InvalidInput) as caught:
        validate_span(ONE, 6, 10, "secret words")
    assert "secret" not in caught.value.message
    assert "beta" not in caught.value.message


# Lines of two paragraphs: positions 1000 (two lines) and 2000 (one line).
LINES = [
    LineGeometry(1000, 0, 10, True),
    LineGeometry(1000, 11, 8, True),
    LineGeometry(1500, 0, 0, False),  # furniture between them
    LineGeometry(2000, 0, 12, True),
]


def span(note: int, start: tuple[int, int], end: tuple[int, int], level: int = 1) -> Span:
    return Span(note, 7, level, start[0], start[1], end[0], end[1])


def marks(spans: list[Span]) -> list[list[tuple[int, int, int]]]:
    return [
        [(h.annotation_id, h.start, h.end) for h in line] for line in line_highlights(LINES, spans)
    ]


def test_a_span_within_one_line() -> None:
    assert marks([span(1, (1000, 2), (1000, 6))]) == [[(1, 2, 6)], [], [], []]


def test_a_span_crossing_a_line_break_skips_the_joining_space() -> None:
    assert marks([span(1, (1000, 8), (1000, 14))]) == [[(1, 8, 10)], [(1, 0, 3)], [], []]


def test_a_span_crossing_segments_skips_furniture() -> None:
    assert marks([span(1, (1000, 15), (2000, 4))]) == [[], [(1, 4, 8)], [], [(1, 0, 4)]]


def test_a_span_starting_before_the_page_and_ending_after_it_covers_every_line() -> None:
    assert marks([span(1, (500, 3), (9000, 1))]) == [[(1, 0, 10)], [(1, 0, 8)], [], [(1, 0, 12)]]


def test_a_span_that_only_touches_a_line_end_leaves_no_mark() -> None:
    assert marks([span(1, (1000, 10), (1000, 11))]) == [[], [], [], []]
    assert marks([span(1, (1000, 19), (2000, 0))]) == [[], [], [], []]


def test_nested_and_overlapping_spans_are_ordered_outer_first() -> None:
    found = line_highlights(
        LINES,
        [
            span(3, (1000, 4), (1000, 9)),
            span(1, (1000, 0), (1000, 9)),
            span(2, (1000, 2), (1000, 6), 2),
        ],
    )
    assert [(h.annotation_id, h.start, h.end, h.level) for h in found[0]] == [
        (1, 0, 9, 1),
        (2, 2, 6, 2),
        (3, 4, 9, 1),
    ]
