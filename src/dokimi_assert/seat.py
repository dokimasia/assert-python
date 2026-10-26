# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The seats that an assertion reports through.

The seat that a test passes decides what each surface does:

=============  ==========  ===================================
Seat           check       expect
=============  ==========  ===================================
Collector      raises      collects, raised when the test ends
Standard       raises      raises
Recorder       collects    collects
=============  ==========  ===================================

A fault ends the call on both surfaces. A Recorder keeps the fault, and the
other two seats raise it. A helper of a test ends its own call with a fault
through fault.

A property whose run skips skips the test of a Collector or a Standard
seat. Both raise unittest.SkipTest, which unittest and pytest report as a
skipped test. A Recorder keeps the call record of the skip alone. A call of
rejects whose check skips before it fails skips the test in the same way.
"""

from __future__ import annotations

import threading
import unittest
from typing import TYPE_CHECKING

from dokimi_assert._matcher.seat import Seat
from dokimi_assert._matcher.verdict import end, fault_text
from dokimi_assert._record.calls import keep, lines, own
from dokimi_assert.clock import Clock, System
from dokimi_assert.failure import Failure, render

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["Collector", "Recorder", "Seat", "Standard", "clean_up", "fault"]


def fault(seat: Seat, error: BaseException) -> None:
    """End the call of a helper with error, a fault.

    A fault is an argument or an environment that the helper refuses. A seat
    that has report_fault receives error with ending True, as a Recorder
    does. For any other seat, fault raises error. The faults of this library
    end their calls the same way. fault does not write a call record,
    because the call is not a call of an assertion.

        fault(seat, ValueError("the check calls restart without restartable"))

    A seat that takes the fault returns, so a helper returns after fault.

    Args:
        seat: The seat of the call of the helper.
        error: The fault.

    Raises:
        TypeError: error is not an exception.
    """
    __tracebackhide__ = True
    if not isinstance(error, BaseException):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"seat.fault({error!r}) needs an exception"  # type: ignore[unreachable]
        raise TypeError(msg)  # pyright: ignore[reportUnreachable]
    end(seat, error)


class Standard:
    """A seat that raises on every failure.

    It is the seat to construct outside a test runner. It raises
    AssertionError, which every test framework treats as a failing test. Its
    record raises too: a recorded failure needs a place where it is reported
    when the test ends, and this seat has no end of a test. It writes no
    call record.
    """

    __test__: bool = False

    def helper(self) -> None:
        """Do nothing, because no runner hides the frames of this seat."""

    def fail(self, message: str) -> None:
        """Raise AssertionError with message.

        Args:
            message: The text of the failure.

        Raises:
            AssertionError: Always.
        """
        __tracebackhide__ = True
        raise AssertionError(message)

    def record(self, message: str) -> None:
        """Raise AssertionError with message, because this seat cannot continue.

        Args:
            message: The text of the failure.

        Raises:
            AssertionError: Always.
        """
        __tracebackhide__ = True
        raise AssertionError(message)

    def skip(self, reason: str) -> None:
        """Skip the test with reason.

        Args:
            reason: The reason of the skip.

        Raises:
            unittest.SkipTest: Always.
        """
        __tracebackhide__ = True
        raise unittest.SkipTest(reason)


class Recorder:
    """A seat that collects every failure and raises none.

    A test of an assertion reads what the assertion reported on the
    recorder, and the assertion does not stop the test. The recorder keeps
    the first message of the aborting surface, because nothing after that
    call runs in a real test. It keeps the call record of every call that it
    receives, whatever DOKIMI_ASSERT_RECORD states.

    The methods of Recorder are safe for concurrent use.
    """

    __test__: bool = False

    def __init__(self) -> None:
        """Return a recorder that has received nothing."""
        self._fatal: str | None = None
        self._recorded: list[str] = []
        self._helpers: int = 0
        self._records: list[Failure] = []
        self._faults: list[BaseException] = []
        self._clock: Clock | None = None
        self._guard: threading.Lock = threading.Lock()
        keep(own(self))

    def helper(self) -> None:
        """Count one call of helper."""
        with self._guard:
            self._helpers += 1

    def report(self, failure: Failure, aborting: bool) -> None:
        """Keep one failure record, and its sentence.

        A test reads the fields of the record, and does not search the
        sentence for words. The recorder keeps the sentence too, which
        message returns.

        Args:
            failure: The record that the assertion reported.
            aborting: Whether the record came from the aborting surface.
        """
        with self._guard:
            self._records.append(failure)
        if aborting:
            self.fail(render(failure))
            return
        self.record(render(failure))

    @property
    def failures(self) -> list[Failure]:
        """Every failure record that arrived, in call order.

        A message that a caller passed to fail or record directly leaves no
        record, so an assertion that did not report a record is visible
        here.

        Returns:
            The failure records.
        """
        with self._guard:
            return list(self._records)

    def report_fault(self, fault: BaseException, ending: bool) -> None:
        """Keep one fault, and fail with its text when it ends its call.

        An assertion and fault pass a fault here as the exception it is, so a
        test compares the exception and does not search its text. A fault
        that ends its call fails the recorder, as fail does with the text of
        the fault. A fault that a call notes and runs on past does not fail
        it.

        Args:
            fault: The fault.
            ending: When True, the fault ends its call.
        """
        with self._guard:
            self._faults.append(fault)
        if ending:
            self.fail(fault_text(fault))

    @property
    def faults(self) -> list[BaseException]:
        """Every fault that arrived through report_fault, in call order.

        Returns:
            The faults, those that ended their calls and those that a call
            noted.
        """
        with self._guard:
            return list(self._faults)

    @property
    def records(self) -> list[str]:
        """The call records of the calls on this recorder.

        Each is one line of JSON, in the order of the numbers of the calls.

        Returns:
            The lines of the records.
        """
        return lines(own(self))

    def clock(self) -> Clock:
        """Return the clock that this seat hands assertions.

        Returns:
            The clock that with_clock set, or the platform clock.
        """
        with self._guard:
            return self._clock if self._clock is not None else System()

    def with_clock(self, clock: Clock) -> Recorder:
        """Make the assertions reported here read clock in place of the platform.

        Args:
            clock: The clock that those assertions read.

        Returns:
            The recorder.
        """
        with self._guard:
            self._clock = clock
        return self

    def fail(self, message: str) -> None:
        """Collect a failure of the aborting surface.

        The recorder keeps the first such message.

        Args:
            message: The text of the failure.
        """
        with self._guard:
            if self._fatal is None:
                self._fatal = message

    def record(self, message: str) -> None:
        """Collect a failure of the recording surface.

        Args:
            message: The text of the failure.
        """
        with self._guard:
            self._recorded.append(message)

    @property
    def failed(self) -> bool:
        """Whether a failure arrived through either surface.

        Returns:
            True after a failure.
        """
        with self._guard:
            return self._fatal is not None or bool(self._recorded)

    @property
    def message(self) -> str:
        """The first failure, the one of the aborting surface first.

        It is the empty string when nothing failed. A test that reads it
        does not raise when the assertion under test wrongly reported
        nothing.

        Returns:
            The first message, or the empty string.
        """
        with self._guard:
            if self._fatal is not None:
                return self._fatal
            return self._recorded[0] if self._recorded else ""

    @property
    def messages(self) -> list[str]:
        """Every failure that arrived through record, in call order.

        Returns:
            The messages of the failures.
        """
        with self._guard:
            return list(self._recorded)

    @property
    def helper_calls(self) -> int:
        """The number of calls of helper.

        Returns:
            The number of calls.
        """
        with self._guard:
            return self._helpers


class Collector:
    """A seat that raises on a check and collects what expect records.

    It is the seat of a real test, which the seat fixture supplies. An
    aborting assertion raises at its call. A recording assertion is kept
    until flush, which the fixture calls when the test body ends, so the
    test reports every failure that it recorded at once.

    The methods of Collector are safe for concurrent use.
    """

    __test__: bool = False

    def __init__(self) -> None:
        """Return a collector that has collected nothing."""
        self._collected: list[str] = []
        self._records: list[Failure] = []
        self._cleanups: list[Callable[[], object]] = []
        self._clock: Clock | None = None
        self._guard: threading.Lock = threading.Lock()

    def helper(self) -> None:
        """Do nothing, because pytest hides the frames that mark themselves."""

    def report(self, failure: Failure, aborting: bool) -> None:
        """Take one failure record: raise its sentence when aborting, or keep it.

        The collector keeps the record either way, so a test can read the
        fields of the record.

        Args:
            failure: The record that the assertion reported.
            aborting: Whether the record came from the aborting surface.
        """
        __tracebackhide__ = True
        with self._guard:
            self._records.append(failure)
        if not aborting:
            self.record(render(failure))
            return
        self.fail(render(failure))

    @property
    def failures(self) -> list[Failure]:
        """Every failure record that arrived, in call order.

        Returns:
            The failure records.
        """
        with self._guard:
            return list(self._records)

    def clock(self) -> Clock:
        """Return the clock that this seat hands assertions.

        Returns:
            The clock that with_clock set, or the platform clock.
        """
        with self._guard:
            return self._clock if self._clock is not None else System()

    def with_clock(self, clock: Clock) -> Collector:
        """Make the assertions reported here read clock in place of the platform.

        Args:
            clock: The clock that those assertions read.

        Returns:
            The collector.
        """
        with self._guard:
            self._clock = clock
        return self

    def fail(self, message: str) -> None:
        """Raise AssertionError with message, which stops the test.

        Args:
            message: The text of the failure.

        Raises:
            AssertionError: Always.
        """
        __tracebackhide__ = True
        raise AssertionError(message)

    def record(self, message: str) -> None:
        """Keep a failure, and let the test continue.

        Args:
            message: The text of the failure.
        """
        with self._guard:
            self._collected.append(message)

    def skip(self, reason: str) -> None:
        """Skip the test with reason.

        Args:
            reason: The reason of the skip.

        Raises:
            unittest.SkipTest: Always.
        """
        __tracebackhide__ = True
        raise unittest.SkipTest(reason)

    def cleanup(self, fn: Callable[[], object]) -> None:
        """Register fn to run when the test ends, also when the test fails.

        The seat fixture runs the functions after the test body, the last
        registered first, and reports each function that raises as a
        failure of the test.

        Args:
            fn: The function, such as the removal of a directory that the
                test created.
        """
        with self._guard:
            self._cleanups.append(fn)

    @property
    def collected(self) -> list[str]:
        """Every failure that the collector keeps, in call order.

        Returns:
            The messages of the failures.
        """
        with self._guard:
            return list(self._collected)

    def flush(self) -> None:
        """Raise one AssertionError with every failure that the collector keeps.

        It returns when the collector keeps nothing. It forgets what it
        raised, so a seat that a test reuses does not report a failure
        twice.

        Raises:
            AssertionError: The collector keeps a failure.
        """
        __tracebackhide__ = True
        with self._guard:
            if not self._collected:
                return
            collected, self._collected = self._collected, []
        if len(collected) == 1:
            raise AssertionError(collected[0])
        listed = "\n".join(f"  {n}. {m}" for n, m in enumerate(collected, 1))
        msg = f"{len(collected)} failures:\n{listed}"
        raise AssertionError(msg)

    def _take_cleanups(self) -> list[Callable[[], object]]:
        """Return the registered functions, the last first, and forget them."""
        with self._guard:
            registered, self._cleanups = self._cleanups, []
        return registered[::-1]


def clean_up(collector: Collector) -> None:
    """Run the functions that collector registered through cleanup.

    It runs the last registered first, and forgets them. A function that
    raises does not stop the ones after it: the collector keeps its error as
    a failure, which the next flush reports.

    Args:
        collector: The seat of the test that ended.
    """
    for fn in collector._take_cleanups():  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        try:
            fn()
        except Exception as error:
            collector.record(f"a cleanup failed: {fault_text(error)}")
