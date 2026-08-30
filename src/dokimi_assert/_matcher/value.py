"""The assertions whose subject is a value.

Each takes a seat and a mode, so one comparison serves both public
surfaces and neither can drift from the other.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence, Set, Sized
from typing import Any

from dokimi_assert._matcher.compare import equal as _equal
from dokimi_assert._matcher.option import Option, settings
from dokimi_assert._matcher.seat import Mode, Seat, report


def equal(
    seat: Seat, mode: Mode, got: Any, want: Any, msg: str, *options: Option
) -> None:
    """Report when got and want differ. See the comparison rules."""
    seat.helper()
    if not _equal(got, want, settings(options)):
        report(seat, mode, f"{msg}: want {want!r}, got {got!r}")


def not_equal(
    seat: Seat, mode: Mode, got: Any, want: Any, msg: str, *options: Option
) -> None:
    """Report when got and want are equal."""
    seat.helper()
    if _equal(got, want, settings(options)):
        report(seat, mode, f"{msg}: values are equal, want different: got {got!r}")


def is_true(seat: Seat, mode: Mode, condition: bool, msg: str) -> None:
    """Report when the condition does not hold."""
    seat.helper()
    if not condition:
        report(seat, mode, f"{msg}: expected true, got false")


def is_false(seat: Seat, mode: Mode, condition: bool, msg: str) -> None:
    """Report when the condition holds."""
    seat.helper()
    if condition:
        report(seat, mode, f"{msg}: expected false, got true")


def is_none(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got is not None."""
    seat.helper()
    if got is not None:
        report(seat, mode, f"{msg}: expected none, got {got!r}")


