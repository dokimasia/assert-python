"""Seats an assertion reports through.

An assertion does not raise and does not call a test framework. It
reports through a seat, so one comparison serves a real test, a
recorder and a harness that collects failures for a report.
"""

from __future__ import annotations

from dokimi._matcher.seat import Seat

__all__ = ["Recorder", "Seat", "Standard"]


class Standard:
    """A seat that raises on failure and hides its own frame.

    This is the seat to pass in an ordinary test. It raises
    :exc:`AssertionError`, which every test framework already treats as
    a failing test rather than an error, so nothing here needs an
    exception type of its own.

    ``record`` raises too: nothing in this seat can collect a failure
    and carry on. Use :class:`Recorder` for that.
    """

    __test__ = False

    def helper(self) -> None:
        """Hide this library's frames from the reported traceback."""

    def fail(self, message: str) -> None:
        """Raise :exc:`AssertionError` carrying message."""
        __tracebackhide__ = True
        raise AssertionError(message)

    def record(self, message: str) -> None:
        """Raise :exc:`AssertionError`; this seat cannot carry on.

        A recording assertion needs somewhere to put the failure and
        something to report it at the end. Pass a :class:`Recorder`,
        which pytest's fixture supplies for you.
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

    __test__ = False

    def __init__(self) -> None:
        """Return a recorder that has recorded nothing."""
        self._fatal: str | None = None
        self._recorded: list[str] = []
        self._helpers = 0

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
