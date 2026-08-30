"""Assertions that stop the test at the first failure.

Every assertion takes a seat first and a message last. The message
states the contract under test and is the first line of the failure, so
a failure says what was supposed to be true rather than only what was
observed.

    from dokimi_assert import check

    check.equal(got, want, "Get returns the stored item")

:mod:`dokimi_assert.expect` carries the same assertions under the same names
and runs the same comparison. Only what happens on failure differs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TypeVar

from dokimi_assert._matcher import behaviour, errors, order, value, waiting
from dokimi_assert._matcher import raises as raising
from dokimi_assert._matcher.option import Option
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert.rejects import rejects

_E = TypeVar("_E", bound=BaseException)

__all__ = [
    "close_to",
    "completes_within",
    "contains",
    "contains_in_order",
    "does_not_raise",
    "equal",
    "error_as",
    "error_is",
    "error_is_not",
    "eventually",
    "eventually_true",
    "has_error",
    "has_prefix",
    "has_suffix",
    "honours_cancellation",
    "honours_deadline",
    "in_range",
    "is_empty",
    "is_false",
    "is_none",
    "is_not_empty",
    "is_not_none",
    "is_pure",
    "is_true",
    "length",
    "matches",
    "no_error",
    "no_task_leaks",
    "none_handle_safe",
    "not_contains",
    "not_equal",
    "pairwise",
    "raises",
    "rejects",
]

_MODE = Mode.FATAL


def equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Stop the test when got and want differ.

    Types must match exactly: 0 does not equal False, and 1 does not
    equal 1.0. An absent collection does not equal an empty one; pass
    ``equate_empty()`` where that difference does not matter.
    """
    __tracebackhide__ = True
    seat.helper()
    value.equal(seat, _MODE, got, want, msg, *options)


def not_equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Stop the test when got and want are equal."""
    __tracebackhide__ = True
    seat.helper()
    value.not_equal(seat, _MODE, got, want, msg, *options)


def is_true(seat: Seat, condition: bool, msg: str) -> None:
    """Stop the test when the condition does not hold."""
    __tracebackhide__ = True
    seat.helper()
    value.is_true(seat, _MODE, condition, msg)


def is_false(seat: Seat, condition: bool, msg: str) -> None:
    """Stop the test when the condition holds."""
    __tracebackhide__ = True
    seat.helper()
    value.is_false(seat, _MODE, condition, msg)


def is_none(seat: Seat, got: Any, msg: str) -> None:
    """Stop the test when got is not None."""
    __tracebackhide__ = True
    seat.helper()
    value.is_none(seat, _MODE, got, msg)


def is_not_none(seat: Seat, got: Any, msg: str) -> None:
    """Stop the test when got is None."""
    __tracebackhide__ = True
    seat.helper()
    value.is_not_none(seat, _MODE, got, msg)


def length(seat: Seat, got: Any, want: int, msg: str) -> None:
    """Stop the test when got does not hold want items.

    A value with no length is itself the failure rather than an
    exception, so a wrong type reads like every other failure.
    """
    __tracebackhide__ = True
    seat.helper()
    value.length(seat, _MODE, got, want, msg)


def is_empty(seat: Seat, got: Any, msg: str) -> None:
    """Stop the test when got holds anything."""
    __tracebackhide__ = True
    seat.helper()
    value.is_empty(seat, _MODE, got, msg)


def is_not_empty(seat: Seat, got: Any, msg: str) -> None:
    """Stop the test when got holds nothing."""
    __tracebackhide__ = True
    seat.helper()
    value.is_not_empty(seat, _MODE, got, msg)


def contains(
    seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Stop the test when haystack does not hold needle.

    Text holds a substring, a sequence holds an element, and a mapping
    holds a key.
    """
    __tracebackhide__ = True
    seat.helper()
    value.contains(seat, _MODE, haystack, needle, msg, *options)


