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
from dokimi_assert._matcher.seat import Mode, Seat, report_failure


def equal(
    seat: Seat, mode: Mode, got: Any, want: Any, msg: str, *options: Option
) -> None:
    """Report when got and want differ. See the comparison rules.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        want: The value it is supposed to produce.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone.
    """
    __tracebackhide__ = True
    seat.helper()
    if not _equal(got, want, settings(options)):
        report_failure(seat, mode, "equal", msg, {"want": want, "got": got})


def not_equal(
    seat: Seat, mode: Mode, got: Any, want: Any, msg: str, *options: Option
) -> None:
    """Report when got and want are equal.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        want: The value it is supposed to produce.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone.
    """
    __tracebackhide__ = True
    seat.helper()
    if _equal(got, want, settings(options)):
        report_failure(seat, mode, "not-equal", msg, {"got": got})


def is_true(seat: Seat, mode: Mode, condition: bool, msg: str) -> None:
    """Report when the condition does not hold.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        condition: The condition being stated.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if not condition:
        report_failure(seat, mode, "true", msg)


def is_false(seat: Seat, mode: Mode, condition: bool, msg: str) -> None:
    """Report when the condition holds.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        condition: The condition being stated.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if condition:
        report_failure(seat, mode, "false", msg)


def is_none(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got is not None.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if got is not None:
        report_failure(seat, mode, "nil", msg, {"got": got})


def is_not_none(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got is None.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if got is None:
        report_failure(seat, mode, "not-nil", msg)


def length(seat: Seat, mode: Mode, got: Any, want: int, msg: str) -> None:
    """Report when got does not hold want items.

    Anything without a length is itself the failure rather than an
    exception, so a wrong type reads like every other failure.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        want: The value it is supposed to produce.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if not isinstance(got, Sized):
        report_failure(seat, mode, "length", msg, {"want": want, "got": got})
        return
    if len(got) != want:
        report_failure(seat, mode, "length", msg, {"want": want, "got": len(got)})


def is_empty(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got holds anything.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if not isinstance(got, Sized):
        report_failure(seat, mode, "empty", msg, {"length": got})
        return
    if len(got) != 0:
        report_failure(seat, mode, "empty", msg, {"length": len(got)})


def is_not_empty(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got holds nothing.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if not isinstance(got, Sized):
        report_failure(seat, mode, "not-empty", msg)
        return
    if len(got) == 0:
        report_failure(seat, mode, "not-empty", msg)


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
    """Report when haystack does not hold needle.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        haystack: The container or text to search.
        needle: The element, key or substring to look for.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone.
    """
    __tracebackhide__ = True
    seat.helper()
    found, supported = _holds(haystack, needle, settings(options))
    if not supported:
        report_failure(
            seat, mode, "contains", msg, {"haystack": haystack, "needle": needle}
        )
        return
    if not found:
        report_failure(
            seat, mode, "contains", msg, {"haystack": haystack, "needle": needle}
        )


def not_contains(
    seat: Seat, mode: Mode, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Report when haystack holds needle.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        haystack: The container or text to search.
        needle: The element, key or substring to look for.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone.
    """
    __tracebackhide__ = True
    seat.helper()
    found, supported = _holds(haystack, needle, settings(options))
    if not supported:
        report_failure(
            seat, mode, "not-contains", msg, {"haystack": haystack, "needle": needle}
        )
        return
    if found:
        report_failure(
            seat, mode, "not-contains", msg, {"haystack": haystack, "needle": needle}
        )


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

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        needles: The substrings, in the order they must appear.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    text, ok = _text_of(got)
    if not ok:
        report_failure(
            seat,
            mode,
            "contains-in-order",
            msg,
            {"haystack": got, "needle": "", "index": 0},
        )
        return

    cursor = 0
    for index, needle in enumerate(needles):
        at = text.find(needle, cursor)
        if at < 0:
            report_failure(
                seat,
                mode,
                "contains-in-order",
                msg,
                {"haystack": text, "needle": needle, "index": index},
            )
            return
        cursor = at + len(needle)


def has_prefix(seat: Seat, mode: Mode, got: Any, prefix: str, msg: str) -> None:
    """Report when got does not start with prefix.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        prefix: What the text must start with.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    text, ok = _text_of(got)
    if not ok:
        report_failure(seat, mode, "has-prefix", msg, {"got": got, "prefix": prefix})
        return
    if not text.startswith(prefix):
        report_failure(seat, mode, "has-prefix", msg, {"got": text, "prefix": prefix})


def has_suffix(seat: Seat, mode: Mode, got: Any, suffix: str, msg: str) -> None:
    """Report when got does not end with suffix.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        suffix: What the text must end with.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    text, ok = _text_of(got)
    if not ok:
        report_failure(seat, mode, "has-suffix", msg, {"got": got, "suffix": suffix})
        return
    if not text.endswith(suffix):
        report_failure(seat, mode, "has-suffix", msg, {"got": text, "suffix": suffix})


def matches(seat: Seat, mode: Mode, got: Any, pattern: str, msg: str) -> None:
    """Report when got does not match the regular expression.

    A pattern that does not compile is a failure rather than an
    exception: a test with a broken pattern has established nothing and
    should say so where every other failure is reported.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        pattern: A Python regular expression.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    text, ok = _text_of(got)
    if not ok:
        report_failure(seat, mode, "matches", msg, {"got": got, "pattern": pattern})
        return

    try:
        compiled = re.compile(pattern)
    except re.error:
        report_failure(seat, mode, "matches", msg, {"got": got, "pattern": pattern})
        return

    if compiled.search(text) is None:
        report_failure(seat, mode, "matches", msg, {"got": text, "pattern": pattern})


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

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        want: The value it is supposed to produce.
        tolerance: The largest acceptable absolute difference.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    number, ok = _number_of(got)
    if not ok:
        report_failure(
            seat,
            mode,
            "close-to",
            msg,
            {"got": got, "want": want, "tolerance": tolerance},
        )
        return

    difference = abs(number - want) if not math.isnan(number - want) else math.nan
    if math.isnan(difference) or math.isnan(tolerance):
        report_failure(
            seat,
            mode,
            "close-to",
            msg,
            {"got": got, "want": want, "tolerance": tolerance},
        )
        return
    if difference > tolerance:
        report_failure(
            seat,
            mode,
            "close-to",
            msg,
            {"got": got, "want": want, "tolerance": tolerance},
        )


def in_range(
    seat: Seat, mode: Mode, got: Any, low: float, high: float, msg: str
) -> None:
    """Report when got falls outside the closed interval.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        got: The value produced by the code under test.
        low: The lowest acceptable value.
        high: The highest acceptable value.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if low > high:
        report_failure(
            seat, mode, "in-range", msg, {"got": got, "low": low, "high": high}
        )
        return

    number, ok = _number_of(got)
    if not ok:
        report_failure(
            seat, mode, "in-range", msg, {"got": got, "low": low, "high": high}
        )
        return

    if math.isnan(number):
        report_failure(
            seat, mode, "in-range", msg, {"got": got, "low": low, "high": high}
        )
        return
    if number < low or number > high:
        report_failure(
            seat, mode, "in-range", msg, {"got": got, "low": low, "high": high}
        )
