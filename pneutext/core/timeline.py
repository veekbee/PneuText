"""Narrative time: working out when each event in a text happens. No I/O.

Most time mentions are relative ("five days later"), so the date of any one depends on
those before it. A time point is either *absolute*, holding an ISO 8601 date or date-time
at whatever precision is known, or an *offset*, holding an ISO 8601 duration and the
point it counts from (by default the previous time point in reading order). The resolved
date of a point is computed by walking this chain and is never stored, so correcting one
point updates every point after it.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

PRECISIONS = ("year", "month", "day", "time")

_DATE = re.compile(
    r"(?P<year>\d{4})(?:-(?P<month>\d{2})(?:-(?P<day>\d{2})"
    r"(?:[T ](?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?)?)?)?"
)
_DURATION = re.compile(
    r"(?P<sign>[-+])?P(?:(?P<years>\d+)Y)?(?:(?P<months>\d+)M)?(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?"
)
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class PartialDate:
    """A date or date-time known to some precision; ``moment`` is its earliest instant."""

    moment: datetime
    precision: str  # one of PRECISIONS

    def iso(self) -> str:
        if self.precision == "year":
            return f"{self.moment.year:04d}"
        if self.precision == "month":
            return f"{self.moment.year:04d}-{self.moment.month:02d}"
        if self.precision == "day":
            return self.moment.strftime("%Y-%m-%d")
        return self.moment.strftime("%Y-%m-%dT%H:%M")

    def words(self) -> str:
        """How the date reads in running text: ``28 October 1871``."""
        month = _MONTHS[self.moment.month - 1]
        if self.precision == "year":
            return str(self.moment.year)
        if self.precision == "month":
            return f"{month} {self.moment.year}"
        day = f"{self.moment.day} {month} {self.moment.year}"
        return day if self.precision == "day" else f"{day}, {self.moment:%H:%M}"


@dataclass(frozen=True)
class Duration:
    """A length of time in calendar units. Weeks are kept as days."""

    years: int = 0
    months: int = 0
    days: int = 0
    seconds: int = 0

    def __add__(self, other: Duration) -> Duration:
        return Duration(
            self.years + other.years,
            self.months + other.months,
            self.days + other.days,
            self.seconds + other.seconds,
        )

    def __sub__(self, other: Duration) -> Duration:
        return Duration(
            self.years - other.years,
            self.months - other.months,
            self.days - other.days,
            self.seconds - other.seconds,
        )

    def _parts(self) -> list[tuple[int, str, str]]:
        hours, rest = divmod(abs(self.seconds), 3600)
        minutes, seconds = divmod(rest, 60)
        sign = -1 if self.seconds < 0 else 1
        return [
            (self.years, "Y", "year"),
            (self.months, "M", "month"),
            (self.days, "D", "day"),
            (sign * hours, "H", "hour"),
            (sign * minutes, "M", "minute"),
            (sign * seconds, "S", "second"),
        ]

    def is_negative(self) -> bool:
        values = [value for value, _, _ in self._parts() if value]
        return bool(values) and all(value < 0 for value in values)

    def iso(self) -> str:
        """ISO 8601, with a leading minus when every part is negative."""
        negative = self.is_negative()
        flip = -1 if negative else 1
        parts = self._parts()
        date = "".join(f"{flip * value}{unit}" for value, unit, _ in parts[:3] if value)
        time = "".join(f"{flip * value}{unit}" for value, unit, _ in parts[3:] if value)
        body = date + ("T" + time if time else "")
        return ("-" if negative else "") + "P" + (body or "0D")

    def words(self) -> str:
        """How the duration reads in running text: ``1 year, 2 months, 5 days``."""
        negative = self.is_negative()
        flip = -1 if negative else 1
        said = [
            f"{flip * value} {name}{'' if abs(value) == 1 else 's'}"
            for value, _, name in self._parts()
            if value
        ]
        if not said:
            return "no time"
        return ", ".join(said) + (" earlier" if negative else "")


def parse_date(text: str) -> PartialDate | None:
    """Read ``1871``, ``1871-10``, ``1871-10-28`` or ``1871-10-28T06:30``."""
    match = _DATE.fullmatch(text.strip())
    if match is None:
        return None
    parts = {name: int(value) for name, value in match.groupdict().items() if value is not None}
    precision = (
        "time"
        if "hour" in parts
        else "day"
        if "day" in parts
        else "month"
        if "month" in parts
        else "year"
    )
    try:
        moment = datetime(
            parts["year"],
            parts.get("month", 1),
            parts.get("day", 1),
            parts.get("hour", 0),
            parts.get("minute", 0),
            parts.get("second", 0),
        )
    except ValueError:
        return None  # no such day, month or hour
    return PartialDate(moment, precision)


def parse_duration(text: str) -> Duration | None:
    """Read an ISO 8601 duration such as ``P5D``, ``P3W``, ``P1Y2M`` or ``PT6H``."""
    stripped = text.strip().upper()
    match = _DURATION.fullmatch(stripped)
    if match is None or stripped.rstrip("T") in ("P", "-P", "+P") or stripped.endswith("T"):
        return None
    part = {name: int(value or 0) for name, value in match.groupdict().items() if name != "sign"}
    sign = -1 if match.group("sign") == "-" else 1
    return Duration(
        sign * part["years"],
        sign * part["months"],
        sign * (part["days"] + 7 * part["weeks"]),
        sign * (part["hours"] * 3600 + part["minutes"] * 60 + part["seconds"]),
    )


def add(moment: datetime, duration: Duration) -> datetime:
    """Move a moment by a duration: years and months by the calendar, the rest exactly."""
    months = moment.year * 12 + (moment.month - 1) + duration.years * 12 + duration.months
    year, month = divmod(months, 12)
    month += 1
    day = min(moment.day, calendar.monthrange(year, month)[1])  # 31 Jan + 1 month = 28 Feb
    shifted = moment.replace(year=year, month=month, day=day)
    return shifted + timedelta(days=duration.days, seconds=duration.seconds)


def between(earlier: datetime, later: datetime) -> Duration:
    """The time from one moment to another, in days (and seconds, if any)."""
    delta = later - earlier
    return (
        Duration(days=delta.days, seconds=delta.seconds)
        if delta.days >= 0
        else _negate(between(later, earlier))
    )


def _negate(duration: Duration) -> Duration:
    return Duration() - duration


@dataclass(frozen=True)
class TimePoint:
    """A time mention's value, as stored. ``kind`` is None while no value has been given."""

    id: int
    kind: str | None = None  # "absolute" or "offset"
    at: str | None = None
    offset: str | None = None
    relative_to: int | None = None  # the point an offset counts from; None = the previous one
    label: str | None = None


