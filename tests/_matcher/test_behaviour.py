# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _matcher/behaviour.py tests the assertions about how a subject behaves.

The module computes the verdicts, so this spec checks its verdicts with the
assert statement of pytest.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher import behaviour
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.clock import Controlled
from dokimi_assert.seat import Recorder

if TYPE_CHECKING:
    from collections.abc import Callable


def drive(run: Callable[[Recorder], None], seat: Recorder | None = None) -> Recorder:
    """Call run on seat or on a new recorder, and return the recorder."""
    recorder = seat if seat is not None else Recorder()
    run(recorder)
    return recorder


async def awaits() -> str:
    """Return after one await. A cancellation or a deadline stops it there."""
    await asyncio.sleep(0)
    return "done"


async def returns() -> str:
    """Return before any await."""
    return "done"


async def raises() -> str:
    """Raise an error of its own before any await."""
    msg = "its own reason"
    raise ValueError(msg)


async def raises_when_cancelled() -> str:
    """Raise another error when the cancellation arrives."""
    try:
        await asyncio.sleep(1)
    except asyncio.CancelledError:
        msg = "cancelled badly"
        raise ValueError(msg) from None
    return "done"


async def returns_when_cancelled() -> str:
    """Catch the cancellation and return."""
    try:
        await asyncio.sleep(1)
    except asyncio.CancelledError:
        return "caught"
    return "done"


async def ignores_the_first_cancellation() -> None:
    """Catch the first cancellation and await again.

    The second cancellation stops the coroutine.
    """
    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.sleep(10)
    await asyncio.sleep(10)


class TestNoticeTimeout:
    """NOTICE_TIMEOUT is the wait for a cancelled subject to stop."""

    def test_is_one_second(self) -> None:
        """A cancellation assertion waits at most one second for the subject."""
        assert behaviour.NOTICE_TIMEOUT == 1.0


