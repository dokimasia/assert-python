# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertions that retry, and the assertion that checks a scope for leaks.

The retrying assertions wait on the clock of the seat. On the platform clock
they spend real time, so they suit a condition that something outside the
test makes true. On a controlled clock they advance the clock between
attempts, and they do not spend real time.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.body import Body, run_on
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.seat import Mode, Seat, clock_of
from dokimi_assert._matcher.verdict import Running, fail, pass_
from dokimi_assert._record.calls import own
from dokimi_assert.clock import Clock, wait
from dokimi_assert.failure import call_site

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["LEAK_GRACE", "eventually", "eventually_true", "no_task_leaks"]

#: The shortest wait between two attempts in seconds. Every wait moves a
#: controlled clock forward.
_MIN_WAIT = 0.001

#: The seconds that a check for leaks waits for the tasks and the threads of
#: the scope to end.
LEAK_GRACE = 0.5

#: The seconds between two scans of the check for leaks.
_LEAK_INTERVAL = 0.005


def _wait_within(clock: Clock, deadline: float, duration: float) -> bool:
    """Wait duration on clock, or the time left before deadline when that is less.

    Returns:
        True when another attempt can start. The time on the clock was before
        the deadline, and after the wait it is not later than the deadline.
    """
    now = clock.now()
    if not now < deadline:
        return False
    wait(clock, min(duration, deadline - now))
    return not clock.now() > deadline


def eventually(
    seat: Seat,
    mode: Mode,
    timeout: float,
    interval: float,
    body: Callable[[Any], object],
    msg: str,
) -> None:
    """Report when a body of assertions does not pass within the timeout.

    The body receives a seat of its own, so an assertion inside it ends the
    attempt and not the test. The body runs at least once, even for a
    timeout of 0. The detail of the failure has the number of attempts and
    the message of the last failure. An attempt does not start after the
    timeout, and an attempt passes the call only when it ends by the
    deadline. The record of the call of eventually contains the calls of
    each attempt.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        timeout: The most seconds that the attempts can take.
        interval: The seconds between two attempts.
        body: Receives the seat of an attempt, and checks the condition with
            assertions. A coroutine function runs on an event loop of the
            call.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.begin(seat, call_site())
    clock = clock_of(seat)
    deadline = clock.now() + timeout
    attempts = 0
    with Loop("eventually") as loop:
        while True:
            attempts += 1
            try:
                trial = run_on(Body(call.slot, seat), body, loop)
            except FaultError as error:
                call.faulted(mode, "eventually", msg, error)
                return
            if call.slot is not None:
                call.slot.take(own(trial))
            if not trial.failed and not clock.now() > deadline:
                call.passed(mode, "eventually", msg)
                return
            if not _wait_within(clock, deadline, max(interval, _MIN_WAIT)):
                detail = {"attempts": attempts, "last": trial.message}
                call.failed(mode, "eventually", msg, detail)
                return


def eventually_true(
    seat: Seat, mode: Mode, timeout: float, predicate: Callable[[], object], msg: str
) -> None:
    """Report when a predicate does not become true within the timeout.

    The assertion calls the predicate with a backoff that starts at a
    millisecond and doubles up to a quarter of the timeout. A predicate does
    not give a reason, so the failure has only the number of attempts.
    eventually reports the reason of the last failure.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        timeout: The most seconds that the attempts can take.
        predicate: Returns True when the condition is met. A coroutine
            function runs on an event loop of the call.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.of(seat, call_site())
    clock = clock_of(seat)
    deadline = clock.now() + timeout
    cap = max(timeout / 4, _MIN_WAIT)
    backoff = _MIN_WAIT
    attempts = 0
    with Loop("eventually-true") as loop:
        while True:
            attempts += 1
            try:
                met = loop.resolve(predicate())
            except FaultError as error:
                call.faulted(mode, "eventually-true", msg, error)
                return
            if met and not clock.now() > deadline:
                call.passed(mode, "eventually-true", msg)
                return
            if not _wait_within(clock, deadline, backoff):
                call.failed(mode, "eventually-true", msg, {"attempts": attempts})
                return
            backoff = min(2 * backoff, cap)


def _running() -> set[threading.Thread | asyncio.Task[Any]]:
    """Return the threads and the asyncio tasks of the event loop that run now."""
    alive: set[threading.Thread | asyncio.Task[Any]] = {
        t for t in threading.enumerate() if t.is_alive()
    }
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return alive
    return alive | {t for t in asyncio.all_tasks() if not t.done()}


def _name_of(work: threading.Thread | asyncio.Task[Any]) -> str:
    """Return the name of a thread or a task."""
    if isinstance(work, threading.Thread):
        return f"thread {work.name}"
    return f"task {work.get_name()}"


def no_task_leaks(seat: Seat, mode: Mode, msg: str) -> Callable[[], None]:
    """Mark the start of a scope, and return the check of its end.

        done = no_task_leaks(seat, mode, "the handler cleans up")
        handler.serve(request)
        done()

    The check reports each thread and each asyncio task that started in the
    scope and still runs. It first waits up to half a second for them,
    because a task that is ending is not a leak. It compares identities, so
    a thread or a task that ran before the scope is not a leak.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        msg: The contract under test.

    Returns:
        The check that the caller calls at the end of the scope.
    """
    __tracebackhide__ = True
    seat.helper()
    before = _running()

    def check() -> None:
        __tracebackhide__ = True
        seat.helper()
        deadline = time.monotonic() + LEAK_GRACE
        leaked = _running() - before
        while leaked and time.monotonic() < deadline:
            time.sleep(_LEAK_INTERVAL)
            leaked = _running() - before
        if leaked:
            names = sorted(_name_of(work) for work in leaked)
            fail(seat, mode, "no-task-leaks", msg, {"leaked": names})
            return
        pass_(seat, mode, "no-task-leaks", msg)

    return check
