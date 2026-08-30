"""Assertions about how a subject behaves, rather than what it returns.

Python has no single cancellation convention the way Go has
``context.Context`` in every signature. Its real one is asyncio, whose
``CancelledError`` and timeouts are the true analogue, so the
cancellation assertions drive a coroutine function.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from dokimi._matcher.compare import equal as _equal
from dokimi._matcher.option import Option, settings
from dokimi._matcher.seat import Mode, Seat, report

_S = TypeVar("_S")

#: How long a cancellation assertion waits for a subject to notice
#: before calling it unresponsive.
NOTICE_TIMEOUT = 1.0


def honours_cancellation(
    seat: Seat, mode: Mode, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Report when a cancelled subject does not raise CancelledError.

    The subject is started and cancelled at once, so this asks whether
    it yields to cancellation at all rather than how fast it notices.
    A subject that swallows the cancellation and returns fails here.
    """
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

    problem = asyncio.run(drive())
    if problem is not None:
        report(seat, mode, f"{msg}: {problem}")


def honours_deadline(
    seat: Seat, mode: Mode, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Report when a subject given no time does not time out.

    The deadline has already passed when the subject starts, so a
    subject that yields at all is cut short. One that never yields
    fails, and so does one that catches the cancellation and returns
    anyway. Those are the cases worth catching.

    This uses :func:`asyncio.timeout` rather than
    :func:`asyncio.wait_for`. ``wait_for`` with a timeout of zero never
    starts the coroutine at all, which CPython documents in the source
    of that function, so every subject would time out and pass.
    """
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

    problem = asyncio.run(drive())
    if problem is not None:
        report(seat, mode, f"{msg}: {problem}")


def completes_within(
    seat: Seat, mode: Mode, within: float, fn: Callable[[], Any], msg: str
) -> None:
    """Report when fn takes longer than within seconds.

    The subject is measured, not interrupted: this says whether it
    finished in time, and a subject that runs long runs to completion
    first. Spends real time, up to however long fn takes.
    """
    seat.helper()

    started = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - started

    if elapsed > within:
        report(seat, mode, f"{msg}: took {elapsed:.3f}s, want at most {within:.3f}s")


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
    """
    seat.helper()

    before = observe()
    fn()
    after = observe()

    if not _equal(after, before, settings(options)):
        report(
            seat,
            mode,
            f"{msg}: observable state changed: was {before!r}, now {after!r}",
        )


def none_handle_safe(
    seat: Seat, mode: Mode, fn: Callable[[Any], Any], msg: str
) -> None:
    """Report when a subject given None where a handle goes crashes.

    An exception that is not an ``AttributeError`` or ``TypeError`` is
    fine: refusing the call is a decision. Those two are what a missing
    None check produces, and they are what this catches.
    """
    seat.helper()
    try:
        fn(None)
    except (AttributeError, TypeError) as caught:
        report(seat, mode, f"{msg}: a None handle was dereferenced: {caught!r}")
    except Exception:
        pass
