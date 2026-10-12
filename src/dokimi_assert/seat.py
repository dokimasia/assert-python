"""The seats that an assertion reports through.

The seat that a test passes decides what each surface does:

=============  ==========  ===================================
Seat           check       expect
=============  ==========  ===================================
Collector      raises      collects, raised when the test ends
Standard       raises      raises
Recorder       collects    collects
=============  ==========  ===================================
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from dokimi_assert._matcher.seat import Seat
from dokimi_assert._matcher.verdict import fault_text
from dokimi_assert._record.calls import keep, lines, own
from dokimi_assert.clock import Clock, System
from dokimi_assert.failure import Failure, render

__all__ = ["Collector", "Recorder", "Seat", "Standard", "clean_up"]


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
        """
        with self._guard:
            return list(self._records)

    @property
    def records(self) -> list[str]:
        """The call records of the calls on this recorder.

        Each is one line of JSON, in the order of the numbers of the calls.
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
        """Whether a failure arrived through either surface."""
        with self._guard:
            return self._fatal is not None or bool(self._recorded)

    @property
    def message(self) -> str:
        """The first failure, the one of the aborting surface first.

        It is the empty string when nothing failed. A test that reads it
        does not raise when the assertion under test wrongly reported
        nothing.
        """
        with self._guard:
            if self._fatal is not None:
                return self._fatal
            return self._recorded[0] if self._recorded else ""

    @property
    def messages(self) -> list[str]:
        """Every failure that arrived through record, in call order."""
        with self._guard:
            return list(self._recorded)

    @property
    def helper_calls(self) -> int:
        """The number of calls of helper."""
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
        """Every failure record that arrived, in call order."""
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
        """Every failure that the collector keeps, in call order."""
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
        raise AssertionError(f"{len(collected)} failures:\n{listed}")

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
    for fn in collector._take_cleanups():  # pyright: ignore[reportPrivateUsage]
        try:
            fn()
        except Exception as error:
            collector.record(f"a cleanup failed: {fault_text(error)}")