def not_contains(
    seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Stop the test when haystack holds needle."""
    __tracebackhide__ = True
    seat.helper()
    value.not_contains(seat, _MODE, haystack, needle, msg, *options)


def contains_in_order(seat: Seat, got: Any, needles: Sequence[str], msg: str) -> None:
    """Stop the test when got does not hold every needle in order.

    Each needle must appear after the previous one's match ends, which
    is what catches a formatter that reorders its fields.
    """
    __tracebackhide__ = True
    seat.helper()
    value.contains_in_order(seat, _MODE, got, needles, msg)


def has_prefix(seat: Seat, got: Any, prefix: str, msg: str) -> None:
    """Stop the test when got does not start with prefix."""
    __tracebackhide__ = True
    seat.helper()
    value.has_prefix(seat, _MODE, got, prefix, msg)


def has_suffix(seat: Seat, got: Any, suffix: str, msg: str) -> None:
    """Stop the test when got does not end with suffix."""
    __tracebackhide__ = True
    seat.helper()
    value.has_suffix(seat, _MODE, got, suffix, msg)


def matches(seat: Seat, got: Any, pattern: str, msg: str) -> None:
    """Stop the test when got does not match the pattern.

    The pattern matches anywhere in got; anchor it to require the whole
    value. A pattern that does not compile is a failure rather than an
    exception.
    """
    __tracebackhide__ = True
    seat.helper()
    value.matches(seat, _MODE, got, pattern, msg)


def close_to(seat: Seat, got: Any, want: float, tolerance: float, msg: str) -> None:
    """Stop the test when got is further than tolerance from want.

    A NaN anywhere fails, because no tolerance contains one.
    """
    __tracebackhide__ = True
    seat.helper()
    value.close_to(seat, _MODE, got, want, tolerance, msg)


def in_range(seat: Seat, got: Any, low: float, high: float, msg: str) -> None:
    """Stop the test when got falls outside the closed interval."""
    __tracebackhide__ = True
    seat.helper()
    value.in_range(seat, _MODE, got, low, high, msg)


def no_error(seat: Seat, exc: BaseException | None, msg: str) -> None:
    """Stop the test when an exception was raised."""
    __tracebackhide__ = True
    seat.helper()
    errors.no_error(seat, _MODE, exc, msg)


def has_error(seat: Seat, exc: BaseException | None, msg: str) -> None:
    """Stop the test when nothing was raised."""
    __tracebackhide__ = True
    seat.helper()
    errors.has_error(seat, _MODE, exc, msg)


def error_is(
    seat: Seat, exc: BaseException | None, target: BaseException, msg: str
) -> None:
    """Stop the test when target is not exc or one of its causes."""
    __tracebackhide__ = True
    seat.helper()
    errors.error_is(seat, _MODE, exc, target, msg)


def error_is_not(
    seat: Seat, exc: BaseException | None, target: BaseException, msg: str
) -> None:
    """Stop the test when target is exc or one of its causes."""
    __tracebackhide__ = True
    seat.helper()
    errors.error_is_not(seat, _MODE, exc, target, msg)


def error_as(
    seat: Seat, exc: BaseException | None, want: type[_E], msg: str
) -> _E | None:
    """Return the first exception of type want in the chain.

    Stop the test when the chain holds none.
    """
    __tracebackhide__ = True
    seat.helper()
    return errors.error_as(seat, _MODE, exc, want, msg)


def raises(seat: Seat, fn: Callable[[], Any], msg: str) -> BaseException | None:
    """Run fn and return what it raised.

    Stop the test when fn returns without raising.
    """
    __tracebackhide__ = True
    seat.helper()
    return raising.raises(seat, _MODE, fn, msg)


def does_not_raise(seat: Seat, fn: Callable[[], Any], msg: str) -> None:
    """Run fn and stop when it raises."""
    __tracebackhide__ = True
    seat.helper()
    raising.does_not_raise(seat, _MODE, fn, msg)


def pairwise(
    seat: Seat,
    items: Sequence[Any],
    predicate: Callable[[Any, Any], bool],
    msg: str,
) -> None:
    """Stop the test when an adjacent pair fails the predicate."""
    __tracebackhide__ = True
    seat.helper()
    order.pairwise(seat, _MODE, items, predicate, msg)


def honours_cancellation(
    seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Stop the test when a cancelled subject does not raise CancelledError."""
    __tracebackhide__ = True
    seat.helper()
    behaviour.honours_cancellation(seat, _MODE, fn, msg)


def honours_deadline(seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str) -> None:
    """Stop the test when a subject given no time does not time out."""
    __tracebackhide__ = True
    seat.helper()
    behaviour.honours_deadline(seat, _MODE, fn, msg)


def completes_within(
    seat: Seat, within: float, fn: Callable[[], Any], msg: str
) -> None:
    """Stop the test when fn takes longer than within seconds."""
    __tracebackhide__ = True
    seat.helper()
    behaviour.completes_within(seat, _MODE, within, fn, msg)


def is_pure(
    seat: Seat,
    observe: Callable[[], Any],
    fn: Callable[[], Any],
    msg: str,
    *options: Option,
) -> None:
    """Stop the test when observed state changes across a call."""
    __tracebackhide__ = True
    seat.helper()
    behaviour.is_pure(seat, _MODE, observe, fn, msg, *options)


def none_handle_safe(seat: Seat, fn: Callable[[Any], Any], msg: str) -> None:
    """Stop the test when a subject given None where a handle goes crashes."""
    __tracebackhide__ = True
    seat.helper()
    behaviour.none_handle_safe(seat, _MODE, fn, msg)


def eventually(
    seat: Seat,
    timeout: float,
    interval: float,
    body: Callable[[Any], None],
    msg: str,
) -> None:
    """Run body every interval until it passes or timeout expires.

    Stop the test with the last attempt's failure when it never passes.
    """
    __tracebackhide__ = True
    seat.helper()
    waiting.eventually(seat, _MODE, timeout, interval, body, msg)


def eventually_true(
    seat: Seat, timeout: float, predicate: Callable[[], bool], msg: str
) -> None:
    """Call predicate with backoff until true or timeout expires.

    Stop the test when it never becomes true.
    """
    __tracebackhide__ = True
    seat.helper()
    waiting.eventually_true(seat, _MODE, timeout, predicate, msg)


def no_task_leaks(seat: Seat, msg: str) -> Callable[[], None]:
    """Record the running tasks and return a check for the leftovers.

    The check stops when a task started after this call is still
    running.
    """
    __tracebackhide__ = True
    seat.helper()
    return waiting.no_task_leaks(seat, _MODE, msg)
