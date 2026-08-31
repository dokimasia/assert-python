"""Assertions that retry, and one that checks nothing was left running.

These spend real time. The timeouts are the smallest that still tell
the outcomes apart.
"""

from __future__ import annotations

import asyncio

from dokimi_assert import check
from dokimi_assert._matcher.seat import Seat
from dokimi_assert.seat import Recorder, Standard

OUTER = Standard()


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
    check.is_true(OUTER, seat.failed, "a body that never passes is reported")
    check.contains(
        OUTER, seat.message, "the inner reason", "the last attempt's reason is kept"
    )


def test_eventually_passes_once_the_body_settles() -> None:
    """A body that comes good within the timeout passes."""
    attempts = 0

    def body(trial: Seat) -> None:
        nonlocal attempts
        attempts += 1
        check.is_true(trial, attempts >= 3, "it settled")

    seat = Recorder()
    check.eventually(seat, 1.0, 0.005, body, "it converges")
    check.is_false(OUTER, seat.failed, f"a settling body passes: {seat.message}")
    check.is_true(OUTER, attempts >= 3, "the body ran until it settled")


def test_eventually_true_reports_the_timeout() -> None:
    """A predicate that never holds reports the wait running out."""
    seat = Recorder()
    check.eventually_true(seat, 0.02, lambda: False, "it settles")
    check.is_true(OUTER, seat.failed, "a predicate that never holds is reported")
    check.is_true(
        OUTER,
        seat.failures[0].detail["attempts"] >= 1,
        "the failure counts the attempts it made",
    )


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
    check.is_true(OUTER, seat.failed, "a task still running is reported")


def test_no_task_leaks_passes_when_the_task_finished() -> None:
    """A task that completed before the check is not a leak."""

    async def drive() -> Recorder:
        seat = Recorder()
        done = check.no_task_leaks(seat, "the worker stops")

        await asyncio.ensure_future(asyncio.sleep(0))
        done()
        return seat

    seat = asyncio.run(drive())
    check.is_false(OUTER, seat.failed, f"a finished task is not a leak: {seat.message}")
