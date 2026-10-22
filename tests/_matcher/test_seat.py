"""The spec of _matcher/seat.py tests the interface through which assertions report."""

from __future__ import annotations

from dokimi_assert._matcher.seat import (
    Mode,
    clock_of,
    name_test,
    named_test,
    report,
    takes_faults,
    takes_records,
)
from dokimi_assert.clock import Controlled, System
from dokimi_assert.seat import Collector, Recorder, Standard


class TestReport:
    """report sends one sentence to a seat."""

    def test_sends_a_soft_failure_through_record(self) -> None:
        """Under Mode.SOFT the seat records the sentence."""
        seat = Recorder()
        report(seat, Mode.SOFT, "it broke")
        assert (seat.messages, seat.helper_calls) == (["it broke"], 1)

    def test_sends_a_fatal_failure_through_fail(self) -> None:
        """Under Mode.FATAL the seat fails with the sentence."""
        seat = Recorder()
        report(seat, Mode.FATAL, "it broke")
        assert (seat.message, seat.messages) == ("it broke", [])


class TestTakesRecords:
    """takes_records reports whether a seat receives the record."""

    def test_reports_true_for_a_seat_with_report(self) -> None:
        """A recorder receives the record."""
        assert takes_records(Recorder())

    def test_reports_false_for_a_seat_without_report(self) -> None:
        """A standard seat receives the sentence."""
        assert not takes_records(Standard())


class TestTakesFaults:
    """takes_faults reports whether a seat receives a fault as an exception."""

    def test_reports_true_for_a_seat_with_report_fault(self) -> None:
        """A recorder receives the fault."""
        assert takes_faults(Recorder())

    def test_reports_false_for_a_seat_without_report_fault(self) -> None:
        """A collector ends the call with the exception."""
        assert not takes_faults(Collector())


class _Clocked:
    """A seat whose clock method returns the value that the seat received."""

    def __init__(self, given: object) -> None:
        self.given: object = given

    def clock(self) -> object:
        """Return the value that the seat received."""
        return self.given


class TestClockOf:
    """clock_of returns the clock of a seat."""

    def test_returns_the_clock_of_the_seat(self) -> None:
        """Assertions read the clock of the seat."""
        clock = Controlled(3.0)
        assert clock_of(_Clocked(clock)) is clock

    def test_returns_the_platform_clock_for_a_clock_that_is_not_a_clock(self) -> None:
        """The platform clock replaces a value of clock() that is not a clock."""
        assert isinstance(clock_of(_Clocked("noon")), System)

    def test_returns_the_platform_clock_for_a_seat_without_one(self) -> None:
        """A seat without clock() gets the platform clock."""
        assert isinstance(clock_of(Standard()), System)


class TestNameTest:
    """name_test names the test that a seat runs."""

    def test_stores_the_path_as_a_tuple(self) -> None:
        """named_test returns the segments of the path."""
        seat = Recorder()
        name_test(seat, ["tests", "test_store.py", "test_get"])
        assert named_test(seat) == ("tests", "test_store.py", "test_get")

    def test_replaces_the_path_of_a_seat_that_has_one(self) -> None:
        """The seat keeps the path of the last call."""
        seat = Recorder()
        name_test(seat, ["tests", "test_a.py", "test_a"])
        name_test(seat, ["tests", "test_b.py", "test_b"])
        assert named_test(seat) == ("tests", "test_b.py", "test_b")


class TestNamedTest:
    """named_test returns the path of the test that a seat runs."""

    def test_returns_none_for_a_seat_without_a_name(self) -> None:
        """A seat without a name does not run a named test."""
        assert named_test(Recorder()) is None

    def test_returns_none_for_a_seat_that_cannot_be_a_key(self) -> None:
        """An unhashable seat does not have a name."""
        assert named_test([]) is None
