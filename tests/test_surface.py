"""The two surfaces report the same thing.

The corpus drives both surfaces for every assertion whose arguments it
can state as data, which is 17 of the 41. The rest take a callable, a
timeout or a coroutine, and no corpus file can hold one. They are
covered here: each is driven through both surfaces against a recorder,
and the two messages must match.

A recorder records whichever path an assertion takes, so the only
difference between the surfaces in this file is which module the name
was read from. That is the point. The aborting and recording surfaces
are meant to differ in what they do to the run, not in what they say.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from dokimi import check, expect
from dokimi.seat import Recorder, Seat, Standard

OUTER = Standard()

BOOM = ValueError("boom")


async def _returns() -> None:
    """Return without yielding, so cancellation cannot reach this."""
    return None


def _raises() -> None:
    """Raise, for the assertions that want a callable that does not."""
    raise RuntimeError("boom")


def _never() -> bool:
    """Never hold, so a waiting assertion runs out of time."""
    return False


def _always() -> bool:
    """Hold at once, so a waiting assertion returns on its first look."""
    return True


def _needs_a_value(got: Any) -> int:
    """Raise on None, for the assertion that passes one."""
    return len(got)


def _slow() -> None:
    """Take longer than any deadline this file gives it."""
    time.sleep(0.2)


def _nothing() -> None:
    """Do nothing, for the assertions that want a callable that returns."""


def _ascending(a: Any, b: Any) -> bool:
    """Hold when a comes before b."""
    return bool(a < b)


def _keeps_the_handle(got: Any) -> Any:
    """Return the handle it was given, whatever that was."""
    return got


def _never_converges(seat: Seat) -> None:
    """State something that will not become true."""
    check.is_true(seat, False, "it converges")


def _already_holds(_: Seat) -> None:
    """State nothing, so the first attempt is the last."""


def _impure() -> tuple[Any, ...]:
    """Return an observe and a call that changes what it observes."""
    state = [1, 2]

    def observe() -> list[Any]:
        return list(state)

    def bump() -> None:
        state.append(3)

    return (observe, bump)


def _pure() -> tuple[Any, ...]:
    """Return an observe and a call that changes nothing."""
    state = [1, 2]

    def observe() -> list[Any]:
        return list(state)

    return (observe, _nothing)


#: A failing call per assertion the corpus cannot reach, as the
#: arguments that follow the seat. Each entry is built fresh per drive,
#: because an assertion that reads state twice must see the same start
#: on both surfaces or the two messages cannot be compared.
FAILING: dict[str, Callable[[], Sequence[Any]]] = {
    "no_error": lambda: (BOOM,),
    "has_error": lambda: (None,),
    "error_is": lambda: (BOOM, KeyError("other")),
    "error_is_not": lambda: (BOOM, BOOM),
    "error_as": lambda: (BOOM, KeyError),
    "raises": lambda: (_nothing,),
    "does_not_raise": lambda: (_raises,),
    "pairwise": lambda: ([2, 1], _ascending),
    "honours_cancellation": lambda: (_returns,),
    "honours_deadline": lambda: (_returns,),
    "completes_within": lambda: (0.01, _slow),
    "is_pure": _impure,
    "none_handle_safe": lambda: (_needs_a_value,),
    "eventually": lambda: (0.01, 0.005, _never_converges),
    "eventually_true": lambda: (0.01, _never),
}


@pytest.mark.parametrize("name", sorted(FAILING))
def test_both_surfaces_report_the_same_failure(name: str) -> None:
    """The recording surface says exactly what the aborting one says."""
    msg = "the stated contract"

    aborting, recording = Recorder(), Recorder()
    getattr(check, name)(aborting, *FAILING[name](), msg)
    getattr(expect, name)(recording, *FAILING[name](), msg)

    check.is_true(OUTER, aborting.failed, f"check.{name} reports the failure")
    check.is_true(OUTER, recording.failed, f"expect.{name} reports the failure")
    check.equal(
        OUTER,
        recording.message,
        aborting.message,
        f"{name} says the same thing on both surfaces",
    )


@pytest.mark.parametrize("name", sorted(FAILING))
def test_the_recording_surface_does_not_abort(name: str) -> None:
    """A recorded failure leaves the run going, which is the difference."""
    seat = Recorder()

    getattr(expect, name)(seat, *FAILING[name](), "the first contract")
    getattr(expect, name)(seat, *FAILING[name](), "the second contract")

    check.length(OUTER, seat.messages, 2, f"expect.{name} records every failure")


@pytest.mark.parametrize("surface", [check, expect], ids=["check", "expect"])
def test_no_task_leaks_reports_a_task_left_running(surface: Any) -> None:
    """A task still running when the check closes is a leak."""

    async def leak(seat: Any) -> None:
        close = surface.no_task_leaks(seat, "the handler cleans up after itself")
        leaked = asyncio.ensure_future(asyncio.sleep(10))
        await asyncio.sleep(0)
        close()
        leaked.cancel()

    seat = Recorder()
    asyncio.run(leak(seat))

    check.is_true(OUTER, seat.failed, "a leaked task is reported")


@pytest.mark.parametrize("surface", [check, expect], ids=["check", "expect"])
def test_error_as_returns_what_it_matched(surface: Any) -> None:
    """Both surfaces hand back the matched exception, not just a verdict."""
    caught = surface.error_as(Recorder(), BOOM, ValueError, "it refuses the input")

    check.is_not_none(OUTER, caught, "the matched exception is returned")


@pytest.mark.parametrize("surface", [check, expect], ids=["check", "expect"])
def test_raises_returns_what_was_raised(surface: Any) -> None:
    """Both surfaces hand back the exception, so a caller can read it."""
    caught: BaseException | None = surface.raises(
        Recorder(), _raises, "it refuses the input"
    )

    check.is_not_none(OUTER, caught, "the exception is returned")
    check.contains(OUTER, str(caught), "boom", "it carries the reason")


PASSING: dict[str, Callable[[], Sequence[Any]]] = {
    "no_error": lambda: (None,),
    "has_error": lambda: (BOOM,),
    "error_is": lambda: (BOOM, BOOM),
    "error_is_not": lambda: (BOOM, KeyError("other")),
    "error_as": lambda: (BOOM, ValueError),
    "raises": lambda: (_raises,),
    "does_not_raise": lambda: (_nothing,),
    "pairwise": lambda: ([1, 2], _ascending),
    "completes_within": lambda: (1.0, _nothing),
    "is_pure": _pure,
    "none_handle_safe": lambda: (_keeps_the_handle,),
    "eventually": lambda: (1.0, 0.005, _already_holds),
    "eventually_true": lambda: (1.0, _always),
}
"""A passing call per assertion, for the surfaces that must stay silent."""


@pytest.mark.parametrize("name", sorted(PASSING))
def test_neither_surface_reports_a_passing_call(name: str) -> None:
    """An assertion that holds says nothing, on either surface."""
    aborting, recording = Recorder(), Recorder()
    getattr(check, name)(aborting, *PASSING[name](), "the stated contract")
    getattr(expect, name)(recording, *PASSING[name](), "the stated contract")

    check.is_false(OUTER, aborting.failed, f"check.{name} passes: {aborting.message}")
    check.is_false(
        OUTER, recording.failed, f"expect.{name} passes: {recording.message}"
    )
