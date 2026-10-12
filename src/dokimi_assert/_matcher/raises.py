"""The assertions about a callable that raises.

Both take a callable and not a value, because the exception has to be
raised inside the assertion for the assertion to catch it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dokimi_assert._matcher.loop import close_awaitable
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._matcher.verdict import fail, pass_

__all__ = ["does_not_raise", "raises"]


def raises(seat: Seat, mode: Mode, fn: Callable[[], Any], msg: str) -> Exception | None:
    """Report when fn returns without raising an exception.

    The assertion does not catch KeyboardInterrupt or SystemExit, because
    they end the run. A call of a coroutine function returns a coroutine and
    does not raise. The assertion closes the coroutine and fails.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        fn: The callable under test.
        msg: The contract under test.

    Returns:
        The exception that fn raised, or None when fn returned.
    """
    __tracebackhide__ = True
    seat.helper()
    try:
        result = fn()
    except Exception as error:
        pass_(seat, mode, "throws", msg)
        return error
    close_awaitable(result)
    fail(seat, mode, "throws", msg)
    return None


def does_not_raise(seat: Seat, mode: Mode, fn: Callable[[], Any], msg: str) -> None:
    """Report when fn raises an exception.

    The failure has the exception as got.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        fn: The callable under test.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    try:
        result = fn()
    except Exception as error:
        fail(seat, mode, "not-throws", msg, {"got": error})
        return
    close_awaitable(result)
    pass_(seat, mode, "not-throws", msg)
