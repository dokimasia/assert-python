"""Assertions about a callable raising."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dokimi_assert._matcher.seat import Mode, Seat, report_failure


def raises(
    seat: Seat, mode: Mode, fn: Callable[[], Any], msg: str
) -> BaseException | None:
    """Run fn and report when it returns without raising.

    Returns what fn raised, so a caller can assert on the reason as
    well as the fact. Returns None when fn returned.

    KeyboardInterrupt and SystemExit are not caught: those say
    the run is ending, and reporting one as the raise a test asked for
    would swallow it.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        fn: The callable under test.
        msg: The contract under test. It is the first line of the failure.

    Returns:
        What fn raised, or None when it returned.
    """
    __tracebackhide__ = True
    seat.helper()
    try:
        fn()
    except Exception as caught:
        return caught
    report_failure(seat, mode, "throws", msg)
    return None


def does_not_raise(seat: Seat, mode: Mode, fn: Callable[[], Any], msg: str) -> None:
    """Run fn and report when it raises, naming what it raised.

    The exception is caught rather than allowed to propagate, so one
    misbehaving subject fails its test instead of ending the run.

    This is the assertion for a call that may legitimately fail:
    returning an error is fine, crashing is not.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        fn: The callable under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    try:
        fn()
    except Exception as caught:
        report_failure(seat, mode, "not-throws", msg, {"got": caught})
