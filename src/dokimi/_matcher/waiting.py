"""Assertions that retry, and one that checks nothing was left running.

These spend real time, deliberately. They are for a condition
something outside the test makes true, which a controlled clock cannot
reach: a clock only moves when someone advances it, and nobody will
while this call is blocking.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from dokimi._matcher.seat import Mode, Seat, report

#: Where the backoff in eventually_true starts, and the share of the
#: timeout it will not exceed.
FIRST_BACKOFF = 0.001
BACKOFF_SHARE = 0.25

#: How long a leak check waits for tasks to finish before reporting.
LEAK_GRACE = 0.5
LEAK_INTERVAL = 0.005


class _Trial:
    """A seat that records one attempt's failure and nothing else."""

    def __init__(self) -> None:
        self.message: str | None = None

    def helper(self) -> None:
        """Do nothing; an attempt has no frame worth marking."""

    def fail(self, message: str) -> None:
        """Record the first failure of this attempt."""
        if self.message is None:
            self.message = message

    def record(self, message: str) -> None:
        """Record the first failure of this attempt."""
        self.fail(message)


def eventually(
    seat: Seat,
    mode: Mode,
    timeout: float,
    interval: float,
    body: Callable[[Any], None],
    msg: str,
) -> None:
    """Run body every interval until it passes or timeout expires.

    body receives a seat of its own, so assertions inside it record an
    attempt rather than ending the test. Only the last attempt's
    failure is reported. body runs at least once however short the
    timeout.
    """
    seat.helper()

    deadline = time.monotonic() + timeout
    attempts = 0

    while True:
        trial = _Trial()
        body(trial)
        attempts += 1

        if trial.message is None:
            return
        if time.monotonic() >= deadline:
            report(
                seat,
                mode,
                f"{msg}: still failing after {timeout}s and "
                f"{attempts} attempts: {trial.message}",
            )
            return
        time.sleep(interval)


def eventually_true(
    seat: Seat, mode: Mode, timeout: float, predicate: Callable[[], bool], msg: str
) -> None:
    """Call predicate with backoff until true or timeout expires.

    Backoff starts at a millisecond and doubles, capped at a quarter of
    the timeout. It differs from eventually in what it reports: a
    predicate has no failure to carry, so this says only that the wait
    ran out.
    """
    seat.helper()

    deadline = time.monotonic() + timeout
    backoff = FIRST_BACKOFF
    ceiling = timeout * BACKOFF_SHARE
    attempts = 0

    while True:
        attempts += 1
        if predicate():
            return
        if time.monotonic() >= deadline:
            report(
                seat,
                mode,
                f"{msg}: still false after {timeout}s and {attempts} attempts",
            )
            return
        time.sleep(backoff)
        backoff = min(backoff * 2, ceiling) if ceiling > 0 else backoff


def _running_tasks() -> set[asyncio.Task[Any]]:
    """Return the asyncio tasks alive now, or none outside a loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return set()
    return {t for t in asyncio.all_tasks() if not t.done()}


def no_task_leaks(seat: Seat, mode: Mode, msg: str) -> Callable[[], None]:
    """Record the running tasks and return a check for the leftovers.

        done = no_task_leaks(seat, mode, "the worker stops")
        ...
        done()

    Identity, not count: only tasks started after this call are
    reported. The check waits briefly before reporting, because a task
    on its way out is not a leak.

    It answers only for asyncio. A thread is not an asyncio task and is
    not seen here.
    """
    seat.helper()
    before = _running_tasks()

    def check() -> None:
        deadline = time.monotonic() + LEAK_GRACE
        leaked: set[asyncio.Task[Any]] = set()

        while True:
            leaked = _running_tasks() - before
            if not leaked or time.monotonic() >= deadline:
                break
            time.sleep(LEAK_INTERVAL)

        if leaked:
            names = sorted(t.get_name() for t in leaked)
            report(
                seat,
                mode,
                f"{msg}: {len(leaked)} task(s) still running after "
                f"{LEAK_GRACE}s: {names}",
            )

    return check
