"""The interface through which every assertion reports a failure.

An assertion does not call a test runner, and it does not raise on its own.
It reports to the seat that the caller passes to it. One comparison then
works in a pytest test, in a recorder, and in a harness that collects failures
for a report.
"""

from __future__ import annotations

import weakref
from collections.abc import Callable, Sequence
from enum import Enum
from typing import Protocol, TypeGuard, runtime_checkable

from dokimi_assert.clock import Clock, System
from dokimi_assert.failure import Failure

__all__ = [
    "FaultReporter",
    "Mode",
    "Reporter",
    "Seat",
    "clock_of",
    "name_test",
    "named_test",
    "report",
    "takes_faults",
    "takes_records",
]


@runtime_checkable
class Seat(Protocol):
    """The object through which an assertion reports a failure.

    A seat can also have three more methods. report(failure, aborting)
    receives the failure record in place of its sentence.
    report_fault(fault, ending) receives a fault as the exception it is.
    clock() returns the clock that assertions read.
    """

    def helper(self) -> None:
        """Mark the calling frame as a helper of the test.

        The failure then has the line of the caller and not the line of the
        assertion. Under pytest, the traceback hides the frame.
        """

    def fail(self, message: str) -> None:
        """Record a failure and stop the test.

        The method might not return.

        Args:
            message: The text of the failure.
        """

    def record(self, message: str) -> None:
        """Record a failure and return, so that the test continues.

        Args:
            message: The text of the failure.
        """


class Mode(Enum):
    """The failure method of a seat that an assertion uses."""

    FATAL = "fatal"
    """The assertion reports through fail. fail stops the test."""

    SOFT = "soft"
    """The assertion reports through record, and the test continues."""


def report(seat: Seat, mode: Mode, message: str) -> None:
    """Send one sentence to seat under mode.

    Under Mode.SOFT it sends the sentence through record. Under Mode.FATAL it
    sends the sentence through fail, and it might not return.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at the failure, or SOFT to record it.
        message: The text of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if mode is Mode.SOFT:
        seat.record(message)
        return
    seat.fail(message)


class Reporter(Protocol):
    """A seat that takes the failure record in place of its sentence."""

    def report(self, failure: Failure, aborting: bool) -> None:
        """Receive one failure record.

        Args:
            failure: The record of the failing call.
            aborting: When True, the failure comes from the aborting surface.
                When False, it comes from the recording surface.
        """


def takes_records(seat: object) -> TypeGuard[Reporter]:
    """Report whether seat takes failure records.

    Args:
        seat: The seat of a call.

    Returns:
        True when the seat has a callable member report.
    """
    return callable(getattr(seat, "report", None))


class FaultReporter(Protocol):
    """A seat that takes a fault as the exception it is."""

    def report_fault(self, fault: BaseException, ending: bool) -> None:
        """Receive one fault.

        Args:
            fault: The fault.
            ending: When True, the fault ends the call. When False, the call
                notes the fault and runs on past it.
        """


def takes_faults(seat: object) -> TypeGuard[FaultReporter]:
    """Report whether seat takes faults as exceptions.

    Args:
        seat: The seat of a call.

    Returns:
        True when the seat has a callable member report_fault.
    """
    return callable(getattr(seat, "report_fault", None))


def clock_of(seat: object) -> Clock:
    """Return the clock of seat, or the platform clock.

    Args:
        seat: The seat of a call. A test supplies time through it.

    Returns:
        What clock() of the seat returns, or System when the seat does not
        have a clock.
    """
    member: Callable[[], object] | None = getattr(seat, "clock", None)
    if callable(member):
        supplied = member()
        if isinstance(supplied, Clock):
            return supplied
    return System()


#: The path of the test that each seat runs.
_TESTS: weakref.WeakKeyDictionary[object, tuple[str, ...]] = weakref.WeakKeyDictionary()


def name_test(seat: object, path: Sequence[str]) -> None:
    """Name the test that seat runs.

    The first segments of the path are the parts of the module path of the
    test. The module path is relative to the root directory of pytest. The
    last segment is the name of the item with its class and its parameters.
    A property keeps its store under that path.

    Args:
        seat: The seat of the test.
        path: The segments.
    """
    _TESTS[seat] = tuple(path)


def named_test(seat: object) -> tuple[str, ...] | None:
    """Return the path of the test that seat runs.

    Args:
        seat: The seat.

    Returns:
        The segments of the path, or None for a seat that does not run a
        named test.
    """
    try:
        return _TESTS.get(seat)
    except TypeError:
        return None