def is_not_none(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got is None."""
    seat.helper()
    if got is None:
        report(seat, mode, f"{msg}: expected a value, got none")


def length(seat: Seat, mode: Mode, got: Any, want: int, msg: str) -> None:
    """Report when got does not hold want items.

    Anything without a length is itself the failure rather than an
    exception, so a wrong type reads like every other failure.
    """
    seat.helper()
    if not isinstance(got, Sized):
        report(seat, mode, f"{msg}: length not supported for {type(got).__name__}")
        return
    if len(got) != want:
        report(seat, mode, f"{msg}: expected length {want}, got {len(got)}")


def is_empty(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got holds anything."""
    seat.helper()
    if not isinstance(got, Sized):
        report(seat, mode, f"{msg}: emptiness not supported for {type(got).__name__}")
        return
    if len(got) != 0:
        report(seat, mode, f"{msg}: expected empty, got length {len(got)}")


def is_not_empty(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got holds nothing."""
    seat.helper()
    if not isinstance(got, Sized):
        report(seat, mode, f"{msg}: emptiness not supported for {type(got).__name__}")
        return
    if len(got) == 0:
        report(seat, mode, f"{msg}: expected non-empty, got length 0")


def _holds(haystack: Any, needle: Any, relax: Option) -> tuple[bool, bool]:
    """Report whether haystack holds needle, and whether it can answer."""
    if isinstance(haystack, str):
        if not isinstance(needle, str):
            return False, False
        return needle in haystack, True

    if isinstance(haystack, (bytes, bytearray)):
        probe = needle.encode() if isinstance(needle, str) else needle
        return probe in haystack, True

    if isinstance(haystack, Mapping):
        return needle in haystack, True

    if isinstance(haystack, (Sequence, Set)):
        return any(_equal(item, needle, relax) for item in haystack), True

    return False, False


def contains(
    seat: Seat, mode: Mode, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Report when haystack does not hold needle."""
    seat.helper()
    found, supported = _holds(haystack, needle, settings(options))
    if not supported:
        report(
            seat,
            mode,
            f"{msg}: containment not supported for {type(haystack).__name__}",
        )
        return
    if not found:
        report(seat, mode, f"{msg}: {haystack!r} does not contain {needle!r}")


def not_contains(
    seat: Seat, mode: Mode, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Report when haystack holds needle."""
    seat.helper()
    found, supported = _holds(haystack, needle, settings(options))
    if not supported:
        report(
            seat,
            mode,
            f"{msg}: containment not supported for {type(haystack).__name__}",
        )
        return
    if found:
        report(seat, mode, f"{msg}: {haystack!r} contains {needle!r}, want it absent")


def _text_of(got: Any) -> tuple[str, bool]:
    """Read a value as text, accepting str and bytes."""
    if isinstance(got, str):
        return got, True
    if isinstance(got, (bytes, bytearray)):
        return got.decode(errors="replace"), True
    return "", False


def contains_in_order(
    seat: Seat, mode: Mode, got: Any, needles: Sequence[str], msg: str
) -> None:
    """Report when got does not hold every needle in order.

    Each needle must appear after the previous one's match ends, which
    is what catches a formatter that reorders its fields.
    """
    seat.helper()
    text, ok = _text_of(got)
    if not ok:
        report(
            seat,
            mode,
            f"{msg}: ordered containment requires text, got {type(got).__name__}",
        )
        return

    cursor = 0
    for index, needle in enumerate(needles):
        at = text.find(needle, cursor)
        if at < 0:
            report(
                seat,
                mode,
                f"{msg}: needle {index} ({needle!r}) not found after position "
                f"{cursor} in {text!r}",
            )
            return
        cursor = at + len(needle)


def has_prefix(seat: Seat, mode: Mode, got: Any, prefix: str, msg: str) -> None:
    """Report when got does not start with prefix."""
    seat.helper()
    text, ok = _text_of(got)
    if not ok:
        report(seat, mode, f"{msg}: prefix requires text, got {type(got).__name__}")
        return
    if not text.startswith(prefix):
        report(seat, mode, f"{msg}: {text!r} does not start with {prefix!r}")


def has_suffix(seat: Seat, mode: Mode, got: Any, suffix: str, msg: str) -> None:
    """Report when got does not end with suffix."""
    seat.helper()
    text, ok = _text_of(got)
    if not ok:
        report(seat, mode, f"{msg}: suffix requires text, got {type(got).__name__}")
        return
    if not text.endswith(suffix):
        report(seat, mode, f"{msg}: {text!r} does not end with {suffix!r}")


def matches(seat: Seat, mode: Mode, got: Any, pattern: str, msg: str) -> None:
    """Report when got does not match the regular expression.

    A pattern that does not compile is a failure rather than an
    exception: a test with a broken pattern has established nothing and
    should say so where every other failure is reported.
    """
    seat.helper()
    text, ok = _text_of(got)
    if not ok:
        report(
            seat,
            mode,
            f"{msg}: pattern matching requires text, got {type(got).__name__}",
        )
        return

    try:
        compiled = re.compile(pattern)
    except re.error as err:
        report(seat, mode, f"{msg}: pattern {pattern!r} does not compile: {err}")
        return

    if compiled.search(text) is None:
        report(seat, mode, f"{msg}: {text!r} does not match {pattern!r}")


def _number_of(got: Any) -> tuple[float, bool]:
    """Read a value as a number, refusing bool.

    ``bool`` subclasses ``int``, so a bare isinstance check would let
    True through as 1, which the standard's no-coercion rule forbids.
    """
    if isinstance(got, bool):
        return 0.0, False
    if isinstance(got, (int, float)):
        return float(got), True
    return 0.0, False


def close_to(
    seat: Seat, mode: Mode, got: Any, want: float, tolerance: float, msg: str
) -> None:
    """Report when got is further than tolerance from want.

    A NaN anywhere fails. Every comparison against NaN is false, so a
    bare check would pass one rather than reject it.
    """
    seat.helper()
    number, ok = _number_of(got)
    if not ok:
        report(
            seat, mode, f"{msg}: tolerance requires a number, got {type(got).__name__}"
        )
        return

    difference = abs(number - want) if not math.isnan(number - want) else math.nan
    if math.isnan(difference) or math.isnan(tolerance):
        report(
            seat,
            mode,
            f"{msg}: {number} is not within {tolerance} of {want}: "
            "NaN is outside every tolerance",
        )
        return
    if difference > tolerance:
        report(seat, mode, f"{msg}: {number} is not within {tolerance} of {want}")


def in_range(
    seat: Seat, mode: Mode, got: Any, low: float, high: float, msg: str
) -> None:
    """Report when got falls outside the closed interval."""
    seat.helper()
    if low > high:
        report(seat, mode, f"{msg}: empty range [{low}, {high}]")
        return

    number, ok = _number_of(got)
    if not ok:
        report(seat, mode, f"{msg}: range requires a number, got {type(got).__name__}")
        return

    if math.isnan(number):
        report(seat, mode, f"{msg}: NaN is not in [{low}, {high}]")
        return
    if number < low or number > high:
        report(seat, mode, f"{msg}: {number} is not in [{low}, {high}]")
