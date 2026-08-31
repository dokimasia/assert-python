"""Seats an assertion reports through.

An assertion does not raise and does not call a test framework. It
reports through a seat, so one comparison serves a real test, a
recorder and a harness that collects failures for a report.
"""

from __future__ import annotations

import threading

from dokimi_assert._matcher.seat import Seat
from dokimi_assert.clock import Clock, System
from dokimi_assert.failure import Failure, render

__all__ = ["Collector", "Recorder", "Seat", "Standard"]


class Standard:
    """A seat that raises on failure and hides its own frame.

    This is the seat to pass in an ordinary test. It raises
    :exc:`AssertionError`, which every test framework already treats as
    a failing test rather than an error, so nothing here needs an
    exception type of its own.

    ``record`` raises too: nothing in this seat can collect a failure
    and carry on. Use :class:`Recorder` for that.
    """

    __test__: bool = False

    def helper(self) -> None:
        """Hide this library's frames from the reported traceback."""

    def fail(self, message: str) -> None:
        """Raise AssertionError carrying message.

        Args:
            message: The failure text, already formatted.
        """
        __tracebackhide__ = True
        raise AssertionError(message)

    def record(self, message: str) -> None:
        """Raise AssertionError; this seat cannot carry on.

        A recording assertion needs somewhere to put the failure and
        something to report it once the test body is done. This seat
        has no end to report at, so it treats a recorded failure like
        an aborting one rather than dropping it. Use the seat
        fixture, whose Collector has a test to end.

        Args:
            message: The failure text, already formatted.
        """
        __tracebackhide__ = True
        raise AssertionError(message)


class Recorder:
    """A seat that records a failure instead of raising.

    It is what lets an assertion be tested by reading what it reported
    rather than suffering it, and what the recording surface reports
    through so several failures are seen in one run.

    It follows a real seat in the one way that matters for reading a
    failure back: the first fatal message is the one kept, because in a
    real test nothing after that call runs.
    """

    __test__: bool = False

    def __init__(self) -> None:
        """Return a recorder that has recorded nothing."""
        self._fatal: str | None = None
        self._recorded: list[str] = []
        self._helpers: int = 0
        self._records: list[Failure] = []
        self._clock: Clock | None = None
        self._guard: threading.Lock = threading.Lock()

    def helper(self) -> None:
        """Count one helper-frame mark."""
        with self._guard:
            self._helpers += 1

    def report(self, failure: Failure, aborting: bool) -> None:
        """Record one failure as the record it is.

        This is what lets a test read the assertion's own fields rather
        than search its sentence for words. The rendered sentence is
        kept too, so message answers what it always did.

        Args:
            failure: The record the assertion reported.
            aborting: Whether it came from the aborting surface.
        """
        with self._guard:
            self._records.append(failure)
        if aborting:
            self.fail(render(failure))
            return
        self.record(render(failure))

    @property
    def failures(self) -> list[Failure]:
        """Every record that arrived, in call order.

        A message passed straight to fail or record leaves none, so an
        assertion that did not report a record is visible here.

        Returns:
            Every record that arrived, in call order.
        """
        with self._guard:
            return list(self._records)

    def clock(self) -> Clock:
        """The clock this seat hands assertions.

        Returns:
            What with_clock set, or the platform clock.
        """
        with self._guard:
            return self._clock if self._clock is not None else System()

    def with_clock(self, clock: Clock) -> Recorder:
        """Make assertions reported here read clock rather than the platform.

        Args:
            clock: Where those assertions read time.

        Returns:
            The receiver, so the call chains onto the constructor.
        """
        with self._guard:
            self._clock = clock
        return self

    def fail(self, message: str) -> None:
        """Record a failure. The first message is the one kept.

        Args:
            message: The failure text, already formatted.
        """
        with self._guard:
            if self._fatal is None:
                self._fatal = message

    def record(self, message: str) -> None:
        """Record a failure and return.

        Args:
            message: The failure text, already formatted.
        """
        with self._guard:
            self._recorded.append(message)

    @property
    def failed(self) -> bool:
        """Whether any failure was recorded, through either path.

        Returns:
            Whether any failure was recorded, through either path.
        """
        with self._guard:
            return self._fatal is not None or bool(self._recorded)

    @property
    def message(self) -> str:
        """The first failure recorded, preferring the aborting path.

        Empty when nothing failed. Most tests assert on one failure,
        and reading this rather than indexing a list keeps them from
        raising when the assertion under test wrongly reported nothing.

        Returns:
            The first failure recorded, or an empty string when nothing failed.
        """
        with self._guard:
            if self._fatal is not None:
                return self._fatal
            return self._recorded[0] if self._recorded else ""

    @property
    def messages(self) -> list[str]:
        """Every failure recorded through record, in call order.

        Returns:
            Every failure recorded through record, in call order.
        """
        with self._guard:
            return list(self._recorded)

    @property
    def helper_calls(self) -> int:
        """How many times helper was called.

        Returns:
            How many times helper was called.
        """
        with self._guard:
            return self._helpers


