"""Where a matcher sends a failure.

A matcher never raises directly and never calls a test framework. It
reports through a seat, so one comparison serves a real test, a
recorder and a harness that collects failures for a report.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable


@runtime_checkable
class Seat(Protocol):
    """The failure surface a matcher reports through."""

    def helper(self) -> None:
        """Mark the calling frame as a helper.

        A failure is then attributed to the caller's line rather than
        to the matcher. Under pytest this hides the frame from the
        traceback.
        """

    def fail(self, message: str) -> None:
        """Record a failure and stop the test.

        This may not return.

        Args:
            message: The failure text, already formatted.
        """

    def record(self, message: str) -> None:
        """Record a failure and return, so the test carries on.

        Args:
            message: The failure text, already formatted.
        """


class Mode(Enum):
    """Which of a seat's two failure methods a matcher uses."""

    FATAL = "fatal"
    """Report through fail, stopping the test at the first failure."""

    SOFT = "soft"
    """Report through record, so the test runs on."""


def report(seat: Seat, mode: Mode, message: str) -> None:
    """Mark the calling frame and send one failure to seat.

    This does not decide whether anything failed. A matcher calls it
    only once its own comparison has failed, so every call produces
    exactly one reported failure. Under FATAL it may not return.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        message: The failure text, already formatted.
    """
    __tracebackhide__ = True
    seat.helper()
    if mode is Mode.SOFT:
        seat.record(message)
        return
    seat.fail(message)
