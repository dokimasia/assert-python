"""The assertions built on Python's own model rather than translated.

Go states cancellation with ``context.Context``. Python has no such
convention, so these use asyncio, whose CancelledError and timeouts are
the real analogue. That makes them the assertions most likely to be
wrong, and the ones worth driving hardest.
"""

from __future__ import annotations

import asyncio

from dokimi import check
from dokimi.seat import Recorder


async def _respects() -> None:
    """Yield, so cancellation reaches this subject."""
    await asyncio.sleep(10)


async def _ignores() -> None:
    """Return without yielding, so cancellation cannot reach this."""
    return None


def test_honours_cancellation_passes_a_subject_that_yields() -> None:
    """A subject that awaits is reached by cancellation."""
    seat = Recorder()
    check.honours_cancellation(seat, _respects, "it checks for cancellation")
    assert not seat.failed, seat.message


def test_honours_cancellation_reports_a_subject_that_does_not() -> None:
    """A subject that returns without yielding is not cancellable."""
    seat = Recorder()
    check.honours_cancellation(seat, _ignores, "it checks for cancellation")
    assert seat.failed


def test_honours_deadline_passes_a_subject_that_yields() -> None:
    """A subject given no time is cut short at its first await."""
    seat = Recorder()
    check.honours_deadline(seat, _respects, "it checks its deadline")
    assert not seat.failed, seat.message


def test_completes_within_passes_a_fast_subject() -> None:
    """A subject that returns at once is inside any real ceiling."""
    seat = Recorder()
    check.completes_within(seat, 1.0, lambda: None, "it is quick")
    assert not seat.failed, seat.message


def test_completes_within_reports_a_slow_subject() -> None:
    """A subject slower than its ceiling is reported."""
    seat = Recorder()
    check.completes_within(seat, 0.0, lambda: None, "it is quick")
    assert seat.failed


def test_is_pure_passes_when_the_projection_holds() -> None:
    """A call that changes nothing observed passes."""
    state = [1, 2]
    seat = Recorder()
    check.is_pure(seat, lambda: list(state), lambda: None, "it changes nothing")
    assert not seat.failed, seat.message


def test_is_pure_reports_when_the_projection_changes() -> None:
    """A call that changes observed state is reported."""
    state = [1, 2]
    seat = Recorder()
    check.is_pure(
        seat, lambda: list(state), lambda: state.append(3), "it changes nothing"
    )
    assert seat.failed


def test_none_handle_safe_passes_a_subject_that_refuses() -> None:
    """Refusing a None handle with a decision of its own is fine."""

    def refuses(handle: object) -> None:
        if handle is None:
            raise ValueError("a handle is required")

    seat = Recorder()
    check.none_handle_safe(seat, refuses, "it survives a missing handle")
    assert not seat.failed, seat.message


def test_none_handle_safe_reports_a_subject_that_dereferences() -> None:
    """Dereferencing a None handle is what this catches."""
    seat = Recorder()
    check.none_handle_safe(
        seat, lambda handle: handle.cancelled, "it survives a missing handle"
    )
    assert seat.failed


def test_eventually_reports_the_last_attempt() -> None:
    """A body that never passes reports its own reason, not a timeout."""
    seat = Recorder()
    check.eventually(
        seat,
        0.02,
        0.005,
        lambda trial: check.is_true(trial, False, "the inner reason"),
        "it converges",
    )
    assert seat.failed
    assert "the inner reason" in seat.message


def test_eventually_passes_once_the_body_settles() -> None:
    """A body that comes good within the timeout passes."""
    attempts = 0

    def body(trial: object) -> None:
        nonlocal attempts
        attempts += 1
        check.is_true(trial, attempts >= 3, "it settled")

    seat = Recorder()
    check.eventually(seat, 1.0, 0.005, body, "it converges")
    assert not seat.failed, seat.message
    assert attempts >= 3


def test_eventually_true_reports_the_timeout() -> None:
    """A predicate that never holds reports the wait running out."""
    seat = Recorder()
    check.eventually_true(seat, 0.02, lambda: False, "it settles")
    assert seat.failed
    assert "still false" in seat.message


def test_no_task_leaks_reports_a_task_left_running() -> None:
    """A task started in the scope and still running is a leak."""

    async def drive() -> Recorder:
        seat = Recorder()
        done = check.no_task_leaks(seat, "the worker stops")

        task = asyncio.ensure_future(asyncio.sleep(5))
        await asyncio.sleep(0)
        done()

        task.cancel()
        return seat

    seat = asyncio.run(drive())
    assert seat.failed


def test_no_task_leaks_passes_when_the_task_finished() -> None:
    """A task that completed before the check is not a leak."""

    async def drive() -> Recorder:
        seat = Recorder()
        done = check.no_task_leaks(seat, "the worker stops")

        await asyncio.ensure_future(asyncio.sleep(0))
        done()
        return seat

    seat = asyncio.run(drive())
    assert not seat.failed, seat.message
