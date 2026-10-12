"""The spec of _matcher/waiting.py tests the assertions that wait."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from dokimi_assert._matcher import value, waiting
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.clock import Controlled
from dokimi_assert.seat import Collector, Recorder
from helpers import records


def controlled() -> tuple[Recorder, Controlled]:
    """Return a recorder on a controlled clock, and the clock."""
    clock = Controlled(0)
    return Recorder().with_clock(clock), clock


def settles_after(attempts: int) -> tuple[list[int], Any]:
    """Return a counter and a body that fails until the attempt numbered attempts."""
    count = [0]

    def body(trial: Any) -> None:
        count[0] += 1
        value.is_true(trial, Mode.FATAL, count[0] >= attempts, f"attempt {count[0]}")

    return count, body


class TestLeakGrace:
    """LEAK_GRACE is the wait for the work of a scope to end."""

    def test_is_half_a_second(self) -> None:
        """A check for leaks waits at most half a second."""
        assert waiting.LEAK_GRACE == 0.5


class TestEventually:
    """eventually retries a body of assertions."""

    def test_passes_a_body_that_passes_at_once(self) -> None:
        """One passing attempt is enough."""
        seat, _ = controlled()
        count, body = settles_after(1)
        waiting.eventually(seat, Mode.FATAL, 10.0, 1.0, body, "c")
        assert (seat.failed, count[0]) == (False, 1)

    def test_passes_a_body_that_passes_at_its_third_attempt(self) -> None:
        """The assertion advances a controlled clock between attempts."""
        seat, clock = controlled()
        count, body = settles_after(3)
        waiting.eventually(seat, Mode.FATAL, 10.0, 1.0, body, "c")
        assert (seat.failed, count[0], clock.now()) == (False, 3, 2.0)

    def test_fails_a_body_that_never_passes(self) -> None:
        """The failure at the timeout has the attempts and the last message."""
        seat, _ = controlled()
        _, body = settles_after(100)
        waiting.eventually(seat, Mode.SOFT, 2.5, 1.0, body, "c")
        assert dict(seat.failures[0].detail) == {"attempts": 4, "last": "attempt 4"}

    def test_records_the_calls_of_each_attempt_under_its_call(self) -> None:
        """Each attempt is a run of the call of eventually."""
        seat, _ = controlled()
        _, body = settles_after(2)
        waiting.eventually(seat, Mode.FATAL, 10.0, 1.0, body, "outer")
        assert [
            (r["seq"], r.get("parent"), r.get("run"), r["verdict"])
            for r in records(seat)
        ] == [
            (1, None, None, "pass"),
            (2, 1, 1, "fail"),
            (3, 1, 2, "pass"),
        ]

    def test_runs_the_attempts_of_a_call_that_does_not_write_a_record(self) -> None:
        """The attempts run on a seat that does not keep records."""
        clock = Controlled(0)
        seat = Collector().with_clock(clock)
        count, body = settles_after(2)
        waiting.eventually(seat, Mode.FATAL, 10.0, 1.0, body, "c")
        assert (count[0], clock.now()) == (2, 1.0)

    def test_runs_a_coroutine_body(self) -> None:
        """A coroutine function runs on the loop of the call."""
        seat, _ = controlled()

        async def body(trial: Any) -> None:
            await asyncio.sleep(0)
            value.is_true(trial, Mode.FATAL, True, "inner")

        waiting.eventually(seat, Mode.FATAL, 10.0, 1.0, body, "c")
        assert not seat.failed

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine body."""
        seat, _ = controlled()

        async def body(_: Any) -> None:
            return None

        async def test() -> None:
            waiting.eventually(seat, Mode.FATAL, 10.0, 1.0, body, "c")

        asyncio.run(test())
        assert seat.message.startswith("eventually runs a coroutine")


class TestEventuallyTrue:
    """eventually_true retries a predicate with a backoff."""

    def test_passes_a_predicate_that_becomes_true(self) -> None:
        """The assertion calls the predicate until it returns True."""
        seat, _ = controlled()
        results = iter([False, False, True])
        waiting.eventually_true(seat, Mode.FATAL, 10.0, lambda: next(results), "c")
        assert not seat.failed

    def test_fails_a_predicate_that_never_becomes_true(self) -> None:
        """A predicate that never returns True fails at the timeout."""
        seat, _ = controlled()
        waiting.eventually_true(seat, Mode.FATAL, 0.01, lambda: False, "c")
        assert seat.failures[0].assertion == "eventually-true"
        assert seat.failures[0].detail["attempts"] > 1

    def test_awaits_a_coroutine_predicate(self) -> None:
        """A coroutine function runs on the loop of the call."""
        seat, _ = controlled()

        async def is_ready() -> bool:
            return True

        waiting.eventually_true(seat, Mode.FATAL, 1.0, is_ready, "c")
        assert not seat.failed

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine predicate."""
        seat, _ = controlled()

        async def is_ready() -> bool:
            return True

        async def test() -> None:
            waiting.eventually_true(seat, Mode.FATAL, 1.0, is_ready, "c")

        asyncio.run(test())
        assert seat.message.startswith("eventually-true runs a coroutine")


class TestNoTaskLeaks:
    """no_task_leaks reports threads and tasks that still run at the end of a scope."""

    def test_passes_a_scope_whose_work_ends(self) -> None:
        """A thread that ends within the grace is not a leak."""
        seat = Recorder()
        done = waiting.no_task_leaks(seat, Mode.FATAL, "c")
        thread = threading.Thread(target=lambda: None)
        thread.start()
        done()
        assert not seat.failed

    def test_fails_a_thread_that_still_runs(self) -> None:
        """A thread that runs past the grace is a leak."""
        seat = Recorder()
        release = threading.Event()
        done = waiting.no_task_leaks(seat, Mode.FATAL, "c")
        thread = threading.Thread(target=release.wait, name="worker")
        thread.start()
        done()
        release.set()
        thread.join()
        assert seat.failures[0].detail == {"leaked": ["thread worker"]}

    def test_fails_a_task_that_still_runs(self) -> None:
        """An asyncio task that runs past the grace is a leak."""
        seat = Recorder()

        async def test() -> None:
            done = waiting.no_task_leaks(seat, Mode.FATAL, "c")
            task = asyncio.get_running_loop().create_task(
                asyncio.sleep(10), name="sleeper"
            )
            await asyncio.sleep(0)
            done()
            task.cancel()

        asyncio.run(test())
        assert seat.failures[0].detail == {"leaked": ["task sleeper"]}
