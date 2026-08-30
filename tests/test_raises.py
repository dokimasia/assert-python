"""Assertions about a callable raising."""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert.seat import Recorder, Standard

OUTER = Standard()

REASON = "the stated reason"


def test_raises_passes_a_callable_that_raises() -> None:
    """A callable that raises satisfies the assertion."""
    seat = Recorder()
    check.raises(seat, lambda: (_ for _ in ()).throw(ValueError(REASON)), "it refuses")
    check.is_false(OUTER, seat.failed, "a raising callable passes")


def test_raises_returns_what_was_raised() -> None:
    """The exception is returned, so a caller can assert on the reason."""

    def refuse() -> None:
        raise ValueError(REASON)

    caught = check.raises(Recorder(), refuse, "it refuses")

    check.is_not_none(OUTER, caught, "the exception is returned")
    check.contains(OUTER, str(caught), REASON, "it carries the reason")


def test_raises_reports_a_callable_that_returns() -> None:
    """A callable that returns is reported."""
    seat = Recorder()
    check.raises(seat, lambda: None, "it refuses")
    check.is_true(OUTER, seat.failed, "a returning callable fails")


def test_raises_returns_none_when_nothing_was_raised() -> None:
    """Nothing is returned when nothing was raised."""
    check.is_none(
        OUTER,
        check.raises(Recorder(), lambda: None, "it refuses"),
        "nothing is returned when the callable returned",
    )


def test_does_not_raise_passes_a_callable_that_returns() -> None:
    """A callable that returns satisfies the assertion."""
    seat = Recorder()
    check.does_not_raise(seat, lambda: None, "it survives")
    check.is_false(OUTER, seat.failed, "a returning callable passes")


def test_does_not_raise_reports_what_was_raised() -> None:
    """A raising callable is reported, naming what it raised."""

    def crash() -> None:
        raise ValueError(REASON)

    seat = Recorder()
    check.does_not_raise(seat, crash, "it survives")

    check.is_true(OUTER, seat.failed, "a raising callable fails")
    check.contains(OUTER, seat.message, REASON, "the failure names the reason")


def test_does_not_raise_contains_the_exception() -> None:
    """The exception does not escape, so one subject cannot end the run."""

    def crash() -> None:
        raise ValueError(REASON)

    seat = Recorder()
    check.does_not_raise(seat, crash, "it survives")

    # Reaching this line is the assertion: an uncaught exception would
    # have failed this test rather than being recorded.
    check.is_true(OUTER, seat.failed, "the exception was recorded, not raised")
