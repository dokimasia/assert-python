# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertions about an error value.

A failure of a call is a value that the call returns or an exception that
it raises. A Python call raises, so an error here is an exception that the
caller caught, or None when the call did not raise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from dokimi_assert._matcher.verdict import fail, pass_

if TYPE_CHECKING:
    from dokimi_assert._matcher.seat import Mode, Seat

__all__ = [
    "chain",
    "error_as",
    "error_is",
    "error_is_not",
    "has_error",
    "matches_target",
    "no_error",
]

_E = TypeVar("_E", bound=BaseException)


def chain(error: BaseException | None) -> list[BaseException]:
    """Return error and every exception that it wraps.

    The list starts with error. The walk follows __cause__ first, and then
    __context__. A raise with from sets __cause__. Python sets __context__
    for an exception that is raised while another one is handled. The walk
    stops at a cycle.

    Args:
        error: The error, or None.

    Returns:
        The chain, or an empty list for None.
    """
    out: list[BaseException] = []
    seen: set[int] = set()
    current = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        out.append(current)
        current = current.__cause__ or current.__context__
    return out


def matches_target(error: BaseException | None, target: object) -> bool:
    """Report whether target matches error or an exception that it wraps.

    An exception matches the same object, and a class matches each of its
    instances.

    Args:
        error: The error, or None.
        target: An exception or a class of exceptions.

    Returns:
        True when an exception of the chain matches target.
    """
    for link in chain(error):
        if link is target:
            return True
        if isinstance(target, type) and isinstance(link, target):
            return True
    return False


def no_error(seat: Seat, mode: Mode, error: BaseException | None, msg: str) -> None:
    """Report when an error is present.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        error: The error, or None when there was none.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if error is not None:
        fail(seat, mode, "err-absent", msg, {"got": error})
        return
    pass_(seat, mode, "err-absent", msg)


def has_error(seat: Seat, mode: Mode, error: BaseException | None, msg: str) -> None:
    """Report when an error is not present.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        error: The error, or None when there was none.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if error is None:
        fail(seat, mode, "err-present", msg)
        return
    pass_(seat, mode, "err-present", msg)


def error_is(
    seat: Seat, mode: Mode, error: BaseException | None, target: object, msg: str
) -> None:
    """Report when target matches neither error nor an exception that it wraps.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        error: The error, or None.
        target: The sentinel exception, or a class of exceptions.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if not matches_target(error, target):
        fail(seat, mode, "err-is", msg, {"want": target, "got": error})
        return
    pass_(seat, mode, "err-is", msg)


def error_is_not(
    seat: Seat, mode: Mode, error: BaseException | None, target: object, msg: str
) -> None:
    """Report when target matches error or an exception that it wraps.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        error: The error, or None.
        target: The sentinel exception, or a class of exceptions.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    if matches_target(error, target):
        fail(seat, mode, "err-is-not", msg, {"got": error})
        return
    pass_(seat, mode, "err-is-not", msg)


def error_as(
    seat: Seat, mode: Mode, error: BaseException | None, want: type[_E], msg: str
) -> _E | None:
    """Return the first exception of the class want in the chain of error.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        error: The error, or None.
        want: The class of exceptions.
        msg: The contract under test.

    Returns:
        The exception, or None when the chain does not have one. The
        assertion then fails, and a test on the recording surface continues
        with None.
    """
    __tracebackhide__ = True
    seat.helper()
    for link in chain(error):
        if isinstance(link, want):
            pass_(seat, mode, "err-as", msg)
            return link
    fail(seat, mode, "err-as", msg, {"want": want, "got": error})
    return None