@dataclass(frozen=True)
class Resolved:
    """What a time point resolves to."""

    id: int
    date: PartialDate | None  # the narrative date, when the chain reaches an absolute point
    elapsed: Duration | None  # otherwise: time elapsed since the start of its chain
    root: int | None  # the point its chain starts from
    problem: str | None = None  # why it could not be resolved, in plain words


def resolve(points: list[TimePoint]) -> dict[int, Resolved]:
    """Resolve every time point. ``points`` is in reading order."""
    by_id = {point.id: point for point in points}
    previous_valued: dict[int, int | None] = {}
    last: int | None = None
    for point in points:
        previous_valued[point.id] = last
        if point.kind is not None:
            last = point.id

    done: dict[int, Resolved] = {}

    def solve(point: TimePoint, trail: tuple[int, ...]) -> Resolved:
        if point.id in done:
            return done[point.id]
        if point.id in trail:
            return Resolved(point.id, None, None, None, "It counts from itself, in a circle.")
        result = _solve_one(point, trail)
        done[point.id] = result
        return result

    def _solve_one(point: TimePoint, trail: tuple[int, ...]) -> Resolved:
        if point.kind is None:
            return Resolved(point.id, None, None, None, "No value has been given yet.")
        if point.kind == "absolute":
            date = parse_date(point.at or "")
            if date is None:
                return Resolved(point.id, None, None, None, "The date is not written as a date.")
            return Resolved(point.id, date, Duration(), point.id)
        duration = parse_duration(point.offset or "")
        if duration is None:
            return Resolved(point.id, None, None, None, "The offset is not written as a duration.")
        base_id = point.relative_to if point.relative_to is not None else previous_valued[point.id]
        if base_id is None:
            # Nothing to count from: this point starts a chain of elapsed time only.
            return Resolved(point.id, None, duration, point.id)
        base_point = by_id.get(base_id)
        if base_point is None:
            return Resolved(point.id, None, None, None, "The point it counts from is gone.")
        base = solve(base_point, (*trail, point.id))
        if base.problem is not None:
            return Resolved(
                point.id, None, None, None, "The point it counts from has no date: " + base.problem
            )
        if base.date is not None:
            # Precision is that of the date the chain starts from: never finer than known.
            moved = PartialDate(add(base.date.moment, duration), base.date.precision)
            return Resolved(point.id, moved, None, base.root)
        assert base.elapsed is not None
        return Resolved(point.id, None, base.elapsed + duration, base.root)

    for point in points:
        solve(point, ())
    return done


def elapsed_between(earlier: Resolved, later: Resolved) -> Duration | None:
    """Time from one resolved point to another, when the two can be compared."""
    if earlier.date is not None and later.date is not None:
        return between(earlier.date.moment, later.date.moment)
    if (
        earlier.elapsed is not None
        and later.elapsed is not None
        and earlier.root is not None
        and earlier.root == later.root
        and earlier.date is None
        and later.date is None
    ):
        return later.elapsed - earlier.elapsed
    return None
