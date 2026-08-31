"""The clock a seat carries, and what a test can do with it."""

from __future__ import annotations

import threading
import time

from dokimi_assert import check
from dokimi_assert.clock import Controlled, System
from dokimi_assert.seat import Recorder, Seat, Standard

#: The seat these tests state their own verdicts on. A test of the
#: clock cannot report through a seat it is driving.
OUTER = Standard()


def test_now_answers_the_start_until_it_is_advanced() -> None:
    """A controlled clock reads what it was given until something moves it."""
    clock = Controlled(100.0)

    check.equal(OUTER, clock.now(), 100.0, "it reads the start")
    clock.advance(30.0)
    check.equal(OUTER, clock.now(), 130.0, "it reads the advance")


def test_advance_does_not_move_time_backwards() -> None:
    """Time on this clock only goes forward."""
    clock = Controlled(100.0)
    clock.advance(-30.0)

    check.equal(OUTER, clock.now(), 100.0, "a negative advance moves nothing")


def test_sleep_returns_once_another_thread_advances_past_it() -> None:
    """A sleeper waits for the clock, not for the wall."""
    clock = Controlled(0.0)
    done = threading.Event()

    def sleeper() -> None:
        clock.sleep(60.0)
        done.set()

    thread = threading.Thread(target=sleeper)
    thread.start()
    try:
        clock.advance(30.0)
        check.is_false(
            OUTER, done.wait(0.05), "it does not return before the clock reaches it"
        )

        # Advancing well past the duration releases the sleeper
        # whichever side of the first advance it started on, which
        # keeps this from turning on thread scheduling.
        clock.advance(3600.0)
        check.is_true(
            OUTER, done.wait(1.0), "it returns once the clock passes the duration"
        )
    finally:
        clock.advance(3600.0)
        thread.join(timeout=1.0)


def test_a_recorder_answers_the_platform_clock_by_default() -> None:
    """A seat that was given no clock reads the platform."""
    seat = Recorder()

    check.is_true(
        OUTER, isinstance(seat.clock(), System), "it answers the platform clock"
    )


def test_with_clock_supplies_the_clock_an_assertion_reads() -> None:
    """A test that wants control says so on the seat."""
    seat = Recorder().with_clock(Controlled(100.0))

    check.equal(
        OUTER, seat.clock().now(), 100.0, "the assertion reads what it was given"
    )


def test_eventually_gives_up_without_spending_real_time() -> None:
    """An hour of controlled timeout costs no waiting."""
    seat = Recorder().with_clock(Controlled(0.0))

    started = time.monotonic()

    def never(inner: Seat) -> None:
        check.is_true(inner, False, "never settles")

    check.eventually(seat, 3600.0, 60.0, never, "the body settles")
    elapsed = time.monotonic() - started

    check.is_true(OUTER, seat.failed, "a body that never settles reports")
    check.is_true(OUTER, elapsed < 5.0, "an hour of controlled time costs no waiting")


def test_eventually_passes_once_the_body_settles() -> None:
    """A body that comes right is not reported, and stops being retried."""
    seat = Recorder().with_clock(Controlled(0.0))
    attempts = 0

    def settles_on_the_third(inner: Seat) -> None:
        nonlocal attempts
        attempts += 1
        check.is_true(inner, attempts >= 3, "not yet")

    check.eventually(seat, 3600.0, 60.0, settles_on_the_third, "the body settles")

    check.is_false(OUTER, seat.failed, "a body that settles is not reported")
    check.equal(OUTER, attempts, 3, "it stops once the body comes right")
