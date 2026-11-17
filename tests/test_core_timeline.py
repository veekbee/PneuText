from __future__ import annotations

from datetime import datetime

import pytest

from pneutext.core.timeline import (
    Duration,
    TimePoint,
    add,
    between,
    elapsed_between,
    parse_date,
    parse_duration,
    resolve,
)


@pytest.mark.parametrize(
    ("text", "precision", "iso", "words"),
    [
        ("1871", "year", "1871", "1871"),
        ("1871-10", "month", "1871-10", "October 1871"),
        ("1871-10-28", "day", "1871-10-28", "28 October 1871"),
        ("1871-10-28T06:30", "time", "1871-10-28T06:30", "28 October 1871, 06:30"),
        ("1871-10-28 06:30:15", "time", "1871-10-28T06:30", "28 October 1871, 06:30"),
    ],
)
def test_dates_at_whatever_precision_is_known(
    text: str, precision: str, iso: str, words: str
) -> None:
    date = parse_date(text)
    assert date is not None
    assert (date.precision, date.iso(), date.words()) == (precision, iso, words)


@pytest.mark.parametrize(
    "text", ["", "October 1871", "1871-13", "1871-02-30", "71", "1871-10-28T25:00"]
)
def test_what_is_not_a_date(text: str) -> None:
    assert parse_date(text) is None


@pytest.mark.parametrize(
    ("text", "expected", "iso", "words"),
    [
        ("P5D", Duration(days=5), "P5D", "5 days"),
        ("P3W", Duration(days=21), "P21D", "21 days"),
        ("P1Y2M", Duration(years=1, months=2), "P1Y2M", "1 year, 2 months"),
        ("PT6H", Duration(seconds=21600), "PT6H", "6 hours"),
        (
            "P1DT12H30M",
            Duration(days=1, seconds=45000),
            "P1DT12H30M",
            "1 day, 12 hours, 30 minutes",
        ),
        ("-P2D", Duration(days=-2), "-P2D", "2 days earlier"),
        ("p5d", Duration(days=5), "P5D", "5 days"),
        ("P0D", Duration(), "P0D", "no time"),
    ],
)
def test_durations(text: str, expected: Duration, iso: str, words: str) -> None:
    duration = parse_duration(text)
    assert duration == expected
    assert (duration.iso(), duration.words()) == (iso, words)


@pytest.mark.parametrize("text", ["", "P", "PT", "5D", "P5", "five days", "P1DT", "P5X"])
def test_what_is_not_a_duration(text: str) -> None:
    assert parse_duration(text) is None


def test_adding_follows_the_calendar_for_months_and_years() -> None:
    assert add(datetime(1871, 10, 28), Duration(days=5)) == datetime(1871, 11, 2)
    assert add(datetime(1871, 1, 31), Duration(months=1)) == datetime(1871, 2, 28)
    assert add(datetime(1872, 2, 29), Duration(years=1)) == datetime(1873, 2, 28)
    assert add(datetime(1871, 12, 15), Duration(months=2, days=1)) == datetime(1872, 2, 16)
    assert add(datetime(1871, 10, 28), Duration(days=-28)) == datetime(1871, 9, 30)
    assert add(datetime(1871, 10, 28, 6), Duration(seconds=20 * 3600)) == datetime(1871, 10, 29, 2)


def test_time_between_two_moments_is_counted_in_days() -> None:
    assert between(datetime(1871, 10, 28), datetime(1871, 12, 7)) == Duration(days=40)
    assert between(datetime(1871, 12, 7), datetime(1871, 10, 28)) == Duration(days=-40)
    assert between(datetime(1871, 10, 28, 6), datetime(1871, 10, 29, 18)) == Duration(
        1 - 1, 0, 1, 43200
    )


def dates(points: list[TimePoint]) -> dict[int, str | None]:
    return {i: (r.date.iso() if r.date else None) for i, r in resolve(points).items()}


def test_an_offset_counts_from_the_previous_point_in_reading_order() -> None:
    points = [
        TimePoint(1, "absolute", at="1871-10-28"),
        TimePoint(2, "offset", offset="P3D"),
        TimePoint(3, "offset", offset="P5D"),
        TimePoint(4, "offset", offset="P3W"),
    ]
    assert dates(points) == {1: "1871-10-28", 2: "1871-10-31", 3: "1871-11-05", 4: "1871-11-26"}


