"""The assertions built on Python's own model rather than translated.

Go states cancellation with ``context.Context``. Python has no such
convention, so these use asyncio, whose CancelledError and timeouts are
the real analogue. That makes them the assertions most likely to be
wrong, and the ones worth driving hardest.

Every assertion here is driven twice, once with a subject that holds
and once with one that does not. A one-sided test passes against an
assertion that reports nothing whatever it is given, which is a real
way for one of these to be wrong.
"""

from __future__ import annotations

import asyncio

from dokimi_assert import check
from dokimi_assert.seat import Recorder, Standard

OUTER = Standard()


async def _respects() -> None:
    """Yield, so cancellation reaches this subject."""
    await asyncio.sleep(10)


async def _ignores() -> None:
    """Return without yielding, so cancellation cannot reach this."""
    return None


async def _swallows() -> str:
    """Catch the cancellation and return anyway."""
    try:
        await asyncio.sleep(10)
    except asyncio.CancelledError:
        return "carried on regardless"
    return "not cancelled"


def test_honours_cancellation_passes_a_subject_that_yields() -> None:
    """A subject that awaits is reached by cancellation."""
    seat = Recorder()
    check.honours_cancellation(seat, _respects, "it checks for cancellation")
    check.is_false(OUTER, seat.failed, f"a yielding subject passes: {seat.message}")


def test_honours_cancellation_reports_a_subject_that_does_not() -> None:
    """A subject that returns without yielding is not cancellable."""
    seat = Recorder()
    check.honours_cancellation(seat, _ignores, "it checks for cancellation")
    check.is_true(OUTER, seat.failed, "a subject that never yields is reported")


def test_honours_deadline_passes_a_subject_that_yields() -> None:
    """A subject given no time is cut short at its first await."""
    seat = Recorder()
    check.honours_deadline(seat, _respects, "it checks its deadline")
    check.is_false(OUTER, seat.failed, f"a yielding subject passes: {seat.message}")


def test_honours_deadline_reports_a_subject_that_never_yields() -> None:
    """A subject that runs to completion ignored the deadline.

    An implementation built on ``asyncio.wait_for`` with a timeout of
    zero passes this subject, because that call never starts the
    coroutine. The assertion has to actually run the body.
    """
    seat = Recorder()
    check.honours_deadline(seat, _ignores, "it checks its deadline")
    check.is_true(OUTER, seat.failed, "a subject given no time that returned is caught")


def test_honours_deadline_reports_a_subject_that_swallows_the_cancellation() -> None:
    """Catching the cancellation and returning is not honouring it."""
    seat = Recorder()
    check.honours_deadline(seat, _swallows, "it checks its deadline")
    check.is_true(OUTER, seat.failed, "swallowing the cancellation is reported")


def test_completes_within_passes_a_fast_subject() -> None:
    """A subject that returns at once is inside any real ceiling."""
    seat = Recorder()
    check.completes_within(seat, 1.0, lambda: None, "it is quick")
    check.is_false(OUTER, seat.failed, f"a fast subject passes: {seat.message}")


def test_completes_within_reports_a_slow_subject() -> None:
    """A subject slower than its ceiling is reported."""
    seat = Recorder()
    check.completes_within(seat, 0.0, lambda: None, "it is quick")
    check.is_true(OUTER, seat.failed, "a subject over its ceiling is reported")


def test_completes_within_names_the_ceiling_it_missed() -> None:
    """The failure carries both readings, so the margin is visible."""
    seat = Recorder()
    check.completes_within(seat, 0.0, lambda: None, "it is quick")
    check.contains(OUTER, seat.message, "want at most", "it names the ceiling")


def test_is_pure_passes_when_the_projection_holds() -> None:
    """A call that changes nothing observed passes."""
    state = [1, 2]
    seat = Recorder()
    check.is_pure(seat, lambda: list(state), lambda: None, "it changes nothing")
    check.is_false(
        OUTER, seat.failed, f"an unchanged projection passes: {seat.message}"
    )


def test_is_pure_reports_when_the_projection_changes() -> None:
    """A call that changes observed state is reported."""
    state = [1, 2]
    seat = Recorder()
    check.is_pure(
        seat, lambda: list(state), lambda: state.append(3), "it changes nothing"
    )
    check.is_true(OUTER, seat.failed, "a changed projection is reported")


def test_is_pure_ignores_what_the_projection_leaves_out() -> None:
    """The projection defines what nothing means, so this passes."""
    state = {"kept": 1, "ignored": 0}
    seat = Recorder()
    check.is_pure(
        seat,
        lambda: state["kept"],
        lambda: state.__setitem__("ignored", 1),
        "it changes nothing observable",
    )
    check.is_false(OUTER, seat.failed, f"an unobserved change passes: {seat.message}")


def test_none_handle_safe_passes_a_subject_that_refuses() -> None:
    """Refusing a None handle with a decision of its own is fine."""

    def refuses(handle: object) -> None:
        if handle is None:
            raise ValueError("a handle is required")

    seat = Recorder()
    check.none_handle_safe(seat, refuses, "it survives a missing handle")
    check.is_false(OUTER, seat.failed, f"a refusing subject passes: {seat.message}")


def test_none_handle_safe_reports_a_subject_that_dereferences() -> None:
    """Dereferencing a None handle is what this catches."""
    seat = Recorder()
    check.none_handle_safe(
        seat, lambda handle: handle.cancelled, "it survives a missing handle"
    )
    check.is_true(OUTER, seat.failed, "dereferencing a None handle is reported")
