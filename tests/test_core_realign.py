from __future__ import annotations

from pneutext.core.realign import OffsetMap


def carried(old: str, new: str, phrase: str) -> str:
    """What a span over ``phrase`` in the old text covers in the new one."""
    at = old.index(phrase)
    moved = OffsetMap(old, new)
    return new[moved.start(at) : moved.end(at + len(phrase))]


def test_a_span_after_an_insertion_shifts_with_its_words() -> None:
    assert carried("the gray heron stood", "the old gray heron stood", "heron") == "heron"


def test_a_span_before_a_change_stays_put() -> None:
    assert carried("the gray heron stood", "the gray heron stood still", "gray") == "gray"


def test_a_correction_inside_a_span_is_taken_in() -> None:
    assert carried("the gary heron stood", "the gray heron stood", "gary heron") == "gray heron"


def test_text_added_at_the_edges_of_a_span_stays_outside_it() -> None:
    assert carried("the heron stood", "the tall heron, alone, stood", "heron") == "heron"


def test_a_span_whose_words_were_removed_collapses() -> None:
    old, new = "the gray heron stood", "the heron stood"
    moved = OffsetMap(old, new)
    at = old.index("gray")
    assert moved.end(at + 4) <= moved.start(at)


def test_a_span_reaching_either_end_of_the_text_keeps_reaching_it() -> None:
    old, new = "reeds ran out", "The reeds ran out far"
    moved = OffsetMap(old, new)
    assert new[moved.start(0) : moved.end(len(old))] == "reeds ran out"
    assert OffsetMap(old, old).end(len(old)) == len(old)