def test_correcting_one_point_moves_every_point_after_it() -> None:
    later = [TimePoint(2, "offset", offset="P3D"), TimePoint(3, "offset", offset="P5D")]
    before = dates([TimePoint(1, "absolute", at="1871-10-28"), *later])
    after = dates([TimePoint(1, "absolute", at="1872-01-01"), *later])
    assert (before[3], after[3]) == ("1871-11-05", "1872-01-09")


def test_an_offset_may_count_from_a_named_point_instead() -> None:
    points = [
        TimePoint(1, "absolute", at="1871-10-28", label="arrival"),
        TimePoint(2, "offset", offset="P5D"),
        TimePoint(3, "offset", offset="P2D", relative_to=1),  # two days after arrival, not after 2
        TimePoint(4, "offset", offset="P1D"),  # the previous point is 3
    ]
    assert dates(points) == {1: "1871-10-28", 2: "1871-11-02", 3: "1871-10-30", 4: "1871-10-31"}


def test_a_point_without_a_value_is_passed_over_by_those_that_follow() -> None:
    points = [
        TimePoint(1, "absolute", at="1871-10-28"),
        TimePoint(2),  # imported without a value
        TimePoint(3, "offset", offset="P5D"),
    ]
    found = resolve(points)
    assert found[3].date is not None and found[3].date.iso() == "1871-11-02"
    assert found[2].date is None and found[2].problem == "No value has been given yet."


def test_precision_is_never_finer_than_the_date_the_chain_starts_from() -> None:
    points = [
        TimePoint(1, "absolute", at="1871-10"),
        TimePoint(2, "offset", offset="P5D"),
        TimePoint(3, "offset", offset="P40D"),
    ]
    found = resolve(points)
    assert [found[i].date.words() for i in (1, 2, 3)] == [  # type: ignore[union-attr]
        "October 1871",
        "October 1871",
        "November 1871",
    ]
    year = resolve([TimePoint(1, "absolute", at="1871"), TimePoint(2, "offset", offset="P1Y3M")])
    assert year[2].date is not None and year[2].date.iso() == "1872"


def test_a_chain_with_no_absolute_point_resolves_to_elapsed_time_only() -> None:
    points = [
        TimePoint(1, "offset", offset="P0D", label="start"),
        TimePoint(2, "offset", offset="P5D"),
        TimePoint(3, "offset", offset="P1M2D"),
    ]
    found = resolve(points)
    assert [found[i].date for i in (1, 2, 3)] == [None, None, None]
    assert [found[i].elapsed.iso() for i in (1, 2, 3)] == ["P0D", "P5D", "P1M7D"]  # type: ignore[union-attr]
    assert {found[i].root for i in (1, 2, 3)} == {1}


def test_bad_values_and_circles_are_explained_not_raised() -> None:
    found = resolve(
        [
            TimePoint(1, "absolute", at="October"),
            TimePoint(2, "offset", offset="five days", relative_to=1),
            TimePoint(3, "offset", offset="P1D", relative_to=4),
            TimePoint(4, "offset", offset="P1D", relative_to=3),
            TimePoint(5, "offset", offset="P1D", relative_to=99),
        ]
    )
    assert found[1].problem == "The date is not written as a date."
    assert found[2].problem == "The offset is not written as a duration."
    assert "circle" in (found[3].problem or "")
    assert found[5].problem == "The point it counts from is gone."
    assert all(found[i].date is None for i in found)


def test_elapsed_time_since_a_labeled_point() -> None:
    found = resolve(
        [
            TimePoint(1, "absolute", at="1871-10-28", label="arrival"),
            TimePoint(2, "offset", offset="P5D"),
            TimePoint(3, "offset", offset="P5W"),
        ]
    )
    assert elapsed_between(found[1], found[3]) == Duration(days=40)
    assert elapsed_between(found[1], found[1]) == Duration()
    assert elapsed_between(found[3], found[1]) == Duration(days=-40)


def test_elapsed_time_within_a_chain_that_has_no_date() -> None:
    found = resolve(
        [
            TimePoint(1, "offset", offset="P0D", label="start"),
            TimePoint(2, "offset", offset="P5D"),
            TimePoint(3, "offset", offset="P1M"),
            TimePoint(9, "absolute", at="1871"),
        ]
    )
    assert elapsed_between(found[1], found[3]) == Duration(months=1, days=5)
    # A dated point and an undated chain cannot be compared.
    assert elapsed_between(found[1], found[9]) is None
