from __future__ import annotations

import pytest

from pneutext.core.references import PageReference, Place, format_citation, parse_reference


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("45", Place(45), Place(45)),
        ("45.12", Place(45, 12), Place(45, 12)),
        ("292-293", Place(292), Place(293)),
        ("45.12-46.3", Place(45, 12), Place(46, 3)),
        ("45.12-45.14", Place(45, 12), Place(45, 14)),
        (" 7 - 9 ", Place(7), Place(9)),
        ("292\u2013293", Place(292), Place(293)),
    ],
)
def test_the_four_forms_of_reference(text: str, start: Place, end: Place) -> None:
    assert parse_reference(text) == PageReference(start, end)


@pytest.mark.parametrize(
    "text", ["", "p45", "45.", "45.12.3", "9-2", "45.12-45.3", "0", "45.0", "x"]
)
def test_what_is_not_a_reference(text: str) -> None:
    assert parse_reference(text) is None


def test_references_print_back_in_their_own_syntax() -> None:
    for text in ("45", "45.12", "292-293", "45.12-46.3"):
        reference = parse_reference(text)
        assert reference is not None
        assert str(reference) == text


def test_citations_read_as_pages() -> None:
    assert format_citation(PageReference(Place(292), Place(293))) == "p. 292-293"
    assert format_citation(PageReference(Place(45, 12), Place(45, 12))) == "p. 45.12"