class Collector:
    """A seat that aborts on a check and collects what expect records.

    This is what a real test needs and what the ``seat`` fixture
    supplies. :class:`Standard` cannot collect, because it has no end
    of test to report at; :class:`Recorder` collects everything and
    aborts on nothing, which is right for reading a failure back and
    wrong for suffering one.

    An aborting assertion raises where it stands. A recording one is
    kept until :meth:`flush`, which the fixture calls once the test
    body is done, so several failing properties of one value are all
    reported from one run.
    """

    __test__: bool = False

    def __init__(self) -> None:
        """Return a seat holding nothing."""
        self._collected: list[str] = []
        self._records: list[Failure] = []
        self._clock: Clock | None = None
        self._guard: threading.Lock = threading.Lock()

    def helper(self) -> None:
        """Hide this library's frames from the reported traceback."""

    def report(self, failure: Failure, aborting: bool) -> None:
        """Take one record: raise it when aborting, keep it otherwise.

        The record is kept either way, so a test can read the
        assertion's own fields rather than search its sentence.

        Args:
            failure: The record the assertion reported.
            aborting: Whether it came from the aborting surface.
        """
        __tracebackhide__ = True
        with self._guard:
            self._records.append(failure)
        if aborting:
            self.fail(render(failure))
            return
        self.record(render(failure))

    @property
    def failures(self) -> list[Failure]:
        """Every record that arrived, in call order.

        Returns:
            Every record that arrived, in call order.
        """
        with self._guard:
            return list(self._records)

    def clock(self) -> Clock:
        """The clock this seat hands assertions.

        Returns:
            What with_clock set, or the platform clock.
        """
        with self._guard:
            return self._clock if self._clock is not None else System()

    def with_clock(self, clock: Clock) -> Collector:
        """Make assertions reported here read clock rather than the platform.

        Args:
            clock: Where those assertions read time.

        Returns:
            The receiver, so the call chains onto the constructor.
        """
        with self._guard:
            self._clock = clock
        return self

    def fail(self, message: str) -> None:
        """Raise AssertionError, stopping the test here.

        Args:
            message: The failure text, already formatted.
        """
        __tracebackhide__ = True
        raise AssertionError(message)

    def record(self, message: str) -> None:
        """Keep a failure, and let the test carry on.

        Args:
            message: The failure text, already formatted.
        """
        with self._guard:
            self._collected.append(message)

    @property
    def collected(self) -> list[str]:
        """Every failure recorded so far, in call order.

        Returns:
            Every failure kept so far, in call order.
        """
        with self._guard:
            return list(self._collected)

    def flush(self) -> None:
        """Raise one AssertionError carrying every failure.

        Returns when nothing was recorded. Clears what it raised, so a
        seat reused across phases does not report a failure twice.
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
