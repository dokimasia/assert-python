# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertions about the equality, truth, size, text and number of a value.

Each takes a seat and a mode, so both surfaces share one implementation. A
value of the wrong type fails like any other value. A mistaken argument then
ends with a failure record and not with an exception.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence, Sized
from collections.abc import Set as AbstractSet
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.compare import contains_element
from dokimi_assert._matcher.compare import equal as _equal
from dokimi_assert._matcher.option import Option, settings
from dokimi_assert._matcher.verdict import fail, pass_
from dokimi_assert._pattern.match import compile_pattern
from dokimi_assert._pattern.parse import PatternError

if TYPE_CHECKING:
    from dokimi_assert._matcher.seat import Mode, Seat

__all__ = [
    "close_to",
    "contains",
    "contains_in_order",
    "equal",
    "has_prefix",
    "has_suffix",
    "in_range",
    "is_empty",
    "is_false",
    "is_none",
    "is_not_empty",
    "is_not_none",
    "is_true",
    "length",
    "length_of",
    "matches",
    "not_contains",
    "not_equal",
    "number_of",
]


def length_of(value: object) -> int | None:
    """Return the number of items of a value that has a length.

    Args:
        value: The value.

    Returns:
        The number of the Unicode scalar values of a str, of the bytes of
        bytes and of a bytearray, and of the items of any other sized value.
        It is None for a str with a surrogate code point, for None and for a
        value without a length.
    """
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            return None
        return len(value)
    if isinstance(value, Sized):
        return len(value)
    return None


def number_of(value: object) -> int | float | None:
    """Return value when it is a number, and None for any other value.

    A bool is not a number, although bool is a subclass of int.

    Args:
        value: The value.

    Returns:
        An int or a float, or None.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def equal(
    seat: Seat, mode: Mode, got: Any, want: Any, msg: str, *options: Option
) -> None:
    """Report when got and want differ.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The value that the code under test produced.
        want: The value that it is supposed to produce.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    if not _equal(got, want, settings(options)):
        fail(seat, mode, "equal", msg, {"want": want, "got": got})
        return
    pass_(seat, mode, "equal", msg)


def not_equal(
    seat: Seat, mode: Mode, got: Any, want: Any, msg: str, *options: Option
) -> None:
    """Report when got and want are equal.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The value that the code under test produced.
        want: The value that it must not equal.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    if _equal(got, want, settings(options)):
        fail(seat, mode, "not-equal", msg, {"got": got})
        return
    pass_(seat, mode, "not-equal", msg)


def is_true(seat: Seat, mode: Mode, condition: object, msg: str) -> None:
    """Report when the condition is not true.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        condition: The condition.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if not condition:
        fail(seat, mode, "true", msg)
        return
    pass_(seat, mode, "true", msg)


def is_false(seat: Seat, mode: Mode, condition: object, msg: str) -> None:
    """Report when the condition is true.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        condition: The condition.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if condition:
        fail(seat, mode, "false", msg)
        return
    pass_(seat, mode, "false", msg)


def is_none(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got is not None.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The value that the code under test produced.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if got is not None:
        fail(seat, mode, "nil", msg, {"got": got})
        return
    pass_(seat, mode, "nil", msg)


def is_not_none(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got is None.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The value that the code under test produced.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if got is None:
        fail(seat, mode, "not-nil", msg)
        return
    pass_(seat, mode, "not-nil", msg)


def length(seat: Seat, mode: Mode, got: Any, want: int, msg: str) -> None:
    """Report when got does not have want items.

    For a value without a length, got is None.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The value that the code under test produced.
        want: The number of items that got must have.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    size = length_of(got)
    if size != want:
        fail(seat, mode, "length", msg, {"want": want, "got": size})
        return
    pass_(seat, mode, "length", msg)


