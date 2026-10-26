# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of clock.py: the clocks that an assertion reads."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from dokimi_assert import check
from dokimi_assert.clock import Controlled, System, wait

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestSystemNow:
    """System.now, the reading of the platform clock."""

    def test_returns_the_monotonic_reading_of_the_platform(
        self, seat: Collector
    ) -> None:
        """The reading lies between two readings of the platform."""
        before = time.monotonic()
        now = System().now()
        check.in_range(seat, now, before, time.monotonic(), "the reading")


class TestSystemSleep:
    """System.sleep, a wait on the platform clock."""

    def test_waits_the_duration_on_the_platform(self, seat: Collector) -> None:
        """The performance counter passes the duration.

        The monotonic clock of Windows before Python 3.13 ticks every 15.6 ms,
        so only the performance counter times a sleep of 10 ms.
        """
        before = time.perf_counter()
        System().sleep(0.01)
        check.is_true(seat, time.perf_counter() - before >= 0.01, "the time passed")


class TestControlledNow:
    """Controlled.now, the reading of a clock that a test moves."""

    def test_returns_the_start_until_the_clock_is_advanced(
        self, seat: Collector
    ) -> None:
        """A new clock reads its start."""
        check.equal(seat, Controlled(100.0).now(), 100.0, "the start")


class TestControlledAdvance:
    """Controlled.advance, the clock moved forward."""

    def test_moves_the_clock_forward(self, seat: Collector) -> None:
        """The reading rises by the duration."""
        clock = Controlled(100.0)
        clock.advance(30.0)
        check.equal(seat, clock.now(), 130.0, "the reading after the advance")

    def test_ignores_a_duration_that_is_not_positive(self, seat: Collector) -> None:
        """Time on the clock does not run backwards."""
        clock = Controlled(100.0)
        clock.advance(-30.0)
        clock.advance(0.0)
        check.equal(seat, clock.now(), 100.0, "the reading")


class TestControlledSleep:
    """Controlled.sleep, a wait until the clock passes a duration."""

    def test_returns_at_once_for_a_duration_that_is_not_positive(
        self, seat: Collector
    ) -> None:
        """No advance is needed for a sleep of nothing."""
        clock = Controlled(5.0)
        clock.sleep(0.0)
        clock.sleep(-1.0)
        check.equal(seat, clock.now(), 5.0, "the reading")

    def test_returns_once_another_thread_advances_the_clock_past_it(
        self, seat: Collector
    ) -> None:
        """A sleeper waits for the clock, not for the platform."""
        clock = Controlled(0.0)
        stop = threading.Event()

        def advancer() -> None:
            while not stop.is_set():
                clock.advance(10.0)
                stop.wait(0.001)

        thread = threading.Thread(target=advancer, daemon=True)
        thread.start()
        clock.sleep(60.0)
        stop.set()
        thread.join(5.0)
        check.is_true(seat, clock.now() >= 60.0, "the clock passed the duration")


class _Sleeping:
    """A clock without advance, which keeps the durations that it slept."""

    def __init__(self) -> None:
        self.slept: list[float] = []

    def now(self) -> float:
        return 0.0

    def sleep(self, duration: float) -> None:
        self.slept.append(duration)


class TestWait:
    """wait, time moved forward on a clock."""

    def test_advances_a_controlled_clock(self, seat: Collector) -> None:
        """A controlled clock moves at once."""
        clock = Controlled(0.0)
        wait(clock, 2.5)
        check.equal(seat, clock.now(), 2.5, "the reading")

    def test_sleeps_on_a_clock_without_advance(self, seat: Collector) -> None:
        """Any other clock is slept against."""
        clock = _Sleeping()
        wait(clock, 2.5)
        check.equal(seat, clock.slept, [2.5], "the sleeps")