class TestHonoursCancellation:
    """honours_cancellation checks a subject that it cancels at its first await."""

    def test_passes_a_subject_that_stops_at_its_await(self) -> None:
        """The assertion passes a subject that raises CancelledError at its await."""
        seat = drive(
            lambda s: behaviour.honours_cancellation(s, Mode.FATAL, awaits, "c")
        )
        assert not seat.failed

    def test_fails_a_subject_that_returns_before_it_awaits(self) -> None:
        """A subject that never awaits fails with None as got."""
        seat = drive(
            lambda s: behaviour.honours_cancellation(s, Mode.FATAL, returns, "c")
        )
        assert dict(seat.failures[0].detail) == {"got": None}

    def test_fails_a_subject_that_raises_before_it_awaits(self) -> None:
        """A subject that raises fails with the error as got."""
        seat = drive(
            lambda s: behaviour.honours_cancellation(s, Mode.FATAL, raises, "c")
        )
        assert isinstance(seat.failures[0].got, ValueError)

    def test_fails_a_subject_that_raises_another_error_when_cancelled(self) -> None:
        """A cancelled subject that raises another error fails with the error."""
        seat = drive(
            lambda s: behaviour.honours_cancellation(
                s, Mode.FATAL, raises_when_cancelled, "c"
            )
        )
        assert str(seat.failures[0].got) == "cancelled badly"

    def test_fails_a_subject_that_returns_when_cancelled(self) -> None:
        """The assertion fails a subject that catches the cancellation and returns."""
        seat = drive(
            lambda s: behaviour.honours_cancellation(
                s, Mode.FATAL, returns_when_cancelled, "c"
            )
        )
        assert seat.failures[0].got == "the cancelled subject returned"

    def test_fails_a_subject_that_does_not_stop_after_the_cancellation(self) -> None:
        """A subject that does not stop within NOTICE_TIMEOUT fails."""
        seat = drive(
            lambda s: behaviour.honours_cancellation(
                s, Mode.FATAL, ignores_the_first_cancellation, "c"
            )
        )
        assert seat.failures[0].got == (
            f"the subject did not stop within {behaviour.NOTICE_TIMEOUT}s"
        )

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault inside a running event loop."""
        seat = Recorder()

        async def test() -> None:
            behaviour.honours_cancellation(seat, Mode.FATAL, awaits, "c")

        asyncio.run(test())
        assert seat.message == (
            "honours-cancellation runs a coroutine on an event loop of its own, "
            "and an event loop already runs in this thread"
        )
        assert seat.failures == []


class TestHonoursDeadline:
    """honours_deadline checks a subject that starts after its deadline."""

    def test_passes_a_subject_that_awaits(self) -> None:
        """The assertion passes a subject that the deadline stops at its await."""
        seat = drive(lambda s: behaviour.honours_deadline(s, Mode.FATAL, awaits, "c"))
        assert not seat.failed

    def test_fails_a_subject_that_returns_before_it_awaits(self) -> None:
        """A subject that never awaits fails with None as got."""
        seat = drive(lambda s: behaviour.honours_deadline(s, Mode.SOFT, returns, "c"))
        assert dict(seat.failures[0].detail) == {"got": None}

    def test_fails_a_subject_that_raises(self) -> None:
        """A subject that raises fails with the error as got."""
        seat = drive(lambda s: behaviour.honours_deadline(s, Mode.FATAL, raises, "c"))
        assert isinstance(seat.failures[0].got, ValueError)


class TestCompletesWithin:
    """completes_within checks that a subject returns within a duration."""

    def test_passes_a_subject_that_returns_in_time(self) -> None:
        """A quick subject passes."""
        seat = drive(
            lambda s: behaviour.completes_within(s, Mode.FATAL, 5.0, lambda: 1, "c")
        )
        assert not seat.failed

    def test_passes_a_subject_that_raises_in_time(self) -> None:
        """A subject that raises in time passes.

        The assertion checks the time of the subject and not its result.
        """

        def fails() -> None:
            msg = "quick"
            raise ValueError(msg)

        seat = drive(
            lambda s: behaviour.completes_within(s, Mode.FATAL, 5.0, fails, "c")
        )
        assert not seat.failed

    def test_runs_a_coroutine_function_on_a_loop_of_its_thread(self) -> None:
        """A coroutine function runs to its end on the thread."""
        seat = drive(
            lambda s: behaviour.completes_within(s, Mode.FATAL, 5.0, awaits, "c")
        )
        assert not seat.failed

    def test_fails_a_subject_that_has_not_returned_at_the_deadline(self) -> None:
        """The assertion fails at the deadline and does not wait for the subject."""
        started = time.monotonic()
        seat = drive(
            lambda s: behaviour.completes_within(
                s, Mode.FATAL, 0.05, lambda: time.sleep(1), "c"
            )
        )
        assert time.monotonic() - started < 0.9
        assert seat.failures[0].want == 0.05
        assert seat.failures[0].got >= 0.05

    def test_fails_a_subject_that_is_late_on_the_clock_of_the_seat(self) -> None:
        """The assertion measures the subject on the clock of the seat."""
        clock = Controlled(0)
        seat = Recorder().with_clock(clock)
        drive(
            lambda s: behaviour.completes_within(
                s, Mode.FATAL, 1.0, lambda: clock.advance(2.5), "c"
            ),
            seat,
        )
        assert dict(seat.failures[0].detail) == {"want": 1.0, "got": 2.5}


class TestIsPure:
    """is_pure checks a call that must not change what observe returns."""

    def test_passes_a_call_that_does_not_change_the_state(self) -> None:
        """A call after which observe returns an equal value passes."""
        state = [1]
        seat = drive(
            lambda s: behaviour.is_pure(
                s, Mode.FATAL, lambda: list(state), lambda: None, "c"
            )
        )
        assert not seat.failed

    def test_fails_a_call_that_changes_the_state(self) -> None:
        """A call that changes the state fails.

        want is the reading before the call, and got is the reading after it.
        """
        state = [1]
        seat = drive(
            lambda s: behaviour.is_pure(
                s, Mode.FATAL, lambda: list(state), lambda: state.append(2), "c"
            )
        )
        assert dict(seat.failures[0].detail) == {"want": [1], "got": [1, 2]}

    def test_awaits_coroutine_functions(self) -> None:
        """The assertion awaits a coroutine of observe and of the call."""

        async def observe() -> int:
            return 1

        seat = drive(lambda s: behaviour.is_pure(s, Mode.FATAL, observe, returns, "c"))
        assert not seat.failed

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault inside a running event loop.

        observe returns a coroutine, and the assertion cannot run it there.
        """
        seat = Recorder()

        async def test() -> None:
            behaviour.is_pure(seat, Mode.FATAL, returns, lambda: None, "c")

        asyncio.run(test())
        assert seat.message.startswith("pure runs a coroutine")


class TestNoneHandleSafe:
    """none_handle_safe checks a subject that receives None."""

    def test_passes_a_subject_that_returns(self) -> None:
        """A subject that checks the handle passes."""
        seat = drive(
            lambda s: behaviour.none_handle_safe(s, Mode.FATAL, lambda h: h, "c")
        )
        assert not seat.failed

    def test_passes_a_subject_that_refuses_the_call(self) -> None:
        """A subject that raises an error of its own passes."""

        def refuses(_: Any) -> None:
            msg = "no handle"
            raise ValueError(msg)

        seat = drive(lambda s: behaviour.none_handle_safe(s, Mode.FATAL, refuses, "c"))
        assert not seat.failed

    def test_fails_a_subject_that_reads_an_attribute_of_none(self) -> None:
        """A subject that reads an attribute of None fails with the error as got."""
        seat = drive(
            lambda s: behaviour.none_handle_safe(
                s, Mode.FATAL, lambda h: h.cancelled(), "c"
            )
        )
        assert isinstance(seat.failures[0].got, AttributeError)

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when the subject is a coroutine function."""
        seat = Recorder()

        async def subject(_: Any) -> None:
            return None

        async def test() -> None:
            behaviour.none_handle_safe(seat, Mode.FATAL, subject, "c")

        asyncio.run(test())
        assert seat.message.startswith("nil-context-safe runs a coroutine")