def is_empty(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got has an item, or does not have a length.

    The detail has got and length. length is None for a value without a
    length.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The value that the code under test produced.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    size = length_of(got)
    if size != 0:
        fail(seat, mode, "empty", msg, {"got": got, "length": size})
        return
    pass_(seat, mode, "empty", msg)


def is_not_empty(seat: Seat, mode: Mode, got: Any, msg: str) -> None:
    """Report when got does not have an item.

    A value without a length fails too.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The value that the code under test produced.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if not length_of(got):
        fail(seat, mode, "not-empty", msg, {"got": got})
        return
    pass_(seat, mode, "not-empty", msg)


def _contained(haystack: Any, needle: Any, options: tuple[Option, ...]) -> bool | None:
    """Report whether haystack contains needle.

    A str contains a substring, bytes and a bytearray contain a byte string
    or a byte, a mapping contains a key, and a sequence or a set contains an
    element. Keys and elements are compared by the rules of equal.

    Returns:
        True when haystack contains needle, and False when it does not. It is
        None when the question does not apply to haystack.
    """
    if isinstance(haystack, str):
        return needle in haystack if isinstance(needle, str) else None
    if isinstance(haystack, (bytes, bytearray)):
        if isinstance(needle, (bytes, bytearray)) or (
            isinstance(needle, int) and not isinstance(needle, bool)
        ):
            return needle in haystack
        return None
    if isinstance(haystack, Mapping):
        return contains_element(haystack.keys(), needle, settings(options))
    if isinstance(haystack, (Sequence, AbstractSet)):
        return contains_element(haystack, needle, settings(options))
    return None


def contains(
    seat: Seat, mode: Mode, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Report when haystack does not contain needle.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        haystack: The text or the collection.
        needle: The substring, the element or the key.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    if not _contained(haystack, needle, options):
        fail(seat, mode, "contains", msg, {"haystack": haystack, "needle": needle})
        return
    pass_(seat, mode, "contains", msg)


def not_contains(
    seat: Seat, mode: Mode, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Report when haystack contains needle, or the question does not apply to it.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        haystack: The text or the collection.
        needle: The substring, the element or the key.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    if _contained(haystack, needle, options) is not False:
        fail(seat, mode, "not-contains", msg, {"haystack": haystack, "needle": needle})
        return
    pass_(seat, mode, "not-contains", msg)


def contains_in_order(
    seat: Seat, mode: Mode, got: Any, needles: Sequence[str], msg: str
) -> None:
    """Report when got does not contain the needles in order.

    Each needle must start after the end of the match of the needle before
    it.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The text.
        needles: The substrings in the order in which they must appear.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if not isinstance(got, str):
        detail = {"haystack": got, "needle": "", "index": 0}
        fail(seat, mode, "contains-in-order", msg, detail)
        return
    cursor = 0
    for index, needle in enumerate(needles):
        at = got.find(needle, cursor)
        if at < 0:
            detail = {"haystack": got, "needle": needle, "index": index}
            fail(seat, mode, "contains-in-order", msg, detail)
            return
        cursor = at + len(needle)
    pass_(seat, mode, "contains-in-order", msg)


def has_prefix(seat: Seat, mode: Mode, got: Any, prefix: str, msg: str) -> None:
    """Report when got is not a str that starts with prefix.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The text.
        prefix: The start that got must have.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if not isinstance(got, str) or not got.startswith(prefix):
        fail(seat, mode, "has-prefix", msg, {"got": got, "prefix": prefix})
        return
    pass_(seat, mode, "has-prefix", msg)


def has_suffix(seat: Seat, mode: Mode, got: Any, suffix: str, msg: str) -> None:
    """Report when got is not a str that ends with suffix.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The text.
        suffix: The end that got must have.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if not isinstance(got, str) or not got.endswith(suffix):
        fail(seat, mode, "has-suffix", msg, {"got": got, "suffix": suffix})
        return
    pass_(seat, mode, "has-suffix", msg)


def matches(seat: Seat, mode: Mode, got: Any, pattern: str, msg: str) -> None:
    """Report when got is not a str that a pattern of the portable subset matches.

    The pattern matches anywhere in the text. A pattern outside the subset
    fails, and reason is the text with which the parser of the subset
    refuses it. reason is None for a pattern inside the subset.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The text.
        pattern: A pattern of the portable subset.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    reason: str | None = None
    found = False
    try:
        expression = compile_pattern(pattern)
    except PatternError as error:
        reason = str(error)
    else:
        found = isinstance(got, str) and expression.search(got) is not None
    if not found:
        fail(
            seat,
            mode,
            "matches",
            msg,
            {"got": got, "pattern": pattern, "reason": reason},
        )
        return
    pass_(seat, mode, "matches", msg)


def close_to(
    seat: Seat, mode: Mode, got: Any, want: float, tolerance: float, msg: str
) -> None:
    """Report when got is not a number within tolerance of want.

    A NaN fails as got, as want and as the tolerance, because a tolerance
    does not contain a NaN. Two equal infinities fail, because their
    difference is NaN.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The number.
        want: The number that got must be near.
        tolerance: The largest absolute difference that passes.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    value = number_of(got)
    close = False
    if value is not None:
        try:
            difference = abs(value - want)
        except OverflowError:
            difference = math.inf
        close = difference <= tolerance
    if not close:
        detail = {"got": got, "want": want, "tolerance": tolerance}
        fail(seat, mode, "close-to", msg, detail)
        return
    pass_(seat, mode, "close-to", msg)


def in_range(
    seat: Seat, mode: Mode, got: Any, low: float, high: float, msg: str
) -> None:
    """Report when got is not a number in the closed interval from low to high.

    A NaN is not in any range. When low is above high, or when a bound is
    NaN, the range does not contain a number.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The number.
        low: The lowest number of the range.
        high: The highest number of the range.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    value = number_of(got)
    if value is None or not low <= value <= high:
        fail(seat, mode, "in-range", msg, {"got": got, "low": low, "high": high})
        return
    pass_(seat, mode, "in-range", msg)
