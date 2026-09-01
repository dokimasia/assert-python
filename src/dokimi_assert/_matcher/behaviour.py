"""Assertions about how a subject behaves, rather than what it returns.

Python has no single cancellation convention the way Go has
context.Context in every signature. Its real one is asyncio, whose
CancelledError and timeouts are the true analogue, so the
cancellation assertions drive a coroutine function.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from dokimi_assert._matcher.compare import equal as _equal
from dokimi_assert._matcher.option import Option, settings
from dokimi_assert._matcher.seat import Mode, Seat, clock_of, report_failure

_S = TypeVar("_S")

#: How long a cancellation assertion waits for a subject to notice
#: before calling it unresponsive.
NOTICE_TIMEOUT = 1.0


def _on_its_own_loop(
    assertion: str, drive: Callable[[], Coroutine[Any, Any, Any]]
) -> Any:
    """Run drive on an event loop belonging to this assertion.

    These assertions own the loop so a test using one stays a plain def.
    That works only where no loop is running yet. A test that is already
    async is told so here, naming the assertion, rather than meeting
    asyncio's own error raised from somewhere inside this library.

    Args:
        assertion: The canonical id, so the message names what failed.
        drive: Builds the coroutine to run. Called only once the loop is
            known to be free, so nothing is left unawaited.

    Returns:
        Whatever drive's coroutine returned.

    Raises:
        RuntimeError: When a loop is already running.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(drive())

    msg = (
        f"{assertion} runs the event loop itself, so it cannot be called "
        f"from a test that is already running one. Write the test as a "
        f"plain def and let the assertion drive the subject, or drive the "
        f"subject yourself and assert on what it raised."
    )
    raise RuntimeError(msg)


def honours_cancellation(
    seat: Seat, mode: Mode, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Report when a cancelled subject does not raise CancelledError.

    The subject is started and cancelled at once, so this asks whether
    it yields to cancellation at all rather than how fast it notices.
    A subject that swallows the cancellation and returns fails here.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        fn: The callable under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()

    async def drive() -> str | None:
        task = asyncio.ensure_future(fn())
        await asyncio.sleep(0)
        task.cancel()
        try:
            await asyncio.wait_for(task, NOTICE_TIMEOUT)
        except asyncio.CancelledError:
            return None
        except TimeoutError:
            return (
                f"the subject did not stop within {NOTICE_TIMEOUT}s of being cancelled"
            )
        except Exception as caught:
            return f"cancellation produced {caught!r}, want CancelledError"
        return "a cancelled subject returned normally"

    problem = _on_its_own_loop("honours-cancellation", drive)
    if problem is not None:
        report_failure(seat, mode, "honours-cancellation", msg, {"got": problem})


def honours_deadline(
    seat: Seat, mode: Mode, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Report when a subject given no time does not time out.

    The deadline has already passed when the subject starts, so a
    subject that yields at all is cut short. One that never yields
    fails, and so does one that catches the cancellation and returns
    anyway. Those are the cases worth catching.

    This uses asyncio.timeout rather than
    asyncio.wait_for. wait_for with a timeout of zero never
    starts the coroutine at all, which CPython documents in the source
    of that function, so every subject would time out and pass.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        fn: The callable under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()

    async def drive() -> str | None:
        try:
            async with asyncio.timeout(0):
                await fn()
        except (TimeoutError, asyncio.CancelledError):
            return None
        except Exception as caught:
            return f"an expired deadline produced {caught!r}, want a timeout"
        return "a subject given no time returned normally"

    problem = _on_its_own_loop("honours-deadline", drive)
    if problem is not None:
        report_failure(seat, mode, "honours-deadline", msg, {"got": problem})


def completes_within(
    seat: Seat, mode: Mode, within: float, fn: Callable[[], Any], msg: str
) -> None:
    """Report when fn takes longer than within seconds.

    The subject is measured, not interrupted: this says whether it
    finished in time, and a subject that runs long runs to completion
    first. Spends real time, up to however long fn takes.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        within: The ceiling, in seconds.
        fn: The callable under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()

    clock = clock_of(seat)
    started = clock.now()
    fn()
    elapsed = clock.now() - started

    if elapsed > within:
        report_failure(
            seat,
            mode,
            "completes-within",
            msg,
            # Milliseconds is the granularity this assertion is about,
            # and sixteen digits of a duration is false precision.
            {"want": within, "got": round(elapsed, 3)},
        )


def is_pure(
    seat: Seat,
    mode: Mode,
    observe: Callable[[], _S],
    fn: Callable[[], Any],
    msg: str,
    *options: Option,
) -> None:
    """Report when observed state changes across a call.

    The projection observe returns defines what changing nothing means:
    whatever it leaves out, fn is free to change. Return a copy. A
    projection sharing memory with the subject reads the same object
    twice and passes whatever fn did.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        observe: Called before and after fn; returns a projection of state.
        fn: The callable under test.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone.
    """
    __tracebackhide__ = True
    seat.helper()

    before = observe()
    fn()
    after = observe()

    if not _equal(after, before, settings(options)):
        report_failure(seat, mode, "pure", msg, {"want": before, "got": after})


def none_handle_safe(
    seat: Seat, mode: Mode, fn: Callable[[Any], Any], msg: str
) -> None:
    """Report when a subject given None where a handle goes crashes.

    An exception that is not an AttributeError or TypeError is
    fine: refusing the call is a decision. Those two are what a missing
    None check produces, and they are what this catches.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        fn: The callable under test.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    try:
        fn(None)
    except (AttributeError, TypeError) as caught:
        report_failure(seat, mode, "nil-context-safe", msg, {"got": caught})
    except Exception:
        pass
