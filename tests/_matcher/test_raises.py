"""The spec of _matcher/raises.py tests the assertions about a callable that raises."""

from __future__ import annotations

import warnings

from dokimi_assert._matcher import raises
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.seat import Recorder


def boom() -> None:
    """Raise an error."""
    raise ValueError("boom")


async def coroutine() -> None:
    """Do nothing. A call returns a coroutine."""


class TestRaises:
    """raises checks that a callable raises."""

    def test_returns_what_the_callable_raised(self) -> None:
        """The assertion passes and returns the error."""
        seat = Recorder()
        error = raises.raises(seat, Mode.FATAL, boom, "c")
        assert isinstance(error, ValueError)
        assert not seat.failed

    def test_fails_a_callable_that_returns(self) -> None:
        """The assertion returns None, and the failure does not have a detail."""
        seat = Recorder()
        assert raises.raises(seat, Mode.FATAL, lambda: 1, "c") is None
        assert seat.failures[0].assertion == "throws"

    def test_closes_the_coroutine_of_a_coroutine_function(self) -> None:
        """A coroutine that nobody awaits does not raise a warning."""
        seat = Recorder()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            raises.raises(seat, Mode.FATAL, coroutine, "c")
        assert seat.failed


class TestDoesNotRaise:
    """does_not_raise checks that a callable returns."""

    def test_passes_a_callable_that_returns(self) -> None:
        """A callable that returns passes."""
        seat = Recorder()
        raises.does_not_raise(seat, Mode.FATAL, lambda: 1, "c")
        assert not seat.failed

    def test_fails_a_callable_that_raises(self) -> None:
        """The failure has the error as got."""
        seat = Recorder()
        raises.does_not_raise(seat, Mode.FATAL, boom, "c")
        assert isinstance(seat.failures[0].got, ValueError)

    def test_closes_the_coroutine_of_a_coroutine_function(self) -> None:
        """A coroutine that nobody awaits does not raise a warning."""
        seat = Recorder()
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            raises.does_not_raise(seat, Mode.FATAL, coroutine, "c")
        assert not seat.failed
