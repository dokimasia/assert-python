# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _matcher/body.py tests the seat that an assertion makes for a body."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from dokimi_assert._matcher.body import Body, Ended, run_on
from dokimi_assert._matcher.loop import Loop
from dokimi_assert.seat import Recorder

if TYPE_CHECKING:
    from dokimi_assert._matcher.seat import Seat


class TestBody:
    """Body is the seat of a run, and it records whether the run failed."""

    def test_returns_a_seat_that_has_not_failed(self) -> None:
        """A new seat has not failed and does not have a message."""
        seat = Body(None, Recorder())
        assert (seat.failed, seat.message) == (False, "")


class TestBodyHelper:
    """Body.helper is the helper method that the seat protocol requires."""

    def test_does_not_change_the_seat(self) -> None:
        """The frames of a body are the frames of the test, so helper does nothing."""
        seat = Body(None, Recorder())
        seat.helper()
        assert (seat.failed, seat.message) == (False, "")


class TestBodyFail:
    """Body.fail keeps a failure that ends the body."""

    def test_ends_the_body_with_ended(self) -> None:
        """Body.fail keeps the message and raises Ended."""
        seat = Body(None, Recorder())
        with pytest.raises(Ended):
            seat.fail("stops")
        assert (seat.failed, seat.message) == (True, "stops")

    def test_keeps_the_message_of_an_earlier_failure(self) -> None:
        """The seat keeps the text of the first failure."""
        seat = Body(None, Recorder())
        seat.record("first")
        with pytest.raises(Ended):
            seat.fail("stops")
        assert seat.message == "first"


class TestBodyRecord:
    """Body.record keeps a failure, and the body continues."""

    def test_keeps_the_first_failure_that_it_records(self) -> None:
        """The seat keeps the first message that record receives."""
        seat = Body(None, Recorder())
        seat.record("first")
        seat.record("second")
        assert (seat.failed, seat.message) == (True, "first")


class TestBodyReportFault:
    """Body.report_fault receives a fault of a call of the body."""

    def test_ends_the_body_with_the_text_of_a_fault_that_ends_its_call(self) -> None:
        """An ending fault fails the body as fail does with its text."""
        seat = Body(None, Recorder())
        with pytest.raises(Ended):
            seat.report_fault(ValueError("the input is refused"), True)
        assert (seat.failed, seat.message) == (True, "the input is refused")

    def test_passes_a_noted_fault_to_the_seat_of_the_assertion(self) -> None:
        """A noted fault does not fail the body."""
        parent = Recorder()
        seat = Body(None, parent)
        noted = ValueError("the store skips a file")
        seat.report_fault(noted, False)
        assert (seat.failed, parent.faults, parent.failed) == (False, [noted], False)


class TestRunOn:
    """run_on runs a body on its seat."""

    def test_ends_the_run_at_a_failure_that_stops(self) -> None:
        """A body that fails its seat stops at the failure."""
        reached: list[str] = []

        def body(seat: Seat) -> None:
            seat.fail("stops")
            reached.append("after")

        with Loop("x") as loop:
            seat = run_on(Body(None, Recorder()), body, loop)
        assert (seat.failed, reached) == (True, [])

    def test_runs_a_coroutine_body(self) -> None:
        """A body that returns a coroutine runs on the loop."""

        async def body(seat: Seat) -> None:
            seat.record("async")

        with Loop("x") as loop:
            seat = run_on(Body(None, Recorder()), body, loop)
        assert seat.message == "async"

    def test_raises_another_exception_of_the_body(self) -> None:
        """An exception of the body is not a failure of the body."""

        def body(_: Seat) -> None:
            msg = "defect"
            raise KeyError(msg)

        with Loop("x") as loop, pytest.raises(KeyError):
            run_on(Body(None, Recorder()), body, loop)

    def test_runs_the_cleanups_of_the_body_the_last_registered_first(self) -> None:
        """The seat runs its cleanups once the body has ended."""
        order: list[str] = []

        def body(seat: Seat) -> None:
            cast("Body", seat).cleanup(lambda: order.append("first"))
            cast("Body", seat).cleanup(lambda: order.append("second"))
            seat.fail("stops")

        with Loop("x") as loop:
            run_on(Body(None, Recorder()), body, loop)
        assert order == ["second", "first"]

    def test_runs_the_cleanups_of_a_body_that_raises(self) -> None:
        """A body that raises still runs its cleanups before the error leaves."""
        order: list[str] = []

        def body(seat: Seat) -> None:
            cast("Body", seat).cleanup(lambda: order.append("released"))
            msg = "defect"
            raise KeyError(msg)

        with Loop("x") as loop, pytest.raises(KeyError):
            run_on(Body(None, Recorder()), body, loop)
        assert order == ["released"]


class TestBodyCleanup:
    """Body.cleanup registers a function that runs when the body ends."""

    def test_fails_the_body_at_a_failure_in_a_cleanup(self) -> None:
        """A failure that stops in a cleanup is a failure of the body."""
        order: list[str] = []

        def body(seat: Seat) -> None:
            cast("Body", seat).cleanup(lambda: order.append("first"))
            cast("Body", seat).cleanup(lambda: seat.fail("the release fails"))

        with Loop("x") as loop:
            seat = run_on(Body(None, Recorder()), body, loop)
        assert (seat.failed, seat.message, order) == (
            True,
            "the release fails",
            ["first"],
        )

    def test_raises_the_error_of_a_cleanup_after_the_later_cleanups(self) -> None:
        """The first error of a cleanup leaves run_on once every cleanup ran."""
        order: list[str] = []

        def busy() -> None:
            msg = "the port is busy"
            raise OSError(msg)

        def body(seat: Seat) -> None:
            cast("Body", seat).cleanup(lambda: order.append("first"))
            cast("Body", seat).cleanup(busy)

        with Loop("x") as loop, pytest.raises(OSError, match="the port is busy"):
            run_on(Body(None, Recorder()), body, loop)
        assert order == ["first"]

    def test_runs_an_awaitable_of_a_cleanup_on_the_loop_of_the_call(self) -> None:
        """A coroutine function that a body registers runs on the loop."""
        order: list[str] = []

        async def close() -> None:
            order.append("closed")

        def body(seat: Seat) -> None:
            cast("Body", seat).cleanup(close)

        with Loop("x") as loop:
            run_on(Body(None, Recorder()), body, loop)
        assert order == ["closed"]

    def test_runs_a_function_that_arrives_after_the_cleanups_at_once(self) -> None:
        """A cleanup that a seat receives after its body ended runs at once."""
        order: list[str] = []

        async def late() -> None:
            order.append("late")

        with Loop("x") as loop:
            seat = run_on(Body(None, Recorder()), lambda _: None, loop)
        seat.cleanup(late)
        assert order == ["late"]
