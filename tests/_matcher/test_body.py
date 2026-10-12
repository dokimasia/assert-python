"""The spec of _matcher/body.py tests the seat that an assertion makes for a body."""

from __future__ import annotations

import pytest

from dokimi_assert._matcher.body import Body, Ended, run_on
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.seat import Seat


class TestBody:
    """Body is the seat of a run, and it records whether the run failed."""

    def test_returns_a_seat_that_has_not_failed(self) -> None:
        """A new seat has not failed and does not have a message."""
        seat = Body(None)
        assert (seat.failed, seat.message) == (False, "")


class TestBodyHelper:
    """Body.helper is the helper method that the seat protocol requires."""

    def test_does_not_change_the_seat(self) -> None:
        """The frames of a body are the frames of the test, so helper does nothing."""
        seat = Body(None)
        seat.helper()
        assert (seat.failed, seat.message) == (False, "")


class TestBodyFail:
    """Body.fail keeps a failure that ends the body."""

    def test_ends_the_body_with_ended(self) -> None:
        """Body.fail keeps the message and raises Ended."""
        seat = Body(None)
        with pytest.raises(Ended):
            seat.fail("stops")
        assert (seat.failed, seat.message) == (True, "stops")

    def test_keeps_the_message_of_an_earlier_failure(self) -> None:
        """The seat keeps the text of the first failure."""
        seat = Body(None)
        seat.record("first")
        with pytest.raises(Ended):
            seat.fail("stops")
        assert seat.message == "first"


class TestBodyRecord:
    """Body.record keeps a failure, and the body continues."""

    def test_keeps_the_first_failure_that_it_records(self) -> None:
        """The seat keeps the first message that record receives."""
        seat = Body(None)
        seat.record("first")
        seat.record("second")
        assert (seat.failed, seat.message) == (True, "first")


class TestRunOn:
    """run_on runs a body on its seat."""

    def test_ends_the_run_at_a_failure_that_stops(self) -> None:
        """A body that fails its seat stops at the failure."""
        reached: list[str] = []

        def body(seat: Seat) -> None:
            seat.fail("stops")
            reached.append("after")

        with Loop("x") as loop:
            seat = run_on(Body(None), body, loop)
        assert (seat.failed, reached) == (True, [])

    def test_runs_a_coroutine_body(self) -> None:
        """A body that returns a coroutine runs on the loop."""

        async def body(seat: Seat) -> None:
            seat.record("async")

        with Loop("x") as loop:
            seat = run_on(Body(None), body, loop)
        assert seat.message == "async"

    def test_raises_another_exception_of_the_body(self) -> None:
        """An exception of the body is not a failure of the body."""

        def body(_: Seat) -> None:
            raise KeyError("defect")

        with Loop("x") as loop, pytest.raises(KeyError):
            run_on(Body(None), body, loop)
