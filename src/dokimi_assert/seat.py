"""Seats an assertion reports through.

An assertion does not raise and does not call a test framework. It
reports through a seat, so one comparison serves a real test, a
recorder and a harness that collects failures for a report.
"""

from __future__ import annotations

from dokimi_assert._matcher.seat import Seat

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
        """Raise :exc:`AssertionError` carrying message."""
        __tracebackhide__ = True
        raise AssertionError(message)

    def record(self, message: str) -> None:
        """Raise :exc:`AssertionError`; this seat cannot carry on.

        A recording assertion needs somewhere to put the failure and
        something to report it once the test body is done. This seat
        has no end to report at, so it treats a recorded failure like
        an aborting one rather than dropping it. Use the ``seat``
        fixture, whose :class:`Collector` has a test to end.
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

    def helper(self) -> None:
        """Count one helper-frame mark."""
        self._helpers += 1

    def fail(self, message: str) -> None:
        """Record a failure. The first message is the one kept."""
        if self._fatal is None:
            self._fatal = message

    def record(self, message: str) -> None:
        """Record a failure and return."""
        self._recorded.append(message)

    @property
    def failed(self) -> bool:
        """Whether any failure was recorded, through either path."""
        return self._fatal is not None or bool(self._recorded)

    @property
    def message(self) -> str:
        """The first failure recorded, preferring the aborting path.

        Empty when nothing failed. Most tests assert on one failure,
        and reading this rather than indexing a list keeps them from
        raising when the assertion under test wrongly reported nothing.
        """
        if self._fatal is not None:
            return self._fatal
        return self._recorded[0] if self._recorded else ""

    @property
    def messages(self) -> list[str]:
        """Every failure recorded through ``record``, in call order."""
        return list(self._recorded)

    @property
    def helper_calls(self) -> int:
        """How many times ``helper`` was called."""
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

    def helper(self) -> None:
        """Hide this library's frames from the reported traceback."""

    def fail(self, message: str) -> None:
        """Raise :exc:`AssertionError`, stopping the test here."""
        __tracebackhide__ = True
        raise AssertionError(message)

    def record(self, message: str) -> None:
        """Keep a failure, and let the test carry on."""
        self._collected.append(message)

    @property
    def collected(self) -> list[str]:
        """Every failure recorded so far, in call order."""
        return list(self._collected)

    def flush(self) -> None:
        """Raise one :exc:`AssertionError` carrying every failure.

        Returns when nothing was recorded. Clears what it raised, so a
        seat reused across phases does not report a failure twice.
        """
        __tracebackhide__ = True
        if not self._collected:
            return

        collected, self._collected = self._collected, []
        if len(collected) == 1:
            raise AssertionError(collected[0])

        listed = "\n".join(f"  {n}. {m}" for n, m in enumerate(collected, 1))
        raise AssertionError(f"{len(collected)} failures:\n{listed}")
